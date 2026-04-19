---
name: "token-flow-tracing"
description: "Trigger Pattern transfer\|transferFrom\|safeTransfer\|mint\|burn\|balanceOf.this - Inject Into Lifecycle, External-Env agents"
---

# TOKEN_FLOW_TRACING Skill

> **Trigger Pattern**: `transfer\|transferFrom\|safeTransfer\|mint\|burn\|balanceOf.*this`
> **Inject Into**: Lifecycle, External-Env agents

For every token the protocol handles:

## 1. Token Entry Points

Where can tokens enter?
- `deposit()` / `stake()` functions - standard entry points
- Unsolicited transfers - direct `transfer()` to contract address (bypasses deposit logic)
- Callback receipts - `onERC721Received`, `onERC1155Received`, `onERC1155BatchReceived`
- `receive()` / `fallback()` for native ETH
- Side-effect receipts - tokens sent as part of external call (e.g., unstake returns tokens)

## 2. Token State Tracking

For each entry point:
- What state variable tracks the balance?
- Is `balanceOf(address(this))` used directly? → **Donation attack vector**
- Are tracked balances vs actual balances compared anywhere?
- Can tracked balance get out of sync with actual balance?

**Red flags**:
- Exchange rate calculations using `balanceOf(address(this))` directly
- No "skim" or "sync" function to reconcile discrepancies
- Accounting variables updated BEFORE token transfer completes

## 3. Token Exit Points

Where can tokens leave?
- `withdraw()` / `unstake()` functions
- Fee distributions to treasury/stakers
- Reward claims
- Emergency withdrawals / rescue functions
- Liquidation transfers

For each exit: does the tracked balance decrease BEFORE or AFTER the actual transfer?
For each transfer call: can the source address be underfunded at execution time? (funds deployed externally, locked, or lent out → transfer reverts)

### 3b. Self-Transfer Accounting
For each transfer function: can the sender and recipient be the same address?
If YES: does a self-transfer update accounting state (fees credited, rewards claimed, snapshots updated, share ratios changed) without net token movement? Flag as FINDING.

## 4. Token Type Separation (Multi-Token Protocols)

For protocols handling multiple token types:
- Are different token types handled by different code paths?
- Can one token type's code path be triggered with another type?
- Are approvals/allowances type-specific or shared?
- Does the protocol distinguish between:
  - Native vs wrapped (e.g., ETH vs WETH)
  - Legacy vs upgraded tokens (e.g., token migrations)
  - Base vs receipt tokens (e.g., underlying vs yield-bearing)
  - Staking receipt tokens (e.g., validator shares, LP tokens, delegation receipts)

**Check**: If function A handles TokenX and function B handles TokenY, can TokenX reach function B's logic? Also: within a single function, if some code paths branch on token type (e.g., input handling), do ALL code paths branch consistently (e.g., refund, fee, return)?

## 5. Unsolicited Transfer Analysis

Can tokens be sent to the contract without calling `deposit()`?

If **YES**:
- Does this break accounting? (tracked balance != actual balance)
- Does this inflate exchange rates? (more assets per share)
- Does this enable first-depositor attack amplification?
- Are there "skim" or "sync" functions to reconcile?
- Can an attacker front-run deposits with unsolicited transfers?

If **NO**:
- Why not? (rebasing token? transfer hook? access control?)
- Is the protection reliable? (can it be bypassed?)

## 5b. Unsolicited Transfer Matrix (All Token Types)

For EVERY external token type the protocol holds, queries, or receives as side effects - not just the protocol's primary token:

| Token Type | Can Transfer To Protocol? | Changes Protocol Accounting? | Blocks Operations? | Triggers Side Effects? |
|------------|--------------------------|-----------------------------|--------------------|----------------------|
| {token_a} | YES/NO | YES/NO | YES/NO | YES/NO |

**RULE**: If ANY token type is transferable to the protocol AND affects state → analyze each consequence:
- Accounting impact: Does tracked vs actual balance diverge?
- Iteration impact: Does the protocol iterate over sources of this token? (gas DoS vector)
- Operation blocking: Does non-zero balance of this token prevent admin operations?
- Side effect chain: Does receiving this token trigger further side effects (reward claims, state changes)?

## 6. Token Flow Checklist

For each token identified:

| Token | Entry Points | Exit Points | Tracking Var | balanceOf(this) Used? | Unsolicited Possible? |
|-------|--------------|-------------|--------------|----------------------|----------------------|
| [Name] | deposit, receive | withdraw, claim | totalDeposited | YES/NO | YES/NO |

## 7. Cross-Token Interactions

For protocols with multiple tokens:
- Can operations on TokenA affect TokenB's accounting?
- Are there exchange rate dependencies between tokens?
- Can withdrawing TokenA affect availability of TokenB?

## 8. External Call Return Type Verification

For every external call that returns tokens or values:

### 8a. Return Type Mismatch Check
- What token type does the protocol EXPECT to receive?
- What token type does the external contract ACTUALLY return?
- Are these the same token, or different representations?

**Common mismatches**:
- Legacy vs upgraded tokens (e.g., TokenV1 vs TokenV2 after migration)
- Native vs wrapped (e.g., ETH vs WETH)
- Bridged vs canonical (e.g., bridged USDC vs native USDC)
- Different decimal precision tokens

**Check**: `interface.function() returns (TokenA)` - verify TokenA is what's actually returned, not TokenB

### 8b. Return Value Validation
- Does the protocol validate return values before use?
- Can zero/max/unexpected returns cause issues?
- Is there a mismatch between documented and actual returns?

## 9. Transfer Side Effects Analysis

For every `transfer()` / `transferFrom()` call to external contracts:

### 9a. On-Transfer Behavior
- Does the token have transfer hooks? (ERC777, ERC1363)
- Does transfer trigger reward claims or state changes?
- Can transfer revert under certain conditions?

### 9b. Side Effect Inventory

| Token | On Transfer Side Effect | Impact on Protocol |
|-------|------------------------|-------------------|
| [Token] | Claims pending rewards | Unexpected balance increase |
| [Token] | Updates delegation state | Accounting mismatch |
| [Token] | Triggers rebase | Exchange rate affected |

### 9c. Specific Checks for Staking Receipts
- Does transferring staking receipts claim rewards automatically?
- Does transfer change the token's internal delegation accounting?
- Can side effects be exploited to inflate/deflate balances?

**Example**: Transferring staking receipt tokens (e.g., stETH, aTokens) may trigger rebases or reward claims as a side effect

### 9d. Side Effect Token Type Analysis

For each documented side effect that produces or claims tokens:

| External Call / Event | Side Effect | Token Type Produced | Protocol Handles This Type? | Mismatch? |
|-----------------------|-------------|--------------------|-----------------------------|-----------|
| {call_or_event} | {side_effect} | {token_type_or_UNKNOWN} | YES/NO | YES/NO |

**RULE**: If side effect token type != protocol's expected token type → FINDING (stranded tokens of wrong type)
**RULE**: If side effect token type is UNKNOWN → CONTESTED (assume adversarial per Rule 4)
**RULE**: Check BOTH direct calls AND unsolicited transfers for side effect token types

## Example Application

```solidity
// RED FLAG: Direct balance usage
uint256 rate = token.balanceOf(address(this)) / totalShares;

// BETTER: Tracked balance
uint256 rate = totalPooledTokens / totalShares;

// But check: is totalPooledTokens updated correctly on ALL entry paths?
```

## Finding Template

When this skill identifies an issue:

```markdown
**ID**: [LC-N] or [EX-N]
**Severity**: [based on fund impact]
**Step Execution**: ✓1,2,3,4,5,6,7,8,9 | ✗(reasons) | ?(uncertain)
**Location**: Contract.sol:LineN
**Title**: [Token type] can enter/exit via [path] without [expected accounting update]
**Description**: [Trace the token flow and where it diverges from expected]
**Impact**: [What breaks: exchange rates, user balances, protocol insolvency]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Selected from `candidates.jsonl` (500 capped from 724). Distinct mechanisms prioritised; duplicates dropped; HIGH preferred.

---

- Pattern: fee-on-transfer token mishandling
  Where it hit: `LOB.receiveTokens()` — contract credits the pre-transfer amount rather than measuring actual received balance after `safeTransferFrom`, causing accounting to record more tokens than arrived
  Severity: HIGH
  Source: Solodit (row_id 1563)
  Summary: Protocol uses the input parameter directly as the credited amount without comparing pre- and post-transfer balances. For any token that deducts a fee on transfer the internal ledger overstates the deposit, producing inflated balances. An attacker can withdraw more than deposited or drain the pool over time.
  Map to: transferFrom, fee_on_transfer

---

- Pattern: fee-on-transfer token mishandling (revert path)
  Where it hit: `Swappee.swappee()` — balance snapshot taken before `transferFrom`, then the pre-fee amount is forwarded to Uniswap, which reverts because the contract holds less than it tries to swap
  Severity: MEDIUM
  Source: Solodit (row_id 1696)
  Summary: Contract captures `amount` from the call argument and later calls the router with the same figure. When a FOT token reduces the received amount the downstream approval and swap fail on insufficient balance. The fix is to measure `balanceOf(this)` before and after and use the delta.
  Map to: transferFrom, fee_on_transfer

---

- Pattern: rebasing token accounting — missed yield accrual
  Where it hit: `EnjoyoorsVaultDeposits._deposit()` — vault records the deposited nominal amount; rebasing token grows the contract balance over time but the extra yield is never credited to users
  Severity: HIGH
  Source: Solodit (row_id 2104)
  Summary: The vault tracks absolute token amounts at deposit time. As the rebasing token increases every holder's balance the difference between the tracked amount and actual `balanceOf(this)` grows permanently. Users who withdraw later receive only their original nominal amount, leaving the accrued yield stranded.
  Map to: rebasing, transfer

---

- Pattern: rebasing token in withdrawal queue — snapshot stale at claim time
  Where it hit: `WithdrawQueue.withdraw()` — stores `amountToRedeem` in stETH terms at request time; by claim time the rebasing balance may have decreased, causing the transfer to revert or the queue to under-distribute
  Severity: HIGH
  Source: Solodit (row_id 6968)
  Summary: The protocol locks a fixed stETH amount at withdrawal request time. stETH rebases continuously; a downward rebase between request and claim makes the stored amount exceed the contract's real balance, reverting the claim. An upward rebase silently forfeits the surplus to the protocol. The mitigation is to store and transfer shares rather than a nominal amount.
  Map to: rebasing, transfer

---

- Pattern: safeTransfer vs transfer — non-standard ERC20 (USDT returns void)
  Where it hit: `Treasury.sol` — uses raw `transfer` / `transferFrom` with USDT; USDT returns no bool, so the call succeeds at the EVM level but the Solidity ABI decoder treats the missing return value as a revert in strict-mode compilers
  Severity: HIGH
  Source: Solodit (row_id 6091)
  Summary: Treasury interacts with USDT using ERC-20's `transfer` and `transferFrom`. USDT on mainnet does not return a boolean. Contracts compiled with Solidity >=0.8 that decode the return value revert on every USDT call, bricking fee collection and withdrawals. Wrapping calls in `SafeERC20.safeTransfer` eliminates the return-value decode step.
  Map to: transfer, safeTransfer, non_standard_ERC20

---

- Pattern: safeTransfer vs transfer — Solmate SafeTransferLib no-code check missing
  Where it hit: `StakingRewards` vault initialisation — Solady/Solmate `safeTransfer` skips the code-existence check; attacker predicts a future token address and stakes before deployment, minting shares with a silent no-op transfer
  Severity: HIGH
  Source: Solodit (row_id 3657)
  Summary: Solady's `safeTransfer` does not assert the target has deployed code. An attacker computes the future token address (e.g. a CREATE2 Uniswap pair), stakes before deployment, and the transfer silently succeeds while `totalSupply` increases. When the real token deploys the attacker holds diluted-for-free shares. The fix is to check `address(token).code.length > 0` on initialisation.
  Map to: safeTransfer, non_standard_ERC20

---

- Pattern: transferFrom approval race / arbitrary-from attack
  Where it hit: `StakingKo.deligateStake()` — passes an attacker-controlled address as the `from` parameter to `transferFrom`, allowing the caller to drain any address that has approved the contract
  Severity: HIGH
  Source: Solodit (row_id 2175)
  Summary: The delegate-stake path accepts an arbitrary `from` address and calls `token.transferFrom(from, contract, amount)`. Any account that has outstanding approval to the staking contract can be drained by a front-runner supplying that account as `from`. The fix is to use `msg.sender` as the source in all `transferFrom` calls.
  Map to: transferFrom

---

- Pattern: transferFrom approval race — permit2 token mismatch
  Where it hit: `V3Vault.sol` — three `permit2.permitTransferFrom()` calls never validate that `TokenPermissions.token` equals the vault's accepted asset, so a user's permit for any ERC-20 is accepted as USDC collateral
  Severity: HIGH
  Source: Solodit (row_id 8104)
  Summary: Permit2's `permitTransferFrom` enforces the caller-supplied `TokenPermissions` but the vault never checks that the token in those permissions matches its own asset. An attacker crafts a permit for a worthless token, deposits it, and borrows against real USDC collateral they did not supply. The fix adds a token-equality check before accepting the permit.
  Map to: transferFrom, non_standard_ERC20

---

- Pattern: token with callback hook (ERC777 / ERC1363) — reentrancy via transfer hook
  Where it hit: `LOB` — ERC-20 tokens with send/receive hooks let an attacker reenter external functions; the report classifies this as critical because trader balance is updated after the external transfer call
  Severity: HIGH
  Source: Solodit (row_id 1567)
  Summary: The contract transfers tokens to an attacker-controlled address before updating the sender's internal balance. A token implementing `tokensReceived` (ERC777) or `onTransferReceived` (ERC1363) triggers the attacker's fallback mid-execution. The attacker re-enters the same function, double-spends the in-flight amount, and exits with double the tokens. CEI ordering and `nonReentrant` both fix this.
  Map to: transfer, transferFrom

---

- Pattern: self-transfer accounting exploit — rewards drained via transfer-to-self
  Where it hit: `ResolvStakingV2` — user transfers staking tokens to themselves; internal accounting credits the full reward snapshot again without any net token movement
  Severity: HIGH
  Source: Solodit (row_id 799)
  Summary: The transfer handler updates reward checkpoints as though a real balance change occurred. A self-transfer (sender == recipient) triggers the checkpoint update with no actual movement of funds, resetting the reward accumulator in the caller's favour. Repeating this in a loop drains all pending rewards from other stakers. The fix is to add `require(from != to)` in the transfer hook.
  Map to: transfer, transferFrom


## Step Execution Checklist (MANDATORY)

> **CRITICAL**: You MUST report completion status for ALL sections. Findings with incomplete sections will be flagged for depth review.

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Token Entry Points | YES | ✓/✗/? | |
| 2. Token State Tracking | YES | ✓/✗/? | |
| 3. Token Exit Points | YES | ✓/✗/? | |
| 4. Token Type Separation | IF multi-token | ✓/✗(N/A)/? | |
| 5. Unsolicited Transfer Analysis | YES | ✓/✗/? | |
| 5b. Unsolicited Transfer Matrix (All Types) | **YES** | ✓/✗/? | **MANDATORY** - never skip |
| 6. Token Flow Checklist | YES | ✓/✗/? | |
| 7. Cross-Token Interactions | IF multi-token | ✓/✗(N/A)/? | |
| 8. External Call Return Type | **YES** | ✓/✗/? | **MANDATORY** - never skip |
| 9. Transfer Side Effects | **YES** | ✓/✗/? | **MANDATORY** - never skip |
| 9d. Side Effect Token Type | **YES** | ✓/✗/? | **MANDATORY** - never skip |

### Cross-Reference Markers

**After Section 5** (Unsolicited Transfer Analysis):
- IF staking receipts identified → **MUST complete Sections 8-9**
- IF external calls return tokens → **MUST verify return type in Section 8**

**After Section 8** (External Call Return Type):
- Cross-reference with `STAKING_RECEIPT_TOKENS.md` Section 8 for on-transfer side effects
- IF return type UNKNOWN in production → mark finding as CONTESTED

**After Section 9** (Transfer Side Effects):
- IF side effects UNKNOWN → assume YES (adversarial default per Rule 5)
- MUST document: "Assumed adversarial: [effect]. Impact if true: [trace]"

### Mandatory Forced Output

For Sections 8 and 9, you MUST produce output even if uncertain:

**Section 8 Output** (always required):
```markdown
### 8. External Call Return Type Verification
| External Call | Expected Return | Verified Production Return | Match? |
|--------------|-----------------|---------------------------|--------|
| [call] | [expected] | [verified/UNVERIFIED] | ✓/✗/? |

**If UNVERIFIED**: Finding verdict cannot be REFUTED. Use CONTESTED.
```

**Section 9 Output** (always required):
```markdown
### 9. Transfer Side Effects Analysis
| Token | On Transfer Side Effect | Verified? | Assumed Impact |
|-------|------------------------|-----------|----------------|
| [token] | [effect or UNKNOWN] | YES/NO | [impact trace] |

**Adversarial Default Applied**: [list assumptions made]
```
