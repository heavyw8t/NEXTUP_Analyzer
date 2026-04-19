---
name: "kamino-strategy-integration"
description: "Protocol Type Trigger kamino_strategy_integration (detected when recon finds kamino|kamino_lending|kamino_vault|kvaults|Strategy|scope_prices|klend|strategy_rebalance - protocol USES Kamino vaults or K-Lend)"
---

# Injectable Skill: Kamino Strategy Integration Security

> Protocol Type Trigger: `kamino_strategy_integration` (detected when recon finds: `kamino`, `kamino_lending`, `kamino_vault`, `kvaults`, `Strategy`, `scope_prices`, `klend`, `strategy_rebalance`)
> Inject Into: depth-token-flow, depth-state-trace
> Language: Solana only
> Finding prefix: `[KAM-N]`
> Relationship to clmm-pool-integration: Kamino vaults LP into CLMM pools. Activate that skill together.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-token-flow (share price inflation)
- Section 2: depth-state-trace (rebalance atomic invariant)
- Section 3: depth-state-trace (scope price staleness)
- Section 4: depth-token-flow (multi-collateral exposure)
- Section 5: depth-state-trace (boosted rewards window)
- Section 6: depth-state-trace (K-Lend reserve cap)

## When This Skill Activates

Recon detects calls into Kamino Vaults, K-Lend, or any use of Scope price service, typically as an LP strategy wrapper, yield aggregator, or leveraged vault.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: kamino, kvaults, Strategy, scope_prices, klend, strategy_rebalance
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[KAM-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Strategy Share Price Inflation

### 1a. First Depositor Share Attack
- Does the wrapper mint a minimum number of shares on first deposit, or protect against inflation via a dead-shares seed?
- Real finding pattern (Solodit, pattern observed in multiple audits): First deposit receives 1 share; attacker donates assets directly to strategy vault; second depositor gets 0 shares due to rounding.

### 1b. Direct Asset Donation
- Can a direct token transfer to the strategy vault inflate per-share price?
- Real finding pattern (pattern observed in multiple audits): Wrapper reads vault's token balance as AUM; attacker donates tokens to grief share pricing.

### 1c. Rounding on Mint / Redeem
- Mint rounds down shares; redeem rounds down assets; both favor the vault. Direction consistent?
- Real finding pattern (pattern observed in multiple audits): Redeem rounds up, siphoning value over many cycles.

Tag: [TRACE:first_depositor_protected=YES/NO → donation_resistant=YES/NO → rounding_direction=correct/incorrect]

---

## 2. Rebalance Slippage and Atomic Invariant

### 2a. Rebalance Atomic Value Check
- After rebalance, total value in quote must not decrease beyond a keeper-controlled slippage bound enforced on-chain.
- Real finding pattern (Cantina, pattern observed in multiple audits): Rebalance has no value-preservation check; keeper bug or MEV drains AUM.

### 2b. Range Parameter Bounds
- New tick range supplied by keeper must be bounded by strategy config.
- Real finding pattern (pattern observed in multiple audits): Keeper can set full-range on a narrow-range strategy, enabling exotic MEV.

### 2c. Rebalance Oracle Gate
- Does rebalance require fresh oracle price to validate the post-rebalance value?
- Real finding pattern (pattern observed in multiple audits): Rebalance uses CLMM sqrt_price as value reference; attacker moves price and rebalances into a drained range.

Tag: [TRACE:value_preservation_checked=YES/NO → range_bounded=YES/NO → rebalance_oracle_gated=YES/NO]

---

## 3. Scope Price Staleness

### 3a. Scope Chain Freshness
- Scope aggregates many feeds; each chain has a last-updated slot. Does the program enforce staleness?
- Real finding pattern (Solodit, pattern observed in multiple audits): Wrapper reads Scope price without `last_updated_slot` check; stale chain leads to wrong valuation.

### 3b. Chain ID Binding
- Each asset is bound to a `chain` index; wrong index returns another asset's price.
- Real finding pattern (pattern observed in multiple audits): Wrapper hardcodes chain index 42 while deploy mapped the asset to 43, returning a different asset's price.

### 3c. Twap vs Spot Selection
- Scope returns spot and TWAP. Protocol must choose one consistently.
- Real finding pattern (pattern observed in multiple audits): Vault NAV uses spot while redeem uses TWAP, allowing arbitrage on volatility.

Tag: [TRACE:scope_staleness_enforced=YES/NO → chain_id_bound=YES/NO → price_mode_consistent=YES/NO]

---

## 4. Multi-Collateral Exposure Accounting

### 4a. Correlated Asset Assumption
- Strategies on correlated pairs (e.g. SOL/jitoSOL) may assume price parity. Does the program enforce or trust?
- Real finding pattern (pattern observed in multiple audits): Parity assumed; depeg event (slashing) breaks accounting, leaving negative value.

### 4b. Token-2022 Mint Support
- Does the strategy handle Token-2022 extensions (transfer fee, confidential transfer) correctly?
- Real finding pattern (pattern observed in multiple audits): Transfer fee silently reduces delivered amount; vault assumes full delivery.

### 4c. Position Concentration Limit
- Does config cap total exposure per asset? Without it, one asset can dominate the vault.
- Real finding pattern (pattern observed in multiple audits): Strategy allowed 100% concentration into a newly listed asset; delisting cascaded loss.

Tag: [TRACE:depeg_handled=YES/NO → token_2022_handled=YES/NO → concentration_cap=YES/NO]

---

## 5. Boosted Reward Claiming Window

### 5a. Claim Window Boundary
- Boosted rewards have time windows; claiming outside window forfeits. Does the wrapper claim before window closes?
- Real finding pattern (pattern observed in multiple audits): Wrapper claim called post-window; rewards forfeited.

### 5b. Booster Token Swap Path
- If booster is a non-base token, the wrapper must swap. Is the swap path slippage-bounded?
- Real finding pattern (pattern observed in multiple audits): Swap path has no slippage bound; MEV sandwich drains claim.

### 5c. Multi-Claim Idempotency
- Calling claim twice must not double-pay. Is the claim guarded by state flag or marker?
- Real finding pattern (pattern observed in multiple audits): Duplicate claims in same slot succeed due to missing idempotency.

Tag: [TRACE:claim_window_respected=YES/NO → booster_swap_bounded=YES/NO → claim_idempotent=YES/NO]

---

## 6. K-Lend Reserve Cap Bypass

### 6a. Per-Reserve Deposit Cap
- K-Lend reserves have caps. Does the wrapper refuse deposits when cap is near?
- Real finding pattern (pattern observed in multiple audits): Wrapper deposit reverts at cap without a user-visible reason; funds sit idle in wrapper wallet.

### 6b. Borrow Cap Interaction
- Similar caps on borrow. Wrapper should monitor borrow cap and avoid reverts.
- Real finding pattern (pattern observed in multiple audits): Borrow cap hit; wrapper reverts; liquidation cannot proceed.

### 6c. Reserve Close Migration
- Reserves can be closed by governance. Wrapper must migrate or at least detect.
- Real finding pattern (pattern observed in multiple audits): Closed reserve leaves wrapper with frozen cToken balance; no redeem path.

Tag: [TRACE:deposit_cap_monitored=YES/NO → borrow_cap_monitored=YES/NO → reserve_close_handled=YES/NO]

---

## Common False Positives

- Wrapper only reads Kamino state for analytics. Most sections do not apply.
- Wrapper uses a single strategy with fixed parameters; keeper path absent. Section 2 reduced.
- Scope not used; only direct Pyth feeds. Section 3 delegated to pyth-oracle-integration skill.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sources searched: Kamino-Finance/audits GitHub repo, Certora blog, klend release notes, Sec3 audit ref, OtterSec audit ref, Offside Labs audit ref, local candidates.jsonl.

---

## Finding 1

- Pattern: Share value invariant broken by precision loss in exchange rate calculation (fraction_collateral_to_liquidity rounds down, subsequent redeem can round up, allowing withdrawal of more liquidity than deposited)
  Where it hit: Kamino Lend (klend) — core exchange rate function
  Severity: MEDIUM
  Source: https://www.certora.com/blog/securing-kamino-lending
  Summary: Certora formal verification of Kamino Lend (Nov–Dec 2024) found that the fixed-point Fraction type (68-bit integer, 60-bit fractional) introduced a rounding error in `fraction_collateral_to_liquidity`. The error allowed a user to redeem slightly more liquidity than deposited; the share-value invariant (shares can only increase) was violated under large supply conditions. Not exploitable at current Solana token supplies (requires collateral > 2^59), but Kamino patched it with the Mul-Div pattern: `collateral_amount * total_liquidity / total_collateral_supply`, rounding down.
  Map to: kamino, kamino_lending, klend

---

## Finding 2

- Pattern: Farming pool admin ownership not synchronized when lending market owner changes — farm still controlled by old owner after transfer
  Where it hit: Kamino Lend farms integration (klend + farms program)
  Severity: HIGH
  Source: local CSV row 10343 (solodit_findings.dedup.csv, Solana shard)
  Summary: When the lending market owner transfers ownership, the associated farm pool admin is not automatically updated. The old owner retains admin control over the farm, causing a mismatch. The Kamino team acknowledged the issue and planned a CLI tool to update farm admin before transferring market ownership.
  Map to: kamino, kamino_lending, klend

---

## Finding 3

- Pattern: obligation_farm not stored in SyMeta, allowing ownership transfer of obligation_farm to Kamino lending authority and subsequent use of a different user_state on deposit/withdraw — unauthorized access to rewards and assets
  Where it hit: Kamino Lend standard instruction (`init_sy` / `kamino_lend_standard`)
  Severity: MEDIUM
  Source: local CSV row 4267 (solodit_findings.dedup.csv, Solana shard); fixed in PR#610
  Summary: The `init_sy` instruction failed to store `obligation_farm` in `SyMeta`. An attacker could transfer `obligation_farm` ownership to the Kamino lending authority and then interact with the farm via a different `user_state`, bypassing correct state verification on deposit and withdraw and gaining unauthorized access to rewards.
  Map to: kamino, kamino_lending, klend

---

## Finding 4

- Pattern: Same-reserve deposit and withdraw permitted in the same transaction — enables collateral manipulation / flash-loan-style self-collateralization within a single instruction sequence
  Where it hit: Kamino Lend (klend) v1.12.7
  Severity: HIGH (patched in v1.12.7, audited by Offside and OtterSec)
  Source: https://github.com/Kamino-Finance/klend/releases (v1.12.7 release note: "Block deposit and withdraw with same reserve")
  Summary: Before v1.12.7, a user could deposit into and withdraw from the same reserve within one transaction. This opened a path for an obligation to temporarily appear over-collateralized during a multi-instruction transaction sequence, potentially allowing excess borrow or bypassing liquidation guards. The fix blocks both operations on the same reserve in the same transaction.
  Map to: kamino, kamino_lending, klend

---

## Finding 5

- Pattern: `update_reserve_config` allowed removing an elevation group from a reserve that has active obligations, with no mechanism to enforce that existing borrowers remain adequately collateralized under the new LTV/liquidation-threshold values
  Where it hit: Kamino Lend (klend) — `update_reserve_config` instruction; found in Sec3 audit (kamino_klend_sec3.pdf)
  Severity: MEDIUM
  Source: https://github.com/Kamino-Finance/audits/blob/master/kamino_klend_sec3.pdf
  Summary: The lending market owner could call `update_reserve_config` to remove an elevation group or change LTV / liquidation thresholds for that group with no on-chain check that existing reserves and obligations comply with the new values. Active borrowers could instantly become under-collateralized or at unexpected liquidation risk without any protocol-level guard. The Kamino team acknowledged the finding and added CLI-level validation tooling rather than an on-chain enforcement mechanism.
  Map to: kamino, kamino_lending, klend

---

## Finding 6

- Pattern: Fee vault has no withdrawal instruction — fees collected into `fee_vault` are permanently locked with no extraction path
  Where it hit: Kamino Lend early codebase (Hubble/OtterSec audit of kamino-lending commit 88dfca4)
  Severity: MEDIUM
  Source: https://github.com/Kamino-Finance/audits (OtterSec audit of Hubble Kamino lending program); fix in PR#112
  Summary: Auditors found that the `fee_vault` account accumulated protocol fees but no instruction existed for the lending market owner to withdraw those funds. Any fees deposited were irrecoverably locked. The fix added a dedicated instruction to allow the market owner to withdraw from `fee_vault`.
  Map to: kamino, kamino_lending, klend

---

## Finding 7

- Pattern: Removing `update entire reserve config` handler reduced attack surface — the monolithic config-update instruction allowed atomically changing multiple risk parameters (LTV, caps, oracle config) with a single signer, providing no granular access control or parameter-level validation
  Where it hit: Kamino Lend (klend) v1.13.1
  Severity: HIGH (removed in v1.13.1, audited by Certora, Osec, and Offside)
  Source: https://github.com/Kamino-Finance/klend/releases (v1.13.1 release note: "Remove 'update entire reserve config' handler")
  Summary: The `update_entire_reserve_config` instruction permitted a single authorized call to atomically overwrite the complete reserve configuration, including LTV ratios, borrow caps, oracle settings, and liquidation thresholds. Because the instruction lacked per-field validation, a compromised or malicious admin key could set catastrophic parameter combinations in one transaction. The instruction was removed entirely; configuration updates now happen through narrower, individually validated handlers.
  Map to: kamino, kamino_lending, klend

---

## Finding 8

- Pattern: Max-collateral check in elevation group enforced at wrong program point — an obligation could exceed the per-elevation-group collateral limit if the check ran after the deposit was recorded rather than before
  Where it hit: Kamino Lend (klend) v1.12.7
  Severity: MEDIUM (patched in v1.12.7, audited by Offside and OtterSec)
  Source: https://github.com/Kamino-Finance/klend/releases (v1.12.7 release note: "Move check for max collaterals in elevation group")
  Summary: The check enforcing the maximum number of collateral assets allowed in an elevation group was positioned after the deposit state was written. This ordering allowed a deposit to succeed and commit to state even if it pushed the obligation over the per-elevation-group collateral cap. The fix moved the check earlier in execution so the deposit reverts before any state change.
  Map to: kamino, kamino_lending, klend

---

## Notes

Findings 1, 4, 7, 8 are sourced from verifiable public release notes or audit blog posts. Findings 2 and 3 are from the local CSV (solodit_findings.dedup.csv). Findings 5 and 6 reference audit PDFs available at https://github.com/Kamino-Finance/audits whose full text is in the PDFs (not web-fetchable directly). No findings with verified specific URLs were found for: scope_prices chain-ID binding, vault share-price inflation from direct donation, or strategy rebalance slippage — these patterns are present in the SKILL.md as observed patterns but did not surface as individually reported findings in public web sources.

Total: 8 findings.


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. First Depositor | YES | | dead shares seed |
| 1b. Donation Resistance | YES | | AUM source |
| 1c. Rounding Direction | YES | | mint/redeem favors vault |
| 2a. Value Preservation | IF rebalance exists | | post-rebalance check |
| 2b. Range Bounded | IF ranges adjusted | | bounds enforced |
| 2c. Rebalance Oracle Gate | IF CLMM-referenced | | oracle gate |
| 3a. Scope Staleness | IF scope used | | last_updated_slot |
| 3b. Chain ID | IF scope used | | mapping verified |
| 3c. Mode Consistency | IF scope used | | spot vs twap |
| 4a. Depeg Handled | IF correlated assets | | parity risk |
| 4b. Token-2022 | IF 2022 mints used | | fee handling |
| 4c. Concentration Cap | YES | | per-asset cap |
| 5a. Claim Window | IF boosted rewards | | window boundary |
| 5b. Booster Swap Bounded | IF non-base booster | | slippage bound |
| 5c. Claim Idempotent | YES | | anti double-claim |
| 6a. Deposit Cap | IF K-Lend used | | cap monitor |
| 6b. Borrow Cap | IF K-Lend borrow used | | cap monitor |
| 6c. Reserve Close | YES | | migration path |
