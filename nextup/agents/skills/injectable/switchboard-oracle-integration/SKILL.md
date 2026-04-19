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
