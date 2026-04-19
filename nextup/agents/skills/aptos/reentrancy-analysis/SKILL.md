---
name: "reentrancy-analysis"
description: "Trigger REENTRANCY flag detected (dynamic dispatch, closures, dispatchable FA, function values) - Used by Breadth agents, depth-state-trace"
---

# Skill: REENTRANCY_ANALYSIS

> **Trigger**: REENTRANCY flag detected (dynamic dispatch, closures, dispatchable FA, function values)
> **Used by**: Breadth agents, depth-state-trace
> **Covers**: Cross-module reentrancy via closures, dispatchable FA hook reentrancy, direct/indirect reentrancy, resource lock gaps

## Purpose

Audit reentrancy vectors in Aptos Move. Historically, Move's linear type system and static dispatch prevented reentrancy. Post Move 2.2, function values (closures) and dispatchable FungibleAsset hooks introduce dynamic dispatch, creating reentrancy surfaces analogous to EVM callbacks but with different mechanics and mitigations.

## Background: Aptos Reentrancy Model

**Pre Move 2.2**: No dynamic dispatch. All function calls are statically resolved at compile time. Reentrancy was architecturally impossible (no callbacks, no external calls to untrusted code).

**Post Move 2.2**: Two reentrancy vectors exist:
1. **Function values / closures**: `|arg| { body }` syntax allows passing executable code as parameters. A module calling a user-supplied closure can be reentered.
2. **Dispatchable FungibleAsset hooks**: `withdraw`, `deposit`, and `derived_balance` hooks execute external module code during FA operations. This is framework-level dynamic dispatch.

**`#[module_lock]`**: Prevents INDIRECT reentrancy (cross-module reentry into the locked module). Does NOT prevent DIRECT reentrancy (closure calling back into the same module's function within the same execution frame).

## Methodology

### STEP 1: Dynamic Dispatch Point Inventory

Find ALL uses of dynamic dispatch in the audited modules:

#### 1a. Function Values and Closures

**MANDATORY SEARCH**: Grep all `.move` files for:
1. `|` followed by parameter patterns (closure syntax: `|x| { ... }`, `|x, y| { ... }`)
2. Function types in signatures (e.g., `callback: |u64| -> u64`, `FunctionValue`)
3. `move |` (move closures that capture variables)
4. Functions that accept function-typed parameters

| # | Module | Function | Dynamic Dispatch Type | Caller-Controlled? | Reentrancy Risk |
|---|--------|----------|----------------------|-------------------|----------------|
| 1 | {module} | {func} | Closure parameter | YES/NO | {assess} |
| 2 | {module} | {func} | Stored function value | YES/NO | {assess} |

#### 1b. Dispatchable FA Hooks

**MANDATORY SEARCH**: Grep for:
1. `dispatchable_fungible_asset` module usage
2. `register_dispatch_functions` or equivalent hook registration
3. `withdraw_with_*`, `deposit_with_*` function patterns
4. `derived_balance` implementations

| # | Module | Hook Type | Registered Function | External Code Executed? |
|---|--------|-----------|--------------------|-----------------------|
| 1 | {module} | withdraw | {module::withdraw_hook} | YES - at every withdrawal |
| 2 | {module} | deposit | {module::deposit_hook} | YES - at every deposit |
| 3 | {module} | derived_balance | {module::balance_hook} | YES - at every balance query |

### STEP 2: Module Lock Analysis

For each module containing dynamic dispatch points:

| Module | Has `#[module_lock]`? | Public Entry Points | Protected by Lock? | Direct Reentry Possible? |
|--------|---------------------|--------------------|--------------------|------------------------|
| {module} | YES/NO | {list entry/public functions} | YES/NO | {YES if lock present - lock prevents indirect but not direct} |

**CRITICAL DISTINCTION**:
- `#[module_lock]` = YES: **Indirect** reentrancy blocked (Module A -> closure -> Module A's function). **Direct** reentrancy still possible (within same function frame, closure calls same module's public function via friend or inline).
- `#[module_lock]` = NO: Both direct and indirect reentrancy possible.

**Check**: For each module WITHOUT `#[module_lock]`:
1. Does it have any dynamic dispatch points (from Step 1)?
2. If YES: cross-module reentrancy is possible - trace all paths.

### STEP 3: Third-Party Resource Lock Bypass

If the audited module stores data in a third-party resource abstraction:

| Data Structure | Provided By Module | Our Module Uses | Third-Party Lock Protects Us? |
|---------------|-------------------|----------------|------------------------------|
| SmartTable | aptos_std | YES/NO | NO - their lock protects THEIR invariants, not ours |
| Table | aptos_std | YES/NO | NO |
| {custom_struct} | {third_party} | YES/NO | NO |

**Pattern**: Module A stores its accounting data in a SmartTable (from `aptos_std`). `aptos_std` may have `#[module_lock]`. But this lock only prevents reentry into `aptos_std` - it does NOT prevent reentry into Module A. An attacker can reenter Module A while Module A's SmartTable operation is in progress.

**Check**: Does the protocol rely on a third-party module's lock for its own reentrancy protection? If YES -> FINDING.

### STEP 4: State Consistency Analysis (Check-Effect-Interaction)

For each dynamic dispatch point identified in Step 1:

#### 4a. Pre-Dispatch State Snapshot

| Dispatch Point | State READ Before Dispatch | State MODIFIED Before Dispatch | State Modified AFTER Dispatch |
|---------------|--------------------------|------------------------------|------------------------------|
| {func:line} | {variables/resources read} | {variables/resources written} | {variables/resources written} |

#### 4b. Reentrancy Impact Trace

For each dispatch point where state is modified before dispatch:

```
1. Function entry: Read state S1 (e.g., user_balance = 100)
2. Modify state: S1 partially updated (e.g., user_balance -= 50, but total_supply not yet updated)
3. Dynamic dispatch: closure/hook executes
4. REENTRY: Attacker calls back into same module
5. Reentrant call reads: S1 (modified) - sees user_balance = 50
6. Reentrant call reads: S2 (NOT yet modified) - sees stale total_supply = 1000 (should be 950)
7. Inconsistency: S1 and S2 are out of sync
8. Original execution resumes: modifies S2 (total_supply = 950)
9. Impact: [describe what the attacker gained]
```

**Key question for each dispatch point**: Is there ANY pair of state variables (S1, S2) where S1 is updated before dispatch but S2 is updated after? If YES, the reentrant call sees an inconsistent state.

### STEP 5: Dispatchable FA Specific Reentrancy

If the protocol uses dispatchable FungibleAsset:

#### 5a. Withdraw Hook Reentrancy

```move
// Framework calls this DURING withdrawal:
fun withdraw_hook(store: Object<FungibleStore>, amount: u64, ...) {
    // This code runs AFTER the framework has decided to withdraw
    // but potentially BEFORE the calling module's post-withdrawal logic

    // Can this hook call back into the protocol?
    // What state has been partially modified at this point?
}
```

**Trace**: What is the call stack at the point the withdraw hook fires?
1. Protocol function (e.g., `redeem()`)
2. Framework `fungible_asset::withdraw()`
3. Hook: `module::withdraw_hook()`
4. Hook can call: ??? (any public function accessible)

#### 5b. Deposit Hook Blocking

Can a deposit hook selectively revert to block specific operations?
- If protocol performs a transfer (withdraw from A + deposit to B), can the deposit hook on B prevent the entire operation?
- Can this be used to grief liquidations, reward distributions, or time-sensitive operations?

#### 5c. Balance Query Reentrancy

If `derived_balance` hook is registered:
- Does calling `fungible_asset::balance()` trigger external code?
- Can this external code modify state that the caller depends on?
- Is `balance()` called within a state modification sequence? (read-modify-write pattern where read triggers hook)

### STEP 6: Mitigation Recommendations Framework

For each reentrancy vector found, categorize the recommended fix:

| Vector | Recommended Fix | Implementation |
|--------|----------------|----------------|
| Cross-module via closure | Add `#[module_lock]` | Module-level attribute |
| Direct reentrancy | Check-Effect-Interaction pattern | Reorder operations: all state writes before dispatch |
| Dispatchable FA hook | Complete all state updates before FA operations | Move all `borrow_global_mut` before `withdraw`/`deposit` |
| Third-party resource bypass | Module-level boolean guard | `assert!(!is_executing, E_REENTRANCY)` pattern |

## Key Questions (Must Answer All)

1. **Dynamic dispatch**: Does the module use function values, closures, or dispatchable FA hooks?
2. **Module lock**: Is `#[module_lock]` applied? What does it cover vs not cover?
3. **State ordering**: For each dispatch point, is all state fully updated before the dispatch?
4. **Third-party reliance**: Does the module rely on another module's lock for its own safety?
5. **Hook surface**: If dispatchable FA, which hooks are registered and who controls them?

## Common False Positives

1. **No dynamic dispatch**: If the module has zero closure parameters, zero function values, and does not use dispatchable FA, reentrancy is not possible in Move
2. **Read-only callbacks**: If the closure only reads state (no `borrow_global_mut`, no state writes), reentrancy cannot cause inconsistency
3. **Framework-only hooks**: If hooks are registered by the framework and not by user-controllable code, the hook code is trusted
4. **Module lock + no direct reentry**: If `#[module_lock]` is present AND the closure does not call the same module's functions, reentrancy is fully blocked
5. **Atomic transactions**: Move transactions are atomic - partial state is never visible cross-transaction (only within the same transaction via reentrancy)

## Output Schema

```markdown
## Finding [RE-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED / CONTESTED
**Step Execution**: ✓1,2,3,4,5,6 | ✗N(reason) | ?N(uncertain)
**Rules Applied**: [R4:✓/✗, R10:✓/✗, R12:✓/✗]
**Severity**: Critical/High/Medium/Low/Info
**Location**: module_name.move:LineN

**Reentrancy Type**: DIRECT / INDIRECT / HOOK_BASED / THIRD_PARTY_BYPASS
**Dispatch Point**: {function:line where dynamic dispatch occurs}
**Inconsistent State**: {which state variables are out of sync during callback}

**Description**: What's wrong
**Impact**: What can happen (double-spend, state corruption, fund theft)
**Evidence**: Code showing the dispatch point and state ordering

### Attack Sequence
1. [Attacker calls function X]
2. [State S1 is modified]
3. [Dynamic dispatch triggers callback]
4. [Callback reenters function Y which reads stale S2]
5. [Impact: ...]

### Precondition Analysis (if PARTIAL/REFUTED)
**Missing Precondition**: [What blocks exploitation]
**Precondition Type**: STATE / ACCESS / TIMING / EXTERNAL / BALANCE

### Postcondition Analysis (if CONFIRMED/PARTIAL)
**Postconditions Created**: [What conditions this creates]
**Postcondition Types**: [List applicable types]
**Who Benefits**: [Who can use these]
```

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: ERC-777 `tokensReceived` hook allows malicious token holder to reenter and block migration indefinitely
  Where it hit: VariableSupplyToken / `mint()` calling `tokensReceived` hook
  Severity: HIGH
  Source: Solodit (row_id 18768)
  Summary: After a fix attempt, `mint` was modified to call the ERC-777 `tokensReceived` hook before setting `isMigratingFromLegacy = false`. A malicious token holder whose contract implements `tokensReceived` can reenter the mint path and repeatedly revert the migration, permanently blocking the flag from clearing. The CEI ordering violation — dispatching the hook before finalizing migration state — is the root cause. The fix is to complete all state writes before invoking external hooks or to avoid calling the ERC-777 hook during migration.
  Map to: reentrancy, callback, CEI_violation

- Pattern: ERC-777 sending/receiving hooks disabled by BWGToken, breaking hook-dependent contracts and creating silent reentrancy assumption
  Where it hit: BWGToken / `StorageOperator.batchSend()` and `_beforeTokenTransfer()` hook
  Severity: HIGH
  Source: Solodit (row_id 12082)
  Summary: BWGToken disabled ERC-777 hooks while downstream contracts (StorageOperator) assumed they were active. Any contract on the `costableList` that implements a sending hook causes `batchSend` to revert when triggered by `_beforeTokenTransfer`. The underlying design defect is trusting external hook callbacks without a module-level guard against reentry; when hooks fire unexpectedly, an adversary-controlled receiver hook can preempt the batch logic. The recommended fix is to either enforce that hooks are never called or follow OpenZeppelin's ERC-777 guard pattern.
  Map to: reentrancy, callback, back_call

- Pattern: Double release of tokens in `acquireConviction()` — transfer executes before clearing the locked-token record
  Where it hit: ERC20ConvictionScore.sol / `acquireConviction()` line 316
  Severity: HIGH
  Source: Solodit (row_id 17867)
  Summary: When a user acquires a conviction score back from an NFT, the function first releases locked FSD tokens via the NFT's internal transfer, then unconditionally transfers the same amount again from the protocol on line 316. State (locked balance cleared) is not updated before the second transfer dispatches, so the protocol pays out twice. This is a CEI violation: the interaction (first transfer) completes, the locked-token record is not zeroed, and a second interaction fires against the same record. The fix is to remove the redundant transfer on line 316.
  Map to: CEI_violation, reentrancy, back_call

- Pattern: `give_coin` uses `add_flow_out` instead of `add_flow_in` during interchain receive, corrupting flow accounting
  Where it hit: CoinManagement (Move) / `give_coin()`
  Severity: HIGH
  Source: Solodit (row_id 6915)
  Summary: `give_coin` is invoked when the protocol receives tokens via an interchain transfer. It calls `add_flow_out` (outflow tracking) instead of `add_flow_in` (inflow tracking). The result is that every incoming token batch is booked as an outflow, causing the flow limiter to allow double the intended outbound volume. In an `acquires`-annotated Move function, this means the global resource for flow limits is mutably borrowed and updated with the wrong direction, leaving the resource in a permanently inconsistent state after each cross-chain receipt. The fix is to call `add_flow_in` for received tokens.
  Map to: acquires, CEI_violation, back_call

- Pattern: Blacklist restriction in `sdeusd.move` bypassed by specifying a non-blocked receiver address
  Where it hit: sdeusd.move / staking and mint restriction logic
  Severity: MEDIUM
  Source: Solodit (row_id 671)
  Summary: Full and soft restrictions are supposed to prevent blacklisted users from staking or receiving newly minted sdeUSD. The restriction checks only validate the caller's address, not the receiver address passed as a parameter. A blacklisted user can stake by nominating an unblocked address as the receiver, and newly minted sdeUSD can still land at a fully blacklisted address within the current epoch. In Move terms, the `acquires` path that writes the restricted-user resource does not gate on the receiver's restriction status, only the signer's. The fix is to add restriction checks for both caller and receiver in each relevant code path.
  Map to: acquires, CEI_violation

- Pattern: `gulp_emissions()` allows a removed pool to continue accumulating Blend token emissions
  Where it hit: Blend Protocol / `Backstop` contract / `update_rz_emis_data()`
  Severity: MEDIUM
  Source: Solodit (row_id 775)
  Summary: After a pool is removed from the reward zone, `gulp_emissions()` can still be called for it. The `update_rz_emis_data` function does not check whether the pool is in the reward zone before crediting emissions, so a removed pool continues to drain the emission budget. This is a back-call pattern: an external call (`gulp_emissions`) reaches back into reward-zone state that should be inaccessible post-removal, because the state transition (pool removal) did not revoke the pool's ability to trigger that code path. The fix is to gate `update_rz_emis_data` on active reward-zone membership.
  Map to: back_call, CEI_violation

- Pattern: `request_withdraw_stake` in `staking_pool.move` rounds withdrawn token count to zero for small amounts
  Where it hit: staking_pool.move / `request_withdraw_stake()`
  Severity: MEDIUM
  Source: Solodit (row_id 11772)
  Summary: The function divides the requested withdrawal by a pool ratio before recording the amount. For small inputs the integer division truncates to zero, so the function records a zero-token withdrawal and returns successfully without transferring anything. An attacker can use this to grief the accounting: repeated zero-amount withdrawal requests update internal counters without actually moving tokens, creating a mismatch between the recorded pending-withdrawal state and the actual pool balance. The acquires pattern on the pool resource is exercised every call, so the resource lock is repeatedly obtained and released with no net effect. The fix is to assert that the computed token count is non-zero before proceeding.
  Map to: acquires, CEI_violation

- Pattern: `release` in `token_vesting.move` transfers vested funds to the transaction sender instead of the whitelisted beneficiary
  Where it hit: token_vesting.move / `release()`
  Severity: HIGH
  Source: Solodit (row_id 12643)
  Summary: The function validates the whitelisted address and computes the vested amount correctly, but the subsequent transfer sends tokens to the signer (caller) rather than to the validated receiver address. Any caller who can invoke `release` receives tokens intended for the beneficiary. In Move's `acquires` model, the vesting resource is borrowed mutably, the vested amount is deducted from the locked balance, and the transfer fires to the wrong address — the resource update is committed but the funds land in the wrong account. The fix is to either enforce that the signer matches the beneficiary or pass the beneficiary address directly to the transfer call.
  Map to: acquires, CEI_violation


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Dynamic Dispatch Point Inventory | YES | ✓/✗/? | Both closures (1a) and FA hooks (1b) |
| 2. Module Lock Analysis | YES | ✓/✗/? | Direct vs indirect distinction |
| 3. Third-Party Resource Lock Bypass | IF third-party data structures used | ✓/✗(N/A)/? | |
| 4. State Consistency Analysis | FOR EACH dispatch point | ✓/✗/? | Pre/post dispatch state traced |
| 5. Dispatchable FA Specific | IF dispatchable FA used | ✓/✗(N/A)/? | 5a, 5b, 5c sub-steps |
| 6. Mitigation Recommendations | FOR EACH finding | ✓/✗/? | |

If any step skipped, document valid reason (N/A, no dynamic dispatch, no dispatchable FA, module lock covers all paths).
