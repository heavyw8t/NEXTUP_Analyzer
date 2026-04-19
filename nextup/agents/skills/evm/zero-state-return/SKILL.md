---
name: "zero-state-return"
description: "Trigger Always inject into Arithmetic agent (extends existing ZERO_STATE_ECONOMICS) - Purpose Check protocol return-to-zero state, not just initial zero state"
---

# ZERO_STATE_RETURN Skill

> **Trigger**: Always inject into Arithmetic agent (extends existing ZERO_STATE_ECONOMICS)
> **Purpose**: Check protocol return-to-zero state, not just initial zero state

## Overview

ZERO_STATE_ECONOMICS checks initial zero state. This skill EXTENDS it to cover:
- Protocol returning to zero after normal operations
- Residual assets when supply returns to zero
- Re-entry vulnerabilities after full exit

## 1. Return-to-Zero Scenarios

After normal operations, can the protocol return to:

| State | Trigger | Check |
|-------|---------|-------|
| `totalSupply == 0` | All users withdrew/burned | Does this recreate first-depositor conditions? |
| `totalPooledAmount == 0` | No funds staked | Are there residual rewards? |
| Empty validator set | All validators removed | Can protocol still function? |
| Zero liquidity | All LP withdrawn | What happens to accumulated fees? |

## 2. Residual Asset Check

When supply returns to zero, check for:

### 2a. Accrued Rewards
- Do rewards persist when totalSupply = 0?
- If yes → inflates exchange rate for next depositor
- Example: Protocol accrues 100 ETH rewards, last user exits, totalSupply = 0, next deposit of 1 wei receives claim to 100 ETH

### 2b. Unclaimed Fees
- Are there fee balances that persist?
- Can first new depositor capture accumulated fees?
- Example: Protocol fees = 10 ETH, users exit, new depositor claims all fees

### 2c. Dust Balances
- Can dust (tiny amounts) affect exchange rate calculations?
- Example: totalSupply = 0, dust balance = 1 wei, exchange rate undefined or manipulable

### 2d. Pending Operations
- Are there pending withdrawals/claims that persist?
- What happens to in-flight operations when supply hits zero?

## 3. Re-Entry Vulnerability Analysis

Does re-entering zero state recreate first-depositor attack conditions?

| Scenario | Initial State | Return-to-Zero State | Same Vulnerability? |
|----------|---------------|---------------------|---------------------|
| First depositor attack | totalSupply=0, totalAssets=0 | totalSupply=0, totalAssets=X (residual) | **WORSE** if residual > 0 |
| Exchange rate manipulation | No shares exist | No shares, but balance exists | YES + amplified |
| Donation attack | Clean state | Dirty state | YES + pre-seeded |

## 4. Protocol Reset Functions

Check for admin functions that can force zero state:

- `emergencyWithdraw()` - does it clear ALL state?
- `rescueTokens()` - can it create accounting mismatch?
- `pause()` + `drain()` - what state remains after?
- `migrate()` - does old contract have residuals?

For each: what state persists after the "reset"?

## 5. Zero-State Return Checklist

```markdown
## Zero-State Return Analysis for [ContractName]

### Can protocol return to zero state?
- [ ] All users can withdraw (no locked funds)
- [ ] All shares can be burned
- [ ] Supply can reach exactly zero

### What persists when supply = 0?
- [ ] Accrued rewards: [amount/none]
- [ ] Protocol fees: [amount/none]
- [ ] Dust balances: [yes/no]
- [ ] Pending operations: [list/none]

### Re-entry vulnerability?
- [ ] Initial zero state protected: [yes/no/how]
- [ ] Return-to-zero state protected: [yes/no/how]
- [ ] Same protection mechanism: [yes/no]

### Exchange rate at return-to-zero:
- [ ] Formula: [show calculation]
- [ ] With residual X: [show calculation]
- [ ] Can attacker inflate rate before re-entry: [yes/no]
```

## 5b. Default/Uninitialized State Values

For each state variable used in arithmetic or control flow, check its **initial value** before any user interaction:

- **Default zero**: Solidity initializes to 0. If a function uses `lastTimestamp`, `startTime`, or `lastUpdate` in subtraction or division BEFORE it has ever been set, the result may be unexpected (e.g., `block.timestamp - 0` = enormous elapsed time, or division by a value derived from 0).
- **First-call path**: Trace the FIRST invocation of each state-modifying function. Does it assume a prior call already initialized dependent variables?
- **Check**: For each variable read in a function, is there a code path where that variable still holds its default value (0, address(0), false)? If yes, does the function behave correctly with that default?

## 6. Code Patterns to Check

```solidity
// Pattern 1: Check covers initial zero only
if (totalSupply == 0) {
    return 1e18; // 1:1 rate
}
// QUESTION: What if totalSupply returns to 0 with balance > 0?

// Pattern 2: Exchange rate with balance
uint256 rate = totalAssets / totalSupply;
// QUESTION: What if totalAssets > 0 and totalSupply = 0 (division by zero)
// QUESTION: What if both return to 0 but at different times?

// Pattern 3: First deposit protection
require(totalSupply > 0 || msg.value >= MIN_FIRST_DEPOSIT);
// QUESTION: Does this check exist for RE-deposits after full exit?
```

## 7. Finding Template

```markdown
**ID**: [AR-N]
**Severity**: [typically HIGH if funds extractable]
**Location**: Contract.sol:LineN
**Title**: Return-to-zero state allows [attack] due to [residual state]
**Description**:
- Protocol can return to totalSupply=0 via [mechanism]
- When this happens, [state variable] retains value of [amount]
- A new depositor can [exploit path]
**Impact**: [Fund extraction / exchange rate manipulation / unfair distribution]
**PoC Scenario**:
1. Users deposit and earn rewards
2. All users withdraw, totalSupply = 0
3. Rewards remain: totalRewards = X
4. Attacker deposits 1 wei
5. Attacker claims X rewards
```

## 8. Integration with ZERO_STATE_ECONOMICS

This skill does NOT replace ZERO_STATE_ECONOMICS. It EXTENDS it:

| Check | ZERO_STATE_ECONOMICS | ZERO_STATE_RETURN |
|-------|---------------------|-------------------|
| Initial zero state | YES | - |
| First depositor attack | YES | - |
| Return to zero | - | YES |
| Residual assets | - | YES |
| Re-entry vulnerability | - | YES |

When applying ZERO_STATE_ECONOMICS, ALSO apply ZERO_STATE_RETURN.
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> Source: candidates.jsonl (26 rows). Selected 8 examples across four sub-patterns.
> Sub-patterns covered: `zero_return`, `default_value`, `uninitialized_mapping`, `zero_address`, `empty_array`.

---

## Example 1
*Sub-pattern*: `default_value`
*Severity*: HIGH
*Source row*: 12715

*Summary*: In GMX-Synthetics `getNextOpenInterestParams()`, `nextLongOpenInterest` and `nextShortOpenInterest` are both initialized to 0. The function updates only the side the user is acting on and leaves the other side at 0. This causes the returned "other side" open interest to be incorrectly zero, producing a price impact calculation that is wrong in magnitude and sign, resulting in direct loss of user funds.

*Why it fits*: A state variable used in arithmetic holds its default zero value on the branch that is not explicitly set. The function assumes both fields will be populated but only half the struct is ever written.

---

## Example 2
*Sub-pattern*: `default_value`
*Severity*: MEDIUM
*Source row*: 18053

*Summary*: The variable `diffMaxMinRuntime` is never assigned or updated, leaving it at its Solidity default of 0. Every calculation that uses it to size bucket indexes or bucket counts evaluates to 0 or reverts on divide-by-zero, making the affected functionality permanently broken at its default state.

*Why it fits*: Uninitialized state variable silently stays at zero and poisons all downstream arithmetic, producing zero outputs rather than an error.

---

## Example 3
*Sub-pattern*: `uninitialized_mapping`
*Severity*: HIGH
*Source row*: 13061

*Summary*: In Carapace Finance `_calculateClaimableAmount`, when all snapshots for a protection seller have been claimed, the function returns `_latestClaimedSnapshotId` as 0 (its mapping default). The caller does not guard against a zero return and writes 0 back as the "last claimed" ID, resetting the seller's claim cursor to the beginning. An attacker can then re-claim all previously claimed unlocked capital repeatedly.

*Why it fits*: A mapping entry that was never explicitly set (or effectively reset to default) produces a zero sentinel that is indistinguishable from a valid first-time state, recreating a "first-claim" condition on subsequent calls.

---

## Example 4
*Sub-pattern*: `uninitialized_mapping`
*Severity*: HIGH
*Source row*: 17952

*Summary*: `getTokenConfigBySymbolHash`, `getTokenConfigByCToken`, and `getTokenConfigByUnderlying` use `-1` (cast to uint) to signal "not found", but uint defaults to 0, making it impossible to return -1. Index 0 is also a valid config slot, so uninitialized mappings return 0, which is treated as "first config found" rather than "not found". Any caller checking for the not-found sentinel gets incorrect results.

*Why it fits*: The uninitialized uint mapping default (0) collides with a valid data value, making the absence of a mapping entry indistinguishable from the presence of the first legitimate entry.

---

## Example 5
*Sub-pattern*: `uninitialized_mapping`
*Severity*: MEDIUM
*Source row*: 14590

*Summary*: In JBTiered721DelegateStore, when a new tier is added with `reservedTokenBeneficiary` equal to `defaultReservedTokenBeneficiaryOf[msg.sender]`, the per-tier mapping `_reservedTokenBeneficiaryOf[msg.sender][_tierId]` is not written. Later, if the owner changes the default beneficiary, the per-tier lookup falls through to the updated default and returns the new address rather than the one explicitly chosen at tier creation time. A tier created for Bob now pays Alice.

*Why it fits*: An unwritten mapping slot returns address(0) / the default, and the lookup logic falls back to a mutable global default, causing the stored intent of a specific value to be silently lost.

---

## Example 6
*Sub-pattern*: `zero_address`
*Severity*: MEDIUM
*Source row*: 18758

*Summary*: Augur's factory contracts call `lookup(key)` on the Augur registry to get the implementation address for a minimal proxy. If the key has not been registered, `lookup` returns `address(0)`. The factory sets this zero address as the proxy target without validation. Calls to `initialize()` on the proxy then revert with no informative message, making proxy deployment silently broken for any unregistered key.

*Why it fits*: A mapping lookup on an unregistered key returns `address(0)` (the EVM default for address mappings), and the caller propagates that zero address into a critical configuration field instead of reverting on the zero sentinel.

---

## Example 7
*Sub-pattern*: `empty_array`
*Severity*: HIGH
*Source row*: 9159

*Summary*: In the AFiBase contract, the deposit path builds a strategy array but only populates it when `strategyNumber == 1`. For any other value the array is returned empty. Callers that iterate the returned array skip all logic, silently treating a misconfigured deposit as a no-op rather than reverting.

*Why it fits*: A conditional branch that writes to an array is not taken, leaving the array at its default (empty). The caller does not check length before iterating, so an empty-array default becomes a silent bypass.

---

## Example 8
*Sub-pattern*: `zero_return`
*Severity*: HIGH
*Source row*: 7217

*Summary*: The `SpigotedLoan.sweep()` function is intended to send unused revenue tokens to the arbiter on borrower default, but it checks for loan status `INSOLVENT`, which is never set by the protocol. The function always evaluates its guard to false and returns 0 without transferring any funds. All unused revenue is permanently locked in the contract, effectively lost to both arbiter and lender.

*Why it fits*: A function that should return a non-zero amount silently returns 0 because the state condition it depends on is never written, matching the "function returns zero due to unset/default state variable" root cause.

---

## Coverage Summary

| Sub-pattern | Examples | Row indices |
|---|---|---|
| `default_value` | 2 | 12715, 18053 |
| `uninitialized_mapping` | 3 | 13061, 17952, 14590 |
| `zero_address` | 1 | 18758 |
| `empty_array` | 1 | 9159 |
| `zero_return` | 1 | 7217 |


