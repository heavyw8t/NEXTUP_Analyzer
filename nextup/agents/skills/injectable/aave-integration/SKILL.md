---
name: "aave-integration"
description: "Protocol Type Trigger aave_integration (detected when recon finds IPool|IPoolAddressesProvider|IAToken|IVariableDebtToken|aToken|DataTypes.ReserveData|supply|borrow|flashLoan - protocol USES Aave as yield/lending layer)"
---

# Injectable Skill: Aave Integration Security

> **Protocol Type Trigger**: `aave_integration` (detected when recon finds: `IPool`, `IPoolAddressesProvider`, `IAToken`, `IVariableDebtToken`, `IStableDebtToken`, `aToken`, `DataTypes.ReserveData`, `getReserveData`, `getUserAccountData`, `supply`, `withdraw`, `borrow`, `repay`, `flashLoan`, `flashLoanSimple`, `AAVE`, `ILendingPool` (V2) - AND the protocol calls Aave, not implements it)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case, depth-external
> **Language**: EVM only
> **Finding prefix**: `[AAV-N]`
> **Relationship to LENDING_PROTOCOL_SECURITY**: That skill covers generic lending protocol patterns. This skill covers Aave-specific integration behaviors (aToken rebasing, V2/V3 API differences, e-mode, reserve data staleness). Both may be active.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-token-flow (aToken rebasing, scaled balance, transfer precision)
- Section 2: depth-external + depth-edge-case (reserve data staleness, interest rate assumptions, pool state)
- Section 3: depth-token-flow + depth-state-trace (flash loan callback safety, reentrancy, fee accounting)
- Section 4: depth-edge-case (liquidation assumptions, health factor, e-mode boundaries)
- Section 5: depth-external (pool upgrades, reserve changes, governance actions)

## When This Skill Activates

Recon detects that the protocol integrates with Aave V2 or V3 — deposits into Aave for yield, uses Aave as a collateral layer, takes flash loans from Aave, or builds on top of Aave's lending infrastructure.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `aave`, `aToken`, `scaledBalanceOf`, `IPool`, `getReserveData`, `flashLoan`, `healthFactor`, `liquidityIndex`, `reserveFactor`, `variableBorrowIndex`, `supplyCap`, `emodeCategory`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[AAV-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. aToken Balance Model and Accounting

aTokens are rebasing tokens — their `balanceOf()` increases over time as interest accrues. This is the #1 source of Aave integration bugs.

### 1a. Rebasing Balance Accounting

- Does the protocol track aToken balances using state variables? If yes: the stored value becomes stale immediately as interest accrues.
- Does the protocol compare stored aToken balance against current `balanceOf()`? The difference grows over time.
- **Real finding pattern (Solodit: multiple)**: Protocol deposits into Aave, stores `shares = aToken.balanceOf(this)`. Later, protocol checks `aToken.balanceOf(this) >= shares` — this always passes due to interest, masking actual insolvency from other operations.
- Does the protocol use `scaledBalanceOf()` instead of `balanceOf()`? Scaled balance is stable (doesn't rebase) and is the correct way to track aToken positions internally.
- **Real finding pattern (C4: Sublime #137)**: `AaveYield.lockTokens` recorded `sharesReceived = diff of aToken balance`, which equals the deposited amount at deposit time. `getTokensForShares()` used `aToken.balanceOf(this)` as denominator (grows with interest) but numerator stayed fixed. Users withdrew only principal — all accrued interest silently consumed by the contract.

### 1b. Transfer Precision (1-2 wei rounding)

- aToken transfers can deliver 1-2 wei less than the specified amount due to internal ray-math rounding (same issue as stETH).
- Does the protocol transfer aTokens and then check the received amount? Strict equality checks (`received == expected`) will fail.
- **Real finding pattern**: Protocol does `aToken.transfer(user, amount)` then asserts contract balance decreased by exactly `amount`. Fails intermittently due to 1 wei rounding.

### 1c. Interest Accrual Timing

- Aave accrues interest on each pool interaction (`supply`, `withdraw`, `borrow`, `repay`, `flashLoan`). Between interactions, interest is not yet reflected in on-chain state until `reserve.updateState()` is called.
- If the protocol reads `getReserveData()` and then performs an action: the action triggers `updateState()`, changing rates and indices. The pre-read data is now stale.
- Does the protocol cache `liquidityIndex` or `variableBorrowIndex` and use them later? These indices change on every pool interaction.

Tag: `[TRACE:atoken_tracking={balanceOf/scaledBalanceOf/state_var} → transfer_rounding_handled={YES/NO} → index_caching={YES/NO}]`

---

## 2. Reserve Data and Interest Rate Dependencies

### 2a. Reserve Data Staleness

- `IPool.getReserveData()` returns the reserve state as of the last interaction. If no one has interacted with the reserve recently, the data is stale.
- **Real finding pattern**: Protocol reads `reserve.currentLiquidityRate` to compute expected yield, but the rate hasn't been updated in hours. The actual rate after the protocol's own interaction differs significantly.
- Does the protocol call `getReserveNormalizedIncome()` / `getReserveNormalizedVariableDebt()`? These are also stale until `updateState()`.
- If the protocol makes decisions based on current rates (e.g., "borrow only if rate < X%"): the rate changes when the protocol's transaction executes.

### 2b. Interest Rate Model Assumptions

- Does the protocol assume interest rates are bounded? Aave V3 uses a kinked rate model — rates jump sharply above the optimal utilization ratio.
- **Real finding pattern**: Protocol assumes borrow rate stays below 10% APY. When utilization spikes (e.g., during market volatility), the rate jumps to 100%+ APY. Protocol's economic model breaks.
- Does the protocol account for rate changes due to its OWN actions? A large supply reduces utilization (lower borrow rate). A large borrow increases utilization (higher borrow rate).

### 2c. Supply and Borrow Caps

- Aave V3 introduced supply caps and borrow caps per reserve. Does the protocol handle `supply()` or `borrow()` reverting when caps are hit?
- **Real finding pattern**: Protocol's strategy deposits into Aave. Supply cap is hit by other users. Protocol's deposit reverts, but the protocol doesn't handle this — funds sit idle or the transaction reverts entirely, blocking user operations.
- Does the protocol check available capacity before attempting supply/borrow?

### 2e. Wrong Liquidity Source Query (Pool vs aToken)

- In Aave V3, all supplied liquidity is held in the `aToken` contract, NOT in the `Pool` contract. `underlyingToken.balanceOf(address(pool))` returns 0 on mainnet.
- **Real finding pattern (C4: Size Protocol #218, Critical)**: `validateVariablePoolHasEnoughLiquidity()` checked `underlyingToken.balanceOf(address(variablePool))`. On mainnet V3, this is always 0. Protocol was completely bricked — all buy/sell credit market functions reverted. Tests passed because the mock pool held tokens itself (unlike real Aave).
- Correct query: `address aToken = pool.getReserveData(asset).aTokenAddress; uint256 liquidity = underlyingToken.balanceOf(aToken);`

### 2d. Reserve Factor and Protocol Revenue

- Aave takes a `reserveFactor` percentage of interest as protocol revenue. This reduces the effective yield for suppliers.
- Does the protocol's yield calculation account for the reserve factor?
- Can governance change the reserve factor? If increased, the protocol's expected yield decreases.

Tag: `[TRACE:reserve_data_freshness={per_tx/cached/stale_ok} → rate_bounds_assumed={YES/NO} → cap_handling={check_first/handle_revert/NONE} → reserve_factor_accounted={YES/NO}]`

---

## 3. Flash Loan Integration

### 3a. Flash Loan Callback Safety

- If the protocol takes flash loans from Aave: does the `executeOperation()` callback validate that `msg.sender == POOL` and that `initiator == address(this)`?
- **Real finding pattern (multiple Solodit)**: Protocol's `executeOperation` checks `msg.sender == POOL` but not `initiator`. An attacker calls `pool.flashLoan(protocolAddress, ...)`, triggering the protocol's callback with attacker-chosen parameters. The protocol executes arbitrary operations thinking it initiated the flash loan.
- Can the flash loan callback be called outside a flash loan context? (Direct call to `executeOperation`)
- **Real finding pattern (Aave V3 Bug Bounty, StErMi)**: Protocol's `executeOperation` checks `msg.sender == POOL` but not `initiator`. Attacker calls `pool.flashLoan(protocolAddress, ...)` — protocol's callback executes with attacker-chosen token/amount/params, paying the premium from the protocol's own balance.

### 3b. Flash Loan Fee Accounting

- Aave V3 flash loan fee is configurable per reserve (default 0.05% for regular, 0 for Aave positions). Aave V2 fee is fixed at 0.09%.
- Does the protocol account for the flash loan fee when computing profitability or repayment?
- **Real finding pattern**: Protocol borrows X via flash loan, performs arbitrage, repays X + fee. But the fee calculation uses the wrong Aave version's percentage, under-repaying and causing the flash loan to revert.
- If the protocol uses `flashLoanSimple()` (V3): note that this doesn't support multi-asset flash loans.

### 3c. Reentrancy via Flash Loan

- During a flash loan, the protocol has temporary custody of borrowed funds. Can it interact with its own state in unexpected ways?
- Can an attacker use an Aave flash loan to manipulate protocol state before a protocol-initiated operation completes? (e.g., flash loan → supply to Aave → inflate the protocol's aToken balance → call protocol's deposit at inflated price → protocol reads stale balance)
- Does the protocol have reentrancy guards on functions that interact with Aave?

Tag: `[TRACE:callback_auth={msg_sender_and_initiator/msg_sender_only/NONE} → fee_version={V2_009/V3_005/dynamic} → reentrancy_guard={YES/NO}]`

---

## 4. Liquidation and Health Factor

If the protocol holds Aave borrow positions:

### 4a. Health Factor Monitoring

- Does the protocol monitor its health factor (`getUserAccountData().healthFactor`)? If it falls below 1.0, the position is liquidatable.
- **Real finding pattern**: Protocol borrows from Aave with moderate LTV. Oracle price moves. Protocol has no health factor monitoring or automatic deleveraging — position gets liquidated by external liquidators, losing the liquidation bonus (typically 5-10%).
- Is there an automated keeper/bot that deleverages when health factor approaches 1.0?

### 4b. Collateral Factor Assumptions

- Does the protocol hardcode LTV or liquidation threshold values? These are governance-controlled and can change.
- **Real finding pattern**: Protocol assumes USDC LTV is 80%. Aave governance changes it to 75%. Protocol's leverage calculations are now wrong — positions can be unexpectedly liquidated.
- Does the protocol read collateral parameters from `getReserveData()` dynamically?

### 4c. E-Mode (Efficiency Mode) — V3 Only

- If the protocol uses Aave V3 e-mode: are e-mode category assumptions hardcoded?
- E-mode allows higher LTV for correlated assets (e.g., stablecoins, ETH/stETH). But:
  - E-mode categories can be changed by governance
  - Collateral and debt must be in the same e-mode category
  - **Real finding pattern**: Protocol enables e-mode for higher leverage. User deposits a collateral not in the e-mode category. The position doesn't get e-mode benefits but the protocol's math assumes it does.

### 4d. Isolation Mode — V3 Only

- If any collateral asset is in isolation mode: the protocol can only borrow isolated stablecoins, and total debt is capped.
- Does the protocol handle isolation mode restrictions?
- Can a user unknowingly trigger isolation mode by depositing an isolated asset?

### 4e. LTV-0 aToken Poisoning (V3 pre-3.0.2)

- In Aave V3 pre-3.0.2, receiving any aToken via `transfer()` automatically enabled it as collateral if the recipient held zero balance of that token.
- **Real finding pattern (V3 Bug Bounty, StErMi Part 3, Critical DoS)**: Attacker sends 1 wei of a zero-LTV aToken to a vault/strategy contract. Auto-enabled as collateral, it blocks all withdrawals and rebalancing operations (`LTV_VALIDATION_FAILED`). Attacker can repeat indefinitely after each remediation.
- If the protocol holds Aave V3 positions: can unsolicited aToken transfers lock the protocol's position? Does it call `setUserUseReserveAsCollateral(poisonToken, false)` as a recovery mechanism?

Tag: `[TRACE:health_factor_monitored={YES/NO} → collateral_params={dynamic/hardcoded} → emode_used={YES/NO} → isolation_handled={YES/NO} → ltv0_poison_recovery={YES/NO}]`

---

## 5. Pool Governance and Upgrade Risk

### 5a. Pool Address Resolution

- Does the protocol use `IPoolAddressesProvider.getPool()` to get the current pool address, or does it hardcode the pool address?
- Aave pools are upgradeable proxies. `AddressesProvider` points to the current implementation.
- **Real finding pattern**: Protocol hardcodes the Aave Pool proxy address (safe) but hardcodes the aToken address. Aave governance upgrades the aToken implementation. Protocol's interface calls fail or behave unexpectedly.

### 5b. Reserve Configuration Changes

- Aave governance can: change LTV/liquidation thresholds, add/remove reserves, pause reserves, change interest rate strategies, set supply/borrow caps, change reserve factors.
- Which of these would break the protocol's assumptions?
- Does the protocol have circuit breakers for governance-induced parameter changes?
- **Real finding pattern**: Aave governance pauses a reserve during a security incident. Protocol's withdraw/repay transactions revert. User funds are temporarily locked in the protocol with no recovery path.

### 5c. V2 vs V3 API Differences

- If the protocol supports both V2 and V3: are API differences handled?
  - V2: `ILendingPool.deposit/withdraw/borrow/repay`
  - V3: `IPool.supply/withdraw/borrow/repay` (deposit renamed to supply)
  - V2 flash loan: `flashLoan(receiver, assets[], amounts[], modes[], onBehalfOf, params, referral)`
  - V3 flash loan: `flashLoan(receiver, assets[], amounts[], modes[], onBehalfOf, params, referral)` (same) + `flashLoanSimple(receiver, asset, amount, params, referral)` (single-asset convenience)
- Are return value differences handled? V3 `supply()` returns void; V2 `deposit()` returns void.
- Does the protocol check `aToken.POOL()` to verify the aToken belongs to the expected pool?

Tag: `[TRACE:pool_resolution={addresses_provider/hardcoded} → governance_impact={list} → circuit_breaker={YES/NO} → aave_version={V2/V3/both}]`

---

## Common False Positives

- **Protocol only holds aTokens as pass-through**: If the protocol receives aTokens and immediately transfers them without internal accounting, rebasing concerns are minimal
- **Using scaledBalanceOf for all tracking**: If the protocol consistently uses `scaledBalanceOf()` instead of `balanceOf()`, the rebasing balance drift doesn't apply
- **No borrow positions**: If the protocol only supplies (never borrows), liquidation, health factor, e-mode, and isolation mode concerns don't apply
- **Single-reserve interaction**: If the protocol only interacts with one specific Aave reserve (not configurable), many reserve-change governance risks are reduced
- **Flash loan receiver is a dedicated contract**: If the flash loan callback is in a separate contract that only the main protocol can call, initiator validation is less critical

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Rebasing Balance Accounting | YES | | balanceOf vs scaledBalanceOf tracking |
| 1b. Transfer Precision | IF aTokens transferred | | 1-2 wei rounding, strict equality |
| 1c. Interest Accrual Timing | IF reserve data read before action | | Index caching, state update order |
| 2a. Reserve Data Staleness | YES | | getReserveData freshness, rate lag |
| 2b. Interest Rate Assumptions | IF protocol depends on rates | | Kink model, utilization spikes |
| 2c. Supply/Borrow Caps | IF V3 | | Cap hit handling, revert recovery |
| 2d. Reserve Factor | IF yield calculation | | Factor accounted, governance change |
| 3a. Flash Loan Callback | IF flash loans used | | msg.sender + initiator validation |
| 3b. Flash Loan Fee | IF flash loans used | | Version-correct fee, repayment |
| 3c. Reentrancy via Flash Loan | IF flash loans used | | State manipulation during loan |
| 4a. Health Factor | IF protocol borrows | | Monitoring, automated deleverage |
| 4b. Collateral Factors | IF protocol borrows | | Dynamic vs hardcoded params |
| 4c. E-Mode | IF V3 e-mode used | | Category assumptions, governance |
| 4d. Isolation Mode | IF V3 + isolated assets | | Debt caps, restriction handling |
| 5a. Pool Address Resolution | YES | | AddressesProvider vs hardcoded |
| 5b. Reserve Config Changes | YES | | Governance impact, pause handling |
| 5c. V2 vs V3 API | IF multi-version | | Naming, return values, flash loan |
