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
