---
name: "switchboard-oracle-integration"
description: "Protocol Type Trigger switchboard_oracle_integration (detected when recon finds switchboard_v2|AggregatorAccountData|latest_confirmed_round|min_oracle_results|variance_threshold|SwitchboardDecimal - protocol USES Switchboard as price feed)"
---

# Injectable Skill: Switchboard Oracle Integration Security

> Protocol Type Trigger: `switchboard_oracle_integration` (detected when recon finds: `switchboard_v2`, `AggregatorAccountData`, `latest_confirmed_round`, `min_oracle_results`, `variance_threshold`, `SwitchboardDecimal`)
> Inject Into: depth-external, depth-edge-case
> Language: Solana only
> Finding prefix: `[SBV-N]`
> Relationship to pyth-oracle-integration: both cover oracle consumption. Protocols with multi-oracle fallback should activate both.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (aggregator account ownership and binding)
- Section 2: depth-edge-case (round freshness + min_oracle_results)
- Section 3: depth-edge-case (variance threshold interaction with staleness)
- Section 4: depth-edge-case (SwitchboardDecimal mantissa/scale math)
- Section 5: depth-external (v2 vs on-demand layout divergence)
- Section 6: depth-external (authority swap mid-flight)

## When This Skill Activates

Recon detects that the program reads prices or arbitrary numeric feeds from Switchboard V2 or Switchboard On-Demand, typically via `AggregatorAccountData::new` and `latest_confirmed_round`.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: switchboard, AggregatorAccountData, latest_confirmed_round, min_oracle_results, variance_threshold
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[SBV-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Aggregator Account Validation

### 1a. Owner Program Pinning
- Does the program pin `aggregator.owner == switchboard_v2::ID` (or on-demand program id)?
- Real finding pattern (Solodit, pattern observed in multiple audits): Anchor account struct types an aggregator as `AccountInfo<'info>` without `#[account(owner = SWITCHBOARD_PROGRAM_ID)]`. Attacker supplies a crafted account.

### 1b. Feed Binding to Market Config
- Is the aggregator pubkey bound to a market configuration, or can any Switchboard feed be supplied?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Lending instruction accepts any feed named in request, enabling price swap to a different asset.

### 1c. Loader Discriminant
- Does the program use `AggregatorAccountData::new` (V2) which checks the discriminator, or raw byte slicing?
- Real finding pattern (pattern observed in multiple audits): Program reads bytes offset 8..16 as `i64 price`, skipping the loader, and therefore skips discriminator validation.

Tag: [TRACE:aggregator_owner_pinned=YES/NO → feed_bound_to_market=YES/NO → loader_discriminator_used=YES/NO]

---

## 2. Round Freshness and min_oracle_results

### 2a. latest_confirmed_round Staleness
- Does the program compare `latest_confirmed_round.round_open_slot` (or `round_open_timestamp`) to `Clock` to enforce a max age?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program uses `latest_confirmed_round.result` directly even if the round opened thousands of slots ago.

### 2b. min_oracle_results Honored
- Does `num_success` meet the configured `min_oracle_results`? Otherwise the aggregate is not quorum-valid.
- Real finding pattern (Cantina, pattern observed in multiple audits): Program consumes the round's `result` regardless of `num_success`, accepting one-oracle outcomes.

### 2c. Unconfirmed Round Read
- Programs should read `latest_confirmed_round` not `current_round`. The current round is not yet quorum-closed.
- Real finding pattern (pattern observed in multiple audits): Helper reads `current_round.result` so an attacker-timed transaction sees a partial round.

Tag: [TRACE:round_max_age_enforced=YES/NO → min_oracle_results_checked=YES/NO → confirmed_vs_current=confirmed/current]

---

## 3. Variance Threshold and Staleness Interaction

### 3a. Variance Threshold Suppresses Updates
- Switchboard only writes a new round when cross-oracle variance exceeds `variance_threshold`. A feed can therefore appear stale even though oracles are running.
- Real finding pattern (Solodit, pattern observed in multiple audits): Program treats unchanged `round_open_slot` as a dead feed and halts, DoS-ing user withdrawals.

### 3b. Threshold Too Loose
- Is `variance_threshold` set so high that real price moves are ignored? Protocol should reject markets whose feed config has threshold > a small percent.
- Real finding pattern (pattern observed in multiple audits): Config accepts markets with 10% variance threshold, enabling 9.9% silent moves.

### 3c. Force-Report Period Assumption
- Protocols sometimes rely on `force_report_period` to cap max feed age regardless of variance. Does the program read and enforce this?
- Real finding pattern (pattern observed in multiple audits): Program ignores `force_report_period`, so a low-variance period appears fresh forever.

Tag: [TRACE:variance_threshold_gt_x_pct=<value> → force_report_period_enforced=YES/NO]

---

## 4. SwitchboardDecimal Parsing

### 4a. Mantissa Sign and Scale
- `SwitchboardDecimal { mantissa: i128, scale: u32 }`. Does the program handle `scale` consistently across positive/negative mantissa?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program casts `mantissa as u128` before scale correction, turning negatives into huge positives.

### 4b. Overflow in Scaling
- `mantissa / 10^scale` or `mantissa * 10^(target_scale - scale)` can overflow `i128` when scale is unexpected.
- Real finding pattern (Cantina, pattern observed in multiple audits): Program assumes scale = 9, but feed returns scale = 18; multiplication overflows.

### 4c. Precision Loss
- When converting to `u64` price-units, does the program round toward safe direction (down for collateral, up for debt)?
- Real finding pattern (pattern observed in multiple audits): Integer division rounds both directions to zero, so tiny prices become zero, bypassing health checks.

Tag: [TRACE:decimal_sign_handled=YES/NO → scale_checked_overflow=YES/NO → rounding_direction=correct/incorrect]

---

## 5. V2 vs On-Demand Layout

### 5a. Wrong Loader for Program
- Switchboard On-Demand uses a different account layout than V2. Loading an on-demand account with V2 loader reads garbage.
- Real finding pattern (pattern observed in multiple audits): Program imports `switchboard_v2` but points at an on-demand feed pubkey; bytes at V2 offsets are unrelated fields.

### 5b. Program ID Allowlist
- Does the program accept both V2 and On-Demand program IDs? Is each mapped to the matching loader?
- Real finding pattern (pattern observed in multiple audits): Allowlist contains both IDs but the loader always treats data as V2.

### 5c. Feature Availability
- Some features (e.g. `min_oracle_results`, result buffer) exist only in one variant. Protocol config should refuse unsupported feeds.
- Real finding pattern (pattern observed in multiple audits): Protocol assumes on-demand behavior on a V2 feed, expecting a nonexistent quorum field.

Tag: [TRACE:program_id_loader_match=YES/NO → feature_supported_per_variant=YES/NO]

---

## 6. Feed Authority Swap

### 6a. Authority Rotation Mid-Flight
- A feed's authority can be rotated off-chain; the oracle operator changes. Does the protocol re-validate authority or trust first bind?
- Real finding pattern (Solodit, pattern observed in multiple audits): Market stored feed pubkey only. Authority changes, job definitions change, price semantics shift. Program unaware.

### 6b. Queue and Crank Trust
- Which oracle queue and crank are permitted? A feed can be moved to a queue with different slashing guarantees.
- Real finding pattern (pattern observed in multiple audits): Protocol does not pin queue, so authority moves feed to a low-stake queue.

### 6c. Job Definition Drift
- Job hash drift (TWAP aggregation over different CEX sources) causes silent price model changes.
- Real finding pattern (pattern observed in multiple audits): Perp market relies on mid-price from two venues. Operator drops a venue; feed becomes thin and manipulable.

Tag: [TRACE:authority_rechecked=YES/NO → queue_pinned=YES/NO → job_hash_pinned=YES/NO]

---

## Common False Positives

- Program uses a wrapper service that already validates discriminator and authority. Sections 1 and 6 checks are delegated.
- Feed is informational only (UI hint, not used in token-flow math). Most sections do not apply.
- Protocol uses Switchboard purely as a keeper-trigger VRF signal, not price. Decimal and variance sections do not apply.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Sources gathered via web search. Findings are from post-mortems, audit reports, and published security research. The local CSV already covers two findings (staleness missing timestamp check, VRF RandomnessCommit replay). The entries below are distinct from those two.

---

- Pattern: Single-source Switchboard feed accepted without multi-oracle quorum, enabling spot price manipulation
  Where it hit: Solend isolated pools (USDH collateral), November 2022
  Severity: HIGH (resulted in $1.26M bad debt)
  Source: https://ackee.xyz/blog/2022-solana-hacks-explained-solend/ and https://immunebytes.com/blog/solends-isolated-pools-exploitation-nov-2-2022-detailed-analysis/
  Summary: Solend's USDH lending pool read its price exclusively from a Switchboard V2 feed whose only job was the Saber USDH/USDC pool. The feed had no min_oracle_results guard requiring cross-source quorum, so an attacker pumped the Saber pool price from ~$1 to ~$15 (spending ~$113k USDC per wave, spamming the account to block same-slot arbitrage), causing Switchboard's aggregator to accept the inflated value. The attacker deposited USDH as collateral and borrowed against the inflated price across three waves, creating $1.26M in bad debt.
  Map to: switchboard_v2, AggregatorAccountData, latest_confirmed_round, min_oracle_results

---

- Pattern: LP token price fed through Switchboard can be manipulated via flash-loan-inflated pool reserves
  Where it hit: Hypothetical class of Solana lending protocols using Switchboard LP feeds (OtterSec research, Feb 2022)
  Severity: CRITICAL (theoretical; OtterSec estimated up to $200M exposure across Solana lending)
  Source: https://osec.io/blog/2022-02-16-lp-token-oracle-manipulation/
  Summary: OtterSec showed that Switchboard feeds pricing LP tokens by reading the on-chain pool reserve ratio (the standard AMM sqrt-k formula) are susceptible to flash-loan inflation: an attacker inflates reserves in one transaction, reads the elevated Switchboard feed value, uses the overpriced LP as collateral, borrows, then unwinds. The root cause is that Switchboard's per-job aggregation reflects spot pool state, not TWAP, and protocols that consume the feed without a variance threshold check or max-staleness guard cannot detect the spike. This research prompted multiple Solana protocols to replace Switchboard LP feeds with on-chain TWAP constructions.
  Map to: switchboard_v2, AggregatorAccountData, latest_confirmed_round, variance_threshold

---

- Pattern: Switchboard aggregator account owner not pinned to the switchboard_v2 program ID, enabling a crafted account substitution
  Where it hit: Generic pattern documented in Solana audit best-practice literature (Slowmist, Sec3, RareSkills security-checks post); directly flagged as a common audit finding in multiple Solana lending and perp audits
  Severity: HIGH
  Source: https://github.com/slowmist/solana-smart-contract-security-best-practices and https://rareskills.io/post/solana-essential-security-checks
  Summary: Programs that pass the Switchboard aggregator as a raw `AccountInfo` without asserting `account.owner == switchboard_v2::ID` allow an attacker to supply a crafted account with arbitrary byte content at the expected field offsets. The attacker controls the reported price returned by `AggregatorAccountData::new`, bypassing all subsequent round-freshness and quorum checks because those checks run on attacker-controlled data. The fix is a constraint such as `#[account(owner = SWITCHBOARD_V2_PROGRAM_ID)]` in Anchor, or an explicit owner assertion before deserialization.
  Map to: switchboard_v2, AggregatorAccountData

---

- Pattern: Switchboard feed staleness not enforced: program calls latest_confirmed_round.result without comparing round_open_slot to Clock
  Where it hit: Multiple Solana lending and perp protocols (pattern documented in Solana audit guides; the Solend incident confirmed real-world exploitability of stale-feed windows)
  Severity: HIGH
  Source: https://rareskills.io/post/solana-switchboard-oracle (documents correct usage of max_stale_slots); https://www.zealynx.io/blogs/solana-security-checklist (checklist item: "revert if price data older than current_slot - 2")
  Summary: Programs that read `latest_confirmed_round.result` directly without a slot-age gate accept arbitrarily old prices. During network congestion or deliberate oracle transaction spamming, the most-recently-confirmed round can be many hundreds of slots stale. An attacker who can predict or cause congestion can force the program to transact at a stale price. The Switchboard SDK exposes `check_staleness(unix_timestamp, max_seconds)` and `max_stale_slots` precisely to guard against this, but protocols omitting these calls are exploitable. This is distinct from the CSV finding (row 3677) in that it covers the on-chain slot-comparison path rather than just the timestamp field.
  Map to: switchboard_v2, AggregatorAccountData, latest_confirmed_round

---

- Pattern: Switchboard feed used with a single oracle (num_success == 1) while min_oracle_results is misconfigured or unchecked, giving one oracle operator full price control
  Where it hit: Solana DeFi protocols relying on low-staked Switchboard queues; pattern discussed in Switchboard post-Solend post-incident recommendations and Cyfrin oracle manipulation guide
  Severity: HIGH
  Source: https://immunebytes.com/blog/solends-isolated-pools-exploitation-nov-2-2022-detailed-analysis/ (post-incident improvement list); https://www.cyfrin.io/blog/price-oracle-manipulation-attacks-with-examples
  Summary: After the Solend exploit, Switchboard's post-incident recommendations explicitly called out that protocol-side code must verify `latest_confirmed_round.num_success >= aggregator.min_oracle_results` before consuming the result. A round with num_success = 1 means a single oracle operator's submission was accepted as the aggregate; if that operator is compromised or malicious, any price can be written. Protocols that read `result` without checking `num_success` effectively trust a single data point as quorum-validated. The fix requires asserting `num_success >= min_oracle_results` after loading `AggregatorAccountData`.
  Map to: switchboard_v2, AggregatorAccountData, latest_confirmed_round, min_oracle_results

---

- Pattern: Switchboard VRF randomness committed multiple times before reveal, allowing brute-force of favorable outcomes
  Where it hit: Solana on-chain coin-flip and gaming programs using Switchboard VRF (documented in Switchboard's own security communications and referenced in audit findings; CSV row 5130 is a direct example)
  Severity: HIGH
  Source: https://docs.switchboard.xyz/product-documentation/aggregator/how-to-use-the-switchboard-oracle-aggregator (VRF commitment model); https://medium.com/@aniqarq/a-comprehensive-dive-into-switchboard-the-everything-oracle-64aa9768c8a4
  Summary: Programs that allow the RandomnessCommit instruction to be called multiple times for the same game state let an attacker commit, receive a VRF result, discard it if unfavorable by committing again, and repeat until the outcome is favorable. The protocol should enforce that once a commitment is in flight (committed but not yet revealed), no second commitment is accepted. The consumer program should also store the seed slot and verify it has not changed during the settlement call to prevent front-running of the reveal. This is included here as a separate web-sourced entry to give the pattern a documented source URL distinct from the CSV summary.
  Map to: switchboard_v2

---

## Coverage note

The local CSV provides 2 findings (row 3677: missing timestamp staleness check; row 5130: VRF RandomnessCommit replay). The 6 entries above add distinct documented patterns: single-source quorum absence (Solend exploit), LP token flash-loan oracle inflation (OtterSec research), missing aggregator owner pin, slot-based staleness gate omission, num_success not checked against min_oracle_results, and a sourced VRF commitment brute-force entry. Total unique web-sourced findings: 6.


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Owner Program Pinning | YES | | program id check |
| 1b. Feed Bound to Market | YES | | not arbitrary |
| 1c. Loader Discriminant | YES | | V2 loader used |
| 2a. latest_confirmed_round Staleness | YES | | age gate |
| 2b. min_oracle_results | YES | | quorum enforced |
| 2c. Confirmed vs Current | YES | | confirmed path |
| 3a. Variance Suppression | YES | | stale-but-healthy case |
| 3b. Threshold Too Loose | YES | | config bound |
| 3c. Force Report Period | IF max age is mission-critical | | enforced |
| 4a. Mantissa Sign | YES | | i128 cast |
| 4b. Scale Overflow | YES | | checked math |
| 4c. Rounding Direction | YES | | safe direction per role |
| 5a. Wrong Loader | IF on-demand feeds in scope | | loader matches variant |
| 5b. Program ID Allowlist | IF multi-variant | | loader per id |
| 5c. Feature Availability | IF assuming a specific feature | | feature supported |
| 6a. Authority Rotation | YES | | re-validation |
| 6b. Queue Pinned | YES | | trust boundary |
| 6c. Job Hash Pinned | IF price model sensitive | | drift detection |
