---
name: "v4-hook-security"
description: "Protocol Type Trigger v4_hook (detected when recon finds IHooks|beforeSwap|afterSwap|beforeAddLiquidity|beforeRemoveLiquidity + PoolManager - AND the protocol IS the hook implementation, not a DEX caller)"
---

# Injectable Skill: Uniswap V4 Hook Security

> **Protocol Type Trigger**: `v4_hook` (detected when recon finds: `IHooks`, `beforeSwap`, `afterSwap`, `beforeAddLiquidity`, `beforeRemoveLiquidity`, `PoolManager`, `PoolKey`, `BalanceDelta` - AND the protocol implements hook callbacks, i.e., it IS the hook, not a DEX caller)
> **Inject Into**: Breadth agents, depth-external, depth-token-flow, depth-edge-case
> **Language**: EVM only
> **Finding prefix**: `[V4H-N]`
> **Relationship to DEX_INTEGRATION_SECURITY**: That skill covers "protocol calls DEX." This skill covers the reverse: "protocol IS a DEX hook callback target." Both may be active if a protocol both implements hooks AND calls other DEXes.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Sections 1, 2: depth-external (pool identity, caller authentication, multi-pool isolation)
- Section 3: depth-token-flow (reward accrual per-pool vs per-token, donation accounting)
- Section 4: depth-edge-case (native token handling, Currency.unwrap, address(0))
- Section 5: depth-token-flow + depth-edge-case (donation distribution fairness, tick-range analysis)
- Section 6: depth-external (hook flag permissions, PoolManager trust boundary)

## When This Skill Activates

Recon detects that the protocol implements Uniswap V4 hook callbacks. Key indicators:
- Contract inherits from `BaseHook`, `IHooks`, or implements `beforeSwap`/`afterSwap`/`beforeAddLiquidity`/`beforeRemoveLiquidity`
- Imports or references `PoolManager`, `PoolKey`, `BalanceDelta`, `Currency`
- Contains `getHookPermissions()` or `HookPermissions` struct

This skill analyzes security of the **hook implementation itself** — the protocol receiving callbacks from PoolManager. It does NOT cover the protocol's own calls to external DEXes (that is DEX_INTEGRATION_SECURITY).

---

## 1. Pool Identity and Caller Authentication

Uniswap V4 allows multiple pools for the same token pair (different fee tiers, tick spacings, or configurations). All pools sharing the same hook contract will invoke the hook's callbacks. The hook MUST validate which pool is calling.

### 1a. PoolManager as Sole Caller
- Does the hook enforce that `msg.sender == address(poolManager)` on ALL callback entry points?
- Are there any public/external functions that bypass this check and directly modify hook state?
- If the hook uses a modifier (e.g., `onlyPoolManager`, `poolManagerOnly`): verify it covers ALL callback functions, not just some.

Tag: `[TRACE:callback_{name} → msg.sender_check={YES/NO} → modifier={name_or_NONE}]`

### 1b. Pool Whitelisting
- Does the hook maintain a whitelist/registry of authorized pools (by PoolId or PoolKey)?
- If the hook accrues rewards, distributes fees, or modifies shared state: does it check that the calling pool is authorized BEFORE performing those operations?
- If no whitelist exists: can an attacker create an unauthorized pool with the same hook and trigger state changes?

For each state-modifying callback, trace:
```
callback(PoolKey key, ...) {
    // Is `key` validated against a whitelist BEFORE any state change?
    // Can a pool with key={attacker-chosen-fee, attacker-chosen-tickSpacing} reach this code?
}
```

Tag: `[TRACE:callback_{name} → pool_validated={YES/NO} → validation_method={whitelist/listing_check/NONE} → state_change_before_validation={YES/NO}]`

### 1c. Pool Enumeration Attack Surface
- List all pools that can share this hook (same hook address, different pool parameters).
- For each: can the attacker control pool creation? (Uniswap V4 pool creation is permissionless)
- What hook state is shared across all pools using this hook? What state is per-pool?
- If state is shared (global counters, reward indices, fee accumulators): can one pool's callbacks corrupt another pool's accounting?

Tag: `[TRACE:shared_state={variables} → per_pool_state={variables} → cross_pool_corruption={YES/NO}]`

---

## 2. Per-Pool vs Global Accrual Isolation

When a hook manages rewards, fees, or other accruing values:

### 2a. Accrual Scope
- Is reward/fee accrual performed per-pool (keyed by PoolId) or globally (per-token or per-hook)?
- If global: can an unlisted/unauthorized pool trigger accrual and siphon value meant for listed pools?
- Trace the exact accrual function: does it use `PoolKey`/`PoolId` as a key, or only `token`/`address`?

### 2b. Distribution Scope
- When rewards are distributed (e.g., via `donate`, direct transfer, or internal accounting): are they distributed to the specific pool that triggered accrual, or to a global pool?
- Can an attacker create a pool, trigger accrual, then claim the distribution from a different (legitimate) pool?

### 2c. Accrual Timing
- Can an attacker call add/remove liquidity on an unauthorized pool to trigger accrual at a favorable time?
- Is there a minimum liquidity or minimum activity threshold before accrual occurs?
- Can zero-liquidity pools trigger accrual?

Tag: `[TRACE:accrual_key={pool_id/token/global} → distribution_target={same_pool/global} → unauthorized_trigger={YES/NO}]`

---

## 3. Donation Accounting

V4 hooks commonly use `PoolManager.donate()` to distribute rewards to LPs.

### 3a. Donation Source Validation
- Where do donated funds come from? Hook's own balance? Minted tokens? External transfers?
- Can the donation amount be manipulated by controlling the hook's balance (e.g., unsolicited token transfers)?
- Is donation amount computed from accrued state that could be inflated by unauthorized pool activity (Section 2)?

### 3b. Donation Target Isolation
- Does `donate()` send to the correct pool? Trace the `PoolKey` parameter passed to `donate()`.
- Can an attacker cause donations to be sent to their pool instead of the intended pool?
- If donations are global (same token across pools): is value being leaked to unauthorized pools?

### 3c. Balance-Based Accounting in Hooks
- Does the hook use `balanceOf(address(this))` or similar for accounting?
- If yes: can an attacker send tokens directly to the hook to inflate balances and manipulate donation amounts?
- Does the hook use a pull-based accounting pattern (internal balance tracking) or push-based (ambient balance)?

Tag: `[TRACE:donate_source={balance/accrual/mint} → donate_pool_key={explicit/inherited} → balance_manipulable={YES/NO}]`

---

## 4. Native Token (ETH) Handling via Currency

Uniswap V4 represents native ETH as `address(0)` internally via the `Currency` type. `Currency.unwrap()` returns `address(0)` for native ETH.

### 4a. ERC20 Calls on Currency.unwrap()
- Grep for `IERC20(Currency.unwrap(` or equivalent patterns.
- For each: does the code handle the case where `Currency.unwrap()` returns `address(0)`?
- Calling `IERC20(address(0)).balanceOf(...)`, `.transfer(...)`, or `.approve(...)` will REVERT — there is no contract at address(0).
- Check ALL paths: fee collection, reward distribution, balance queries, token transfers.

### 4b. Native ETH Transfer Paths
- When the hook needs to handle native ETH: does it use `address.call{value: amount}("")` instead of ERC20 transfer?
- Does the hook's fee collection logic branch on `Currency.isNative()` or `Currency.unwrap() == address(0)`?
- Are there any functions that assume all pool currencies are ERC20 tokens?

### 4c. Pool Support Scope
- Does the protocol claim to support "all Uniswap V4 pools"? If yes: native ETH pools MUST be handled.
- If native ETH pools are explicitly unsupported: is this enforced at listing/registration time, or is it just documented?
- Can a native ETH pool be created with this hook and reach code paths that assume ERC20?

Tag: `[TRACE:currency_unwrap_sites={list} → address_zero_handled={YES/NO per site} → native_eth_supported={YES/NO/IMPLICIT}]`

---

## 5. LP Reward Distribution Fairness

When hooks distribute rewards to LPs via `PoolManager.donate()`:

### 5a. Donate Distribution Semantics
- `PoolManager.donate(key, amount0, amount1)` distributes tokens to in-range LPs proportional to their liquidity at the CURRENT tick.
- LPs who were in-range during the accrual period but are out-of-range at distribution time receive NOTHING.
- LPs who were out-of-range during accrual but are in-range at distribution time receive an unearned share.

### 5b. Temporal Fairness Gap
- How long can rewards accumulate between distributions? (Is distribution triggered on every swap, or only on liquidity events?)
- During the accrual period, which LPs provided active liquidity? At distribution time, are the same LPs in range?
- Can an attacker manipulate the tick (via swap) just before triggering distribution to move rewards to their narrow-range position?

Attack pattern:
1. Rewards accumulate over time without distribution
2. Attacker swaps to move tick to a position where only their narrow-range LP is in range
3. Attacker triggers distribution (e.g., add/remove liquidity with 0 delta)
4. Attacker's position captures most/all donated rewards
5. Attacker swaps back to restore original tick
6. Cost: swap fees on both legs. Profit: captured rewards minus swap costs.

### 5c. Distribution Frequency Analysis
- Is distribution triggered on EVERY hook callback, or only on specific events?
- Can distribution be triggered by anyone (permissionless) or only by specific actors?
- What is the maximum accrual period before distribution? Longer periods = larger reward pools = more profitable manipulation.

### 5d. Mitigation Assessment
- Does the hook use time-weighted LP tracking (epoch-based snapshots)?
- Does the hook use a commit-reveal or delay mechanism to prevent tick manipulation before distribution?
- Does the hook restrict who can trigger distribution callbacks?
- If none of these: the distribute-to-current-tick pattern is exploitable.

Tag: `[TRACE:distribution_trigger={every_swap/liquidity_event/manual} → accrual_period={bounded/unbounded} → tick_manipulable_before_distribute={YES/NO} → fairness_mechanism={TWAP/epoch/commit_reveal/NONE}]`

---

## 6. Hook Permissions and PoolManager Trust Boundary

### 6a. Hook Flag Analysis
- Read `getHookPermissions()` return value. Which callbacks are enabled?
- For each enabled callback: does the hook perform state changes? Value transfers? External calls?
- Are any dangerous operations (token minting, reward accrual, fee modification) performed in `before*` callbacks where the pool operation hasn't happened yet?

### 6b. Return Value Manipulation
- V4 hooks can return delta values that modify pool behavior (e.g., `afterSwap` can return a fee override).
- Can the hook's return value be manipulated to extract value from the pool?
- Is the hook's return value bounded or validated by the protocol?

### 6c. Hook-to-Hook Interaction
- If the protocol uses multiple hooks or the hook interacts with other V4 hooks: are there reentrancy or ordering concerns?
- Can a callback in one hook trigger operations that invoke another hook on the same pool?

Tag: `[TRACE:enabled_hooks={list} → state_changes_in_before={YES/NO per hook} → return_value_manipulation={YES/NO}]`

---

## Common False Positives

- **Single-pool hooks**: If the hook is designed for exactly one pool and enforces this at initialization (e.g., stores PoolId in constructor and checks it in every callback), pool identity attacks don't apply
- **View-only hooks**: Hooks that only read state in callbacks (logging, analytics) without writing state or distributing value — pool identity is irrelevant
- **Donation to full-range positions**: If all LPs use full-range positions (like Uniswap V2 style), tick manipulation doesn't affect distribution fairness
- **Admin-only pool creation**: If pool creation with this hook requires admin authorization AND is enforced on-chain (not just docs), unauthorized pool attacks are blocked

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Pool Identity & Caller Auth | YES | | PoolManager check, whitelist, enumeration |
| 2. Per-Pool vs Global Accrual | IF hook manages rewards/fees | | Accrual scope, distribution scope |
| 3. Donation Accounting | IF hook uses donate() | | Source, target, balance manipulation |
| 4. Native Token Handling | YES | | Currency.unwrap, address(0), ETH paths |
| 5. LP Reward Distribution Fairness | IF hook distributes to LPs | | Temporal fairness, tick manipulation |
| 6. Hook Permissions & Trust | YES | | Flags, return values, interactions |
