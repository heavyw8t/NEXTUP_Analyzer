---
name: "semi-trusted-roles"
description: "Type Thought-template (instantiate before use) - Research basis Insider threat modeling, keeper/bot abuse vectors"
---

# Skill: Semi-Trusted Role Analysis

> **Type**: Thought-template (instantiate before use)
> **Research basis**: Insider threat modeling, keeper/bot abuse vectors

## Trigger Patterns
```
onlyBot|onlyOperator|onlyKeeper|BOT_ROLE|OPERATOR_ROLE|KEEPER_ROLE|
hasRole.*BOT|hasRole.*OPERATOR|hasRole.*KEEPER|automated|keeper
```

## Reasoning Template

### Step 1: Inventory Role Permissions
- In {CONTRACTS}, find all functions callable by {ROLE_NAME}
- For each function at {ROLE_FUNCTIONS}:
  - What state does it modify?
  - What external calls does it make?
  - What parameters does it accept?

### Step 2: Analyze Within-Scope Abuse
For each permitted action, ask:

**Timing Abuse**:
- Can {ROLE_NAME} execute at harmful times? (front-run users, during rebalance)
- Can {ROLE_NAME} delay execution to harm users?

**Parameter Abuse**:
- Can {ROLE_NAME} pass harmful parameters? (max slippage, wrong recipient)
- Are parameters validated, or trusted implicitly?

**Sequence Abuse**:
- Can {ROLE_NAME} execute operations out of order?
- Can {ROLE_NAME} skip required operations?

**Omission Abuse**:
- Can {ROLE_NAME} harm users by NOT acting? (skip sync, delay distribution)

### Step 3: Model Attack Scenarios
```
Scenario A: Timing Attack
1. {ROLE_NAME} monitors mempool for user transaction {USER_ACTION}
2. {ROLE_NAME} front-runs with {ROLE_ACTION}
3. User's transaction executes with worse conditions
4. Impact: {TIMING_IMPACT}

Scenario B: Parameter Attack
1. {ROLE_NAME} calls {ROLE_FUNCTION} with {MALICIOUS_PARAMS}
2. Parameters are not validated against {EXPECTED_CONSTRAINTS}
3. Impact: {PARAM_IMPACT}

Scenario C: Key Compromise
1. {ROLE_NAME} private key is compromised
2. Attacker can call: {ROLE_FUNCTIONS}
3. Maximum extractable value: {MAX_DAMAGE}
4. Recovery options: {RECOVERY_PATH}
```

### Step 4: Assess Mitigations
- Is there a timelock on {ROLE_NAME} actions?
- Is {ROLE_NAME} a multisig?
- **Does a removal/revocation function for {ROLE_NAME} EXIST?** If NO -> FINDING: role is irrevocable without contract upgrade/migration. Severity: minimum Medium if role can modify user-facing state.
- Can admin revoke {ROLE_NAME} quickly?
- Are there rate limits or cooldowns?

## Key Questions (must answer all)
1. What is the maximum damage if {ROLE_NAME} acts maliciously?
2. What is the maximum damage if {ROLE_NAME} key is compromised?
3. Are there time-sensitive operations where {ROLE_NAME} timing matters?
4. What user funds or protocol state can {ROLE_NAME} affect?

## Common False Positives
- **View-only operations**: If role can only read state, no abuse vector
- **Idempotent operations**: If calling twice has same effect as once, timing abuse is limited
- **User-initiated dependency**: If role action requires user to initiate first, front-running may not apply
- **Economic alignment**: If role is economically aligned (staked collateral), malicious action has cost

## Reverse Perspective: User Exploitation of Roles

> **Critical insight**: Don't just analyze how the role can harm users -- analyze how USERS can exploit predictable role behavior.

### Step 5: Model User-Side Exploitation

**Predictability Analysis**:
- Is the role's behavior predictable? (scheduled tasks, triggered by events)
- Can users observe when the role will act?
- Can users front-run or back-run the role's actions?

**Scenario D: User Exploits Keeper Timing**
```
1. User observes that {ROLE_NAME} executes {ROLE_ACTION} at predictable times
2. User positions themselves before {ROLE_ACTION} (front-running the keeper)
3. {ROLE_ACTION} executes, changing state
4. User benefits from known state change
5. Impact: {USER_EXPLOIT_IMPACT}
```

**Scenario E: User Griefs Role Preconditions**
```
1. {ROLE_FUNCTION} has precondition: {PRECONDITION}
2. User can manipulate state to violate {PRECONDITION}
3. {ROLE_NAME} calls {ROLE_FUNCTION}, which reverts
4. System enters degraded state (no keeper actions possible)
5. Impact: {GRIEF_IMPACT}
```

**Scenario F: User Forces Suboptimal Role Action**
```
1. {ROLE_NAME} must choose between options based on state
2. User manipulates state to make worst option appear best
3. {ROLE_NAME} (following honest behavior) chooses suboptimal path
4. User profits from forced suboptimal execution
5. Impact: {SUBOPTIMAL_IMPACT}
```

**Scenario G: Same-Chain Rate Staleness via Discrete Updates**
```
1. Protocol's exchange rate only updates when {ROLE_NAME} acts (discrete updates)
2. Between role actions, rate is stale -- does not reflect accumulated value
3. User monitors for {ROLE_NAME} pending transaction
4. User enters at stale rate (favorable), {ROLE_NAME} executes, rate updates
5. User exits at updated rate (or holds appreciating position)
6. Impact: {RATE_ARBIT_IMPACT}
```
Note: This differs from cross-chain staleness. This applies when the rate is stale ON THE SAME CHAIN because updates only happen on specific role actions (compounding, rebalancing, harvesting), not on every user interaction.

### Step 6: Precondition Griefability Check

For each function callable by {ROLE_NAME}:

| Function | Preconditions | User Can Manipulate? | Grief Impact |
|----------|--------------|---------------------|--------------|
| {func} | balance > 0 | YES - withdraw all | Keeper stuck |
| {func} | cooldown passed | NO - time-based | N/A |
| {func} | threshold met | YES - partial withdraw | Delayed execution |

**Generic Rule**: Any admin/keeper function precondition that depends on user-manipulable state is potentially griefable.

### Step 6b: Admin/Privileged Function Griefability (EXHAUSTIVE)

**MANDATORY**: Use Slither (`list_functions` with role modifiers, `analyze_modifiers`) to enumerate ALL privileged functions. Do NOT rely on manual scanning -- manual scanning misses functions. Validate your count against the Slither output.

Extend griefability analysis beyond the semi-trusted role to ALL admin/privileged functions:

For each function callable by DEFAULT_ADMIN_ROLE or equivalent:

| Function | Preconditions | External State Dependency? | User Can Manipulate? | Grief Impact |
|----------|--------------|---------------------------|---------------------|--------------|
| {admin_fn} | {preconditions} | YES/NO | YES/NO | {impact if griefed} |

**Enumeration completeness check**:
- [ ] Slither `list_functions` count for role-restricted functions: {N}
- [ ] Functions analyzed in this table: {M}
- [ ] If M < N -> INCOMPLETE -- analyze missing functions before proceeding

**Specific checks**:
- Can users create state that blocks admin operations? (pending withdrawals blocking migration, non-zero balances blocking entity removal)
- Can users transfer tokens to the protocol that block operations? (unsolicited token transfers creating non-zero balances -- see Rule 11)
- Can users initiate multi-step operations whose in-flight state blocks admin actions?

**RULE**: If ANY admin function has a user-griefable precondition -> severity >= MEDIUM if it blocks critical protocol operations.

### Key Questions
5. Can users predict when {ROLE_NAME} will act?
6. Can users manipulate preconditions to block {ROLE_NAME}?
7. Can users profit by positioning around {ROLE_NAME}'s scheduled actions?
8. What happens if {ROLE_NAME} cannot execute? (system degradation)
9. Can users block admin operations via state manipulation or token transfers?

## Instantiation Parameters
```
{CONTRACTS}           -- Contracts to analyze
{ROLE_NAME}           -- Specific role (BOT_ROLE, OPERATOR, etc.)
{ROLE_FUNCTIONS}      -- Functions this role can call
{USER_ACTION}         -- User action that could be front-run
{ROLE_ACTION}         -- Role action used in attack
{TIMING_IMPACT}       -- Impact of timing attack
{MALICIOUS_PARAMS}    -- Harmful parameter values
{EXPECTED_CONSTRAINTS}-- What params should be validated against
{PARAM_IMPACT}        -- Impact of parameter attack
{MAX_DAMAGE}          -- Maximum extractable value
{RECOVERY_PATH}       -- How to recover from compromise
```

## Output Schema
| Field | Required | Description |
|-------|----------|-------------|
| role_permissions | yes | Functions callable by role |
| timing_vectors | yes | Timing-based abuse opportunities |
| parameter_vectors | yes | Parameter-based abuse opportunities |
| omission_vectors | yes | Harm from inaction |
| user_exploit_vectors | yes | How users can exploit the role |
| max_damage | yes | Worst-case damage assessment |
| mitigations | yes | Existing protections |
| finding | yes | CONFIRMED / REFUTED / CONTESTED / NEEDS_DEPTH |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | Status for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> Source: candidates.jsonl (252 rows). 8 distinct mechanisms selected.
> Tags used: `keeper`, `operator`, `relayer`, `crank`, `automation`, `bot_race`, `semi_trusted`

---

## Example 1 — Keeper Price Manipulation via Parameter Omission

*Tags*: `keeper`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Parameter abuse — keeper selects whether to include a fresh Pyth price update, passing an empty array to use a stale price favorable to themselves.

*Summary*: Flatmoney protocol allows keepers to update the Pyth oracle price when executing an order, but the check can be bypassed by passing an empty array. Keepers choose whether to push the latest price or not based on which benefits them, causing systematic losses to LPs or long traders.

*Why it qualifies*: Classic parameter abuse under SKILL.md Step 2. The keeper is trusted to provide fresh oracle data but faces no enforcement. The attacker vector is within-scope role action with no malicious-params validation.

*Pattern to detect*:
- `executeOrder` or similar accepts `bytes[] calldata priceUpdateData`
- No `require(priceUpdateData.length > 0)` or equivalent
- Keeper fee paid regardless of whether update was provided
- Protocol prices positions using whichever price is stored at execution time

---

## Example 2 — Keeper Opens Already-Liquidatable Positions

*Tags*: `keeper`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Omission abuse — keeper is permitted to open positions with no check that the resulting position is above liquidation threshold.

*Summary*: ELFI protocol keepers can execute order creation for positions that are immediately underwater. No post-open solvency check exists. A malicious or negligent keeper can cause protocol insolvency if liquidation is not profitable enough to cover losses.

*Why it qualifies*: SKILL.md Step 2 Omission Abuse and Step 3 Scenario B. Role action (`executeOrder`) modifies critical protocol state without a guard the role is trusted to honor. The fix is a post-execution health check that the role cannot bypass.

*Pattern to detect*:
- `executeCreateOrder` or `openPosition` callable by keeper role only
- No `isLiquidatable` check at end of execution
- Liquidation function exists separately and is called by a different keeper path

---

## Example 3 — Keeper Reward Front-Running (Bot Race)

*Tags*: `keeper`, `bot_race`, `semi_trusted`
*Severity*: MEDIUM
*Mechanism*: Timing abuse — attacker monitors mempool for a legitimate keeper transaction and front-runs it with the same call to steal the reward without doing the underlying work.

*Summary*: KeeperRewardDistributor rewards are proportional to position size, creating a high-value MEV target. An attacker can front-run honest keepers by sending the same keeper transaction with higher gas, claiming the reward while the honest keeper's transaction reverts or arrives too late.

*Why it qualifies*: SKILL.md Step 3 Scenario A (Timing Attack). Predictable reward calculation tied to observable on-chain state lets attackers replicate the keeper action without the off-chain infrastructure cost the protocol assumes keepers bear.

*Pattern to detect*:
- `performUpkeep` / `executeTask` with no `msg.sender` allowlist or commit-reveal
- Reward calculated as `f(positionSize)` visible before execution
- No slashing or bond requirement for the caller
- Contracts: `KeeperRewardDistributor.sol`, `BatchManager.sol`, `LimitOrderManager.sol`

---

## Example 4 — User Griefs Keeper via Commit Queue Spam (DoS)

*Tags*: `keeper`, `crank`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Precondition griefability (SKILL.md Step 6) — user creates unbounded queue depth that causes keeper's upkeep call to exceed the block gas limit.

*Summary*: PoolCommitter (Tracer / Perpetual Pools) has no minimum commit size and no queue depth cap. A malicious user submits thousands of near-zero commits, expanding the array iterated by `executeAllCommitments`. The keeper's `performUpkeep` exceeds block gas limit and the pool cannot update, effectively halting all user positions.

*Why it qualifies*: SKILL.md Step 5 Scenario E and Step 6. The precondition the keeper relies on (a bounded commit array) depends entirely on user-controlled state. No admin action can drain the queue without executing all entries.

*Pattern to detect*:
- `commit(uint256 amount)` with no `require(amount >= MIN_COMMIT)`
- `executeAllCommitments()` iterates `commits[]` without a length cap
- No emergency drain or skip mechanism for malformed entries

---

## Example 5 — Relayer Signed-Order Replay

*Tags*: `relayer`, `operator`, `semi_trusted`
*Severity*: MEDIUM
*Mechanism*: Relayer replay — absence of a nonce in the signed order struct lets the same hash be reused for multiple executions; operator can also supply different execute params than the user signed.

*Summary*: Krystal DeFi's `StructHash.Order` has no nonce field. The same signed order hash can be submitted by the operator role multiple times, draining user funds across repeated executions. Additionally, the execute parameters passed at runtime are not verified against the signed order, so the operator can change routing or amounts.

*Why it qualifies*: SKILL.md Step 2 Parameter Abuse and Step 3 Scenario B. The operator (semi-trusted relayer role) is trusted to pass matching params; there is no on-chain enforcement. Replay is a secondary vector from the same root cause.

*Pattern to detect*:
- EIP-712 `hashStruct` of an order type that lacks a `nonce` or `deadline` field
- `executeOrder(Order calldata order, ExecParams calldata exec)` where `exec` fields are not part of the signed hash
- Mapping `executedOrders[hash]` absent or not set atomically before external call

---

## Example 6 — Whitelisted Relayer Debits Wrong Account

*Tags*: `relayer`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Parameter abuse — when `msg.sender` is a whitelisted relayer, a cross-chain operation uses `msg.sender` as the source of funds instead of the intended `from` parameter, debiting the relayer's balance or a different user.

*Summary*: Tapioca DAO's Magnetar contract handles `TOFT_SEND_FROM` operations. When the caller is a whitelisted relayer, the token deduction uses `msg.sender` instead of the `from` field embedded in the payload. This causes either a revert (if the relayer has no balance) or a debit from the wrong account.

*Why it qualifies*: SKILL.md Step 2 Parameter Abuse. The role (whitelisted relayer) is granted trust that collapses the distinction between caller and intended payer. Any cross-chain operation that preserves `msg.sender` through a relay hop is susceptible.

*Pattern to detect*:
- `onlyWhitelistedRelayer` or equivalent modifier
- Token transfer uses `msg.sender` rather than a `from` field decoded from calldata
- Cross-chain message payload contains `from` / `srcSender` that is never validated against `msg.sender`

---

## Example 7 — Crank Fee Drain via Empty-Array Settle

*Tags*: `crank`, `keeper`, `automation`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Crank incentive misalignment — `settle` function pays the keeper fee via a `keep` modifier that runs unconditionally, even when the caller passes empty arrays performing no actual work.

*Summary*: Perennial v2 `KeeperFactory#settle` iterates an `ids` array to settle accounts and pays the caller a keeper fee through the `keep` modifier. Passing an empty array skips the loop entirely but still pays the fee. Any address can call this in a tight loop to drain the entire keeper fee balance, leaving no incentive for legitimate keepers.

*Why it qualifies*: SKILL.md Step 3 Scenario A combined with crank incentive misalignment. The fee payout is not gated on demonstrable work. The attack requires no role and no capital, making it unconditionally exploitable.

*Pattern to detect*:
- `function settle(bytes32[] calldata ids, ...) external keep(...)`
- `keep` modifier transfers fee to `msg.sender` before or after the function body regardless of `ids.length`
- No `require(ids.length > 0)` at the top of the function

---

## Example 8 — Automation Race: Missing Access Control on Reward Completion

*Tags*: `automation`, `relayer`, `bot_race`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Timing abuse — a function intended to be called only by the protocol's designated relayer/automation has no `msg.sender` check, allowing any address to call it first and redirect rewards.

*Summary*: PoolTogether's `rngComplete` in `RngRelayAuction.sol` is meant to be called by the Gelato relayer to finalize an RNG draw and send auction rewards to the designated recipient. The function has no access control. An attacker monitors the mempool for the relayer's pending transaction, front-runs it with a different `_rewardRecipient`, and collects all auction rewards. The legitimate relayer's transaction then reverts or succeeds with zero reward.

*Why it qualifies*: SKILL.md Step 3 Scenario A (Timing Attack). The role (relayer) is assumed to be the exclusive caller but this is not enforced. Front-running is trivially achievable by any observer of the public mempool.

*Pattern to detect*:
- `function rngComplete(..., address _rewardRecipient)` with no `onlyRelayer` or equivalent
- Reward distribution uses the caller-supplied `_rewardRecipient` directly
- Gelato / Chainlink Automation / Keep3r integration where the automation address is known but not validated on-chain

---

## Example 9 — Keeper Omission Creates Rate Staleness Arbitrage

*Tags*: `keeper`, `crank`, `semi_trusted`
*Severity*: MEDIUM
*Mechanism*: Omission abuse (SKILL.md Scenario G) — protocol exchange rate only updates when the keeper pushes new data; between updates the rate is stale and arbitrageable by users who observe the pending keeper transaction.

*Summary*: DSR Oracle (Maker cross-chain) accumulates interest continuously on-chain but the `conversionRate` stored in `DSROracleBase` only updates when a keeper calls the update function. During the delay, the stored rate underrepresents true value. Users deposit at the stale (low) rate and exit after the keeper update, capturing risk-free yield. A sudden jump in rate also exposes protocols that consume it to flash-loan attacks timed around the update.

*Why it qualifies*: SKILL.md Step 5 Scenario G (Same-Chain Rate Staleness via Discrete Updates). The keeper is honest but predictable; users can observe the pending update and position accordingly.

*Pattern to detect*:
- `conversionRate` or equivalent updated only via a permissioned `update()` call, not on every user interaction
- `getConversionRate()` returns the stored value without applying elapsed-time accrual
- Keeper update is observable in mempool (public transaction, predictable schedule)

---

## Example 10 — Operator Unchecked Parameter Erases All User Debt

*Tags*: `operator`, `keeper`, `semi_trusted`
*Severity*: HIGH
*Mechanism*: Parameter abuse — keeper-callable swap function accepts a `_rewardProportion` parameter with no upper-bound check; setting it above 1e18 applies all swap proceeds to debt repayment, zeroing every user's debt.

*Summary*: Taurus Protocol's `SwapHandler.swapForTau` is callable by the keeper role to swap yield tokens for TAU and distribute proceeds. The `_rewardProportion` parameter controls what fraction goes to debt erasure versus user distribution. With no `require(_rewardProportion <= 1e18)`, a keeper can erase all protocol debt in one call. TAU becomes unbacked, effectively worthless.

*Why it qualifies*: SKILL.md Step 2 Parameter Abuse, Step 3 Scenario B, and Step 4 (no rate limit or parameter constraint on the keeper action). The keeper role has a legitimate reason to call the function but can use an out-of-range value to produce catastrophic state.

*Pattern to detect*:
- `swapForTau(uint256 _rewardProportion, ...)` or analogous function callable by `KEEPER_ROLE`
- `_rewardProportion` used as a multiplier in debt accounting without `<= 1e18` guard
- No timelock or multisig on the keeper role


## Step Execution Checklist (MANDATORY)

> **CRITICAL**: You MUST report completion status for ALL steps. Both directions (role->user AND user->role) are equally important.

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Inventory Role Permissions | YES | | |
| 2. Analyze Within-Scope Abuse | YES | | |
| 3. Model Attack Scenarios (A,B,C) | YES | | |
| 4. Assess Mitigations | YES | | |
| 5. Model User-Side Exploitation (D,E,F) | **YES** | | **MANDATORY** -- never skip |
| 6. Precondition Griefability Check | **YES** | | **MANDATORY** -- never skip |
| 6b. Admin Function Griefability | **YES** | | **MANDATORY** -- never skip |

### Cross-Reference Markers

**After Step 4** (Assess Mitigations):
- **DO NOT STOP HERE** -- Steps 5-6 analyze the reverse direction
- IF role has any preconditions depending on user state -> **MUST complete Step 6**

**After Step 5** (User-Side Exploitation):
- Cross-reference with `TOKEN_FLOW_TRACING.md` for token-related griefing vectors
- IF keeper actions are predictable -> document MEV/front-running vectors

**After Step 6** (Precondition Griefability):
- IF any precondition is user-griefable -> severity >= MEDIUM
- Document system degradation if keeper is blocked

### Output Format for Step Execution

```markdown
**Step Execution**: checkmark1,2,3,4,5,6 | (no skips for this skill)
```

OR if incomplete:

```markdown
**Step Execution**: checkmark1,2,3,4 | ?5,6(user exploitation not analyzed)
**FLAG**: Incomplete analysis -- requires depth review (missing reverse direction)
```
