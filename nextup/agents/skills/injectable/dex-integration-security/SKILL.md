---
name: "dex-integration-security"
description: "Protocol Type Trigger dex_integration (detected when recon finds swap|addLiquidity|removeLiquidity|IUniswapV2Router|ISwapRouter|amountOutMin|amountOutMinimum|slippage - AND the..."
---

# Injectable Skill: DEX Integration Security

> **Protocol Type Trigger**: `dex_integration` (detected when recon finds: swap|addLiquidity|removeLiquidity|IUniswapV2Router|ISwapRouter|amountOutMin|amountOutMinimum|slippage - AND the protocol is NOT itself a DEX implementation)
> **Inject Into**: Breadth agents, depth-external, depth-edge-case
> **Language**: Primarily EVM; applicable to Sui PTB-based DEX interactions
> **Finding prefix**: `[DEX-N]`

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Sections 1, 2: depth-external (external DEX call safety, return value handling)
- Sections 3, 4: depth-edge-case (boundary conditions, fee tier assumptions)
- Section 5: depth-state-trace (approval state management)

## When This Skill Activates

Recon detects DEX integration patterns: `swap`, `addLiquidity`, `removeLiquidity`, `IUniswapV2Router`, `ISwapRouter`, `amountOutMin`, `amountOutMinimum`, `slippage`, `exactInputSingle`, `exactInput`, `swapExactTokensForTokens` - but the protocol itself is NOT a DEX/AMM implementation. This skill analyzes the CALLER's integration with an external DEX, not the DEX internals.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `swap`, `getAmountsOut`, `swapExactTokensForTokens`, `deadline`, `slippage`, `router`, `pair`, `reserves`, `amountOutMin`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[DEX-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Slippage Parameter Analysis

For each function that calls a DEX swap:

### 1a. Parameter Origin
- Is `amountOutMin` (or equivalent) user-provided or computed on-chain?
- If computed: what oracle or price source feeds the computation? (cross-reference ORACLE_ANALYSIS if applicable)
- Can the parameter be set to 0? If yes: trace all callers - does ANY code path pass 0 as slippage tolerance?

### 1b. Parameter Forwarding
- Is the slippage parameter forwarded through intermediate functions? At each hop: is it modified, scaled, or silently dropped?
- For protocols that apply their own fee before swapping: is `amountOutMin` adjusted to account for the fee deduction from the input amount?

### 1c. Multi-Hop and Multi-Swap
- For multi-hop swaps (encoded path): is slippage checked on intermediate amounts or only the final output?
- For operations requiring multiple sequential swaps: is slippage enforced per-swap or only on aggregate output?

Tag: `[TRACE:swap_call → amountOutMin_source={user/computed/hardcoded} → value_can_be_zero={YES/NO} → forwarded_through={functions}]`

---

## 2. Deadline Enforcement

For each function that calls a DEX router:

### 2a. Deadline Value
- Is a `deadline` parameter passed to the DEX router?
- Is `block.timestamp` used as the deadline? (provides no MEV protection - always passes)
- Is the deadline hardcoded to `type(uint256).max` or equivalent? (same issue - no protection)

### 2b. Queued or Delayed Swaps
- For protocols that queue swaps for later execution: is the deadline relative to queue time or execution time?
- If relative to queue time: a long queue delay can cause the swap to execute at a stale price with an expired market context

### 2c. L2 Considerations
- For L2 deployments: does the deadline account for sequencer delay or batch submission lag?
- Can the sequencer hold a transaction to execute it at a favorable time within the deadline window?

Tag: `[TRACE:router_call → deadline={value_or_source} → block.timestamp_used={YES/NO} → queue_delay_considered={YES/NO}]`

---

## 3. Return Value Handling

For each DEX call that returns swap output amounts:

### 3a. Actual vs Expected
- Does the protocol check the actual amount received vs the expected output?
- For fee-on-transfer tokens: does the protocol use the router return value (pre-fee) or re-check balance (post-fee)?
- If the protocol uses `balanceOf` delta: is the delta computed correctly (post-balance minus pre-balance in the same transaction)?

### 3b. Multi-Output Validation
- For `removeLiquidity` calls: are BOTH output token amounts validated?
- For swaps returning multiple values: are all return values consumed, or are some silently ignored?

### 3c. Failure Handling
- If the DEX call reverts: does the protocol handle the revert gracefully, or does it propagate and brick a larger operation (e.g., batch liquidation blocked by one failed swap)?
- For try/catch wrapped swaps: does the catch path leave state consistent?

Tag: `[TRACE:swap_return → checked={YES/NO} → fee_on_transfer_aware={YES/NO} → revert_handling={propagate/catch/ignore}]`

---

## 4. Fee Tier and Pool Assumptions

### 4a. Hardcoded Pool or Fee Tier
- Are pool addresses or fee tiers (e.g., Uniswap V3 fee tiers: 100, 500, 3000, 10000) hardcoded?
- If hardcoded: can the optimal pool change over time due to liquidity migration or new pool deployment?
- Does the protocol verify the pool contract is genuine (not a malicious contract deployed at an expected address)?

### 4b. Pool Liquidity Assumptions
- Does the protocol assume sufficient liquidity exists in the target pool?
- For large swap amounts: can the swap fail or produce extreme slippage if pool liquidity drops?
- For protocols specifying pools by fee tier: what happens if multiple pools exist for the same pair with different fee tiers?

Tag: `[TRACE:pool_selection → hardcoded={YES/NO} → fee_tier={value} → pool_verified={YES/NO} → liquidity_assumption={documented/implicit}]`

---

## 5. Router Approval Safety

### 5a. Approval Scope
- Does the protocol grant unlimited (`type(uint256).max`) approval to the router?
- Is the approval granted once in initialization or per-transaction?
- If per-transaction with exact amounts: is a race condition possible between approval and swap execution?

### 5b. Router Mutability
- Is the router address upgradeable or replaceable (via admin setter)?
- After a router migration: are stale approvals to the old router revoked?
- Can the old router still spend tokens if approvals remain?

### 5c. Permit Usage
- For protocols using permit (EIP-2612) instead of approve: is the permit deadline scoped tightly?
- Is the permit nonce managed correctly to prevent replay?
- Can a permit intended for one router be used by a different contract?

Tag: `[TRACE:approval → scope={unlimited/exact} → router_upgradeable={YES/NO} → stale_revoked={YES/NO}]`

---

## Common False Positives
- **`amountOutMin = 0` in atomic flash loan context**: If the entire operation reverts on net loss within the same transaction, zero slippage tolerance is acceptable (atomic protection guarantees revert on unfavorable outcome)
- **Hardcoded pool address for canonical immutable pair**: Stable pairs on immutable DEX deployments (e.g., WETH/USDC on Uniswap V3 mainnet) carry low migration risk
- **Unlimited approval to verified immutable router**: If the router contract is non-upgradeable and its code is verified, unlimited approval is low risk
- **`block.timestamp` deadline on private/protected functions**: If the swap function is only callable by a trusted keeper within a controlled execution flow, MEV deadline protection may be enforced upstream

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Protocol sets `amount0Min` and `amount1Min` to zero for all AMM router interactions (swaps and liquidity additions)
  Where it hit: AMM router integration contract (swaps + addLiquidity)
  Severity: HIGH
  Source: Solodit (row_id 2810)
  Summary: All interactions with the Uniswap router (swaps, liquidity additions) pass `amount0Min = 0` and `amount1Min = 0`, providing no slippage protection. Any transaction can be front-run or sandwiched, causing the protocol to receive far less than expected. Fix requires either a state-variable-controlled slippage percentage or a minimum-received revert guard.
  Map to: amountOutMin, slippage, IUniswapV2Router, sandwich

- Pattern: `amountOutMinimum` hardcoded to `1` in internal swap function regardless of input size
  Where it hit: `_swapExactInputSingle` inside a protocol's buy-and-burn / treasury swap flow
  Severity: HIGH
  Source: Solodit (row_id 3753)
  Summary: The `swapStableToBCUT` function always passes `amountOutMinimum = 1` to `ISwapRouter.exactInputSingle`, making slippage protection effectively zero. An attacker can front-run the transaction, move the pool price, and cause the contract to receive a near-zero output. Fix is to compute `amountOutMinimum` off-chain via an oracle before submitting the transaction.
  Map to: amountOutMin, slippage, ISwapRouter, sandwich

- Pattern: Slippage tolerance assigned to a local memory variable that is never forwarded to the actual swap call
  Where it hit: NestedDca contract executing Uniswap V3 swaps
  Severity: HIGH
  Source: Solodit (row_id 12155)
  Summary: The slippage parameter is computed and stored in a memory variable at one call level but the downstream function that executes the swap receives a hardcoded zero instead. The memory variable is silently dropped at the call boundary. An attacker can sandwich every swap because the live call carries no slippage protection despite the protocol appearing to set one.
  Map to: amountOutMin, slippage, ISwapRouter

- Pattern: Slippage computed from `slot0` spot price rather than TWAP, making the minimum output manipulable
  Where it hit: Repayment flow in a lending protocol that swaps collateral via Uniswap V3
  Severity: HIGH
  Source: Solodit (row_id 9943)
  Summary: The protocol derives `sqrtPrice` from `slot0()` and uses it to calculate `amountOutMin` on-chain. Because `slot0` reflects the current manipulable spot price, a sandwich attack can inflate the price before the slippage calculation and deflate it during the swap, causing the minimum output check to pass while the user takes a loss. Fix is to use Uniswap V3 TWAP or a Chainlink oracle for the reference price.
  Map to: amountOutMin, slippage, ISwapRouter, sandwich

- Pattern: Deadline parameter not checked in the swap function, allowing transactions to be held and executed at stale prices
  Where it hit: GluexRouter.swap() public entry point
  Severity: HIGH
  Source: Solodit (row_id 1030)
  Summary: The protocol's official documentation requires a deadline check but the `swap()` function omits it entirely. A transaction can remain pending indefinitely and be mined at any future block, executing at prices far from the user's expectation. Fix is to add a `require(block.timestamp <= deadline)` guard at the start of the swap function.
  Map to: slippage, ISwapRouter, sandwich

- Pattern: Deadline hardcoded to `type(uint256).max` in the DEX router call, rendering MEV protection useless
  Where it hit: CurveSpell.sol providing liquidity to a DEX
  Severity: HIGH
  Source: Solodit (row_id 12139)
  Summary: The router call passes `deadline = type(uint256).max`, which means the deadline check always passes and the transaction can be executed at any future block. Combined with the absence of tight slippage bounds, a MEV bot can sandwich the pending transaction and extract value from the protocol. Fix is to pass a meaningful deadline (e.g. `block.timestamp + N`) for all Uniswap interactions.
  Map to: slippage, IUniswapV2Router, ISwapRouter, sandwich

- Pattern: Wrong router interface imported (`ISwapRouter` instead of `IV3SwapRouter`), causing all Uniswap calls on the target chain to revert
  Where it hit: Protocol deployed on Base network calling the Uniswap SwapRouter02
  Severity: HIGH
  Source: Solodit (row_id 3569)
  Summary: The protocol uses the mainnet `ISwapRouter` interface which includes a `deadline` parameter, but the deployed SwapRouter02 on Base implements `IV3SwapRouter` which omits that parameter. Every swap and rebalance call reverts at the ABI level. Fix is to import `IV3SwapRouter` from the `swap-router-contracts` repository and remove the `deadline` field from all call structs.
  Map to: ISwapRouter, swap callback

- Pattern: Pool fee tier hardcoded to a specific value; if no pool exists at that tier the swap reverts and collateral is locked
  Where it hit: Strategy contract that adjusts debt by swapping through a Uniswap V3 pool
  Severity: HIGH
  Source: Solodit (row_id 6710)
  Summary: The strategy uses a hardcoded fee value when constructing the swap path. When the actual deployed pool uses a different fee tier the router finds no matching pool and reverts. A second issue arises because the quoted amount for the hardcoded pool differs from the actual pool's output, leaving leftover collateral stranded in the contract and causing user fund loss. Fix is to read the pool fee from configuration rather than hardcoding it.
  Map to: ISwapRouter, amountOutMin, slippage

- Pattern: Router address hardcoded in the contract; deploying on a chain where Uniswap uses a different address locks all swap-dependent functionality
  Where it hit: Protocol with token-swap logic that targets a single Uniswap router address
  Severity: HIGH
  Source: Solodit (row_id 10655)
  Summary: The contract hard-codes the Uniswap router address for one network. On any other network where the router is at a different address, every call to the swap path fails and affected tokens are permanently locked in the protocol. Fix is to pass the router address as a constructor argument or provide an admin setter so the address can be updated per deployment.
  Map to: IUniswapV2Router, ISwapRouter

- Pattern: Protocol swaps without approving tokens to the router, causing every `sellProfits` or equivalent call to fail and tokens to accrue unspendably in the contract
  Where it hit: Yield/fee-collection contract that routes profits through Uniswap
  Severity: HIGH
  Source: Solodit (row_id 10661)
  Summary: The contract sends tokens to itself and then calls the Uniswap router without first calling `approve`. Every router call reverts because the router has no allowance. Tokens accumulate in the contract with no path to recovery. Fix is to call `IERC20.approve(router, amount)` before each swap or grant an initial approval during initialization.
  Map to: IUniswapV2Router, ISwapRouter


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Slippage Parameter Analysis | YES | | Origin, forwarding, multi-hop |
| 2. Deadline Enforcement | YES | | Value, queue delay, L2 |
| 3. Return Value Handling | YES | | Actual vs expected, fee-on-transfer |
| 4. Fee Tier and Pool Assumptions | IF hardcoded pool/fee tier | | Pool verification, liquidity |
| 5. Router Approval Safety | IF protocol approves router | | Scope, mutability, stale approvals |
