---
name: "oracle-analysis"
description: "Trigger Pattern ORACLE flag (required) - Inject Into Breadth agents, depth-external, depth-edge-case"
---

# ORACLE_ANALYSIS Skill

> **Trigger Pattern**: ORACLE flag (required)
> **Inject Into**: Breadth agents, depth-external, depth-edge-case
> **Purpose**: Analyze all oracle integrations in Aptos Move protocols for staleness, decimal errors, zero/negative prices, confidence intervals, multi-oracle aggregation, and failure modes

For every oracle the protocol consumes:

**STEP PRIORITY**: Steps 6 (Failure Modes) and 5c (Deviation Reference) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections (4a-4d, 5a) before skipping 5c or 6.

## 1. Oracle Inventory

Enumerate ALL oracle data sources the protocol reads:

| Oracle | Type | Module Path | Functions Called | Consumers (protocol functions) | Update Frequency | Freshness Guarantee |
|--------|------|-------------|-----------------|-------------------------------|-----------------|---------------------|
| {name} | Pyth / Switchboard / Custom / On-chain TWAP | {module::path} | {get_price / get_result / etc.} | {list all} | {expected} | {documented or UNKNOWN} |

**Aptos oracle landscape**:
- **Pyth Network**: `pyth::price_feed` module, returns `Price { price: I64, conf: u64, expo: I64, publish_time: u64 }`
- **Switchboard**: `switchboard::aggregator` module, returns aggregator results with `mantissa` and `scale`
- **Custom price feeds**: Protocol-specific oracles using `Table` or `SmartTable` for price storage
- **On-chain TWAP**: DEX-derived time-weighted prices (Thala, LiquidSwap, Pontem)

**For each oracle**: What decision does the protocol make based on this data? (pricing, liquidation threshold, reward rate, rebase trigger, collateral valuation, etc.)

## 2. Staleness Analysis

For each oracle identified in Step 1:

### 2a. Staleness Checks Present?

| Oracle | Timestamp Checked? | Max Staleness Enforced? | Staleness Threshold | Appropriate? |
|--------|-------------------|------------------------|--------------------:|-------------|
| {name} | YES/NO | YES/NO | {seconds or NONE} | {analysis} |

**Pyth-specific**: Is `price.publish_time` compared against `timestamp::now_seconds()`? What max age is enforced?
**Switchboard-specific**: Is the aggregator's `latest_confirmed_round.round_open_timestamp` validated?

**If NO staleness check**: What happens when the oracle returns stale data?
- [ ] Protocol uses stale price for liquidations -- unfair liquidations
- [ ] Protocol uses stale price for minting -- mispriced assets
- [ ] Protocol uses stale price for swaps -- arbitrage opportunity
- [ ] Protocol uses stale rate for rewards -- incorrect distribution

### 2b. Stale Data Impact Trace

For each consumer function, trace the impact of receiving data that is {freshness_guarantee x 2} old:

| Consumer Function | Data Used | If Stale By {X}: Impact | Severity |
|-------------------|-----------|------------------------|----------|
| {function} | {price/rate} | {specific impact} | {H/M/L} |

### 2c. Pyth-Specific Checks

| Check | Code Reference | Status |
|-------|---------------|--------|
| `get_price()` or `get_price_no_older_than()` used? | {location} | {which} |
| `price.publish_time` freshness validated? | {location} | YES/NO |
| `price.price` (I64) sign checked (> 0)? | {location} | YES/NO |
| `price.conf` confidence interval checked? | {location} | YES/NO |
| `price.expo` (negative exponent) handled correctly? | {location} | YES/NO |
| Price feed ID hardcoded or configurable? | {location} | {which} |

### 2d. Switchboard-Specific Checks

| Check | Code Reference | Status |
|-------|---------------|--------|
| Aggregator authority validated? | {location} | YES/NO |
| Result staleness checked? | {location} | YES/NO |
| Min/max response thresholds enforced? | {location} | YES/NO |
| Aggregator config (min oracle results, variance threshold) appropriate? | {location} | YES/NO |

## 3. Decimal Normalization Audit

For each oracle data flow:

| Oracle | Oracle Decimals/Exponent | Consumer Expects | Normalization Applied? | Correct? |
|--------|------------------------|-----------------|----------------------|----------|
| {name} | {expo or scale} | {expected by math} | YES/NO | {analysis} |

**Pyth decimal handling**: Pyth uses `expo` field (typically negative, e.g., `expo = -8` means 8 decimal places). The actual price = `price.price * 10^expo`. Common errors:
- Treating `expo` as positive when it is negative
- Not converting I64 exponent to unsigned for power calculation
- Mixing Pyth's expo-based decimals with token decimals (Aptos Coin typically uses 8 decimals, but FungibleAsset varies)

**Switchboard decimal handling**: Uses `mantissa` and `scale` (or `decimals`). Actual value = `mantissa * 10^(-scale)`.

**MANDATORY GREP**: Search all oracle consumer files for hardcoded decimal constants: `100000000`, `1e8`, `10_000_000`, `DECIMAL`, `PRECISION`. For each hit: (1) Is this a decimal normalization constant? (2) Does it match the ACTUAL oracle's decimal format? (3) If the oracle feed changes or is swapped, does this constant break?

**Decimal chain trace**: For each arithmetic operation using oracle data, trace the full decimal chain: `oracle_output_decimals` -> `normalization_step` -> `consumer_expected_decimals`. If any step uses a hardcoded constant rather than reading decimals dynamically -> FINDING.

**Common decimal mismatches on Aptos**:
- Pyth USD feeds: `expo = -8` (8 decimals), but protocol assumes 18
- Aptos native Coin<T>: typically 8 decimals
- FungibleAsset: varies per metadata configuration
- Cross-multiplication without normalization: `price * amount` where price and amount have different decimal bases

### 3d. Decimal Grep Sweep (MECHANICAL -- MANDATORY)

Grep ALL oracle consumer files for `10_u128|pow\(10|DECIMALS|PRECISION|100000000|normalize`. For each match, fill:

| File:Line | Pattern | Hardcoded Value | Oracle's Actual Decimals | Match? |
|-----------|---------|-----------------|-------------------------|--------|

If ANY row shows Match=NO or oracle decimals UNKNOWN with hardcoded constant -> FINDING (R16).
Skipping this step is a Step Execution violation (x3d).

<!-- LOAD_IF: TWAP -->
## 4. TWAP-Specific Analysis

If protocol uses any TWAP oracle (DEX-derived, custom accumulator, etc.):

### 4a. TWAP Window Analysis

| TWAP Oracle | Window Length | Pool Liquidity | Manipulation Cost (est.) | Sufficient? |
|-------------|-------------|----------------|-------------------------|-------------|
| {oracle} | {seconds} | {USD value} | {estimated} | YES/NO |

**Rule of thumb**: TWAP window < 30 min AND pool TVL < $10M -> potentially manipulable.

### 4b. TWAP Arithmetic

| Check | Status | Impact if Wrong |
|-------|--------|-----------------|
| Overflow protection on cumulative price difference? | YES/NO | {impact} |
| Geometric vs arithmetic mean -- correct for use case? | {which used} | {impact if wrong} |
| Time-weighted vs block-weighted -- which is used? | {which} | {manipulation vector} |
| Empty observation slots handled? | YES/NO | {impact} |
| Aptos epoch boundaries handled? (epoch changes can affect timestamps) | YES/NO | {impact} |

### 4c. TWAP Lagging Behavior

During rapid price movements, TWAP lags spot price. Trace:
- What happens when TWAP price is significantly lower than spot? (discounted minting/borrowing)
- What happens when TWAP price is significantly higher than spot? (premium liquidations)
- Is this lag exploitable by attackers who can predict the direction?

### 4d. TWAP Cold-Start Analysis

Check oracle behavior when history is insufficient: (1) zero snapshots, (2) single snapshot, (3) window period not yet elapsed.

| Cold-Start State | Oracle Return Value | Protocol Behavior | Exploitable? |
|------------------|--------------------:|-------------------|-------------|

For each exploitable state: can attacker act during cold-start window at manipulated price? Tag: [BOUNDARY:snapshots=0], [BOUNDARY:snapshots=1].
If TWAP returns 0 or aborts during cold-start with no fallback -> FINDING (R16, minimum Medium).
<!-- END_LOAD_IF: TWAP -->

## 5. Oracle Weight / Threshold Boundaries

For multi-oracle systems or oracle-based thresholds:

<!-- LOAD_IF: MULTI_ORACLE -->
### 5a. Multi-Oracle Systems

| Oracle System | Aggregation Method | Oracle Count | Agreement Required | What if Disagreement? |
|---------------|-------------------|-------------|-------------------|----------------------|
| {system} | Median / Mean / Weighted / First-valid | {N} | {M of N} | {fallback behavior} |

**Check**: What happens at exact threshold boundaries?
- If median of [100, 100, 101]: result = 100. Is that correct?
- If weighted average with equal weights rounds down: impact?
- If one oracle call aborts: does fallback handle it gracefully?
<!-- END_LOAD_IF: MULTI_ORACLE -->

### 5b. Oracle-Based Thresholds

| Threshold | Oracle Data Used | Threshold Value | At Exact Boundary | Off-by-One? |
|-----------|-----------------|----------------|-------------------|-------------|
| {name} | {oracle field} | {value} | {behavior at exact value} | YES/NO |

**Check `>` vs `>=`**: At the exact threshold value, does the protocol behave as intended?

### 5c. Deviation Reference Point Audit

For each deviation check in the protocol (maxDeviation, priceDeviation, deviationThreshold, etc.):

| Parameter | Measured Against | Reference Source | Reference Manipulable? | Reference Staleable? |
|-----------|-----------------|-----------------|----------------------|---------------------|

Checks:
1. What is the deviation MEASURED AGAINST? (previous on-chain price, TWAP, external oracle, hardcoded value)
2. Is the reference point itself manipulable? (e.g., if deviation checks current vs last-recorded, and last-recorded is admin-settable -> admin can set a stale reference that makes all future prices "within deviation")
3. Can the reference become stale? (e.g., if reference is updated only on specific actions, and those actions stop occurring)
4. Is the first recorded price special? (no prior reference -> deviation check may be bypassed on first update)
Tag: `[TRACE:deviation check: current vs {reference} -> reference source: {X} -> manipulable: {Y/N}]`

## 6. Oracle Failure Modes

For each oracle, model failure scenarios:

| Failure Mode | Oracle Behavior | Protocol Response | Impact | Mitigation Present? |
|-------------|-----------------|-------------------|--------|-------------------|
| Zero return | Returns price = 0 | {what happens} | {impact} | YES/NO |
| Abort | Call aborts (Move has no try/catch) | {what happens} | {impact} | YES/NO -- can_* check first? |
| Stale (freshness exceeded) | Returns old data | {what happens} | {impact} | YES/NO -- staleness check? |
| Extreme value | Returns outlier | {what happens} | {impact} | YES/NO -- bounds check? |
| Negative price (Pyth I64) | Returns < 0 | {what happens} | {impact} | YES/NO -- sign check? |
| Feed not initialized | Resource does not exist | {what happens} | {impact} | YES/NO -- exists<T> check? |

**Aptos-specific failure note**: Move does not have try/catch. Oracle call failures result in transaction abort. This means:
- External oracle call that aborts -> entire transaction reverts
- No graceful fallback unless protocol pre-checks oracle state with `exists<>` or similar
- Oracle DoS (feed stops updating) -> all dependent functions become uncallable

**For each unmitigated failure mode**: What is the worst-case impact? Can it lead to fund loss?

**Circuit breaker check**: Does the protocol have a mechanism to pause oracle-dependent operations if the oracle enters a failure state?

## Instantiation Parameters
```
{CONTRACTS}           -- Move modules to analyze
{ORACLE_MODULES}      -- Oracle module paths (pyth::price_feed, switchboard::aggregator, custom)
{CONSUMER_FUNCTIONS}  -- Functions that read oracle data
{PRICE_FEED_IDS}      -- Pyth price feed identifiers or Switchboard aggregator addresses
{TOKEN_DECIMALS}      -- Decimal configuration of tokens in scope
```

## Finding Template

```markdown
**ID**: [OR-N]
**Severity**: [based on fund impact and likelihood of oracle failure/manipulation]
**Step Execution**: checkmark1,2,3,4,5,6 | x(reasons) | ?(uncertain)
**Rules Applied**: [R1:Y, R4:Y, R10:Y, R16:Y]
**Location**: module::function:LineN
**Title**: Oracle [issue type] in [function] enables [attack/failure]
**Description**: [Specific oracle issue with data flow trace]
**Impact**: [Quantified impact under worst-case oracle scenario]
```

## Output Schema

| Field | Required | Description |
|-------|----------|-------------|
| oracle_inventory | yes | All oracle data sources and consumers |
| staleness_vectors | yes | Unmitigated staleness paths |
| decimal_mismatches | yes | Decimal normalization issues |
| failure_modes | yes | Oracle failure scenarios and protocol response |
| finding | yes | CONFIRMED / REFUTED / CONTESTED |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | Status for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Source: WebSearch pass (April 2026). 7 findings across Aptos/Move oracle patterns.
> Tags used: oracle, pyth, switchboard, staleness, price_deviation, zero_price, confidence, spot_price_manipulation, decimal

---

## WE-OR-01

**Title**: Missing Pyth price staleness check allows stale prices to affect collateral valuations
**Severity**: HIGH
**Tags**: oracle, pyth, staleness
**Protocol/Platform**: Generic Aptos lending (Pyth integration pattern)
**Source**: Pyth Best Practices docs + Aptos Move Security Guidelines; corroborated by multiple Aptos audit firms (MoveBit, Zellic)

**Pattern**: Protocol calls `pyth::get_price()` (or the unsafe variant) without comparing `price.publish_time` against `timestamp::now_seconds()`. No maximum staleness threshold enforced. Stale price feeds can persist during oracle downtime or network congestion.

**Attack / Failure Path**:
1. Pyth price feed goes stale (feed publisher offline, network congestion, or targeted DoS).
2. Protocol continues reading `price.price` from the last published `PriceFeed` resource.
3. If the last published price differs materially from current market (e.g., 30-minute-old price during a crash), an attacker borrows at the inflated stale price or avoids liquidation.

**Impact**: Undercollateralized loans originate against stale collateral prices. Protocol accrues bad debt. Under extreme staleness, full insolvency possible.

**Recommended Check**:
```move
let max_age_secs: u64 = 60; // e.g. 60 seconds
let price = pyth::get_price_no_older_than(&price_info_object, clock, max_age_secs);
```
Or manually: `assert!(timestamp::now_seconds() - price.publish_time <= MAX_STALENESS, ESTALE_PRICE);`

**SKILL.md Mapping**: Step 2 (Staleness Analysis) / Step 2c (Pyth-Specific Checks) — `get_price()` vs `get_price_no_older_than()` used?

---

## WE-OR-02

**Title**: Pyth price zero-value not rejected — zero oracle price accepted as valid
**Severity**: HIGH
**Tags**: oracle, pyth, zero_price
**Protocol/Platform**: Bluefin (Sui/Move perpetual exchange — pattern directly applicable to Aptos Pyth consumers)
**Source**: MoveBit audit of Bluefin (Hackenproof contest, February 2024) — https://www.movebit.xyz/blog/post/Bluefin-vulnerabilities-explanation-1.html

**Pattern**: Protocol calls `pyth::get_price_unsafe` and checks that the price is non-negative using `get_magnitude_if_positive`, but does not check for `price == 0`. In Move/Pyth's I64 representation, `0` is encoded as `{magnitude: 0, negative: false}` and passes a "non-negative" check.

**Attack / Failure Path**:
1. If a Pyth feed momentarily returns price = 0 (feed initialization, data gap, or intentional feed manipulation).
2. Protocol accepts `0` as a valid price.
3. Downstream: collateral valued at zero triggers mass liquidations; or perpetual positions calculated at zero price are settled incorrectly.

**Impact**: Protocol-wide incorrect pricing for all operations that consume this feed. Mass incorrect liquidations or under-valued position settlement.

**Fix**: After sign check, add `assert!(price_value > 0, EZERO_PRICE);`

**SKILL.md Mapping**: Step 6 (Oracle Failure Modes) — "Zero return" row; Step 2c — `price.price` (I64) sign checked (> 0)?

---

## WE-OR-03

**Title**: Pyth confidence interval not validated — wide confidence band accepted as precise price
**Severity**: MEDIUM
**Tags**: oracle, pyth, confidence
**Protocol/Platform**: Generic Pyth consumer pattern; specific instance: Debita protocol (Sherlock 2024, issue #548 — cross-chain pattern applicable to Move)
**Source**: https://github.com/sherlock-audit/2024-10-debita-judging/issues/548 + Pyth Best Practices docs

**Pattern**: Protocol reads `price.price` but ignores `price.conf` (confidence interval). Pyth publishes `conf` as a ±range around the price. During market stress, conf can be very wide (e.g., conf/price > 10%), meaning the actual market price could be `price ± conf`. Protocol treats `price.price` as exact.

**Attack / Failure Path**:
1. During a volatile event, Pyth publishes price=1000, conf=200 (20% range).
2. Protocol uses 1000 as the exact collateral value.
3. Attacker borrows using an asset actually worth 800 (lower confidence bound).
4. Attacker exits; collateral is insufficient to cover the debt.

**Impact**: Systematic over-valuation of collateral during market stress precisely when liquidation accuracy matters most. Bad debt accumulation.

**Recommended Check**: Enforce `conf * CONF_MULTIPLIER <= price` (e.g., conf must be < 2% of price). Pyth docs recommend rejecting prices where `conf / price > threshold`.

**SKILL.md Mapping**: Step 2c — `price.conf` confidence interval checked?

---

## WE-OR-04

**Title**: Pyth `publish_time` can be in the future — staleness check is not bidirectional
**Severity**: LOW-MEDIUM
**Tags**: oracle, pyth, staleness
**Protocol/Platform**: Folks Finance (Algorand/Aptos-applicable pattern) — Immunefi Boost finding #33443
**Source**: https://github.com/immunefi-team/Past-Audit-Competitions/blob/main/Folks%20Finance/Boost%20_%20Folks%20Finance%2033443%20-%20%5BSmart%20Contract%20-%20Low%5D%20StalenessCircuitBreakerNode%20checks%20if%20the%20last%20update%20time%20of%20the%20parent%20node%20is%20less%20than%20the%20threshold%20but%20the%20publicTime%20could%20be%20greater%20than%20current%20blocktimestamp.md

**Pattern**: Staleness check only validates that `publish_time` is not too old (`now - publish_time <= threshold`). It does not check that `publish_time <= now`. Due to clock skew or Pyth off-chain publisher issues, `publish_time` can be slightly in the future relative to on-chain `block.timestamp`. The staleness tolerance math treats future timestamps as passing validation.

**Attack / Failure Path**: A Pyth price with `publish_time = now + delta` bypasses "is this too old?" check. The price may correspond to a speculative or erroneous future state. Combining with other oracle timing assumptions, an attacker can craft transactions that use these future-timestamped prices.

**Impact**: Low-to-medium depending on the delta and protocol's use of the price. Creates edge case in timing-sensitive liquidations.

**Fix**: `assert!(price.publish_time <= timestamp::now_seconds(), EFUTURE_PRICE);`

**SKILL.md Mapping**: Step 2c — `price.publish_time` freshness validated?

---

## WE-OR-05

**Title**: Oracle staleness parameter unbounded — admin can set max staleness to u64::MAX enabling permanently stale prices
**Severity**: HIGH
**Tags**: oracle, staleness, price_deviation
**Protocol/Platform**: Navi Protocol (Sui Move — pattern directly applicable to Aptos Pyth/Supra integrations)
**Source**: Veridise audit VAR_Navi-240607 (2024) — https://veridise.com/wp-content/uploads/2024/11/VAR_Navi-240607-Decentralized_Oracle_Integration.pdf

**Pattern (V-NOR-VUL-001)**: A function protected by `OracleAdminCap` allows an authorized admin to update the maximum staleness threshold parameter. The function has no upper-bound validation on the new value. If an admin (or a compromised admin key) sets this to `u64::MAX` or any very large value, the oracle price freshness check is rendered permanently bypassed.

**Attack / Failure Path**:
1. Admin (or attacker with stolen admin key) calls `set_max_staleness(u64::MAX)`.
2. All price freshness assertions pass unconditionally.
3. Protocol proceeds with arbitrarily stale prices indefinitely.

**Impact**: Complete neutralization of the staleness circuit breaker. Combined with a stale feed, enables all failure modes described in WE-OR-01.

**Fix**: Add `assert!(new_max_staleness <= ABSOLUTE_MAX_STALENESS, EINVALID_PARAM);` with a protocol-defined absolute ceiling (e.g., 300 seconds for active feeds).

**SKILL.md Mapping**: Step 5c (Deviation Reference Point Audit) — reference manipulable by admin? Step 6 — circuit breaker check.

---

## WE-OR-06

**Title**: Pyth confidence interval not consumed — separate high-severity finding in Veridise Navi audit
**Severity**: MEDIUM
**Tags**: oracle, pyth, confidence
**Protocol/Platform**: Navi Protocol (Sui Move)
**Source**: Veridise audit VAR_Navi-240607, finding V-NOR-VUL-010 — https://veridise.com/wp-content/uploads/2024/11/VAR_Navi-240607-Decentralized_Oracle_Integration.pdf

**Pattern**: The Navi oracle module fetches price from Pyth but reads only `price.price`, discarding `price.conf`. No confidence band check exists anywhere in the oracle consumption path.

**Note**: This is a separate confirmed finding from a published audit (not an inference), covering the same confidence-band pattern as WE-OR-03 but with a distinct protocol and auditor. Useful as a second data point for prevalence.

**Impact**: As WE-OR-03 — over-valuation of collateral during high-volatility periods.

**SKILL.md Mapping**: Step 2c — `price.conf` confidence interval checked?

---

## WE-OR-07

**Title**: DEX spot price used as sole oracle — flash-loan manipulable in Move username/domain pricing
**Severity**: HIGH
**Tags**: oracle, spot_price_manipulation, price_deviation
**Protocol/Platform**: Initia Move (username module)
**Source**: Local CSV row_index 1804 (candidates.jsonl) — Sherlock/audit finding, HIGH severity

**Pattern**: The `usernames` module reads the spot price from the Dex module (on-chain AMM reserves ratio) to calculate domain registration and extension fees. No TWAP. No external oracle. The spot price can be moved in the same transaction by a flash loan or large deposit.

**Attack / Failure Path**:
1. Attacker takes a flash loan and performs a large swap in the DEX pool used for pricing.
2. Spot price shifts to attacker's advantage (e.g., target token becomes artificially cheap).
3. Attacker registers or extends domains at a fraction of the intended cost in the same transaction.
4. Attacker repays flash loan. Net cost: flash loan fee only. Gain: underpriced domain(s).
5. Other users who register at the now-restored "normal" price effectively overpay relative to attacker.

**Impact**: Domain registrations available at near-zero cost. Protocol revenue drained. Other users front-run on pricing.

**Fix**: Replace spot price with a TWAP (minimum 30-minute window) or an external oracle such as Slinky (Initia's enshrined oracle). Protocol confirmed fix: hardcode price at 1 at launch, migrate to Slinky oracle.

**SKILL.md Mapping**: Step 4 (TWAP-Specific Analysis — absence of TWAP); Step 5c (Deviation Reference — spot price is manipulable reference); Step 6 (Failure modes — flash loan path).

---

## Coverage Summary

| ID | Severity | Tag(s) | Oracle | Source Type |
|----|----------|--------|--------|-------------|
| WE-OR-01 | HIGH | staleness | Pyth | Pyth docs + Aptos guidelines |
| WE-OR-02 | HIGH | zero_price | Pyth | Published audit (MoveBit/Bluefin) |
| WE-OR-03 | MEDIUM | confidence | Pyth | Sherlock finding + Pyth docs |
| WE-OR-04 | LOW-MED | staleness | Pyth | Immunefi Boost finding |
| WE-OR-05 | HIGH | staleness, price_deviation | Pyth/Supra | Published audit (Veridise/Navi) |
| WE-OR-06 | MEDIUM | confidence | Pyth | Published audit (Veridise/Navi) |
| WE-OR-07 | HIGH | spot_price_manipulation | DEX spot | Local CSV (Initia Move, Sherlock) |

Local CSV contributed: 1 directly (WE-OR-07 from row_index 1804). Web research contributed: 6 new findings.
Total: 7 findings.


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Oracle Inventory | YES | Y/x/? | |
| 2. Staleness Analysis | YES | Y/x/? | For each oracle |
| 2c. Pyth-Specific Checks | IF Pyth used | Y/x(N/A)/? | |
| 2d. Switchboard-Specific Checks | IF Switchboard used | Y/x(N/A)/? | |
| 3. Decimal Normalization Audit | YES | Y/x/? | |
| 3d. Decimal Grep Sweep | YES | Y/x/? | MANDATORY mechanical step |
| 4. TWAP-Specific Analysis | IF TWAP used | Y/x(N/A)/? | |
| 4d. TWAP Cold-Start Analysis | IF TWAP used | Y/x(N/A)/? | Zero/single snapshot states |
| 5. Oracle Weight / Threshold Boundaries | IF multi-oracle or thresholds | Y/x(N/A)/? | |
| 5c. Deviation Reference Point Audit | IF deviation checks exist | Y/x(N/A)/? | Reference manipulability |
| 6. Oracle Failure Modes | YES | Y/x/? | For each oracle |
