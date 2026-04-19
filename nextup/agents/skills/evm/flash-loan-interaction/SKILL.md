---
name: "flash-loan-interaction"
description: "Trigger Pattern FLASH_LOAN flag (required) or BALANCE_DEPENDENT flag (optional complement) - Inject Into Breadth agents, depth-token-flow, depth-edge-case"
---

# FLASH_LOAN_INTERACTION Skill

> **Trigger Pattern**: FLASH_LOAN flag (required) or BALANCE_DEPENDENT flag (optional complement)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case

For every flash-loan-accessible state variable or precondition in the protocol:

**⚠ STEP PRIORITY**: Steps 5 (Defense Audit) and 5b (Defense Parity) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections (0c, 4) before skipping 5, 5b, or 3d.

## 0. External Flash Susceptibility Check

Before analyzing the protocol's OWN flash loan paths, check whether external protocols the contract interacts with are susceptible to third-party flash manipulation.

### 0a: External Interaction Inventory

| External Protocol | Interaction Type | State Read by Our Protocol | Can 3rd Party Flash-Manipulate That State? |
|-------------------|-----------------|---------------------------|-------------------------------------------|
| {DEX/pool/vault} | {swap/deposit/query} | {reserves, price, balance} | {YES if spot state / NO if TWAP or time-weighted} |

### 0b: Third-Party Flash Attack Modeling

For each external state marked YES in 0a, model:
1. **Before**: Protocol reads external state X (e.g., pool reserves, spot price)
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

**Cost formula**: `manipulation_cost = slippage * trade_size` where `trade_size = (target_price_change / price_impact_per_unit) * pool_liquidity`. If `manipulation_cost < extractable_value` → VIABLE.

**For Uniswap V2-style**: `price_impact = trade_size / (reserve + trade_size)`. For V3 concentrated liquidity: impact depends on tick range - use actual liquidity in the affected range, not total TVL.
<!-- END_LOAD_IF: DEX_INTERACTION -->

## 1. Flash-Loan-Accessible State Inventory

Enumerate ALL protocol state that can be manipulated within a single transaction via flash-borrowed capital:

| State Variable / Query | Location | Read By | Write Path | Flash-Accessible? | Manipulation Cost |
|------------------------|----------|---------|------------|-------------------|-------------------|
| `balanceOf(address(this))` | {contract} | {functions} | Direct transfer | YES | 0 (donation) |
| `totalSupply` | {contract} | {functions} | mint/burn | YES if permissionless | Deposit amount |
| `getReserves()` | {pool} | {functions} | Swap | YES | Slippage cost |
| Oracle spot price | {oracle} | {functions} | Trade on source | YES | Market depth |
| Threshold/quorum state | {contract} | {functions} | Deposit/stake | YES | Threshold amount |

**For each YES entry**: trace all functions that READ this state and make decisions based on it.

**Rule 15 check**: For each balance/oracle/threshold/rate precondition, model the flash loan atomic sequence.

## 2. Atomic Attack Sequence Modeling

For each flash-loan-accessible state identified in Step 1:

### Attack Template
```
1. BORROW: Flash-borrow {amount} of {token} from {source}
2. MANIPULATE: {action} to change {state_variable} from {value_before} to {value_after}
3. CALL: Invoke {target_function} which reads manipulated state
4. EXTRACT: {what_is_gained} - quantify: {amount}
5. RESTORE: {action} to return state (if needed for repayment)
6. REPAY: Return {amount + fee} to flash loan source
7. PROFIT: {extract - fee - gas} = {net_profit}
```

**Profitability gate**: If net_profit ≤ 0 for all realistic amounts → document as NON-PROFITABLE but check Step 3 for multi-call chains.

**For each sequence, verify**:
- [ ] Can steps 2-5 execute atomically (same transaction)?
- [ ] Does any step revert under normal conditions?
- [ ] Is the manipulation detectable/preventable by the protocol?
- [ ] What is the minimum flash loan amount needed?

## 3. Cross-Function Flash Loan Chains

Model multi-call atomic sequences within a single flash loan:

| Step | Function Called | State Before | State After | Enables Next Step? |
|------|---------------|-------------|------------|-------------------|
| 1 | {function_A} | {state} | {state'} | YES - changes {X} |
| 2 | {function_B} | {state'} | {state''} | YES - enables {Y} |
| N | {function_N} | {state^N} | {final} | EXTRACT profit |

**Key question**: Can calling function A then function B in the same transaction produce a state that neither function alone could create?

**Common multi-call patterns**:
- Deposit → manipulate rate → withdraw (sandwich own deposit)
- Stake → trigger reward calculation → unstake (flash-stake rewards)
- Borrow → manipulate collateral price → liquidate others → repay
- Deposit to inflate shares → withdraw deflated shares

### 3b. Flash-Loan-Enabled Debounce DoS
For each permissionless function with a cooldown/debounce that affects OTHER users (global cooldown, shared timestamp):
Can attacker flash-borrow → call debounced function → trigger cooldown, blocking legitimate callers?

| Function | Cooldown Scope | Shared Across Users? | Flash-Triggerable? | DoS Duration |
|----------|---------------|---------------------|-------------------|-------------|

If cooldown is global/shared AND function is permissionless AND flash-triggerable → FINDING (R2, minimum Medium).

### 3c. No-Op Resource Consumption
For each state-modifying function with a limited-use resource (cooldown, one-time flag, nonce, epoch-bound action):
Can it be called with parameters producing zero economic effect (amount=0, same-token swap, self-transfer) while consuming the resource?

| Function | Resource Consumed | No-Op Parameters | Resource Wasted? | Impact |
|----------|------------------|-----------------|-----------------|--------|

If a no-op call consumes a resource blocking legitimate use → FINDING (R2, resource waste).

### 3d. External Flash × Debounce Cross-Reference (MANDATORY)

For EACH external protocol flagged as flash-susceptible in Section 0:

| External Protocol | Flash-Accessible Action | Debounce/Cooldown Affected (from 3b) | Combined Severity |
|-------------------|------------------------|--------------------------------------|-------------------|

Cross-reference: Can the external flash loan trigger ANY debounce/cooldown found in Step 3b?
If YES:
1. Is the debounce consumption **permanent** (no admin reset) or **temporary** (auto-expires)?
2. If permanent: is there ANY on-chain path to reset? (admin function, governance, time-based expiry)
3. Combined finding inherits the HIGHER severity of the two individual findings
4. Tag: `[TRACE:flash({external}) → call({debounce_fn}) → cooldown consumed → {duration/permanent}]`

If no debounce functions exist from 3b: mark N/A and skip.

<!-- LOAD_IF: BALANCE_DEPENDENT -->
## 4. Flash Loan + Donation Compound Attacks

Combine flash loan capital with unsolicited token transfers:

| Donation Target | Flash Loan Action | Combined Effect | Profitable? |
|-----------------|-------------------|-----------------|-------------|
| {contract}.balanceOf | Deposit/withdraw | Rate manipulation | {YES/NO} |
| {pool}.reserves | Swap | Price oracle manipulation | {YES/NO} |
| {governance}.balance | Vote/propose | Quorum manipulation | {YES/NO} |

**Check**: Can a flash-borrowed amount be donated (not deposited) to the protocol to manipulate `balanceOf(this)` accounting, and then extracted via a subsequent protocol call within the same transaction?
<!-- END_LOAD_IF: BALANCE_DEPENDENT -->

## 5. Flash Loan Defense Audit

For each flash-loan-accessible attack path identified:

| Defense | Present? | Effective? | Bypass? |
|---------|----------|------------|---------|
| Reentrancy guard (`nonReentrant`) | YES/NO | {analysis} | {if YES: how} |
| Same-block prevention (`block.number` check) | YES/NO | {analysis} | Multi-block possible? |
| TWAP instead of spot price | YES/NO | TWAP window length: {N} | Short TWAP vulnerable? |
| Minimum lock period / cooldown | YES/NO | Duration: {N blocks/seconds} | Bypass via partial? |
| Balance snapshot (before/after comparison) | YES/NO | {analysis} | {if YES: how} |
| Flash loan fee exceeds profit | YES/NO | Fee: {X}, max profit: {Y} | Fee < profit? |

**TWAP-specific**: If TWAP window < 30 minutes AND pool liquidity < $10M → flag as potentially manipulable.

## 5b. Defense Parity Audit (Cross-Contract)

For each user-facing action that exists in multiple contracts (stake, withdraw, claim, exit):

| Action | Contract A | Flash Defense | Contract B | Flash Defense | Parity? |
|--------|-----------|---------------|-----------|---------------|---------|
| {action} | {contract} | {defense list} | {contract} | {defense list} | {GAP if different} |

**Key question**: If ContractA.stake() has a cooldown that prevents flash-stake-claim-withdraw,
but ContractB.stake() has NO cooldown for the same economic action - can an attacker use
ContractB as the undefended path to extract the same value?

For each GAP found:
1. Can the undefended contract be used to achieve the same economic outcome?
2. Does the defended contract's protection become meaningless if the undefended path exists?
3. Is the defense difference intentional (documented) or accidental?

## Finding Template

```markdown
**ID**: [FL-N]
**Severity**: [based on profitability and fund impact]
**Step Execution**: ✓1,2,3,4,5 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [R2:✓, R4:✓, R10:✓, R15:✓]
**Location**: Contract.sol:LineN
**Title**: Flash loan enables [manipulation] via [mechanism]
**Description**: [Full atomic attack sequence with amounts]
**Impact**: [Quantified profit/loss with realistic flash loan amounts]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Selected from candidates.jsonl (242 rows). 8 examples covering 6 distinct sub-patterns.

---

## Example 1 — Callback auth missing: initiator not verified in `executeOperation`

*Category*: `callback_auth` / `initiator_check`
*Severity*: HIGH
*Source row*: 9923 | tags: Missing Check; Flash Loan

***Summary***

`WidoCollateralSwap_Aave.executeOperation` and `WidoCollateralSwap_ERC3156.onFlashLoan` did not verify that `msg.sender` was the expected flash loan provider or that the `initiator` was the swap contract itself. Any caller could invoke the callback directly, impersonate another user, and manipulate sensitive parameters.

***Vulnerable pattern***

```solidity
// IERC3156 callback — no initiator check
function onFlashLoan(
    address initiator,
    address token,
    uint256 amount,
    uint256 fee,
    bytes calldata data
) external returns (bytes32) {
    // initiator never verified — attacker calls this directly
    _executeSwap(data);
    return keccak256("ERC3156FlashBorrower.onFlashLoan");
}
```

***Fix***

```solidity
require(msg.sender == address(flashLender), "bad lender");
require(initiator == address(this),         "bad initiator");
```

***Key signals***: `IERC3156`, `onFlashLoan`, `executeOperation`, `initiator`, no `require(initiator == address(this))`

---

## Example 2 — Callback auth missing: arbitrary `executeOperation` via Aave flash loan

*Category*: `callback_auth` / `flashLoan`
*Severity*: HIGH
*Source row*: 16003

***Summary***

`SuperVault.executeOperation` checked only `msg.sender == lendingPool`, not whether the flash loan was self-initiated. An attacker triggered Aave's `lendingPool.flashLoan` with `SuperVault` as the receiver and crafted `params` to invoke `REBALANCE`, draining fees from the victim vault on every call.

***Vulnerable pattern***

```solidity
function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,       // never checked
    bytes calldata params
) external override returns (bool) {
    require(msg.sender == address(lendingPool));  // only lender checked
    _rebalance(params);  // attacker-controlled params
    ...
}
```

***Fix***

```solidity
bool private _flashActive;

function _startFlash(...) internal {
    _flashActive = true;
    lendingPool.flashLoan(...);
    _flashActive = false;
}

function executeOperation(...) external override returns (bool) {
    require(msg.sender == address(lendingPool));
    require(_flashActive, "not self-initiated");
    ...
}
```

***Key signals***: `executeOperation`, `initiator` unused, Aave `flashLoan` with external `receiverAddress`

---

## Example 3 — Balance check fooled by flash loan: reward inflation via spot balance

*Category*: `flashloan_manipulation` / balance-dependent reward accounting
*Severity*: HIGH
*Source row*: 6285

***Summary***

`FeeRewardsProcess.sol` used `balanceOf(stakeToken)` to determine a user's stake weight. An attacker flash-borrowed the stake token, called `claimReward` while holding a temporarily inflated balance, and extracted outsized rewards before repaying the loan.

***Vulnerable pattern***

```solidity
// rewards proportional to live token balance — manipulable
uint256 stakeAmount = IERC20(stakeToken).balanceOf(msg.sender);
uint256 reward = (totalReward * stakeAmount) / totalSupply;
_mintReward(msg.sender, reward);
```

***Fix***

Use the protocol's internal accounting (`stakingAccount.stakeTokenBalances[stakeToken].stakeAmount`) instead of the live ERC-20 balance.

***Key signals***: `balanceOf` used as stake weight in reward calc, no snapshot, no same-block guard

---

## Example 4 — Balance check fooled by flash loan: receiptToken reward inflation

*Category*: `flashloan_manipulation` / `BALANCE_DEPENDENT`
*Severity*: HIGH
*Source row*: 16524

***Summary***

`AavePool` minted reward tokens proportional to the caller's `receiptToken.balanceOf`. An attacker flash-borrowed receipt tokens from a secondary market, called `claimReward`, and received inflated rewards in the same transaction.

***Vulnerable pattern***

```solidity
function claimReward() external {
    uint256 share = receiptToken.balanceOf(msg.sender);  // spot, not deposited amount
    uint256 reward = (pendingRewards * share) / receiptToken.totalSupply();
    _sendReward(msg.sender, reward);
}
```

***Fix***

Track deposited amounts internally; do not use live `balanceOf` for reward distribution. Add a `nonReentrant` guard and consider a same-block deposit/withdraw restriction.

***Key signals***: `receiptToken.balanceOf`, reward calc on spot balance, no deposit snapshot

---

## Example 5 — Flash loan + governance: voting power inflation via flash-staked tokens

*Category*: `flashloan_manipulation` / governance attack
*Severity*: HIGH
*Source row*: 9636 | tags: Vote; Flash Loan; Delegate

***Summary***

An attacker combined a flash loan with ERC-20 token delegation to bypass existing same-block flash loan mitigations. Because delegation updated voting checkpoints immediately and the proposal state check read current (not historical) checkpoints, the attacker could determine the outcome of a proposal that was still in the Locked state, all within one transaction.

***Attack sequence***

```
1. BORROW  flash-loan governance token
2. DELEGATE borrow → attack contract (updates checkpoint)
3. CALL    getProposalState() reads inflated checkpoint → Locked → Succeeded
4. EXECUTE proposal passes in same tx
5. UNDELEGATE + REPAY flash loan
```

***Fix***

Disallow delegation and undelegation in the same block as a deposit or withdrawal. Use ERC20Votes' historical snapshot (`getPastVotes`) rather than current balance for quorum/threshold checks.

***Key signals***: `getPastVotes` vs `getVotes`, delegation in same block, `EarlyExecution` voting mode

---

## Example 6 — Flash loan + oracle manipulation: Uniswap V2 spot price used for pricing

*Category*: `flashloan_manipulation` / oracle
*Severity*: HIGH
*Source row*: 7648 | tags: Oracle

***Summary***

A pricing contract called `uniswapV2Router.getAmountsIn()` directly, reading live pool reserves. An attacker flash-borrowed the reference token, sold it into the pair to crash its price, purchased the protocol's asset at a distorted rate, then repaid the loan. No TWAP was used.

***Vulnerable pattern***

```solidity
// spot price — manipulable in one tx
uint[] memory amounts = router.getAmountsIn(tokenBoxAmount, path);
uint referenceTokenCost = amounts[0];
```

***Fix***

Replace with a TWAP oracle (Uniswap V2's `price0CumulativeLast` / `price1CumulativeLast` with a minimum 30-minute window) or a Chainlink price feed.

***Key signals***: `getAmountsIn`, `getReserves`, `slot0`, `sqrtPriceX96` used for pricing without TWAP

---

## Example 7 — Fee accounting bypass: flash loan fee ignored in `receiveFlashLoan`

*Category*: `flashloan_manipulation` / fee accounting
*Severity*: HIGH
*Source row*: 10508 | tags: External Contract

***Summary***

`scWETHv2` and `scUSDCv2` vaults implemented Balancer's `receiveFlashLoan` callback but repaid exactly the borrowed amount, ignoring the `feeAmounts` parameter. This was safe only because Balancer currently charges zero fees. If Balancer introduces fees, repayment falls short, the flash loan reverts, and the vault's `rebalance`/`withdraw` paths become permanently bricked.

***Vulnerable pattern***

```solidity
function receiveFlashLoan(
    IERC20[] memory tokens,
    uint256[] memory amounts,
    uint256[] memory feeAmounts,  // ignored
    bytes memory userData
) external override {
    // repays only `amounts`, not `amounts + feeAmounts`
    for (uint i; i < tokens.length; i++) {
        tokens[i].safeTransfer(address(vault), amounts[i]);
    }
}
```

***Fix***

```solidity
tokens[i].safeTransfer(address(vault), amounts[i] + feeAmounts[i]);
```

***Key signals***: `receiveFlashLoan`, `feeAmounts` parameter unused, Balancer vault integration

---

## Example 8 — Flash loan + liquidation sandwich: stability pool profit theft

*Category*: `flashloan_manipulation` / liquidation sandwich
*Severity*: HIGH
*Source row*: 8553

***Summary***

An attacker used a flash loan to front-run the Stability Pool's normal liquidation flow. By temporarily depositing flash-borrowed stable tokens into the Stability Pool, triggering a liquidation, and immediately withdrawing, the attacker captured the collateral premium that should have accrued to long-term depositors. This drained liquidation profit from legitimate Stability Pool providers and reduced the incentive to keep the pool funded, risking stablecoin depeg.

***Attack sequence***

```
1. BORROW  flash-loan stable token (e.g. mkUSD)
2. DEPOSIT flash-borrowed tokens into StabilityPool
3. LIQUIDATE an undercollateralized trove — attacker absorbs collateral gain
4. WITHDRAW deposit + collateral gain
5. REPAY   flash loan
PROFIT = collateral_received - flash_loan_fee
```

***Fix***

Apply a time factor: record the block (or timestamp) of each Stability Pool deposit and disallow withdrawal of liquidation gains earned in the same block. Alternatively, use checkpointed reward snapshots so same-block depositors receive zero gain from liquidations they did not fund before the event.

***Key signals***: `StabilityPool`, `deposit`/`withdraw` same-block, no cooldown on liquidation gain, no deposit timestamp

---

## Coverage map

| Sub-pattern | Example(s) |
|---|---|
| `callback_auth` / `initiator_check` missing | 1, 2 |
| Balance check fooled by flash loan (`BALANCE_DEPENDENT`) | 3, 4 |
| Flash + governance / read-only state manipulation | 5 |
| Flash + oracle manipulation (spot price) | 6 |
| Fee accounting bypass in flash callback | 7 |
| Flash + liquidation sandwich | 8 |


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. External Flash Susceptibility Check | YES | ✓/✗/? | For each external protocol interaction |
| 1. Flash-Loan-Accessible State Inventory | YES | ✓/✗/? | |
| 2. Atomic Attack Sequence Modeling | YES | ✓/✗/? | For each accessible state |
| 3. Cross-Function Flash Loan Chains | YES | ✓/✗/? | |
| 3b. Flash-Loan-Enabled Debounce DoS | YES | ✓/✗/? | Shared cooldown functions |
| 3c. No-Op Resource Consumption | YES | ✓/✗/? | Zero-effect calls consuming resources |
| 3d. External Flash × Debounce Cross-Ref | YES | ✓/✗/? | Cross-reference 0 × 3b |
| 4. Flash Loan + Donation Compounds | IF BALANCE_DEPENDENT | ✓/✗(N/A)/? | |
| 5. Flash Loan Defense Audit | YES | ✓/✗/? | For each attack path |
| 5b. Defense Parity Audit | YES | ✓/✗/? | For each action in multiple contracts |
