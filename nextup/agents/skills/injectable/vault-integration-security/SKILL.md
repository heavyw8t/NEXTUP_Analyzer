---
name: "vault-integration-security"
description: "Protocol Type Trigger vault_integration (detected when recon finds ERC4626|IERC4626|deposit|withdraw|convertToAssets|convertToShares|previewRedeem|previewDeposit|maxDeposit|vault AND the protocol CALLS external vaults, not implements them)"
---

# Injectable Skill: Vault Integration Security

> **Protocol Type Trigger**: `vault_integration` (detected when recon finds: `ERC4626`, `IERC4626`, `deposit`, `withdraw`, `convertToAssets`, `convertToShares`, `previewRedeem`, `previewDeposit`, `previewWithdraw`, `maxDeposit`, `maxWithdraw`, `vault` - AND the protocol CALLS external vaults, not implements them)
> **Inject Into**: Breadth agents, depth-external, depth-token-flow, depth-edge-case
> **Language**: Primarily EVM; applicable to any protocol integrating with share-based vaults
> **Finding prefix**: `[VI-N]`
> **Relationship to VAULT_ACCOUNTING**: That skill covers vault internals. This skill covers the CALLER's integration with external vaults: conversion function misuse, withdrawal ordering, cap handling, reward claiming, idle asset yield dilution.
> **Relationship to VAULT_SECURITY**: That skill covers building a vault. This skill covers using one.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Sections 1, 1b: depth-external + depth-token-flow (conversion function accuracy, fee accounting)
- Section 2: depth-edge-case + depth-token-flow (withdrawal ordering, yield optimization)
- Section 3: depth-external (reward token handling from underlying vaults)
- Sections 4, 4b: depth-edge-case (vault cap handling, idle asset yield dilution)
- Section 5: depth-external + depth-state-trace (vault migration, share price staleness)

## When This Skill Activates

Recon detects that the protocol USES external vaults (ERC4626 or custom vault interfaces) as yield sources, collateral, or building blocks. The protocol deposits into, withdraws from, or reads prices from external vault contracts. This skill analyzes the integration, not the vault internals.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `vault_deposit`, `vault_withdraw`, `redeem`, `maxWithdraw`, `maxRedeem`, `ERC4626`, `IERC4626`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[VI-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Conversion Function Misuse — convertToAssets vs previewWithdraw

The most common vault integration bug. `convertToAssets()` and `convertToShares()` are informational functions that do NOT account for withdrawal fees, deposit fees, swap slippage, or any vault-specific deductions. They return the theoretical value, not the actual claimable amount.

### 1a. Overestimated Position Value

1. Identify every call to `convertToAssets(shares)` or `convertToShares(assets)` in the protocol.
2. For EACH call: is the result used to determine:
   - The protocol's actual claimable assets? (BUG if vault has withdrawal fees)
   - Collateral value for lending/borrowing? (BUG: overvalued collateral → under-collateralized loans)
   - NAV calculation for the protocol's own shares? (BUG: inflated NAV)
   - Rebalancing decisions? (BUG: rebalancing assumes more assets than actually available)
3. The ERC4626 spec explicitly states: `convertToAssets` "MUST NOT be inclusive of any fees that are charged against assets in the Vault."
4. Check: does the external vault actually charge fees? Read the vault's `withdraw()` and `redeem()` for fee deductions, or check if `previewWithdraw(assets) != convertToShares(assets)`.

Tag: `[TRACE:convertToAssets_call={location} → used_for={valuation/collateral/nav/rebalance} → vault_has_fees={YES/NO} → overestimation={amount_or_percentage}]`

### 1b. Correct Functions

The correct functions for actual claimable values are:
- **previewWithdraw(assets)**: Returns exact shares that would be burned for a given asset withdrawal. Accounts for fees.
- **previewRedeem(shares)**: Returns exact assets that would be received for burning given shares. Accounts for fees.
- **previewDeposit(assets)**: Returns exact shares that would be minted for a given deposit. Accounts for fees.
- **previewMint(shares)**: Returns exact assets required to mint given shares. Accounts for fees.

Check: does the protocol use the `preview*` functions where it needs actual amounts, and `convertTo*` only for informational/display purposes?

Exception: if the external vault has zero fees (verified by reading the vault contract), `convertTo*` and `preview*` return the same values. But this is fragile — if the vault adds fees later, the integration silently breaks.

Tag: `[TRACE:preview_functions_used={YES/NO} → convertTo_used_for_actual_amounts={YES/NO/locations}]`

---

## 2. Withdrawal Ordering — FIFO vs FILO

If the protocol deposits into multiple external vaults (yield aggregator, index fund, strategy allocator), the order in which it withdraws from vaults directly impacts yield.

### 2a. Withdrawal Priority

1. Identify: does the protocol deposit to multiple external vaults/strategies?
2. If YES: what order does it withdraw from them? Check for:
   - **FIFO** (First In, First Out): withdraws from the first vault in the array/queue first. If vaults are sorted by APY (highest first), this always drains the highest-yield vault first — killing total yield.
   - **FILO** (First In, Last Out): withdraws from the last vault added. If sorted by APY ascending, this correctly drains the lowest-yield vault first.
   - **Custom ordering**: withdraws from a specific vault based on some criteria.
3. Trace the withdrawal path: which vault's assets decrease first?
4. Compute yield impact with concrete numbers:
   - Current allocation: Vault1 (15% APY, 100k), Vault2 (10% APY, 100k), Vault3 (5% APY, 50k)
   - Withdrawal of 50k via FIFO (drains Vault1): new yield = 15%×50k + 10%×100k + 5%×50k = 20k
   - Withdrawal of 50k via FILO (drains Vault3): new yield = 15%×100k + 10%×100k + 5%×0 = 25k
   - Yield loss from FIFO: 25% less yield in this example.

Tag: `[TRACE:multi_vault={YES/NO} → vault_count={N} → withdrawal_order={FIFO/FILO/custom} → yield_impact={computed_difference}]`

### 2b. Deposit Ordering

1. Same analysis for deposits: does the protocol fill the highest-APY vault first?
2. If vaults have caps: does the protocol correctly fill to the cap and overflow to the next vault?
3. What happens if the sorting/ordering of vaults is stale (APY changed since last reorder)?

### 2c. Dynamic Rebalancing

1. Does the protocol rebalance between vaults periodically?
2. If YES: does rebalancing account for withdrawal fees, gas costs, and deposit fees?
3. Can rebalancing be triggered by anyone, or only by a keeper? If anyone: can an attacker trigger unprofitable rebalances to grief the protocol?

Tag: `[TRACE:deposit_order={highest_apy_first/arbitrary} → rebalance={YES/NO} → rebalance_trigger={keeper/anyone} → fee_aware={YES/NO}]`

---

## 3. Reward Token Handling from External Vaults

External vaults may distribute incentive tokens beyond yield (share price appreciation).

### 3a. Unclaimed Rewards

1. List ALL external vaults the protocol deposits into.
2. For EACH vault: does it emit reward tokens? (e.g., Morpho rewards, Aave incentives, Convex CRV+CVX, Curve CRV)
3. Does the protocol claim these rewards? Look for `claim()`, `getReward()`, `claimRewards()`, `harvest()`.
4. If NOT claimed: rewards accumulate in the external vault/protocol, attributed to the protocol's address but never collected. These are stuck forever unless a claim mechanism is added.
5. Quantify: what is the estimated value of unclaimed rewards? (Even a rough estimate helps severity assessment.)

Tag: `[TRACE:external_vaults={list} → reward_tokens={per_vault} → claimed={YES/NO per vault} → stuck_value={estimate}]`

### 3b. Reward Token Routing

1. When rewards ARE claimed: where do the reward tokens go?
   - To the protocol contract? → Are they then distributed to the protocol's depositors?
   - To a treasury/fee recipient? → Is this documented/disclosed to users?
   - To nowhere (stuck in the vault contract)? → Bug.
2. If reward tokens are the same as the deposit token: do they get accounted in the protocol's `totalAssets`? If not: protocol's share price is understated (depositors get less than their fair value).
3. If reward tokens are different: is there a swap mechanism to convert them to the deposit token?

### 3c. Reward Token Changes

1. External protocols can add, remove, or rotate incentive tokens without notice.
2. Does the protocol hardcode reward token addresses?
3. If the external protocol adds a new reward token: will the protocol's claim function miss it?
4. Recommendation: use a configurable reward token list, or query the external protocol for current reward tokens.

Tag: `[TRACE:reward_routing={contract/treasury/stuck} → same_as_deposit_token={YES/NO} → accounted_in_totalAssets={YES/NO} → hardcoded_tokens={YES/NO}]`

---

## 4. Vault Cap Handling and Idle Assets

External vaults may have maximum deposit caps. Failing to handle these correctly causes reverts, idle assets, or yield dilution.

### 4a. Deposit Revert on Full Vault

1. Does the protocol check `maxDeposit(address)` on the external vault before depositing?
2. If NOT checked: deposit TX reverts when the vault is full. This may block the entire protocol's deposit flow.
3. Even if checked: does the protocol handle the case where `maxDeposit` returns 0 (vault completely full)? Or a value less than the user's deposit amount?
4. Trace: user deposits 8000 assets → protocol tries to deposit to external vault with 5000 space → what happens?
   - Reverts? (Bad UX, blocks user)
   - Deposits 5000, returns/holds 3000? (Better, but where do the 3000 go?)

Tag: `[TRACE:maxDeposit_checked={YES/NO} → full_vault_handling={revert/partial/overflow_to_next} → user_impact={blocked/partial_deposit}]`

### 4b. Idle Asset Yield Dilution

The critical bug that many developers miss even after fixing the revert:

1. If the protocol deposits the maximum into a full vault and holds the remainder: the excess assets are IDLE (earning no yield).
2. But these idle assets are still counted in the protocol's `totalAssets`, diluting yield for ALL depositors.
3. Compute yield dilution:
   - Protocol has 120k total assets
   - 50k in Vault1 (15% APY), 50k in Vault2 (5% APY), 20k idle (0% APY)
   - Effective APY: (50k×15% + 50k×5% + 20k×0%) / 120k = 8.3%
   - Without idle: (50k×15% + 50k×5%) / 100k = 10%
   - Yield dilution: 17% less yield
4. Check: after all external vaults are at capacity, does the protocol:
   - Prevent further deposits? (CORRECT — users don't deposit into a yield-diluted pool)
   - Accept deposits anyway? (BUG — new deposits earn no yield but dilute existing depositors)
   - Queue deposits for when space opens? (ACCEPTABLE if communicated)

Tag: `[TRACE:idle_assets_possible={YES/NO} → idle_counted_in_totalAssets={YES/NO} → deposits_blocked_when_full={YES/NO} → yield_dilution={computed_percentage}]`

### 4c. Dynamic Cap Changes

1. External vault caps can change (governance increases/decreases cap).
2. If cap decreases below the protocol's current deposit: can the protocol withdraw the excess? Is it forced to?
3. If cap increases: does the protocol automatically deposit idle assets? Or do they remain idle until manually rebalanced?

Tag: `[TRACE:cap_decrease_handling={auto_withdraw/manual/stuck} → cap_increase_handling={auto_deposit/manual/idle}]`

---

## 5. Vault Migration and Share Price Staleness

### 5a. Vault Upgrades and Migration

1. If the external vault is upgradeable or migratable: does the protocol handle vault address changes?
2. If the protocol hardcodes a vault address: a vault migration leaves the protocol pointing to a deprecated vault.
3. Does the protocol have an admin function to update vault addresses? If YES: are stale approvals to the old vault revoked?

### 5b. Share Price Staleness

1. Does the protocol cache or snapshot the vault's share price?
2. If YES: how often is the cache refreshed? Can the cached price diverge significantly from the actual price?
3. If the protocol reads share price for critical operations (liquidation, rebalancing, collateral valuation): is the read fresh (same block) or potentially stale?
4. For vaults with non-trivial `totalAssets()` computations (e.g., strategy vaults that need to harvest before reporting accurate NAV): does the protocol trigger a harvest/report before reading the share price?

Tag: `[TRACE:vault_address={hardcoded/configurable} → share_price_cached={YES/NO} → cache_staleness={max_duration} → harvest_before_read={YES/NO}]`

### 5c. Vault Pause and Emergency States

1. Can the external vault be paused? Does the protocol handle a paused vault gracefully?
2. If the vault is paused and the protocol tries to withdraw: does the revert propagate and brick the protocol?
3. Does the protocol have a fallback/emergency path for when an external vault is unavailable?

Tag: `[TRACE:vault_pausable={YES/NO} → pause_handling={graceful/propagates_revert} → fallback_path={YES/NO}]`

---

## Common False Positives

- **convertToAssets on zero-fee vault with immutable fee config**: If the external vault provably has 0 fees AND the fee configuration is immutable (not upgradeable), `convertToAssets` == `previewRedeem`. Still fragile but not currently exploitable.
- **Single-vault protocol**: Withdrawal ordering (section 2) doesn't apply when there's only one external vault.
- **Reward tokens with zero emissions**: If the external protocol's reward rate is 0 or the reward program has ended, unclaimed rewards are a non-issue.
- **Idle assets below gas cost threshold**: If idle assets earn less yield than the gas cost to deposit them, keeping them idle is rational behavior, not a bug.
- **Protocol designed as pass-through**: If the protocol explicitly presents itself as a non-yield-optimizing wrapper (e.g., access control layer over a vault), yield dilution from idle assets may be by design.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. convertToAssets Overestimation | YES | | Every call site, fee awareness |
| 1b. Correct Function Usage | YES | | preview* vs convertTo* |
| 2a. Withdrawal Priority | IF multi-vault | | FIFO/FILO, yield impact |
| 2b. Deposit Ordering | IF multi-vault | | APY-sorted, cap-aware |
| 2c. Dynamic Rebalancing | IF rebalancing exists | | Fee-aware, trigger access |
| 3a. Unclaimed Rewards | YES | | All external vaults checked |
| 3b. Reward Token Routing | IF rewards claimed | | Distribution, accounting |
| 3c. Reward Token Changes | IF rewards exist | | Hardcoded vs configurable |
| 4a. Deposit Revert on Full Vault | YES | | maxDeposit check, partial handling |
| 4b. Idle Asset Yield Dilution | YES | | Dilution computation, deposit blocking |
| 4c. Dynamic Cap Changes | IF external caps exist | | Decrease/increase handling |
| 5a. Vault Migration | IF vault address configurable | | Stale approvals |
| 5b. Share Price Staleness | IF price cached/read | | Freshness, harvest trigger |
| 5c. Vault Pause Handling | IF external vault pausable | | Graceful degradation |
