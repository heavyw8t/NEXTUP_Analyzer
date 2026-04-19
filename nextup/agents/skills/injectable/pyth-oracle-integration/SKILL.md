---
name: "pyth-oracle-integration"
description: "Protocol Type Trigger pyth_oracle_integration (detected when recon finds pyth_sdk_solana|PriceAccount|get_price_unchecked|get_price_no_older_than|load_price_feed_from_account_info|PythPriceFeed|SolanaPriceAccount - protocol USES Pyth as price feed)"
---

# Injectable Skill: Pyth Oracle Integration Security

> Protocol Type Trigger: `pyth_oracle_integration` (detected when recon finds: `pyth_sdk_solana`, `PriceAccount`, `get_price_unchecked`, `get_price_no_older_than`, `load_price_feed_from_account_info`, `PythPriceFeed`, `SolanaPriceAccount`)
> Inject Into: depth-external, depth-edge-case, depth-state-trace
> Language: Solana only
> Finding prefix: `[PYTH-N]`
> Relationship to switchboard-oracle-integration: both describe oracle consumption on Solana. Protocols that multiplex feeds should activate both skills.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (account owner, magic, version checks)
- Section 2: depth-edge-case (confidence interval, sigma math)
- Section 3: depth-edge-case (exponent / scaling overflow)
- Section 4: depth-state-trace (staleness, Clock reads)
- Section 5: depth-edge-case (PriceStatus enum handling)
- Section 6: depth-external (EMA vs aggregate path consistency)

## When This Skill Activates

Recon detects that the protocol reads prices from Pyth via `pyth-sdk-solana` or raw `PriceAccount` deserialization, for lending LTV, perpetual mark price, liquidation thresholds, or any value used in token-flow math.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: pyth, publish_time, confidence, get_price_no_older_than, PriceAccount, ema_price, exponent
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[PYTH-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Price Account Validation

### 1a. Owner Program Check
- Does the protocol verify `price_account.owner == pyth_program_id` before deserializing?
- Without this check an attacker can forge a `PriceAccount` layout in any owned account.
- Real finding pattern (Solodit, multiple): Program calls `load_price_feed_from_account_info` but never constrains the owner in the Anchor `AccountInfo`, so a fake feed with `price=u64::MAX` passes.

### 1b. Magic and Version
- Does the program check `PriceAccount.magic == PYTH_MAGIC` and `ver` equals the expected protocol version (currently `2`)?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Program tolerates any `ver`, so a future breaking layout change silently reinterprets fields as prices.

### 1c. Account Type Discriminant
- The first bytes distinguish `PriceAccount`, `ProductAccount`, `MappingAccount`. Does the code reject non-price accounts?
- Real finding pattern (pattern observed in multiple audits): `load_price_account` accepts a `ProductAccount` whose metadata bytes are misread as `expo` and `price`.

### 1d. Feed ID Binding
- Is the expected feed ID (product account key or price feed hash) bound to the market config, or is any Pyth-owned account accepted?
- Real finding pattern (Code4rena, pattern observed in multiple audits): Lending market accepts any SOL-denominated Pyth feed. Attacker swaps feed to a less-liquid asset with identical symbol and manipulates thin-market mid price.

Tag: [TRACE:price_account_owner_checked=YES/NO → magic_version_checked=YES/NO → feed_id_bound=YES/NO]

---

## 2. Confidence Interval Enforcement

### 2a. Confidence Band Consumed
- Does the code read `price.conf` and reject prices where `conf / price > threshold`?
- A wide confidence interval means Pyth itself is unsure; using the point price during such windows causes liquidation / LTV errors.
- Real finding pattern (Solodit, pattern observed in multiple audits): Perp protocol uses `price.price` directly and ignores `conf`. During CEX outages, `conf` widens to 5% but mark price is still consumed, letting arbitrageurs liquidate solvent positions.

### 2b. Lower Bound vs Upper Bound for Direction
- For collateral valuation the safer side is `price - conf`. For debt valuation the safer side is `price + conf`. Does the code pick the correct direction per usage?
- Real finding pattern (Cantina, pattern observed in multiple audits): Single `get_price()` helper returns `price.price` for both collateral and debt paths, so borrowers benefit from symmetric upside on both sides.

### 2c. Confidence Scaling
- `conf` is in the same units as `price` with the same `expo`. Does code apply `expo` consistently when folding `conf` into collateral math?
- Real finding pattern (pattern observed in multiple audits): Code scales `price` by `10^expo` but forgets to scale `conf`, treating a 0.01 USD confidence as 1e10 USD.

Tag: [TRACE:confidence_enforced=YES/NO → directional_bounds=YES/NO → conf_scaled_same_as_price=YES/NO]

---

## 3. Exponent Handling

### 3a. Signed Exponent Application
- Pyth `expo` is `i32` and is typically negative. Does the code correctly apply `price * 10^expo` without flipping sign?
- Real finding pattern (pattern observed in multiple audits): `10u64.pow((-expo) as u32)` panics when `expo > 0` (supported by spec, used by some very-high-priced feeds) because the cast to `u32` wraps.

### 3b. Overflow in Scaling
- If the program converts Pyth (i64 price, expo) into a fixed-point type, does it check for overflow when `expo` is small (large multiplier)?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program computes `price * 10^9` without checked_mul; a feed update that raises price or expo causes the math to overflow `i64` silently in release builds.

### 3c. Consistency of Expo Across Calls
- Does the program re-read `expo` each call, or cache it? Pyth can change `expo` at feed upgrades.
- Real finding pattern (pattern observed in multiple audits): Oracle wrapper caches `expo` at init; later feed republishes with different `expo`; every downstream price value is off by orders of magnitude.

Tag: [TRACE:expo_sign_handled=YES/NO → checked_mul_used=YES/NO → expo_cached=YES/NO]

---

## 4. Staleness Checks (publish_time vs Clock)

### 4a. Per-Read Staleness Assertion
- Does every price read call `get_price_no_older_than(clock, max_age)` or an equivalent `publish_time` gate?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program uses `get_price_unchecked` in a hot path (liquidation) so a halted feed can be replayed for arbitrage.

### 4b. Max Age Parameter
- Is `max_age` a reasonable constant (typically 60s for lending, 10s for perps), or is it unbounded / 0?
- Real finding pattern (Cantina, pattern observed in multiple audits): `max_age = 24 * 3600` effectively disables staleness.

### 4c. Clock Account Trust
- Is the `Clock` sysvar actually the sysvar, or a user-supplied account that can be forged? Anchor usually enforces this but raw instructions may not.
- Real finding pattern (pattern observed in multiple audits): Instruction accepts `clock: AccountInfo` without the sysvar check; attacker supplies a frozen clock to bypass staleness.

### 4d. Aggregate Round Age vs Slot Age
- `publish_time` is unix seconds while `Clock.unix_timestamp` is validator-reported. Drift between cluster time and real time can create false stale or false fresh states.
- Real finding pattern (pattern observed in multiple audits): Chain halts for 40 minutes, `unix_timestamp` frozen, feed keeps publishing; upon resume the `unix_timestamp` jumps and the newest feed is marked stale.

Tag: [TRACE:staleness_enforced=YES/NO → max_age_secs=<n> → clock_sysvar_verified=YES/NO]

---

## 5. PriceStatus / Trading Enum

### 5a. Status != Trading Handling
- Does the program check `price_account.agg.status == PriceStatus::Trading`? Other values (`Unknown`, `Halted`, `Auction`) mean the price is not usable.
- Real finding pattern (Sherlock, pattern observed in multiple audits): Program proceeds on `Unknown` status returning the last trading price, not the current price, during CEX auction windows.

### 5b. PriceStatus Downgrade on Pull Oracles
- With Pyth pull model, an unreceived update keeps `status = Unknown`. Does the program require a fresh pull with `Trading` before consuming?
- Real finding pattern (pattern observed in multiple audits): Program consumes pull-oracle account whose last update is from a different tx, treating stale `Unknown` as usable.

### 5c. Number of Publishers
- `num_publishers` below a threshold makes the aggregate untrustworthy. Does the program enforce a minimum?
- Real finding pattern (Code4rena, pattern observed in multiple audits): Low-liquidity asset drops to one publisher for minutes; program still liquidates using that publisher's quote.

Tag: [TRACE:price_status_checked=YES/NO → pull_freshness_required=YES/NO → min_publishers_enforced=YES/NO]

---

## 6. EMA vs Aggregate Selection

### 6a. Path Consistency
- Does the program mix `ema_price` and `price.price` across code paths? Mixing causes asymmetric liquidation/borrow outcomes.
- Real finding pattern (pattern observed in multiple audits): Collateral valued at EMA, debt at spot. Attacker pumps spot briefly, raising debt valuation and self-liquidating competitors.

### 6b. EMA Staleness
- `ema_price` has its own `publish_time` and `conf`. Are staleness and confidence checks applied to EMA as well?
- Real finding pattern (pattern observed in multiple audits): EMA drifts stale because only `agg.publish_time` is gated.

### 6c. Choice Under Volatility
- EMA is a lagging value. During directional moves it undervalues collateral (or debt). Is the choice documented and intentional?
- Real finding pattern (pattern observed in multiple audits): Documentation implies EMA is used for liquidations but code path uses aggregate, so sudden wicks cause unfair liquidations.

Tag: [TRACE:ema_vs_agg_consistent=YES/NO → ema_staleness_checked=YES/NO → choice_documented=YES/NO]

---

## Common False Positives

- Program only uses Pyth for informational UI hints, not for token-flow math. Most of sections 2 to 6 do not apply.
- Program uses a wrapper that is itself audited (e.g. a vetted on-chain oracle aggregator). Section 1 checks happen there; verify the wrapper is pinned by program ID.
- Program reads only `ema_price` and treats it as authoritative by design, with documented max age. EMA staleness is still in scope.
- Program uses Pyth pull model with explicit `PostedPriceUpdate` verification. Raw account layout bugs (1b, 1c) are handled by the pull SDK.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Owner Program Check | YES | | pyth program id pinning |
| 1b. Magic and Version | YES | | magic + ver |
| 1c. Account Type Discriminant | YES | | price vs product vs mapping |
| 1d. Feed ID Binding | YES | | feed pinned to market |
| 2a. Confidence Band Consumed | IF price used in math | | conf / price ratio |
| 2b. Directional Bounds | IF collateral and debt both priced | | +conf vs -conf |
| 2c. Confidence Scaling | IF conf used | | expo applied to conf |
| 3a. Signed Exponent | YES | | i32 sign handling |
| 3b. Overflow in Scaling | YES | | checked_mul |
| 3c. Expo Consistency | YES | | cached vs live |
| 4a. Per-Read Staleness | YES | | get_price_no_older_than |
| 4b. Max Age | YES | | sane bound |
| 4c. Clock Account Trust | YES | | sysvar verified |
| 4d. Aggregate vs Slot Age | IF halts in threat model | | cluster time drift |
| 5a. Status != Trading | YES | | PriceStatus enum |
| 5b. Pull Oracle Freshness | IF pull model | | Unknown state |
| 5c. Min Publishers | IF thin feeds used | | num_publishers gate |
| 6a. EMA vs Aggregate Consistency | IF both used | | same path across roles |
| 6b. EMA Staleness | IF EMA used | | ema publish_time |
| 6c. Choice Under Volatility | IF liquidations | | documented choice |
