---
name: "flash-loan-interaction"
description: "Trigger Pattern FLASH_LOAN flag (required) or BALANCE_DEPENDENT flag (optional complement) - Inject Into Breadth agents, depth-token-flow, depth-edge-case"
---

# FLASH_LOAN_INTERACTION Skill (Solana)

> **Trigger Pattern**: FLASH_LOAN flag (required) or BALANCE_DEPENDENT flag (optional complement)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case

**Key Solana difference**: There is no callback model. Flash loans work via instruction composition in a single transaction. The attack pattern is: IX1 borrow -> IX2 manipulate -> IX3 exploit -> IX4 repay - all sequential instructions in one transaction.

For every flash-loan-accessible state variable or precondition in the protocol:

**Step Priority**: Steps 5 (Defense Audit) and 5b (Defense Parity) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections (0c, 4) before skipping 5, 5b, or 3d.

## 0. External Flash Susceptibility Check

Before analyzing the protocol's OWN flash loan paths, check whether external programs the protocol CPIs to have state manipulable by a third party within the same transaction.

### 0a: External Interaction Inventory

| External Program | Interaction Type | State Read by Our Program | Can 3rd Party Manipulate That State in Same Tx? |
|------------------|-----------------|---------------------------|------------------------------------------------|
| {DEX/AMM/vault} | {swap/deposit/price query} | {reserves, price, balance} | {YES if spot state / NO if TWAP or slot-gated} |

### 0b: Third-Party Flash Attack Modeling (Instruction Composition)

For each external state marked YES in 0a, model:
1. **IX1 - BORROW**: Flash-borrow via lending program instruction
2. **IX2 - MANIPULATE**: Instruction to external program that changes state X (e.g., swap to move pool reserves)
3. **IX3 - VICTIM CALL**: Instruction to OUR program that reads manipulated state X
4. **IX4 - RESTORE**: Instruction to reverse external manipulation (reverse swap)
5. **IX5 - REPAY**: Instruction to repay flash loan
6. **IMPACT**: What did the attacker gain from our program acting on manipulated state?

**Key question**: Does our program use **spot state** (manipulable within tx) or **time-weighted/slot-gated state** (resistant)?

<!-- LOAD_IF: DEX_INTERACTION -->
### 0c: DEX Price Manipulation Cost Estimation

For each external DEX/AMM whose spot state is read by the program, estimate manipulation cost:

| Pool | Liquidity (USD) | Target Price Change | Est. Trade Size | Slippage Cost | Program Extractable Value | Profitable? |
|------|----------------|--------------------:|----------------|--------------|---------------------------|-------------|
| {pool} | {TVL} | {%} | {USD} | {USD} | {USD} | {YES/NO} |

**Cost formula**: `manipulation_cost = slippage * trade_size`. If `manipulation_cost < extractable_value` -> VIABLE.
<!-- END_LOAD_IF: DEX_INTERACTION -->

## 1. Flash-Loan-Accessible State Inventory

Enumerate ALL program state that can be manipulated within a single transaction via flash-borrowed capital or instruction composition:

| State Variable / Account | Location | Read By | Write Path | Flash-Accessible? | Manipulation Cost |
|--------------------------|----------|---------|------------|-------------------|-------------------|
| `token_account.amount` | {account} | {instructions} | SPL transfer (anyone) | YES | 0 (unsolicited) |
| `vault.total_value` | {PDA} | {instructions} | deposit instruction | YES if permissionless | Deposit amount |
| AMM pool reserves | {pool account} | {instructions} | Swap instruction | YES | Slippage cost |
| Oracle price account | {oracle PDA} | {instructions} | Oracle update IX | YES if same-slot | Market depth |
| Threshold/quorum state | {governance PDA} | {instructions} | Stake/vote IX | YES | Threshold amount |

**For each YES entry**: trace all instructions that READ this state and make decisions based on it.

**Rule 15 check**: For each balance/oracle/threshold/rate precondition, model the instruction composition atomic sequence.

## 2. Atomic Attack Sequence Modeling (Instruction Composition)

For each flash-loan-accessible state identified in Step 1:

### Attack Template (Solana Transaction with Multiple Instructions)
```
TX containing ordered instructions:
  IX1 - BORROW:     Flash-borrow {amount} of {token} from {lending program}
  IX2 - MANIPULATE:  {action} to change {state_variable} from {value_before} to {value_after}
  IX3 - CALL:        Invoke {target_instruction} on our program which reads manipulated state
  IX4 - EXTRACT:     {what_is_gained} - quantify: {amount}
  IX5 - RESTORE:     {action} to return state (if needed for repayment)
  IX6 - REPAY:       Return {amount + fee} to flash loan source

  PROFIT: {extract - fee - tx_fee} = {net_profit}
```

**Profitability gate**: If net_profit <= 0 for all realistic amounts -> document as NON-PROFITABLE but check Step 3 for multi-instruction chains.

**For each sequence, verify**:
- [ ] Can IX2-IX5 execute atomically in one transaction?
- [ ] Does any instruction fail under normal conditions?
- [ ] Is the manipulation detectable/preventable by the program?
- [ ] What is the minimum flash loan amount needed?
- [ ] Does compute unit budget allow the full sequence?

## 3. Cross-Instruction Flash Loan Chains

Model multi-instruction atomic sequences within a single transaction:

| Step | Instruction | State Before | State After | Enables Next Step? |
|------|-------------|-------------|------------|-------------------|
| IX1 | {program_A.instruction_X} | {state} | {state'} | YES - changes {X} |
| IX2 | {program_B.instruction_Y} | {state'} | {state''} | YES - enables {Y} |
| IXN | {program_N.instruction_Z} | {state^N} | {final} | EXTRACT profit |

**Key question**: Can calling instruction A then instruction B in the same transaction produce a state that neither instruction alone could create?

**Common multi-instruction patterns**: Deposit->manipulate oracle->withdraw, stake->trigger reward->unstake, transfer to inflate balance->price-dependent IX->transfer back, multiple CPIs with state mutation between.

### 3b. Flash-Loan-Enabled Debounce DoS
For each permissionless instruction with a cooldown affecting OTHER users (epoch/slot/global timestamp): can attacker compose borrow->debounced IX->trigger cooldown, blocking legitimate callers?

| Instruction | Cooldown Scope | Shared Across Users? | Flash-Triggerable? | DoS Duration |
|-------------|---------------|---------------------|-------------------|-------------|

If global/shared AND permissionless AND flash-triggerable -> FINDING (R2, minimum Medium). **Solana-specific**: `Clock::get()?.slot`/`epoch` cooldowns shorter than 1 slot are ineffective against same-slot composition.

### 3c. No-Op Resource Consumption
For each state-modifying instruction with a limited-use resource (cooldown, one-time flag, nonce, epoch-bound action):
Can it be called with parameters producing zero economic effect (amount=0, same-token swap, self-transfer) while consuming the resource?

| Instruction | Resource Consumed | No-Op Parameters | Resource Wasted? | Impact |
|-------------|------------------|-----------------|-----------------|--------|

If a no-op call consumes a resource blocking legitimate use -> FINDING (R2, resource waste).

### 3d. External Flash x Debounce Cross-Reference (MANDATORY)

For EACH external program flagged as flash-susceptible in Section 0:

| External Program | Flash-Accessible Action | Debounce/Cooldown Affected (from 3b) | Combined Severity |
|------------------|------------------------|--------------------------------------|-------------------|

If YES: (1) permanent or temporary consumption? (2) on-chain reset path? (3) combined severity = HIGHER of the two. Tag: `[TRACE:flash({external})->ix({debounce_fn})->cooldown consumed->{duration}]`. If no debounce from 3b: N/A.

<!-- LOAD_IF: BALANCE_DEPENDENT -->
## 4. Flash Loan + Donation Compound Attacks

Combine flash loan capital with unsolicited SPL/SOL transfers:

| Donation Target | Flash Loan Action | Combined Effect | Profitable? |
|-----------------|-------------------|-----------------|-------------|
| vault token_account.amount | Deposit/withdraw | Rate manipulation | {YES/NO} |
| AMM pool token account | Swap | Price oracle manipulation | {YES/NO} |
| governance staking account | Vote/propose | Quorum manipulation | {YES/NO} |

**Check**: Can a flash-borrowed amount be transferred (not deposited) to the protocol's token account to manipulate `token_account.amount` accounting, and then extracted via a subsequent instruction within the same transaction?

**Solana-specific**: Unsolicited SPL transfers are trivially cheap (no function call needed on receiver side). Anyone who knows the token account address can transfer tokens to it.
<!-- END_LOAD_IF: BALANCE_DEPENDENT -->

## 5. Flash Loan Defense Audit

For each flash-loan-accessible attack path identified:

| Defense | Present? | Effective? | Bypass? |
|---------|----------|------------|---------|
| Anchor reentrancy guard (`#[access_control]`) | YES/NO | {analysis} | {if YES: how} |
| Same-slot prevention (`last_slot` check) | YES/NO | {analysis} | Multi-slot possible? |
| TWAP instead of spot price | YES/NO | TWAP window length: {N slots} | Short TWAP vulnerable? |
| Epoch-based cooldown | YES/NO | Duration: {N epochs} | Bypass via epoch boundary? |
| Balance snapshot (pre/post CPI comparison) | YES/NO | {analysis} | {if YES: how} |
| Flash loan fee exceeds profit | YES/NO | Fee: {X}, max profit: {Y} | Fee < profit? |
| Instruction introspection (sysvar check) | YES/NO | Checks for: {what} | Spoofable? |

**Solana-specific defenses**: `Clock::get()?.slot` comparison, instruction sysvar introspection (detect flash loan IX in tx), CPI depth limits (max 4), compute unit limits as implicit protection.

### 5b. Defense Parity Audit (Cross-Instruction)

For each user-facing action in multiple instructions or program versions:

| Action | Instruction A | Flash Defense | Instruction B | Flash Defense | Parity? |
|--------|--------------|---------------|--------------|---------------|---------|
| {action} | {ix_name} | {defense list} | {ix_name} | {defense list} | {GAP if different} |

**Key question**: If `deposit` has a slot-based cooldown but `deposit_v2` has NONE for the same economic action -- can attacker use `deposit_v2` as the undefended path? For each GAP: can undefended IX achieve same outcome? Does defended IX's protection become meaningless? Intentional or accidental?

## Finding Template

```markdown
**ID**: [FL-N]
**Severity**: [based on profitability and fund impact]
**Step Execution**: S0,1,2,3,4,5 | X(reasons) | ?(uncertain)
**Rules Applied**: [R2:Y, R4:Y, R10:Y, R15:Y]
**Location**: programs/vault/src/instructions/file.rs:LineN
**Title**: Instruction composition enables [manipulation] via [mechanism]
**Description**: [Full atomic instruction sequence with amounts]
**Impact**: [Quantified profit/loss with realistic flash loan amounts]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sources: Asymmetric Research, Ackee Blockchain, Halborn, CertiK, OtterSec disclosures, Mango Markets docs, local CSV (3 hits).

---

## Finding 1: marginfi - Flash Loan Repay Check Bypassed via Account Transfer Instruction

- **Protocol**: marginfi v2 (Solana lending)
- **Severity**: Critical
- **Disclosed**: 2024 (Asymmetric Research / Felix Wilhelm via bug bounty)
- **Funds at risk**: ~$160M
- **Skill tags**: `flash_loan`, `repay_check`, `invoke`
- **Attack class**: Missing repay enforcement on new instruction path

### Description

marginfi used instruction introspection via the Solana `sysvar::instructions` sysvar to verify that a `lending_account_end_flashloan` instruction appeared later in the same transaction, enforcing repayment. A new instruction, `transfer_to_new_account`, was added without updating the flash loan guard. An attacker could:

```
IX1 - borrow via flash loan on account A
IX2 - transfer_to_new_account: move liabilities from A to new account B
IX3 - lending_account_end_flashloan on account A (liabilities already transferred out, check passes)
IX4 - keep borrowed funds in account B
```

The repay check passed because it scanned account A, which no longer held the liability after the transfer.

### Root Cause

Defense parity gap (SKILL.md §5b): the existing flash loan path had the introspection guard, but the new account-transfer instruction was not blocked during an active flash loan, creating an undefended bypass path.

### Fix

Block `transfer_to_new_account` when the source account has an active flash loan. Prevent disabled accounts from being used as repayment destinations.

### Reference

https://blog.asymmetric.re/threat-contained-marginfi-flash-loan-vulnerability/

---

## Finding 2: Crema Finance - Fake Tick Account Injected in Flash Loan to Inflate Fee Claim

- **Protocol**: Crema Finance (Solana CLMM / concentrated liquidity AMM)
- **Severity**: Critical
- **Disclosed**: July 2022 (post-exploit; Ackee Blockchain, Halborn, CertiK post-mortems)
- **Funds lost**: ~$8.78M (partial return after negotiation)
- **Skill tags**: `flash_loan`, `flash_manipulation`, `invoke`, `atomic_borrow_repay`
- **Attack class**: Missing owner/PDA validation on tick account allows fake account injection

### Description

Crema Finance stored price tick data in dedicated tick accounts. The program checked that the tick account was initialized but did not validate that it was derived from the expected pool PDA or owned by the program. Attack sequence:

```
IX1 - flash-borrow large amounts from Solend (multiple liquidity pools)
IX2 - call Crema swap/liquidity instruction, pass a FAKE tick account crafted with an inflated fee accumulator
IX3 - claim fees: the fake tick account reports enormous accrued fees; protocol pays them out
IX4 - repay Solend flash loans from fee proceeds
```

Because tick price data controls fee calculation, writing a high fee value into the fake account drained the protocol's fee reserves in one transaction.

### Root Cause

Missing PDA derivation / owner check on the tick account (SKILL.md §0a, §1). Flash loan capital was used as the swap collateral needed to make the fee instruction credible.

### Fix

Derive tick accounts using `seeds = [pool.key(), tick_index]` and validate the account's owner matches the program ID before reading fee state from it.

### Reference

https://ackee.xyz/blog/2022-solana-hacks-explained-crema-finance/
https://www.halborn.com/blog/post/explained-the-crema-finance-hack-july-2022

---

## Finding 3: Nirvana Finance - Internal Spot Price Oracle Manipulated via Flash Loan

- **Protocol**: Nirvana Finance (Solana algorithmic stablecoin / yield)
- **Severity**: Critical
- **Disclosed**: July 28, 2022 (Ackee Blockchain post-mortem)
- **Funds lost**: ~$3.5M
- **Skill tags**: `flash_loan`, `flash_manipulation`, `atomic_borrow_repay`
- **Attack class**: Spot price oracle readable within same transaction; no TWAP or slot gate

### Description

Nirvana used an internal bonding-curve price oracle derived from pool reserve ratios. Flash-borrowed capital could move those reserves in the same transaction, making the oracle report a manipulated price. Attack:

```
IX1 - borrow 10M USDC from Solend (flash loan)
IX2 - deposit USDC into Nirvana pool to shift reserve ratio; internal oracle price drops
IX3 - mint ANA tokens at the manipulated (artificially low) price
IX4 - swap ANA for USDT at the original stable value, receiving 13.49M USDT
IX5 - repay Solend 10M USDC flash loan
PROFIT: ~$3.49M
```

### Root Cause

Spot-state oracle with no time-weighted averaging and no slot-based cooldown on large mints (SKILL.md §0b, §1, §2). The protocol had only an automated (no manual) audit before launch.

### Fix

Replace spot reserve-ratio oracle with a TWAP over multiple slots. Add a per-slot or per-epoch mint cooldown gated on large amounts to prevent same-transaction manipulation.

### Reference

https://ackee.xyz/blog/2022-solana-hacks-explained-nirvana/

---

## Finding 4: Mango v4 - HealthRegion Instruction Allows Flash Loan Bypass of Health Checks

- **Protocol**: Mango v4 (Solana perpetuals / lending, Blockworks Foundation)
- **Severity**: Critical (disabled by security council before exploit)
- **Disclosed**: March 18, 2023 (OtterSec audit preliminary finding)
- **Skill tags**: `flash_loan`, `invoke`, `flash_manipulation`
- **Attack class**: Composite instruction window disables health check enforcement; bankruptcy instruction exploitable within window

### Description

Mango v4 added `HealthRegionBegin` / `HealthRegionEnd` instructions as a compute-unit optimization. Within a HealthRegion, health checks are suspended. The OtterSec audit identified that an attacker could:

```
IX1 - HealthRegionBegin (health checks suspended)
IX2 - borrow tokens via flash loan (no health check enforced)
IX3 - call TokenLiqBankruptcy or other liquidation instruction in the window
IX4 - deposit tokens back
IX5 - HealthRegionEnd (health check runs on final state only)
```

An attacker composing these instructions in one transaction could extract protocol value by executing instructions that would normally be blocked by mid-transaction health enforcement.

### Root Cause

Composite instruction window (SKILL.md §3, §5): the region design assumed legitimate users; no whitelist restricted which instructions could appear inside a HealthRegion. Flash loan borrow + exploit instruction + repay is a classic Solana instruction composition attack pattern.

### Fix

Mango security council disabled `HealthRegionBegin` on March 18, 2023, pending a fix. The patch restricts which instructions are permitted inside a HealthRegion.

### Reference

https://docs.mango.markets/mango-markets/mango-markets-operations
https://blockworks.co/news/marginfi-flash-loan-bug (context on Solana flash loan audit patterns)

---

## Finding 5: Mango v4 - Flash Loan via HealthRegion + TokenLiqBankruptcy Combined Exploit (Audit Finding)

- **Protocol**: Mango v4 (reported in local CSV row 12730)
- **Severity**: HIGH (CSV sourced)
- **Skill tags**: `flash_loan`, `invoke`, `repay_check`, `flash_manipulation`
- **Attack class**: HealthRegion check suspension enables borrow-operate-deposit bypass

### Description

(Source: local CSV hit, row 12730.) The HealthRegion feature allowed multiple instructions to execute without intermediate health checks. Combined with the FlashLoan instruction, an attacker could borrow tokens, conduct operations (including `TokenLiqBankruptcy`), and deposit them back, bypassing the flash loan repayment enforcement and draining funds. A patch was implemented to only allow necessary instructions within HealthRegions.

This is the same underlying design flaw as Finding 4 but recorded as a distinct audit finding in the vulnerability database, confirming independent discovery.

### Reference

Local CSV row 12730; Mango v4 audit by OtterSec (2023).

---

## Finding 6: SwapBack Protocol - Position Account Mismatch Allows Collateral Claim Without Loan Repayment

- **Protocol**: SwapBack / unnamed (Solana, `swapback.rs`)
- **Severity**: HIGH (CSV sourced, row 7408)
- **Skill tags**: `flash_loan`, `repay_check`, `invoke`
- **Attack class**: Cross-position repayment substitution drains trading pool collateral

### Description

(Source: local CSV hit, row 7408.) `borrow_collateral` in `swapback.rs` introspects the transaction for a `repay_sol` instruction but does not verify that the `random_account_as_id` / `position_account` in the repay instruction matches the one in the borrow. Attack:

```
IX1 - open or identify a position P1 that has already been fully repaid
IX2 - borrow_collateral on position P2 (attacker wants to extract)
IX3 - repay_sol on position P1 (already repaid, no new liability discharged)
IX4 - borrow_collateral instruction sees a repay instruction in the tx and passes
IX5 - attacker claims collateral for P2 without actually repaying P2's loan
```

Any trading pool can be drained by repeating this across positions.

### Root Cause

Instruction introspection checks for the *existence* of a repay instruction but not that it targets the same position (SKILL.md §5). Classic repayment binding gap.

### Fix

Bind the borrow and repay instructions by verifying `repay_ix.position_account == borrow_ix.position_account`.

### Reference

Local CSV row 7408.

---

## Finding 7: Orca Liquidity Lockbox - Flash Loan Enables Instant Deposit-Withdraw Reward Drain

- **Protocol**: Orca LP liquidity_lockbox (Solana, concentrated liquidity rewards)
- **Severity**: MEDIUM (CSV sourced, row 9219)
- **Skill tags**: `flash_loan`, `flash_manipulation`, `atomic_borrow_repay`
- **Attack class**: No lock-up on deposit; flash capital allows instant reward claim then withdraw

### Description

(Source: local CSV hit, row 9219.) The `liquidity_lockbox` contract distributes rewards based on deposited LP position size without enforcing a lock-up period. An attacker can flash-borrow (or buy) a large amount of liquidity tokens, deposit to the lockbox to accrue a proportionally large reward snapshot, immediately withdraw, and repay. Repeating this compresses the reward pool.

```
IX1 - flash-borrow large LP tokens
IX2 - deposit into liquidity_lockbox (reward epoch snapshot taken)
IX3 - claim accrued rewards (large share due to deposit size)
IX4 - withdraw deposited positions
IX5 - repay flash loan
```

### Root Cause

No cooldown / lock-up between deposit and reward claim or withdraw (SKILL.md §3b). Flash capital inflates the attacker's share within a single slot.

### Fix

Add a minimum lock-up duration (e.g., 1 epoch) between deposit and either reward claim or withdrawal. Do not distribute rewards to a position in the same slot it was deposited.

### Reference

Local CSV row 9219.

---

## Finding 8: Generic Solana Flash Loan - Improper Instruction Introspection (load_instruction_at Unchecked)

- **Protocol**: Pattern documented across multiple Solana protocols (Trail of Bits / Crytic "not-so-smart-contracts" catalog)
- **Severity**: Critical (pattern-level)
- **Skill tags**: `flash_loan`, `repay_check`, `invoke`
- **Attack class**: Sysvar account spoofing defeats instruction introspection repay check

### Description

Solana flash loan protocols that rely on instruction introspection to confirm a repay instruction exists in the transaction must validate that the account passed as the instructions sysvar is the *real* `sysvar::instructions` account. Programs using the deprecated `load_instruction_at()` (without `_checked`) do not verify the account key. An attacker can:

```
IX1 - flash-borrow from protocol
IX2 - call borrow instruction, passing a FAKE instructions sysvar account
       (crafted to contain a fake repay instruction at the expected index)
IX3 - introspection reads fake sysvar, believes repay instruction is present
IX4 - borrow succeeds without a real repay instruction in the transaction
IX5 - attacker keeps borrowed funds
```

### Root Cause

`load_instruction_at()` is deprecated because it does not validate the sysvar account identity. Using it allows a completely spoofed instruction list (SKILL.md §5, sysvar check row).

### Fix

Always use `load_instruction_at_checked()`. In Anchor, use `#[account(address = sysvar::instructions::ID)]` on the instructions sysvar account.

### Reference

https://github.com/crytic/building-secure-contracts/blob/master/not-so-smart-contracts/solana/improper_instruction_introspection/README.md
https://solana.com/docs/core/instructions/instruction-introspection

---

## Finding 9: Solana Flash Loan Protocol - Instructions Between Borrow and Repay Not Restricted

- **Protocol**: Pattern; applies to marginfi, Solend-based flash loan consumers, and custom flash loan implementations
- **Severity**: High (pattern-level; confirmed in marginfi disclosure)
- **Skill tags**: `flash_loan`, `repay_check`, `flash_manipulation`, `invoke`
- **Attack class**: Exploit instructions inserted between borrow and repay within same transaction

### Description

Even when instruction introspection correctly confirms a repay instruction exists in the transaction, protocols that do not validate the *ordering* or *content* of instructions between borrow and repay are vulnerable. An attacker can insert arbitrary state-manipulating instructions between the borrow and repay:

```
IX1 - flash_loan_borrow (protocol sets "active flash loan" flag)
IX2 - [attacker instruction: manipulate oracle, drain fees, transfer liabilities, etc.]
IX3 - flash_loan_repay (flag cleared; protocol sees correct repayment)
```

The protocol enforces repayment but allows arbitrary side effects between borrow and repay.

### Root Cause

Instruction introspection checks confirm the repay exists but do not validate that no restricted operations occur in the window (SKILL.md §5, §5b). Marginfi's `transfer_to_new_account` bypass is one concrete instance of this broader pattern.

### Fix

Either: (a) use a CPI-based callback model that restricts the callable surface during the flash loan; or (b) enumerate and explicitly block instructions that must not execute while a flash loan is active (account transfers, liquidations, oracle writes, etc.).

### Reference

https://blog.asymmetric.re/threat-contained-marginfi-flash-loan-vulnerability/
https://hackernoon.com/how-instruction-introspection-makes-solana-flash-loans-structurally-safer-than-ethereums

---

## Summary Table

| # | Protocol | Year | Severity | Funds at Risk / Lost | Skill Tags | Root Cause Category |
|---|----------|------|----------|---------------------|------------|---------------------|
| 1 | marginfi v2 | 2024 | Critical | $160M (prevented) | flash_loan, repay_check, invoke | Defense parity gap: new instruction bypasses repay guard |
| 2 | Crema Finance | 2022 | Critical | $8.78M lost | flash_loan, flash_manipulation, invoke, atomic_borrow_repay | Missing PDA/owner check on tick account |
| 3 | Nirvana Finance | 2022 | Critical | $3.5M lost | flash_loan, flash_manipulation, atomic_borrow_repay | Spot oracle manipulable within tx; no TWAP |
| 4 | Mango v4 | 2023 | Critical | prevented (pre-exploit) | flash_loan, invoke, flash_manipulation | HealthRegion suspends health checks; allows borrow-exploit-repay |
| 5 | Mango v4 (CSV) | 2023 | HIGH | n/a (CSV) | flash_loan, invoke, repay_check, flash_manipulation | Same HealthRegion design flaw (independent DB record) |
| 6 | SwapBack (CSV) | n/a | HIGH | pool drain | flash_loan, repay_check, invoke | Repay binding gap: position_account not matched |
| 7 | Orca lockbox (CSV) | 2023 | MEDIUM | reward drain | flash_loan, flash_manipulation, atomic_borrow_repay | No lock-up on deposit; flash capital inflates reward share |
| 8 | Generic pattern | ongoing | Critical | varies | flash_loan, repay_check, invoke | load_instruction_at unchecked; sysvar spoofing |
| 9 | Generic pattern | ongoing | HIGH | varies | flash_loan, repay_check, flash_manipulation, invoke | Unrestricted instruction window between borrow and repay |

Total: 9 findings (3 from local CSV, 6 from web research).


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. External Flash Susceptibility Check | YES | Y/X/? | For each external program interaction |
| 1. Flash-Loan-Accessible State Inventory | YES | Y/X/? | |
| 2. Atomic Attack Sequence Modeling | YES | Y/X/? | For each accessible state |
| 3. Cross-Instruction Flash Loan Chains | YES | Y/X/? | |
| 3b. Flash-Loan-Enabled Debounce DoS | YES | Y/X/? | Shared cooldown instructions |
| 3c. No-Op Resource Consumption | YES | Y/X/? | Zero-effect calls consuming resources |
| 3d. External Flash x Debounce Cross-Ref | YES | Y/X/? | Cross-reference 0 x 3b |
| 4. Flash Loan + Donation Compounds | IF BALANCE_DEPENDENT | Y/X(N/A)/? | |
| 5. Flash Loan Defense Audit | YES | Y/X/? | For each attack path |
| 5b. Defense Parity Audit | YES | Y/X/? | For each action in multiple instructions |
