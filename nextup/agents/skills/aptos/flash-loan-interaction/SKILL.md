---
name: "flash-loan-interaction"
description: "Trigger Pattern FLASH_LOAN flag (required) or BALANCE_DEPENDENT flag (optional complement) - Inject Into Breadth agents, depth-token-flow, depth-edge-case"
---

# FLASH_LOAN_INTERACTION Skill

> **Trigger Pattern**: FLASH_LOAN flag (required) or BALANCE_DEPENDENT flag (optional complement)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case
> **Purpose**: Analyze flash loan attack surfaces in Aptos Move protocols, focusing on the hot potato receipt pattern, state manipulation during flash loan windows, and defense parity

For every flash-loan-accessible state variable or precondition in the protocol:

**STEP PRIORITY**: Steps 5 (Defense Audit) and 5b (Defense Parity) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections (0c, 4) before skipping 5, 5b, or 3d.

## 0. External Flash Susceptibility Check

Before analyzing the protocol's OWN flash loan paths, check whether external protocols the contract interacts with are susceptible to third-party flash manipulation.

### 0a: External Interaction Inventory

| External Protocol | Interaction Type | State Read by Our Protocol | Can 3rd Party Flash-Manipulate That State? |
|-------------------|-----------------|---------------------------|-------------------------------------------|
| {DEX/pool/vault} | {swap/deposit/query} | {reserves, price, balance} | {YES if spot state / NO if TWAP or time-weighted} |

### 0b: Third-Party Flash Attack Modeling

For each external state marked YES in 0a, model:
1. **Before**: Protocol reads external state X (e.g., pool reserves, spot price from AMM)
2. **Flash manipulate**: Attacker flash-borrows and trades on the external protocol to move state X
3. **Victim call**: Attacker calls OUR protocol function that reads manipulated state X
4. **Restore**: Attacker reverses the external manipulation
5. **Impact**: What did the attacker gain from our protocol acting on manipulated state?

**Key question**: Does our protocol use **spot state** (manipulable) or **time-weighted state** (resistant)?

<!-- LOAD_IF: DEX_INTERACTION -->
### 0c: DEX Price Manipulation Cost Estimation

For each external DEX/pool whose spot state is read by the protocol, estimate manipulation cost:

| Pool | Liquidity (USD) | Target Price Change | Est. Trade Size | Slippage Cost | Protocol Extractable Value | Profitable? |
|------|----------------|--------------------:|----------------|--------------|---------------------------|-------------|
| {pool} | {TVL} | {%} | {USD} | {USD} | {USD} | {YES/NO} |

**For Aptos AMMs**: Most use constant-product (xy=k) or stableswap curves. Identify the specific AMM type from the protocol's swap function signatures (weighted pools, stableswap, or standard xy=k).
<!-- END_LOAD_IF: DEX_INTERACTION -->

## 1. Flash-Loan-Accessible State Inventory

Enumerate ALL protocol state that can be manipulated within a single transaction via flash-borrowed capital:

| State Variable / Query | Location | Read By | Write Path | Flash-Accessible? | Manipulation Cost |
|------------------------|----------|---------|------------|-------------------|-------------------|
| `fungible_asset::balance(store)` | {module} | {functions} | Direct deposit to store | YES if store accepts | 0 (unsolicited) |
| `coin::balance<T>(addr)` | {module} | {functions} | Direct `coin::deposit` | YES if CoinStore exists | 0 (unsolicited) |
| Pool reserves | {pool module} | {functions} | Swap on pool | YES | Slippage cost |
| Oracle spot price | {oracle} | {functions} | Trade on source DEX | YES | Market depth |
| Threshold/quorum state | {module} | {functions} | Deposit/stake | YES | Threshold amount |

**Aptos flash loan mechanics (hot potato pattern)**:
- Flash loan providers (Thala, Echelon, etc.) issue a `FlashLoanReceipt` struct with NO abilities (no `copy`, no `drop`, no `store`, no `key`)
- The receipt MUST be consumed by `repay()` in the same transaction -- Move's type system enforces this
- No callback mechanism: caller receives receipt, performs operations, then passes receipt to repay
- The receipt struct often contains the borrowed amount for repayment validation

**For each YES entry**: trace all functions that READ this state and make decisions based on it.

**Rule 15 check**: For each balance/oracle/threshold/rate precondition, model the flash loan atomic sequence.

## 2. Atomic Attack Sequence Modeling

For each flash-loan-accessible state identified in Step 1:

### Attack Template
```
1. BORROW: Flash-borrow {amount} of {CoinType/FA} from {source}
   -> Receive FlashLoanReceipt (hot potato, no abilities)
2. MANIPULATE: {action} to change {state_variable} from {value_before} to {value_after}
3. CALL: Invoke {target_function} which reads manipulated state
4. EXTRACT: {what_is_gained} -- quantify: {amount}
5. RESTORE: {action} to return state (if needed before repayment)
6. REPAY: Call repay() with FlashLoanReceipt + {amount + fee}
7. PROFIT: {extract - fee - gas} = {net_profit}
```

**Profitability gate**: If net_profit <= 0 for all realistic amounts -> document as NON-PROFITABLE but check Step 3 for multi-call chains.

**For each sequence, verify**:
- [ ] Can steps 2-5 execute atomically (same transaction entry function)?
- [ ] Does any step abort under normal conditions?
- [ ] Is the manipulation detectable/preventable by the protocol?
- [ ] What is the minimum flash loan amount needed?
- [ ] Does the hot potato receipt constrain the call sequence? (receipt must be threaded through all calls)

## 3. Cross-Function Flash Loan Chains

Model multi-call atomic sequences within a single flash loan:

| Step | Function Called | State Before | State After | Enables Next Step? |
|------|---------------|-------------|------------|-------------------|
| 1 | {function_A} | {state} | {state'} | YES -- changes {X} |
| 2 | {function_B} | {state'} | {state''} | YES -- enables {Y} |
| N | {function_N} | {state^N} | {final} | EXTRACT profit |

**Key question**: Can calling function A then function B in the same transaction produce a state that neither function alone could create?

**Aptos-specific multi-call patterns**:
- Deposit to pool -> manipulate price via swap -> withdraw at inflated rate
- Flash-stake to meet threshold -> trigger reward calculation -> unstake
- Borrow from protocol A -> manipulate collateral oracle via AMM trade -> liquidate on protocol B -> repay A
- Inflate FungibleStore balance via deposit -> trigger share price recalculation -> withdraw

### 3b. Flash-Loan-Enabled Debounce DoS

For each permissionless function with a cooldown/debounce that affects OTHER users (global cooldown, shared timestamp, epoch-bound action):
Can attacker flash-borrow -> call debounced function -> trigger cooldown, blocking legitimate callers?

| Function | Cooldown Scope | Shared Across Users? | Flash-Triggerable? | DoS Duration |
|----------|---------------|---------------------|-------------------|-------------|

If cooldown is global/shared AND function is permissionless AND flash-triggerable -> FINDING (R2, minimum Medium).

### 3c. No-Op Resource Consumption

For each state-modifying function with a limited-use resource (cooldown, one-time flag, nonce, epoch-bound action):
Can it be called with parameters producing zero economic effect (amount=0, same-token swap, self-transfer) while consuming the resource?

| Function | Resource Consumed | No-Op Parameters | Resource Wasted? | Impact |
|----------|------------------|-----------------|-----------------|--------|

If a no-op call consumes a resource blocking legitimate use -> FINDING (R2, resource waste).

### 3d. External Flash x Debounce Cross-Reference (MANDATORY)

For EACH external protocol flagged as flash-susceptible in Section 0:

| External Protocol | Flash-Accessible Action | Debounce/Cooldown Affected (from 3b) | Combined Severity |
|-------------------|------------------------|--------------------------------------|-------------------|

Cross-reference: Can the external flash loan trigger ANY debounce/cooldown found in Step 3b?
If YES:
1. Is the debounce consumption **permanent** (no admin reset) or **temporary** (auto-expires)?
2. If permanent: is there ANY on-chain path to reset? (admin function, governance, time-based expiry)
3. Combined finding inherits the HIGHER severity of the two individual findings
4. Tag: `[TRACE:flash({external}) -> call({debounce_fn}) -> cooldown consumed -> {duration/permanent}]`

If no debounce functions exist from 3b: mark N/A and skip.

<!-- LOAD_IF: BALANCE_DEPENDENT -->
## 4. Flash Loan + Donation Compound Attacks

Combine flash loan capital with unsolicited token transfers:

| Donation Target | Flash Loan Action | Combined Effect | Profitable? |
|-----------------|-------------------|-----------------|-------------|
| FungibleStore balance | Deposit/withdraw | Rate manipulation | {YES/NO} |
| CoinStore<T> balance | Swap on DEX pool | Price oracle manipulation | {YES/NO} |
| Governance token balance | Vote/propose | Quorum manipulation | {YES/NO} |

**Aptos-specific donation vectors**:
- `primary_fungible_store::deposit()` -- can deposit to any address's primary store if the store exists
- `coin::deposit<T>()` -- can deposit to any address with a registered CoinStore<T>
- Direct `fungible_asset::deposit()` with a FungibleStore reference
- Object-based stores may have different deposit access patterns

**Check**: Can a flash-borrowed amount be deposited (not through protocol's deposit logic) to the protocol's FungibleStore to manipulate `balance()` accounting, and then extracted via a subsequent protocol call within the same transaction?
<!-- END_LOAD_IF: BALANCE_DEPENDENT -->

## 5. Flash Loan Defense Audit

For each flash-loan-accessible attack path identified:

| Defense | Present? | Effective? | Bypass? |
|---------|----------|------------|---------|
| Reentrancy guard (Move has no native) | YES/NO | {analysis} | {if YES: how} |
| Same-transaction detection (custom) | YES/NO | {analysis} | {bypass vector?} |
| TWAP instead of spot price | YES/NO | TWAP window length: {N} | Short TWAP vulnerable? |
| Minimum lock period / cooldown | YES/NO | Duration: {N seconds/epochs} | Bypass via partial? |
| Balance snapshot (before/after comparison) | YES/NO | {analysis} | {if YES: how} |
| Flash loan fee exceeds profit | YES/NO | Fee: {X}, max profit: {Y} | Fee < profit? |
| Hot potato receipt threading requirement | YES/NO | Receipt must flow through {path} | Can bypass receipt checks? |

**Aptos-specific defense notes**:
- Move does NOT have native reentrancy guards (no `nonReentrant` modifier)
- Move's borrow checker prevents some reentrancy patterns at compile time (cannot borrow `&mut` twice)
- However, inter-module calls can create reentrancy-like patterns via public functions
- Hot potato pattern enforces same-transaction completion but does NOT prevent state manipulation between borrow and repay
- `timestamp::now_seconds()` granularity is per-second, not per-block -- same-second detection is unreliable

## 5b. Defense Parity Audit (Cross-Module)

For each user-facing action that exists in multiple modules or paths (stake, withdraw, claim, swap):

| Action | Module A | Flash Defense | Module B | Flash Defense | Parity? |
|--------|----------|---------------|----------|---------------|---------|
| {action} | {module} | {defense list} | {module} | {defense list} | {GAP if different} |

**Key question**: If ModuleA::stake() has a cooldown that prevents flash-stake-claim-withdraw,
but ModuleB::stake() has NO cooldown for the same economic action -- can an attacker use
ModuleB as the undefended path to extract the same value?

For each GAP found:
1. Can the undefended module be used to achieve the same economic outcome?
2. Does the defended module's protection become meaningless if the undefended path exists?
3. Is the defense difference intentional (documented via friend declarations) or accidental?

## Instantiation Parameters
```
{CONTRACTS}              -- Move modules to analyze
{FLASH_LOAN_SOURCES}     -- Flash loan providers (Thala, Echelon, custom)
{RECEIPT_STRUCTS}         -- Hot potato receipt struct definitions
{FLASH_ACCESSIBLE_STATE} -- State variables manipulable via flash-borrowed capital
{EXTERNAL_PROTOCOLS}     -- External protocols whose state the contract reads
```

## Finding Template

```markdown
**ID**: [FL-N]
**Severity**: [based on profitability and fund impact]
**Step Execution**: checkmark1,2,3,4,5 | x(reasons) | ?(uncertain)
**Rules Applied**: [R2:Y, R4:Y, R10:Y, R15:Y]
**Location**: module::function:LineN
**Title**: Flash loan enables [manipulation] via [mechanism]
**Description**: [Full atomic attack sequence with amounts]
**Impact**: [Quantified profit/loss with realistic flash loan amounts]
```

## Output Schema

| Field | Required | Description |
|-------|----------|-------------|
| external_susceptibility | yes | External protocols susceptible to flash manipulation |
| flash_accessible_state | yes | All state manipulable within a transaction |
| attack_sequences | yes | Modeled atomic attack sequences with profitability |
| cross_function_chains | yes | Multi-call chains within flash loan window |
| defense_audit | yes | Defenses present and their effectiveness |
| defense_parity | yes | Cross-module defense comparison |
| finding | yes | CONFIRMED / REFUTED / CONTESTED |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | Status for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

# aptos/flash-loan-interaction
# Generated: 2026-04-19
# Sources: Aptos docs, Zellic research, CertiK blog, Solodit local CSV (4 hits), web search

---

## Local CSV Findings (4 hits)

### CSV-1
- **Severity**: HIGH
- **Language**: Move (Initia)
- **Tags**: flash_loan, oracle, spot_price
- **Summary**: `usernames` module in Initia Move uses spot price from the Dex module for domain registration/extension pricing. An attacker can flash-borrow or make a large deposit to move the spot price, buying domains below market rate or forcing other users to overpay. Mitigation: TWAP or Slinky oracle.
- **Solodit row**: 1804
- **Skill tags**: `flash_loan`, `oracle_manipulation`, `borrow_repay`

### CSV-2
- **Severity**: HIGH
- **Language**: Move (Unstoppable-DeFi / Vyper, cross-tagged Move)
- **Tags**: flash_loan, sandwich, slippage
- **Summary**: Attacker calls `MarginDex` to open/close positions in Vault, sets infinite slippage, and sandwich-attacks the internal swap inside a flash loan callback, draining swapped tokens. No `_is_liquidatable` check at position end and no oracle deviation guard on `close_position`.
- **Solodit row**: 11081
- **Skill tags**: `flash_loan`, `borrow_repay`, `atomic`

### CSV-3
- **Severity**: HIGH
- **Language**: Move (Arrakis/UniV3 cross-tagged)
- **Tags**: flash_loan, price_deviation_bypass, operator
- **Summary**: Operator bypasses price deviation check during rebalance by routing a swap through a whitelisted router on an unrelated pool they control, then backruns inside a flash loan callback to drain the vault. Fix: enforce price deviation check immediately before liquidity provision.
- **Solodit row**: 11230
- **Skill tags**: `flash_loan`, `borrow_repay`, `atomic`

### CSV-4
- **Severity**: HIGH
- **Language**: Move (Thala THL rewards)
- **Tags**: flash_loan, staking, reward_calculation
- **Summary**: Attacker flash-borrows THL tokens, increases stake amount to inflate the extra-rewards accumulator, claims rewards for the freshly added stake, then repays the flash loan in the same transaction. Root cause: accumulator for extra rewards is not updated before the stake amount changes. Fixed in patch.
- **Solodit row**: 11639
- **Skill tags**: `flash_loan`, `hot_potato`, `borrow_repay`, `atomic`

---

## Web-Sourced Findings (6 additional)

### WEB-1 — FlashLoanReceipt with `drop` ability allows repayment bypass
- **Severity**: CRITICAL
- **Source**: Aptos Move Security Guidelines (aptos.dev/build/smart-contracts/move-security-guidelines)
- **Tags**: `hot_potato`, `resource_release`, `flash_loan`
- **Description**: If a `FlashLoan` or `FlashLoanReceipt` struct is declared with the `drop` ability, a borrower can destroy the receipt resource before calling `repay()`, exiting the loan without returning funds. The hot-potato invariant ("no abilities" struct that cannot be stored, copied, or dropped) is the sole enforcement mechanism for same-transaction repayment in Aptos Move. Adding `drop` nullifies that guarantee.
- **Attack sequence**:
  1. Call `flash_loan<T>(amount)` — receive `FlashLoanReceipt { amount, fee }`
  2. Use borrowed funds.
  3. Discard (drop) the receipt rather than passing it to `repay()`.
  4. Transaction completes; protocol never receives repayment.
- **Impact**: Full loss of loaned pool reserves.
- **Remediation**: Declare FlashLoanReceipt/FlashLoan struct with zero abilities. Compiler enforces that the value must be consumed.
- **Skill tags**: `hot_potato`, `resource_release`, `flash_loan`

### WEB-2 — repay_flash_loan missing coin-type match check
- **Severity**: HIGH
- **Source**: Aptos Move Security Guidelines (aptos.dev/build/smart-contracts/move-security-guidelines)
- **Tags**: `flash_loan`, `borrow_repay`, `type_confusion`
- **Description**: `repay_flash_loan<T>` validates only that `coin::value(repayment) >= receipt.amount + fee`. It does not verify that the generic type `T` of the repayment coin matches the type `T` originally borrowed. An attacker borrows a high-value coin and repays with a different coin of equal nominal integer value but far lower market value.
- **Attack sequence**:
  1. `flash_loan<WBTC>(amount)` — receipt records `amount_in_wbtc`.
  2. Keep WBTC. Acquire equivalent integer units of a near-zero-value token (e.g., a dust token where 1 unit = $0.000001).
  3. Call `repay_flash_loan<DustToken>(receipt, dust_coin)` — integer assert passes, type is never checked.
  4. Protocol receives worthless dust; attacker retains WBTC.
- **Impact**: Complete theft of flash-loaned principal.
- **Remediation**: Use phantom type parameters or `assert!(type_info::type_of<T>() == receipt.coin_type)` inside repay.
- **Skill tags**: `flash_loan`, `borrow_repay`, `type_confusion`

### WEB-3 — Move bytecode verifier CFG bug bypasses hot-potato (Zellic / CVE-class)
- **Severity**: CRITICAL
- **Source**: Zellic "The Billion Dollar Bug" (zellic.io/blog/the-billion-dollar-move-bug/); patched Aptos April 10 2023
- **Tags**: `hot_potato`, `resource_release`, `flash_loan`
- **Description**: A bug in `Bytecode::get_successors` produced an incorrect control-flow graph in the Move bytecode verifier, allowing a crafted bytecode sequence to (a) obtain multiple mutable references to one object, (b) retain a mutable reference to a moved object, and (c) drop an object that lacks the `drop` ability. Effect (c) directly breaks the hot-potato pattern: an attacker could take a flash loan receipt (no abilities) and drop it without repaying, bypassing ALL flash loan implementations on Aptos, Sui, Starcoin, and 0L. Introduced 2022-10-06, silently patched Aptos 2023-04-10.
- **Impact**: Systematic theft of every flash-loan pool on Aptos during the window (Oct 2022 – Apr 2023).
- **Remediation**: Upgrade to Aptos node >= April 2023 release. Application-level: no workaround possible — VM-level fix required.
- **Skill tags**: `hot_potato`, `resource_release`, `flash_loan`

### WEB-4 — Flash-loan-amplified spot-price oracle manipulation (Aptos AMM protocols)
- **Severity**: HIGH
- **Source**: Aptos Move Security Guidelines; Pontem "All About DeFi Flash Loans" (pontem.network); general Aptos DeFi audit pattern
- **Tags**: `flash_loan`, `oracle_manipulation`, `atomic`
- **Description**: Protocols that derive token price from the instantaneous reserve ratio of an Aptos AMM pool (xy=k, weighted, or stableswap) are vulnerable. An attacker flash-borrows a large amount of one token, trades it into the pool to shift reserves and spot price, calls the victim protocol function that reads the spot price (e.g., for collateral valuation, liquidation threshold, or minting ratio), extracts value, reverses the trade, and repays the flash loan — all within one transaction.
- **Attack sequence**:
  1. Flash-borrow large amount of TokenA from Echelon/Thala.
  2. Swap TokenA → TokenB on AMM pool, driving spot price of TokenB up (or down).
  3. Call victim protocol (e.g., mint stablecoin against inflated TokenB collateral, or liquidate undercollateralized position).
  4. Swap TokenB → TokenA to restore pool.
  5. Repay flash loan + fee.
- **Impact**: Unbounded value extraction proportional to protocol TVL and AMM pool depth.
- **Remediation**: Use TWAP (minimum 30-minute window), Pyth Network, or Switchboard oracle instead of spot reserves.
- **Skill tags**: `flash_loan`, `oracle_manipulation`, `atomic`, `borrow_repay`

### WEB-5 — Flash-stake to inflate reward accumulator before snapshot (Aptos staking/lending)
- **Severity**: HIGH
- **Source**: Solodit CSV-4 (Thala, row 11639) + Aptos DeFi staking pattern; corroborated by general Move audit precedents
- **Tags**: `flash_loan`, `hot_potato`, `borrow_repay`, `atomic`
- **Description**: Reward protocols that snapshot or accumulate rewards at the time of a stake/deposit call (rather than lazily on withdrawal) allow flash-staking: attacker borrows governance or staking tokens, calls `stake()` with a large amount to cause the accumulator to record a large share, immediately calls `claim_rewards()` in the same transaction, then calls `unstake()` and repays the flash loan. Net effect: attacker earns rewards for stake they held for zero real time.
- **Conditions**: (a) staking token is flash-borrowable (Thala LP tokens, protocol tokens with flash-loan providers); (b) rewards are credited at stake time rather than time-weighted; (c) no cooldown or lockup enforced before `claim`.
- **Impact**: Drain of reward reserve proportional to per-epoch reward budget and flash-loan-accessible stake supply.
- **Remediation**: Credit rewards lazily on withdrawal only, or enforce a minimum lock period (multiple epochs) before claim is permitted.
- **Skill tags**: `flash_loan`, `hot_potato`, `borrow_repay`, `atomic`

### WEB-6 — Flash-loan fee rounds to zero enabling free capital (Aptos lending protocols)
- **Severity**: MEDIUM
- **Source**: Aptos Move Security Guidelines (fee precision pattern); CertiK Aptos audit lessons
- **Tags**: `flash_loan`, `borrow_repay`, `precision_loss`
- **Description**: When the flash loan fee is computed as `amount * PROTOCOL_FEE_BPS / 10000` using integer arithmetic in Move (u64/u128), borrowing an amount below `10000 / PROTOCOL_FEE_BPS` causes the fee to truncate to zero. For a 5 bps fee, this threshold is 2000 units of the base denomination. An attacker can make many small flash-loan calls, each returning the principal without paying any fee, effectively using the protocol as free capital — removing the economic disincentive and potentially enabling repeated attack probes at zero cost.
- **Attack sequence**:
  1. Choose `amount = floor(10000 / PROTOCOL_FEE_BPS) - 1` (e.g., 1999 for 5 bps).
  2. `flash_loan<T>(1999)` — fee = `1999 * 5 / 10000 = 0`.
  3. Perform arbitrage or manipulation with free capital; repay exactly `1999`.
  4. Repeat in separate transactions.
- **Impact**: Protocol earns no fees; attacker has costless flash capital; potential enabler for other attacks.
- **Remediation**: Add minimum borrow amount check: `assert!(amount >= 10000 / PROTOCOL_FEE_BPS, EAMOUNT_TOO_SMALL)`.
- **Skill tags**: `flash_loan`, `borrow_repay`, `precision_loss`

---

## Skill Tag Coverage Summary

| Tag | CSV hits | Web hits | Total |
|-----|----------|----------|-------|
| `flash_loan` | 4 | 6 | 10 |
| `hot_potato` | 1 | 3 | 4 |
| `borrow_repay` | 3 | 5 | 8 |
| `resource_release` | 0 | 2 | 2 |
| `atomic` | 2 | 3 | 5 |
| `oracle_manipulation` | 1 | 2 | 3 |
| `precision_loss` | 0 | 1 | 1 |
| `type_confusion` | 0 | 1 | 1 |

Total unique findings: **10** (4 CSV + 6 web)


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. External Flash Susceptibility Check | YES | Y/x/? | For each external protocol interaction |
| 1. Flash-Loan-Accessible State Inventory | YES | Y/x/? | |
| 2. Atomic Attack Sequence Modeling | YES | Y/x/? | For each accessible state |
| 3. Cross-Function Flash Loan Chains | YES | Y/x/? | |
| 3b. Flash-Loan-Enabled Debounce DoS | YES | Y/x/? | Shared cooldown functions |
| 3c. No-Op Resource Consumption | YES | Y/x/? | Zero-effect calls consuming resources |
| 3d. External Flash x Debounce Cross-Ref | YES | Y/x/? | Cross-reference 0 x 3b |
| 4. Flash Loan + Donation Compounds | IF BALANCE_DEPENDENT | Y/x(N/A)/? | |
| 5. Flash Loan Defense Audit | YES | Y/x/? | For each attack path |
| 5b. Defense Parity Audit | YES | Y/x/? | For each action in multiple modules |
