---
name: "staking-receipt-tokens"
description: "Type Thought-template (instantiate before use) - Research basis Donation attacks via unsolicited token transfers"
---

# Skill: Staking Receipt Token Analysis

> **Type**: Thought-template (instantiate before use)
> **Research basis**: Donation attacks via unsolicited token transfers

## Trigger Patterns
```
delegation|staking.*receipt|liquid.*staking|getLiquidRewards|unbond|
stake.*share|validator|deposit.*voucher|withdraw.*voucher|claimReward
```

## Reasoning Template

### Step 1: Identify Receipt Tokens
- In {CONTRACTS}, find all external calls that return tokens
- For each, determine:
  - What token type is returned? (shares, vouchers, receipts, LP tokens)
  - Is the returned token ERC20-compatible?
  - Does the protocol hold these tokens?

### Step 2: Check Transferability
- For each receipt token {RECEIPT_TOKEN}:
  - Can it be acquired externally? (stake directly with {EXTERNAL_STAKING})
  - Can it be transferred via standard `transfer()`/`transferFrom()`?
  - Can anyone transfer it to {PROTOCOL_CONTRACT} unsolicited?

### Step 2b: External Token Transferability

For each EXTERNAL staking/delegation token the protocol interacts with (not just the protocol's own receipt token):

1. Is it ERC20-transferable? (check if extends IERC20/IERC20Upgradeable)
2. Can it be transferred TO the protocol contract unsolicited (without calling deposit/stake)?
3. If YES to both:
   a. Does the protocol iterate over these tokens or their sources? (gas DoS from many unsolicited transfers)
   b. Does `getTotalStake(protocol)` or equivalent change? (accounting impact on withdrawal calculations)
   c. Does `transfer()` trigger side effects? (reward auto-claim, delegation state changes)
   d. Does non-zero balance block any admin/privileged operations? (e.g., entity removal requires balance == 0)

| External Token | ERC20? | Unsolicited Transfer? | Iteration DoS? | Balance Impact? | Side Effects? | Blocks Operations? |
|----------------|--------|----------------------|-----------------|-----------------|---------------|-------------------|
| {token_name} | YES/NO | YES/NO | YES/NO | YES/NO | YES/NO | YES/NO |

**RULE**: If ANY external token is ERC20-transferable AND affects protocol state → finding with severity >= MEDIUM.

### Step 3: Trace Balance Dependencies
- In {PROTOCOL_CONTRACT}, find all uses of `balanceOf(address(this))` for {RECEIPT_TOKEN}
- For each usage at {BALANCE_CHECK_LOCATIONS}:
  - What calculation depends on this balance?
  - Is there a tracked state variable that should match?
  - What's the gap risk: tracked vs actual?

### Step 4: Model Donation Attack
```
1. Attacker acquires {RECEIPT_TOKEN} externally via {EXTERNAL_ACQUISITION}
2. Attacker transfers {DONATION_AMOUNT} to {PROTOCOL_CONTRACT}
3. Protocol's balanceOf(this) increases by {DONATION_AMOUNT}
4. Next operation at {AFFECTED_FUNCTION} uses inflated balance
5. Impact: {IMPACT_DESCRIPTION}
```

### Step 5: Assess Severity
- Can attacker profit from this manipulation?
- Can attacker grief other users?
- What's the minimum donation needed for impact?
- Is there a defense (e.g., balance reconciliation)?

## Key Questions (must answer all)
1. Can {RECEIPT_TOKEN} be acquired without going through {PROTOCOL_CONTRACT}?
2. Does {PROTOCOL_CONTRACT} use `balanceOf(this)` for {RECEIPT_TOKEN} in any calculation?
3. Is there a tracked state variable that should equal the actual balance?
4. What happens if tracked ≠ actual?

## Common False Positives
- **Balance reconciliation**: If protocol calls `balanceOf` and compares to tracked state, donation is detected
- **Isolated accounting**: If receipt tokens are accounted separately per user (not pooled), donation doesn't affect others
- **No balance dependency**: If protocol never calls `balanceOf(this)` for this token, donation has no effect
- **Burn on transfer**: Some receipt tokens are non-transferable or burn on transfer

## Multi-Entity Dust Attack Analysis

### Step 6: Identify Multi-Entity Patterns
- Does the protocol interact with MULTIPLE staking entities? (validators, pools, vaults)
- Are there separate receipt tokens per entity?
- How does the protocol aggregate across entities?

### Step 7: Model Compounding Dust
For protocols with N entities:
```
Single entity dust: X tokens (below threshold, ignored)
N entities with dust: N × X tokens
Compounding factor: If dust compounds over time → N × X × T

Check: Can attacker spread small amounts across many entities to:
1. Accumulate significant total value?
2. Avoid per-entity dust thresholds?
3. Exploit aggregation rounding?
```

### Step 8: On-Transfer Side Effects
When receipt tokens are transferred:
- Does `transfer()` trigger reward claims?
- Does `transfer()` update internal delegation state?
- Does `transfer()` call any hooks or callbacks?

**Specific checks**:
| Token | transfer() Side Effect | Exploitable? |
|-------|----------------------|--------------|
| Staking receipts | May claim rewards | Check if rewards go to sender/receiver/neither |
| stETH | Rebases on transfer | Check exchange rate impact |
| LP tokens | May trigger sync | Check for manipulation window |
| cTokens/aTokens | May accrue interest | Check balance vs shares discrepancy |

### Step 9: Cross-Validator Attack Patterns
For protocols managing multiple validators:
```
Pattern A: Dust Spreading
- Attacker creates dust positions across N validators
- Each position below withdrawal threshold
- Total value: significant
- Impact: locked value, accounting discrepancies

Pattern B: Selective Validator Manipulation
- Attacker identifies validator with exploitable state
- Moves delegation to that specific validator
- Exploits validator-specific vulnerability
- Impact: depends on vulnerability

Pattern C: Aggregation Rounding
- Protocol rounds down per-validator withdrawals
- Attacker exploits: N validators × rounding_error = significant loss/gain
```

### Step 10: External Adverse Events on Pending Operations

When the protocol has multi-step operations (request → wait → claim), check what happens if the external entity (validator, pool, vault, market) experiences an adverse event between steps.

| Multi-Step Operation | External Entity | Adverse Event | Impact on Pending Operation | Recovery Path? |
|---------------------|-----------------|---------------|----------------------------|----------------|
| {request→claim} | {entity} | Entity paused/frozen | {what happens to pending claim} | YES/NO |
| {request→claim} | {entity} | Entity slashed/penalized | {what happens to pending claim} | YES/NO |
| {request→claim} | {entity} | Entity deprecated/removed | {what happens to pending claim} | YES/NO |
| {request→claim} | {entity} | Entity liquidated/drained | {what happens to pending claim} | YES/NO |

**Adverse events to check**: pause, slash, penalize, deprecate, remove, liquidate, drain, migrate, upgrade

**RULE**: If a pending multi-step operation has no recovery path when the external entity experiences an adverse event → apply Rule 9 (stranded asset severity floor).

## Instantiation Parameters
```
{CONTRACTS}              - Contracts to analyze
{RECEIPT_TOKEN}          - Specific token (stETH, rETH, cToken, aToken, LP token, etc.)
{EXTERNAL_STAKING}       - Where token can be acquired externally
{PROTOCOL_CONTRACT}      - Contract that holds receipt tokens
{BALANCE_CHECK_LOCATIONS}- Lines where balanceOf(this) is called
{EXTERNAL_ACQUISITION}   - How attacker gets tokens (stake directly, buy on DEX)
{DONATION_AMOUNT}        - Amount transferred in attack
{AFFECTED_FUNCTION}      - Function affected by inflated balance
{IMPACT_DESCRIPTION}     - What goes wrong
```

## Output Schema
| Field | Required | Description |
|-------|----------|-------------|
| receipt_tokens | yes | List of identified receipt tokens |
| transferable | yes | YES/NO for each token |
| balance_dependencies | yes | Functions using balanceOf(this) |
| donation_impact | yes | What happens if balance is inflated |
| tracked_vs_actual | yes | Gap analysis |
| finding | yes | CONFIRMED / REFUTED / CONTESTED / NEEDS_DEPTH |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | ✓/✗/? for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> Skill: `evm/staking-receipt-tokens`
> Selected: 8 of 31 candidates
> Coverage: receipt_token transferable vs bound, sToken, stake_rate, stake_receipt, receipt_burn

---

## Example 1 — Receipt token freely mintable to arbitrary address

- **row_index**: 1880
- **severity**: HIGH
- **theme**: receipt_token transferable vs bound
- **keyword_match**: receipt_token, stake_receipt
- **summary**: `InfiniFiGatewayV1` lets anyone mint iUSD receipt tokens to any address. The `ReceiptToken` contract enforces action restrictions during transfers, so unsolicited minting disrupts user operations and voting mechanisms. Fixed by removing `ActionRestriction` from iUSD/siUSD.
- **skill_steps_triggered**: Step 2 (transferability), Step 2b (unsolicited transfer), Step 3 (balance dependencies), Step 8 (on-transfer side effects — action restrictions fire on transfer)
- **agent_note**: Confirms Step 2b rule: if an external party can mint or transfer receipt_token to protocol without going through deposit path, any action-gating logic breaks. Check `mint(to, amount)` signatures for missing `msg.sender == to` guards.

---

## Example 2 — sToken flash loan steals unlocked capital at snapshot

- **row_index**: 13053
- **severity**: MEDIUM
- **theme**: receipt_token transferable vs bound, stake_rate lag
- **keyword_match**: sToken, stake_receipt
- **summary**: In a protection pool, `assessState` is callable by anyone. An attacker predicts when a late loan triggers `lockCapital`, which snapshots sToken holders. The attacker flash-loans sTokens from a secondary market (e.g. Uniswap), calls `assessState` to snapshot themselves, repays the flash loan, then claims unlocked funds. Fixed by restricting `assessState` to trusted callers.
- **skill_steps_triggered**: Step 1 (receipt token = sToken), Step 2 (transferable — traded on secondary market), Step 4 (donation/transfer attack model — flash loan variant), Step 5 (attacker profits)
- **agent_note**: Flash-loan receipt acquisition is the attack primitive in Step 4 `{EXTERNAL_ACQUISITION}`. Any snapshot that records `balanceOf` at the block of an event (not over time) is vulnerable when receipt_token is freely transferable.

---

## Example 3 — pToken exchange rate corrupted by missing totalBorrows decrement in liquidation

- **row_index**: 11168
- **severity**: HIGH
- **theme**: receipt_rate manipulation
- **keyword_match**: stake_rate (exchange rate), receipt_token (pToken)
- **summary**: DODOV3MM `liquidate` does not decrement `totalBorrows` for the debt token. Because pToken exchange rate is computed from `totalBorrows`, depositors receive more interest than is economically backed. The last withdrawer cannot redeem because insufficient underlying tokens exist.
- **skill_steps_triggered**: Step 3 (balance dependency — exchange rate formula), Step 5 (impact — last withdrawer DoS, interest not covered by anyone)
- **agent_note**: Represents the class where `stake_rate` (exchange rate) diverges from reality because a state mutation path (liquidation) skips the rate-update write. Audit all exit paths for missing `totalBorrows`/`totalSupply` updates.

---

## Example 4 — Wrong bToken exchange rate used for collateral valuation

- **row_index**: 10572
- **severity**: HIGH
- **theme**: receipt_rate manipulation
- **keyword_match**: stake_rate (exchangeRateStored), receipt_token (bToken)
- **summary**: `BlueBerryBank.getIsolatedCollateralValue()` uses the debt token's bToken exchange rate instead of the underlying token's bToken exchange rate. When `underlyingVaultShare` is stored after a softVault mint, retrieving its value requires multiplying by the *underlying* token's `exchangeRateStored`, not the debt token's. Miscalculation leads to wrong position risk assessment.
- **skill_steps_triggered**: Step 3 (balance dependencies — exchange rate read site), Step 5 (impact — mispriced collateral, protocol assumes bad debt)
- **agent_note**: Confirms that receipt_rate errors often arise at the read site rather than the write site. When a protocol holds multiple receipt tokens (one per asset), verify each rate lookup fetches the rate for the *same* token whose balance is being scaled.

---

## Example 5 — sToken withdrawal request resets cooldown, enabling DoS

- **row_index**: 3704
- **severity**: HIGH
- **theme**: sToken burn-without-claim
- **keyword_match**: sToken, stake_receipt (withdrawal NFT introduced as fix)
- **summary**: `SToken.withdrawRequest` is callable by anyone with sufficient allowance on behalf of any owner. Each call resets the cooling period regardless of amount. An attacker loops small requests, perpetually resetting the cooldown and blocking legitimate users from claiming. Fixed by adding an NFT receipt mechanism so withdrawal requests become bound to a non-fungible claim ticket.
- **skill_steps_triggered**: Step 2 (transferability — withdrawRequest callable permissionlessly), Step 8 (on-transfer side effects — NFT receipt introduced to bind claim), Step 5 (impact — DoS on withdrawal)
- **agent_note**: The fix (NFT receipt) turns a fungible permission into a bound stake_receipt. This is the design pattern Step 2b targets: if the withdrawal authorization is separable from the position owner, the claim path is exploitable.

---

## Example 6 — sToken protocol freeze when totalSTokenUnderlying is zero but totalSupply is nonzero

- **row_index**: 13051
- **severity**: MEDIUM
- **theme**: receipt double-accounting
- **keyword_match**: sToken, stake_rate (_getExchangeRate), receipt_burn
- **summary**: In a protection pool, if all underlying is swept but sToken supply remains nonzero, `_getExchangeRate()` returns zero. `convertToSToken` divides by zero and reverts, freezing all new deposits and protection purchases. `_leverageRatio` also becomes zero, blocking buys. Recovery requires every sToken holder to burn shares after enough cycles.
- **skill_steps_triggered**: Step 3 (balance dependency — exchange rate formula reads totalSTokenUnderlying), Step 5 (impact — protocol freeze), Step 4 (gap between tracked totalSTokenUnderlying and actual sToken supply)
- **agent_note**: Demonstrates the `tracked_vs_actual` gap from the Output Schema. When `totalSTokenUnderlying` can reach zero through loss events while `totalSupply` stays nonzero, every function that divides by exchange rate is a freeze vector.

---

## Example 7 — sToken address passed to reward accrual steals contract funds

- **row_index**: 15092
- **severity**: HIGH
- **theme**: receipt double-accounting
- **keyword_match**: sToken, stake_receipt (aToken/vToken distinction)
- **summary**: `RewardsManagerForAave.accrueUserUnclaimedRewards` is public and accepts a token address. The function assumes that if the token is not the variable debt token it must be the aToken, so it uses `supplyBalance` for reward computation. An attacker passes an sToken address, which is neither, but the branch executes and accrues rewards from the wrong balance. Fixed by explicitly validating the token is aToken or vToken.
- **skill_steps_triggered**: Step 1 (identify receipt tokens — sToken, aToken, vToken), Step 2b (unsolicited input — attacker passes arbitrary address), Step 3 (balance dependency — supplyBalance used for reward calc), Step 5 (impact — theft from contract)
- **agent_note**: Confirms that receipt_token confusion attacks arise when protocol code uses implicit type inference ("if not X then must be Y") rather than explicit validation. Any public function that branches on token identity without a strict allowlist is a candidate.

---

## Example 8 — Stake-LP reward rate varies by invocation time; early callers drain pool

- **row_index**: 17602
- **severity**: HIGH
- **theme**: stake_rate lag vs reward distribution
- **keyword_match**: stake_rate, sToken (StakeLP pToken reward tokens)
- **summary**: pSTAKE Finance StakeLP distributes rewards by calling `calculateRewardsAndLiquidity`. The reward amount depends on *when* the function is called because the rate changes over time and not all LP providers have staked. Users who call earlier or later than others receive different amounts; the reward amount can even decrease over time. Fixed by adopting a per-second accumulator algorithm that is time-invariant at claim time.
- **skill_steps_triggered**: Step 3 (balance dependency — reward calculation reads a time-dependent rate), Step 5 (impact — unfair distribution, first-caller advantage), Step 8 (on-transfer side effects — reward claim triggered by LP interactions)
- **agent_note**: Canonical stake_rate lag pattern. Any reward formula of the form `rate * elapsed_since_last_call` gives first-movers an advantage and creates a race condition. Look for `block.timestamp` or `block.number` arithmetic inside reward distribution without a global accumulator checkpoint.


## Step Execution Checklist (MANDATORY)

> **CRITICAL**: You MUST report completion status for ALL steps. Findings with incomplete steps (✗ or ? without valid reason) will be flagged for depth review.

Before finalizing ANY finding, complete this checklist:

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Identify Receipt Tokens | YES | ✓/✗/? | |
| 2. Check Transferability | YES | ✓/✗/? | |
| 2b. External Token Transferability | **YES** | ✓/✗/? | **MANDATORY** - never skip |
| 3. Trace Balance Dependencies | YES | ✓/✗/? | |
| 4. Model Donation Attack | YES | ✓/✗/? | |
| 5. Assess Severity | YES | ✓/✗/? | |
| 6. Identify Multi-Entity Patterns | **IF N>1** | ✓/✗(N/A)/? | Skip only if protocol has single entity |
| 7. Model Compounding Dust | **IF N>1** | ✓/✗(N/A)/? | Skip only if protocol has single entity |
| 8. On-Transfer Side Effects | **YES** | ✓/✗/? | **MANDATORY** - never skip |
| 9. Cross-Validator Attack Patterns | **IF validators** | ✓/✗(N/A)/? | Skip only if no validators |

### Cross-Reference Markers

**After Step 5** (Assess Severity):
- IF protocol manages multiple entities (validators, pools, vaults) → **MUST complete Steps 6-7**
- IF protocol has staking receipts → **MUST complete Step 8**

**After Step 8** (On-Transfer Side Effects):
- IF side effects UNKNOWN → mark CONTESTED (not REFUTED)
- IF side effects may exist → assume YES (adversarial default), trace impact

### Output Format for Step Execution

```markdown
**Step Execution**: ✓1,2,3,4,5,8 | ✗6,7(N/A-single validator) | ✗9(N/A-no multi-validator)
```

OR if incomplete:

```markdown
**Step Execution**: ✓1,2,3,4,5 | ?6,7(need multi-entity analysis) | ?8(transfer effects unknown)
**FLAG**: Incomplete analysis - requires depth review
```
