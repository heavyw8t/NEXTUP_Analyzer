---
name: "drift-perps-integration"
description: "Protocol Type Trigger drift_perps_integration (detected when recon finds drift_program|PerpMarket|SpotMarket|UserStats|funding_rate|amm|insurance_fund|Order|OrderParams - protocol USES Drift perps)"
---

# Injectable Skill: Drift Perps Integration Security

> Protocol Type Trigger: `drift_perps_integration` (detected when recon finds: `drift_program`, `PerpMarket`, `SpotMarket`, `UserStats`, `funding_rate`, `amm`, `insurance_fund`, `Order`, `OrderParams`)
> Inject Into: depth-token-flow, depth-edge-case, depth-external
> Language: Solana only
> Finding prefix: `[DRF-N]`
> Relationship to pyth-oracle-integration: Drift uses Pyth pull oracles. Activate that skill together.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-edge-case (mark vs oracle vs TWAP in PnL)
- Section 2: depth-edge-case (funding rate sign and accrual)
- Section 3: depth-edge-case (liquidation trigger ordering)
- Section 4: depth-token-flow (insurance fund, socialized loss)
- Section 5: depth-edge-case (cross vs isolated margin)
- Section 6: depth-external (JIT auction, taker-maker fees)

## When This Skill Activates

Recon detects CPI into Drift Protocol v2 for placing orders, opening perps positions, or reading market state, common in vaults or structured products that trade perps on behalf of users.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: drift, PerpMarket, SpotMarket, funding_rate, amm, insurance_fund
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[DRF-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Mark vs Oracle vs TWAP in PnL

### 1a. Unrealized PnL Reference
- Drift supports `mark`, `oracle`, and `oracle_twap` for unrealized PnL. Does the protocol choose the correct reference and apply consistently?
- Real finding pattern (Solodit, pattern observed in multiple audits): Wrapper uses `mark` for PnL accrual but `oracle` for margin, letting short-term AMM deviations become realized gains.

### 1b. Oracle Guard Rails
- Drift enforces guard rails between mark and oracle; if triggered, some operations are blocked. Does the wrapper handle the resulting revert?
- Real finding pattern (pattern observed in multiple audits): Wrapper's close-position reverts on guard-rail trip; user funds locked until rails clear.

### 1c. TWAP Window Assumption
- Drift TWAP window is per-market config. Does the wrapper assume a specific window?
- Real finding pattern (pattern observed in multiple audits): Wrapper hardcodes 5-minute TWAP; market config is 1-hour; PnL compounding wrong.

Tag: [TRACE:pnl_reference_consistent=YES/NO → guard_rails_handled=YES/NO → twap_window_dynamic=YES/NO]

---

## 2. Funding Rate Sign and Accrual

### 2a. Sign of Funding Payment
- Longs pay when funding_rate > 0. Does the wrapper account for the sign correctly in its user-level PnL?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Wrapper flips sign; longs appear to be paid by shorts when funding is positive.

### 2b. Funding Rate Snapshot
- Does the wrapper settle funding before computing user-level balances?
- Real finding pattern (pattern observed in multiple audits): Wrapper distributes yield without settling funding; accumulated funding stays with Drift, leaking to next caller.

### 2c. 24h Funding Cap
- Drift caps funding per 24h. Does the wrapper rely on an uncapped linearly-extrapolated rate?
- Real finding pattern (pattern observed in multiple audits): Wrapper extrapolates current rate across 7 days; stale extrapolation misleads users.

Tag: [TRACE:funding_sign_correct=YES/NO → funding_settled_before_distribution=YES/NO → funding_cap_respected=YES/NO]

---

## 3. Liquidation Trigger Ordering

### 3a. Liquidation Priority
- Drift liquidates in a specific order (perp position, spot borrow, etc). Does the wrapper understand the order when exposing liquidation to keepers?
- Real finding pattern (pattern observed in multiple audits): Wrapper liquidates spot borrow first without covering perp; health worsens; cascade.

### 3b. Liquidation Fee Direction
- Liquidation fees flow to the liquidator and insurance fund in a ratio. Wrapper integration must not retain fees that belong to Drift.
- Real finding pattern (pattern observed in multiple audits): Wrapper sweeps liquidation reward into its own treasury and fails to forward to insurance fund.

### 3c. Liquidation With Pending Orders
- Pending orders on a liquidated user can auto-cancel. Does the wrapper handle leftover order state?
- Real finding pattern (pattern observed in multiple audits): Wrapper tracks open orders; Drift cancels; wrapper's mirror state diverges.

Tag: [TRACE:liquidation_order_known=YES/NO → fee_forwarded_to_if=YES/NO → order_cancellation_mirrored=YES/NO]

---

## 4. Insurance Fund Cover / Socialized Loss

### 4a. Socialized Loss Event
- If IF depletes, loss is socialized across perp-market LPs or depositors. Does the wrapper propagate?
- Real finding pattern (pattern observed in multiple audits): Wrapper NAV ignores pending socialized loss; redeemers get full value while remaining users eat more loss.

### 4b. IF Staking Lock
- IF staking positions have unstake delays. Does wrapper model the unbond period?
- Real finding pattern (pattern observed in multiple audits): Wrapper claims IF stake is instantly liquid; redemption flow fails.

### 4c. Cumulative Social Loss
- Cumulative loss share persists across reopens. Does the wrapper read correctly?
- Real finding pattern (pattern observed in multiple audits): Wrapper subtracts loss twice; user PnL negative when it should be zero.

Tag: [TRACE:socialized_loss_propagated=YES/NO → unbond_modeled=YES/NO → cumulative_loss_correct=YES/NO]

---

## 5. Cross vs Isolated Margin

### 5a. Margin Mode Classification
- Drift supports isolated per-market margin via sub-accounts. Does the wrapper classify correctly?
- Real finding pattern (pattern observed in multiple audits): Wrapper uses cross-margin while marketing as isolated; single market blowup drains other positions.

### 5b. Sub-Account Allocation
- Are sub-accounts derived from unique PDA seeds per user? Shared sub-accounts create fungibility issues.
- Real finding pattern (pattern observed in multiple audits): Sub-account PDA seeded by mint only; all users share one account.

### 5c. Position Limit Per Sub-Account
- Drift enforces max positions per sub-account. Does the wrapper track to avoid reverts?
- Real finding pattern (pattern observed in multiple audits): Wrapper places new position; Drift reverts because cap hit; tx fails without clear UX path.

Tag: [TRACE:margin_mode_correct=YES/NO → sub_account_unique=YES/NO → position_cap_respected=YES/NO]

---

## 6. JIT Auction / Taker-Maker Fees

### 6a. JIT Auction Assumption
- Drift JIT auction lets makers fill taker orders at oracle-adjusted price. Does the wrapper assume fill price or handle partial fills?
- Real finding pattern (pattern observed in multiple audits): Wrapper assumes full fill at auction start price; partial fills at worse prices trigger margin breach.

### 6b. Taker vs Maker Fee Routing
- Taker and maker fees differ; wrapper must not double-count or mis-route.
- Real finding pattern (pattern observed in multiple audits): Wrapper includes taker fee in user PnL then also charges it at withdraw.

### 6c. Protocol Fee Recipient Change
- Drift governance can rotate the protocol-fee recipient. Does the wrapper pin a specific recipient or accept whichever?
- Real finding pattern (pattern observed in multiple audits): Wrapper auto-trusts the configured recipient; governance sets a malicious recipient in testnet rehearsal.

Tag: [TRACE:jit_partial_handled=YES/NO → fee_routing_correct=YES/NO → fee_recipient_pinned=YES/NO]

---

## Common False Positives

- Wrapper only reads Drift state for analytics, no CPI. Most sections do not apply.
- Wrapper uses a single fixed market (e.g. SOL-PERP). Sections 3c and 5c reduced.
- IF staking not used. Section 4b does not apply.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. PnL Reference Consistency | YES | | mark/oracle/twap |
| 1b. Guard Rails | YES | | revert handling |
| 1c. TWAP Window | IF wrapper models PnL | | dynamic read |
| 2a. Funding Sign | YES | | sign correctness |
| 2b. Funding Settle | YES | | settle before distribute |
| 2c. Funding Cap | YES | | 24h cap respected |
| 3a. Liquidation Order | IF wrapper owns liquidatable positions | | priority |
| 3b. IF Fee Forwarded | YES | | fee routing |
| 3c. Order Cancellation Mirror | IF wrapper tracks orders | | state sync |
| 4a. Social Loss Propagation | YES | | NAV honest |
| 4b. Unbond Modeled | IF IF stake used | | lockup |
| 4c. Cumulative Loss | YES | | no double counting |
| 5a. Margin Mode Correct | YES | | cross vs isolated |
| 5b. Sub-Account Unique | YES | | per-user PDA |
| 5c. Position Cap | YES | | avoid reverts |
| 6a. JIT Partial Handling | IF JIT used | | partial fill math |
| 6b. Fee Routing | YES | | taker/maker accounting |
| 6c. Fee Recipient Pinned | YES | | governance risk |
