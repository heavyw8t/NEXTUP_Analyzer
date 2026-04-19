---
name: "ptb-composability"
description: "Trigger Pattern PTB flag (always for Sui -- Programmable Transaction Blocks are the Sui transaction model) - Inject Into Breadth agents, depth-external, depth-state-trace"
---

# Skill: PTB_COMPOSABILITY (Sui)

> **Trigger Pattern**: PTB flag (always for Sui -- Programmable Transaction Blocks are the Sui transaction model)
> **Inject Into**: Breadth agents, depth-external, depth-state-trace
> **Finding prefix**: `[PTB-N]`
> **Rules referenced**: R4, R5, R8, R10, R15

Programmable Transaction Blocks (PTBs) are Sui's transaction composition primitive. A single PTB can contain up to 1024 commands, each calling a different function, with return values routed between commands. This enables atomic multi-step sequences that are fundamentally different from EVM's single-entry-point model. Every `public` function is a potential PTB command -- there is no "internal only" visibility equivalent to Solidity's `internal`.

**STEP PRIORITY**: Steps 1 (Single-Call Assumption Audit) and 4 (Atomic Read-Modify-Write) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections (6, 7) before skipping 1, 3, or 4.

---

## 1. Entry Point Inventory

For EVERY `public` and `entry` function in the protocol, classify composability:

| # | Function | Module | Visibility | Returns Value? | Takes Shared Obj? | Composable in PTB? | Notes |
|---|----------|--------|-----------|---------------|-------------------|-------------------|-------|
| 1 | {func} | {mod} | public / entry / public(package) | YES / NO | YES / NO | YES / NO | {context} |

**Sui visibility semantics**:
- `entry` functions: callable from PTB but return values CANNOT be used by subsequent commands (consumed or discarded within the command). Objects can only be transferred, not returned.
- `public` functions: fully composable -- return values pass between commands. This is the primary composability surface.
- `public(package)`: callable only by other modules in the same package. NOT callable from PTB. Safe from external composition.
- `fun` (private): Not callable from outside the module. Safe.

**Key observation**: Any function that is `public` (not `entry`, not `public(package)`) is fully composable. Its return values can be routed to ANY other function in the same PTB.

### 1b. Single-Call Assumption Audit

For EVERY `public` and `entry` function, check whether its security model implicitly assumes it is the ONLY function called in the transaction:

| # | Function | Assumes Single-Call? | What Assumption? | Breakable via PTB? | Impact |
|---|----------|---------------------|-----------------|-------------------|--------|
| 1 | {func} | YES/NO | {describe assumption} | YES/NO | {impact} |

**Common single-call assumptions that PTBs break**:
- **Post-call state check**: Function reads state, performs action, then a SEPARATE function checks the result. Attacker inserts commands between action and check.
- **Balance snapshot**: Function reads a balance at start, assumes balance changed only due to its work. Another PTB command could have changed the balance.
- **One-operation-per-transaction**: Protocol assumes a user can only deposit OR withdraw in a single transaction. PTB allows deposit + borrow + withdraw atomically.
- **Temporal separation**: Protocol assumes time must pass between action A and action B (cooldown). If both functions are callable, PTB executes them in the same transaction with zero time delta.
- **Reentrancy-like patterns**: Function A updates state partially, function B reads partial state. PTBs naturally enable "call A then call B" -- state IS updated between commands.

**Key question for each function**: "If an attacker calls this function as command N in a PTB, and can execute arbitrary commands 1..N-1 before it and N+1..1024 after it, what can go wrong?"

---

## 2. Multi-Step Composition Analysis

For each `public` function that returns objects:

| # | Function | Input Objects | Output Objects | Can Output Be Routed To? | Can Be Called Multiple Times? |
|---|----------|-------------|---------------|-------------------------|----------------------------|
| 1 | {func} | {owned/shared/immutable} | {Coin<T> / Object / HotPotato} | {any function accepting this type} | YES/NO |

**Return value routing checks**:
- **Coin routing**: If function A returns `Coin<T>`, can it be routed to function C (external) instead of intended function B?
- **Coin splitting**: PTB has native `SplitCoins` command. Returned `Coin<T>` can be split. Does protocol assume full amount passed?
- **Coin merging**: PTB has native `MergeCoins` command. Can attacker merge extra coins to inflate amounts?
- **Mutable reference routing**: `&mut Object` references are borrowed for a command and released after. Same object can be passed to multiple commands sequentially. Does command N assume the object wasn't modified by command N-1?
- **Recipient mismatch**: If function returns a value-bearing object, the final `TransferObjects` command determines the recipient.

### 2b. Value Interception Pattern

Model this specific attack for each function returning value:

```
1. Attacker calls protocol_function_A() -> returns Coin<USDC> (intended for pool)
2. Attacker routes Coin<USDC> to their own address via TransferObjects
3. Protocol expects the Coin was consumed by the next step but it was intercepted
```

**Check**: Does the protocol rely on PTB command ordering to ensure returned values reach the right destination? If YES -> the user controls the ordering, not the protocol.

---

## 3. Flash Loan via PTB

Without explicit flash loan protocols, PTBs enable flash-loan-like patterns:

```
1. [Command 1] Split large Coin<SUI> from attacker's balance
2. [Command 2] Deposit into protocol (inflates TVL/balance)
3. [Command 3] Trigger reward distribution (calculated on inflated balance)
4. [Command 4] Withdraw from protocol
5. [Command 5] Join coins back (net zero capital, captured rewards)
```

**Can protocol state be manipulated between PTB commands?**

| Function Pair | Shared State | Deposit-Action-Withdraw Possible? | Defense? |
|--------------|-------------|----------------------------------|---------|
| {deposit, claim} | {pool balance} | YES/NO | {cooldown? same-epoch check? minimum lock?} |

**Hot potato flash loan pattern**:
```
1. borrow(pool, amount) -> (Coin<T>, FlashReceipt)     // Creates hot potato
2. [attacker does arbitrary operations with Coin<T>]
3. repay(pool, coin, receipt)                            // Consumes hot potato
```

**Checks for hot potato flash loans**:
- Does `repay()` verify returned amount >= borrowed amount + fee?
- Can attacker call OTHER protocol functions between borrow and repay that benefit from temporarily inflated balance?
- Is `FlashReceipt` type-parameterized to prevent cross-pool receipt reuse?
- Verify hot potato struct has NO abilities (no `key`, `store`, `drop`, `copy`)

---

## 4. Shared Object Mutation Ordering

Within a PTB touching shared objects:

### 4a. Oracle Manipulation Within PTB

```
1. [Command 1] Call DEX swap to move on-chain price
2. [Command 2] Call protocol function that reads manipulated price
3. [Command 3] Reverse DEX swap to restore price
4. Net effect: Protocol acted on manipulated price, attacker profited
```

**Check**: Does protocol read spot prices (manipulable) or TWAP/oracle prices (resistant)?

### 4b. Balance Manipulation Within PTB

```
1. [Command 1] Deposit large amount (inflate balance/shares)
2. [Command 2] Trigger reward distribution (on inflated balance)
3. [Command 3] Withdraw deposited amount
4. Net effect: Captured rewards with zero time commitment
```

### 4c. State Toggling Within PTB

```
1. [Command 1] Set state to value A (e.g., via AdminCap function)
2. [Command 2] Perform action requiring state A
3. [Command 3] Reset state back to original value B
4. Net effect: Privileged action performed, state appears unchanged
```

**Check**: Possible if attacker controls an AdminCap? (Rule 6: semi-trusted role analysis)

### 4d. Shared Object Reorder Sensitivity

| Shared Object | Invariant | Commands That Mutate It | Sequence-Dependent? | Exploitable? |
|--------------|-----------|------------------------|-------------------|-------------|
| {obj} | {invariant description} | {cmd1, cmd2, cmd3} | YES/NO | {if YES, describe exploit} |

**Check for each shared object**: Write down the invariant. Can a sequence of 2-3 valid individual operations (each maintaining the invariant) produce a combined state that violates the invariant?

---

## 5. Hot Potato Enforcement

For each zero-ability struct (hot potato):

| # | Hot Potato Type | Created By | Consumed By | Abilities | Bypass Possible? |
|---|----------------|-----------|-------------|-----------|-----------------|
| 1 | {Receipt} | {borrow()} | {repay()} | NONE (confirmed) | {analysis} |

**Checks**:
- [ ] Verify struct has NO abilities. If it has `drop` -> NOT a hot potato.
- [ ] Is the consuming function the ONLY function accepting this type?
- [ ] Can multiple hot potatoes be created in a single PTB? Does consumption order matter?
- [ ] Does consuming function validate the hot potato matches the creating context?
- [ ] Can attacker cause consumption precondition to fail AFTER hot potato created? (entire PTB aborts -- griefing vector)
- [ ] Can a wrapper with `store` ability store the hot potato? (bypass via external module -- check for public generic wrappers)

---

## 6. Object Wrapping/Unwrapping in PTB

Can objects be wrapped, manipulated, and unwrapped within a single PTB to bypass checks?

| Wrap Operation | Unwrap Operation | What's Inside | Check Bypassed? |
|---------------|-----------------|-------------|----------------|
| {wrap_func} | {unwrap_func} | {object with restrictions} | {describe bypass or NONE} |

**Pattern**: Object has transfer restrictions (`key` only, no `store`). Attacker wraps it inside a `store`-capable struct, transfers the wrapper, then unwraps on the other side. If wrap and unwrap are both `public` functions -> transfer restriction bypassed within a single PTB.

---

## 7. Gas Budget Manipulation

PTB gas budget is shared across all commands.

| Attack Vector | Description | Check |
|--------------|-------------|-------|
| **Many-small-operations** | 1000+ tiny operations to circumvent aggregate limits | Do aggregate limits track across PTB commands? |
| **Object creation spam** | PTB creates many objects (up to 1024 per PTB) | Unbounded object creation paths? |
| **Gas exhaustion griefing** | Craft PTB that consumes max gas on revert | Gas charged on abort -- attacker pays |

**Typically lower severity**: Sui's gas model charges the sender, so resource attacks are self-penalizing. Focus on aggregate limit bypass.

---

## Output Schema

```markdown
## Finding [PTB-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED / CONTESTED
**Step Execution**: check1,2,3,4,5,6,7 | skip(reason) | uncertain
**Rules Applied**: [R4:___, R5:___, R8:___, R10:___, R15:___]
**Severity**: Critical/High/Medium/Low/Info
**Location**: sources/{module}.move:LineN

**PTB Attack Type**: SINGLE_CALL_ASSUMPTION / RETURN_VALUE_ROUTING / FLASH_LOAN_VIA_PTB / ATOMIC_MANIPULATION / HOT_POTATO_BYPASS / WRAP_UNWRAP_BYPASS / AGGREGATE_LIMIT
**Attack Sequence**:
1. [Command 1]: {what attacker does}
2. [Command 2]: {what attacker does}
3. [Command N]: {what attacker does}
**Net Effect**: {what the attacker gained}

**Description**: What is wrong
**Impact**: What can happen (fund loss, unfair value capture, invariant violation)
**Evidence**: Code showing vulnerability + PTB command sequence
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Sourced from: Trail of Bits blog (Sep 2025), Monethic Sui security workshop, Mirage Audits blog, SlowMist Sui Move Auditing Primer, Dedaub/Cyfrin Cetus post-mortem, Sui documentation, local CSV (1 hit).
> Tags: PTB, programmable_transaction, MoveCall, composability, atomic_composition

---

## Finding [PTB-E1]: PTB Gas Refund Absent on Failed on_call Causes Signer Insolvency

**Source**: Local CSV row 1608 (MEDIUM, Move)
**Protocol Category**: Cross-chain gateway / TSS bridge
**Severity**: Medium

**PTB Attack Type**: SINGLE_CALL_ASSUMPTION

**Description**: A `withdraw_and_call` mechanism on Sui uses a single PTB composed of two commands: a withdrawal and an `on_call` callback. If the `on_call` command fails, the entire PTB reverts atomically, including the gas-fee deduction from the TSS signer. Because no separate PTB exists to refund the gateway for consumed gas on revert, repeated failures leave the signer paying gas without making progress, leading to insolvency and DoS of gateway nodes.

**Attack Sequence**:
1. [Command 1] `withdraw` executes, moving funds to recipient.
2. [Command 2] `on_call` (recipient contract) deliberately reverts.
3. Entire PTB rolls back. Gateway signer loses gas. No refund path exists.
4. Attacker repeats to drain the signer's SUI balance.

**Net Effect**: Gateway node insolvency; DoS on cross-chain withdrawal processing.

**Root Cause**: Protocol assumes a two-command PTB is atomic in a way that protects the gateway from adversarial callee reversion. Gas is not ring-fenced in a separate PTB.

**References**: solodit_findings.dedup.csv row 1608

---

## Finding [PTB-E2]: Nested PTB Call Resets Snapshot Mid-Operation, Bypassing Minimum Return Check

**Source**: Monethic Sui Move Security Workshop writeup (2024)
**Protocol Category**: DEX / yield aggregator
**Severity**: High

**PTB Attack Type**: SINGLE_CALL_ASSUMPTION / ATOMIC_MANIPULATION

**Description**: A `start_harvest()` function records `saved_reserves` at the beginning of an operation to later enforce a minimum return invariant. Because `start_harvest()` is a `public` function, an attacker can call it as an intermediate PTB command *after* a first call already set `saved_reserves`. The second call resets `saved_reserves` to the current (post-manipulation) balance, erasing the baseline. The minimum-return check then compares the final state against the manipulated snapshot, not the original one, and passes.

**Attack Sequence**:
1. [Command 1] Attacker calls `start_harvest()` — `saved_reserves` = 1000.
2. [Command 2] Attacker removes liquidity or drains via another public function — reserves drop to 500.
3. [Command 3] Attacker calls `start_harvest()` again — `saved_reserves` reset to 500.
4. [Command 4] Operation concludes. Minimum-return check compares final 500 against saved 500: passes.
5. Attacker nets the drained 500 tokens with no invariant violation flagged.

**Net Effect**: Minimum-return invariant bypassed; attacker extracts funds that should have been protected.

**Root Cause**: Public visibility of snapshot-setting function combined with no guard preventing multiple calls within a single PTB.

**References**: https://medium.com/@monethic/sui-move-security-workshop-writeup-material-480c5e7d1da3

---

## Finding [PTB-E3]: Hot Potato with `drop` Ability Allows Flash Receipt Abandonment

**Source**: Mirage Audits — "The Ability Mistakes That Will Drain Your Sui Move Protocol" (2025)
**Protocol Category**: Lending / flash loan
**Severity**: Critical

**PTB Attack Type**: HOT_POTATO_BYPASS

**Description**: A flash-loan receipt (hot potato) struct was found in production with the `drop` ability set. A correct hot potato enforces repayment by requiring the receipt to be *consumed* (passed to `repay()`). Adding `drop` allows the PTB to silently discard the receipt at the end of the transaction without ever calling `repay()`, eliminating the repayment obligation entirely.

**Attack Sequence**:
1. [Command 1] `borrow(pool, amount)` — returns `(Coin<T>, FlashReceipt)`.
2. [Command 2] Attacker uses `Coin<T>` as desired (arbitrage, liquidation, etc.).
3. [Command 3] PTB ends. `FlashReceipt` is *dropped* (not passed to `repay()`).
4. Transaction succeeds. Loan is never repaid.

**Net Effect**: Full flash loan principal extracted with zero repayment; protocol drained.

**Root Cause**: `drop` ability on enforcement struct; abilities must be checked as the first audit step before reading implementation logic.

**References**: https://www.mirageaudits.com/blog/sui-move-ability-security-mistakes

---

## Finding [PTB-E4]: PTB Atomic Deposit-Harvest-Withdraw Captures Rewards Without Time Commitment

**Source**: Trail of Bits blog — "How Sui Move rethinks flash loan security" (Sep 2025); Sui PTB documentation
**Protocol Category**: Yield / staking
**Severity**: High

**PTB Attack Type**: FLASH_LOAN_VIA_PTB

**Description**: A staking or yield protocol that distributes rewards based on a point-in-time balance check is vulnerable to atomic deposit-harvest-withdraw within a single PTB. Because all PTB commands execute atomically and state changes are applied after all commands complete, a depositor can inflate the balance for reward calculation and immediately withdraw, capturing rewards with zero time exposure.

**Attack Sequence**:
1. [Command 1] `SplitCoins` — attacker prepares large `Coin<SUI>` from wallet.
2. [Command 2] `deposit(pool, large_coin)` — pool balance inflates, attacker's share of rewards increases.
3. [Command 3] `claim_rewards(pool)` — reward distribution is computed on inflated balance.
4. [Command 4] `withdraw(pool, shares)` — attacker exits fully.
5. [Command 5] `MergeCoins` — attacker consolidates coins. Net: zero capital committed, rewards captured.

**Net Effect**: Reward dilution for honest long-term depositors; protocol reward reserve drained.

**Root Cause**: Protocol assumes time separation between deposit and harvest. PTB collapses that assumption to zero.

**References**: https://blog.trailofbits.com/2025/09/10/how-sui-move-rethinks-flash-loan-security/

---

## Finding [PTB-E5]: `public` Function Return Value Intercepted Before Reaching Intended Recipient

**Source**: Sui PTB documentation; Monethic workshop; SlowMist Sui Auditing Primer
**Protocol Category**: DEX / payment routing
**Severity**: High

**PTB Attack Type**: RETURN_VALUE_ROUTING

**Description**: A `public` function returns `Coin<T>` that is intended by the protocol's design to flow into the next protocol function (e.g., a liquidity pool). Because `public` return values are freely routable within a PTB, the caller can instead direct the returned coin to `TransferObjects` pointing at the attacker's address. The protocol has no mechanism to enforce where the return value goes after the function exits.

**Attack Sequence**:
1. [Command 1] `protocol_redeem(vault, shares)` — returns `Coin<USDC>` (intended for pool deposit).
2. [Command 2] `TransferObjects([Coin<USDC>], attacker_address)` — coin goes to attacker instead.
3. Protocol's assumed invariant (coin re-enters pool) is never enforced.

**Net Effect**: Value leak; attacker extracts redeemed coins that should have been recycled into the protocol.

**Root Cause**: Protocol relied on PTB command ordering convention rather than type-level enforcement (e.g., a consuming function or hot potato) to route return values.

**References**: https://docs.sui.io/concepts/transactions/prog-txn-blocks; https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc

---

## Finding [PTB-E6]: On-Chain Spot Price Manipulated and Read Within Single Atomic PTB

**Source**: SlowMist Sui Auditing Primer; Monethic workshop; Sui oracle documentation
**Protocol Category**: Lending / derivatives
**Severity**: High

**PTB Attack Type**: ATOMIC_MANIPULATION

**Description**: A lending or derivatives protocol reads an on-chain DEX spot price to determine collateral value or liquidation eligibility. Because PTB commands execute in-order and atomically, an attacker can (1) execute a large swap to shift the DEX spot price, (2) call the protocol function that reads the now-manipulated price, and (3) reverse the swap, all within a single PTB. The protocol sees the manipulated price and performs the action (borrow, liquidate, etc.) on the attacker's terms.

**Attack Sequence**:
1. [Command 1] Large swap on DEX pool (e.g., sell TOKEN for SUI) — spot price of TOKEN drops.
2. [Command 2] `liquidate(borrower_position)` — lending protocol reads manipulated spot price, considers position undercollateralized.
3. [Command 3] Reverse swap — spot price restored.
4. Attacker received liquidation bonus based on artificial price.

**Net Effect**: Unfair liquidation of healthy positions; attacker captures liquidation bonus.

**Root Cause**: Protocol relies on DEX spot price (single-block, manipulable) instead of a TWAP or external oracle.

**References**: https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc

---

## Finding [PTB-E7]: Object Wrapping Inside `store`-Capable Struct Bypasses Transfer Restriction

**Source**: Sui Move documentation (object abilities); SlowMist Sui Auditing Primer; Mirage Audits
**Protocol Category**: NFT / soulbound token / restricted asset
**Severity**: Medium

**PTB Attack Type**: WRAP_UNWRAP_BYPASS

**Description**: An object with only the `key` ability (no `store`) cannot be stored inside another struct or transferred via PTB's `TransferObjects` directly. However, if the protocol exposes a `public wrap(obj: RestrictedAsset): Wrapper` function where `Wrapper` has the `store` ability, an attacker can wrap the restricted asset into a transferable container, transfer the container to a new address via `TransferObjects`, then unwrap it with a corresponding `public unwrap` function — all within a single PTB. The transfer restriction is nullified.

**Attack Sequence**:
1. [Command 1] `wrap(restricted_asset)` — returns `Wrapper { inner: RestrictedAsset }` with `store`.
2. [Command 2] `TransferObjects([wrapper], attacker_address_2)` — wrapper transferred freely.
3. [Command 3 — separate PTB by attacker_address_2] `unwrap(wrapper)` — restricted asset recovered at new address.

**Net Effect**: Soulbound or non-transferable assets become freely transferable.

**Root Cause**: Public generic wrap/unwrap functions allow bypassing `key`-only transfer restrictions at the object level.

**References**: https://docs.sui.io/concepts/sui-move-concepts; https://www.mirageaudits.com/blog/sui-move-ability-security-mistakes

---

## Finding [PTB-E8]: `withdraw_and_call` Fails to Isolate Gas Payment, Enabling Grief Attack on TSS Node

**Source**: Local CSV + cross-reference with Sui cross-chain gateway patterns (MoveBit disclosure Oct 2024)
**Protocol Category**: Cross-chain bridge / TSS gateway
**Severity**: Medium

**PTB Attack Type**: SINGLE_CALL_ASSUMPTION

**Description**: Distinct from PTB-E1 (same root, different vector): in addition to signer insolvency, an adversary who can cause the `on_call` leg to revert on demand can selectively block all cross-chain withdrawals for targeted recipients. Because the entire PTB reverts on `on_call` failure and the TSS node must re-sign a new PTB, the attacker forces the gateway into an unbounded re-signing loop for any destination address they control.

**Attack Sequence**:
1. Attacker deploys a destination contract whose `on_call` function always reverts.
2. Attacker requests a cross-chain withdrawal to this address.
3. Gateway TSS node signs and submits the PTB. `on_call` reverts. PTB reverts. Gas lost.
4. Gateway must retry indefinitely. No progress. Gateway eventually runs out of SUI.

**Net Effect**: DoS on the gateway for any targeted address; potential full signer insolvency.

**Root Cause**: Cross-chain gateway PTB does not separate the asset transfer from the callback into independent PTBs with independent gas budgets.

**References**: https://www.movebit.xyz/blog/post/MoveBit-Discovers-and-Helps-Fix-Vulnerability-in-Sui-Cross-Chain-Protocol-20241012.html; local CSV row 1608

---

## Finding [PTB-E9]: Aggregate Limit Bypass via 1024-Command Object Creation Spam

**Source**: Sui documentation (PTB limits); SlowMist Sui Auditing Primer
**Protocol Category**: NFT launchpad / gaming
**Severity**: Low-Medium

**PTB Attack Type**: AGGREGATE_LIMIT

**Description**: Protocols that enforce per-transaction object creation limits (e.g., max mints per TX) solely via function-level counters can be bypassed by calling the mint function multiple times within a single PTB. A PTB can contain up to 1024 commands; if `mint()` is `public` and checks only a local counter that does not persist across commands, an attacker can call it 1024 times in one PTB and circumvent the intended per-transaction cap.

**Attack Sequence**:
1. [Command 1..1024] Call `mint(collection)` 1024 times in a single PTB.
2. Each call sees the same pre-transaction state for the per-transaction counter (if counter is not shared-object-backed).
3. 1024 NFTs minted in one transaction, violating the intended 1-per-tx limit.

**Net Effect**: Fair-launch invariant broken; attacker corners supply.

**Root Cause**: Per-transaction limit stored in local/stack variable rather than a shared object that accumulates mutations within the PTB.

**References**: https://docs.sui.io/concepts/transactions/prog-txn-blocks; https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc

---

## Finding [PTB-E10]: Admin State Toggle Within PTB Executes Privileged Action While Leaving State Unchanged

**Source**: Sui Move security analysis; Monethic workshop pattern generalization
**Protocol Category**: Protocol governance / admin
**Severity**: Medium (High if AdminCap compromised)

**PTB Attack Type**: ATOMIC_MANIPULATION (State Toggling)

**Description**: A protocol exposes `pause(cap)` and `unpause(cap)` as `public` functions controlled by an AdminCap. A separate admin function `restricted_action()` requires the protocol to be *paused* to execute (e.g., an emergency drain). A malicious or compromised admin can call `pause → restricted_action → unpause` in a single PTB, executing the privileged action while the on-chain state appears to never have changed (starts and ends unpaused). Off-chain monitoring that only reads final state will not detect the intermediate pause.

**Attack Sequence**:
1. [Command 1] `pause(admin_cap)` — protocol enters paused state.
2. [Command 2] `restricted_action(admin_cap, ...)` — drains or reconfigures protocol.
3. [Command 3] `unpause(admin_cap)` — protocol returns to active state.
4. Final on-chain state: unpaused. Event logs may not emit pause/unpause if poorly instrumented.

**Net Effect**: Privileged operation executed with no visible protocol state change; monitoring bypassed.

**Root Cause**: Semi-trusted admin role assumed to follow multi-step governance process. PTB collapses multi-step into a single atomic transaction.

**References**: Monethic Sui security workshop (State Toggling pattern); SKILL.md Step 4c


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Entry Point Inventory | YES | | All public/entry functions classified |
| 1b. Single-Call Assumption Audit | YES | | **HIGH PRIORITY** -- every public function checked |
| 2. Multi-Step Composition Analysis | YES | | All return values checked |
| 2b. Value Interception Pattern | YES | | Value-returning functions modeled |
| 3. Flash Loan via PTB | YES | | Deposit-action-withdraw patterns |
| 4. Shared Object Mutation Ordering | YES | | **HIGH PRIORITY** -- oracle, balance, state toggle |
| 4d. Shared Object Reorder Sensitivity | YES | | Invariant + multi-command sequences |
| 5. Hot Potato Enforcement | IF hot potatoes exist | | Zero-ability verified |
| 6. Object Wrapping/Unwrapping | IF wrap/unwrap functions exist | | Transfer restriction bypass |
| 7. Gas Budget Manipulation | IF aggregate limits exist | | |

### Cross-Reference Markers

**After Step 1b**: If single-call assumption found on fund-critical function -> immediate HIGH finding.

**After Step 3**: Cross-reference with SHARE_ALLOCATION_FAIRNESS for deposit-action-withdraw reward capture.

**After Step 4a**: Cross-reference with ORACLE_ANALYSIS if on-chain DEX prices are used.

**After Step 5**: Cross-reference with ABILITY_ANALYSIS Section 5 (Hot Potato Enforcement).

If any step skipped, document valid reason (N/A, no hot potatoes, no external calls, no aggregate limits).
