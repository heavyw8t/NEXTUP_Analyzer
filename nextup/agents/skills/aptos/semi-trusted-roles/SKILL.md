---
name: "semi-trusted-roles"
description: "Trigger Pattern SEMI_TRUSTED_ROLE flag (required) - Inject Into Breadth agents, depth-state-trace"
---

# SEMI_TRUSTED_ROLES Skill

> **Trigger Pattern**: SEMI_TRUSTED_ROLE flag (required)
> **Inject Into**: Breadth agents, depth-state-trace
> **Purpose**: Analyze semi-trusted roles in Aptos Move protocols using capability-based access control, modeling both role-to-user and user-to-role attack vectors

## Trigger Patterns
```
signer|SignerCapability|AdminCap|OperatorCap|KeeperCap|has_role|
assert_admin|assert_operator|friend|acquires|ExtendRef|
DeleteRef|TransferRef|MintRef|BurnRef
```

## Reasoning Template

### Step 1: Inventory Role Permissions

Enumerate ALL privileged roles in the protocol:

| Role | Capability / Check | Module | Functions Callable | State Modifiable | External Calls |
|------|-------------------|--------|-------------------|-----------------|----------------|
| {role} | {SignerCapability / custom Cap struct / signer check / friend} | {module} | {fn list} | {state list} | {calls list} |

**Aptos capability patterns to inventory**:
- **SignerCapability**: Stored in resource, allows generating a signer for the capability's address. Can call any function requiring that signer.
- **Custom capability structs**: `AdminCap`, `OperatorCap` etc. -- often stored in the deployer's account or an Object
- **Signer checks**: `assert!(signer::address_of(account) == @admin, E_NOT_ADMIN)` -- direct address comparison
- **Friend declarations**: `friend module::other` -- allows `other` to call `public(friend)` functions
- **Object Refs**: `ExtendRef`, `DeleteRef`, `TransferRef`, `MintRef`, `BurnRef` -- object-level capabilities
- **Resource account patterns**: Module creates a resource account and stores its `SignerCapability`

For each role at {ROLE_FUNCTIONS}:
- What state does it modify?
- What external calls does it make (via CPI or module calls)?
- What parameters does it accept?

### Step 2: Analyze Within-Scope Abuse (Direction A: Malicious Role)

For each permitted action, ask:

**Timing Abuse**:
- Can {ROLE_NAME} execute at harmful times? (front-run users via transaction ordering, during rebalance)
- Can {ROLE_NAME} delay execution to harm users? (withhold keeper actions)

**Parameter Abuse**:
- Can {ROLE_NAME} pass harmful parameters? (max slippage, wrong recipient address, extreme fee values)
- Are parameters validated on-chain, or trusted implicitly from the role?

**Sequence Abuse**:
- Can {ROLE_NAME} execute operations out of order?
- Can {ROLE_NAME} skip required operations in a multi-step process?

**Omission Abuse**:
- Can {ROLE_NAME} harm users by NOT acting? (skip price updates, delay distributions, never trigger harvest)

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
1. {ROLE_NAME} private key is compromised (or SignerCapability is leaked)
2. Attacker can call: {ROLE_FUNCTIONS}
3. Maximum extractable value: {MAX_DAMAGE}
4. Recovery options: {RECOVERY_PATH}
```

### Step 4: Assess Mitigations

| Mitigation | Present? | Implementation | Effective? |
|-----------|----------|----------------|-----------|
| Timelock on role actions | YES/NO | {code ref} | {analysis} |
| Multisig requirement | YES/NO | {code ref} | {analysis} |
| Role revocation function | YES/NO | {code ref} | {analysis} |
| Rate limits / cooldowns | YES/NO | {code ref} | {analysis} |
| Parameter bounds validation | YES/NO | {code ref} | {analysis} |
| Event emission for monitoring | YES/NO | {code ref} | {analysis} |

**Does a removal/revocation function for {ROLE_NAME} EXIST?** If NO -> FINDING: role is irrevocable without module upgrade. Severity: minimum Medium if role can modify user-facing state.

### Step 4b: Capability Escalation Analysis

| Capability | Stored Where | Can Be Duplicated? | Can Escalate? | Escalation Path |
|-----------|-------------|-------------------|---------------|----------------|
| {cap} | {resource/object} | YES/NO (`copy` ability?) | YES/NO | {if YES: how} |

**Aptos-specific escalation vectors**:
- `SignerCapability` has `copy` + `store` abilities -- can it be extracted and stored elsewhere?
- `ExtendRef` allows adding resources to an Object -- can a role add capabilities it shouldn't have?
- `TransferRef` allows ungated transfer of an Object -- can a role transfer an Object holding other capabilities?
- `MintRef` / `BurnRef` -- can a role with mint capability effectively drain the protocol?
- Friend module access -- can a friend module be upgraded to abuse `public(friend)` functions?

### Step 4c: Capability Transfer and Duplication

| Capability | Has `copy`? | Has `drop`? | Has `store`? | Transfer Function Exists? | Risk |
|-----------|------------|------------|-------------|--------------------------|------|
| {cap} | YES/NO | YES/NO | YES/NO | YES/NO | {assessment} |

**Key checks**:
- If capability has `copy` -> it can be duplicated, creating multiple holders
- If capability has `store` -> it can be placed in global storage, potentially accessible by others
- If capability has `drop` -> it can be silently discarded (may not be a risk, but check if protocol assumes it persists)
- If a `transfer_cap()` function exists -> trace who can call it and whether it validates the recipient

## Reverse Perspective: User Exploitation of Roles

### Step 5: Model User-Side Exploitation (Direction B: Malicious Users)

**Predictability Analysis**:
- Is the role's behavior predictable? (scheduled tasks, triggered by events, MEV-visible)
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
3. {ROLE_NAME} calls {ROLE_FUNCTION}, which aborts
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

### Step 6: Precondition Griefability Check

For each function callable by {ROLE_NAME}:

| Function | Preconditions | User Can Manipulate? | Grief Impact |
|----------|--------------|---------------------|--------------|
| {func} | balance > 0 | YES - withdraw all | Keeper stuck |
| {func} | cooldown passed | NO - time-based | N/A |
| {func} | threshold met | YES - partial withdraw | Delayed execution |
| {func} | resource exists | YES - can delete? | Function aborts |

**Generic Rule**: Any privileged function precondition that depends on user-manipulable state is potentially griefable.

### Step 6b: Admin/Privileged Function Griefability (EXHAUSTIVE)

**MANDATORY**: Enumerate ALL privileged functions by scanning for signer checks, capability acquires, and friend-only visibility. Do NOT rely on manual scanning.

For each function callable by admin or equivalent role:

| Function | Preconditions | External State Dependency? | User Can Manipulate? | Grief Impact |
|----------|--------------|---------------------------|---------------------|--------------|
| {admin_fn} | {preconditions} | YES/NO | YES/NO | {impact if griefed} |

**Enumeration completeness check**:
- [ ] Total role-restricted functions found: {N}
- [ ] Functions analyzed in this table: {M}
- [ ] If M < N -> INCOMPLETE -- analyze missing functions before proceeding

**Specific Aptos checks**:
- Can users create resources that block admin `move_from` operations?
- Can users deposit unsolicited tokens that prevent admin operations expecting zero balance?
- Can users initiate multi-step operations whose pending state blocks admin actions?
- Can users create Objects in a namespace that conflicts with admin Object creation?

## Key Questions (must answer ALL)

1. What is the maximum damage if {ROLE_NAME} acts maliciously?
2. What is the maximum damage if {ROLE_NAME} key/capability is compromised?
3. Are there time-sensitive operations where {ROLE_NAME} timing matters?
4. What user funds or protocol state can {ROLE_NAME} affect?
5. Can users predict when {ROLE_NAME} will act?
6. Can users manipulate preconditions to block {ROLE_NAME}?
7. Can users profit by positioning around {ROLE_NAME}'s scheduled actions?
8. What happens if {ROLE_NAME} cannot execute? (system degradation)
9. Can users block admin operations via state manipulation or unsolicited deposits?

## Common False Positives

- **View-only operations**: If role can only read state, no abuse vector
- **Idempotent operations**: If calling twice has same effect as once, timing abuse is limited
- **User-initiated dependency**: If role action requires user to initiate first, front-running may not apply
- **Economic alignment**: If role is economically aligned (staked collateral), malicious action has cost
- **Module upgrade authority**: Separate from in-protocol roles -- module upgrade is a governance concern, not a semi-trusted role issue (unless the protocol treats it as semi-trusted)

## Instantiation Parameters
```
{CONTRACTS}           -- Move modules to analyze
{ROLE_NAME}           -- Specific role (operator, keeper, admin, etc.)
{ROLE_FUNCTIONS}      -- Functions this role can call
{ROLE_CAPABILITIES}   -- Capability structs held by this role
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
| role_permissions | yes | Functions and capabilities per role |
| timing_vectors | yes | Timing-based abuse opportunities |
| parameter_vectors | yes | Parameter-based abuse opportunities |
| omission_vectors | yes | Harm from inaction |
| capability_escalation | yes | Capability escalation and duplication risks |
| user_exploit_vectors | yes | How users can exploit the role (Direction B) |
| max_damage | yes | Worst-case damage assessment |
| mitigations | yes | Existing protections |
| finding | yes | CONFIRMED / REFUTED / CONTESTED / NEEDS_DEPTH |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | Status for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

---

- Pattern: Operator bypasses an on-chain price deviation check by routing a swap through an unrelated pool controlled by the operator, then backruns to extract vault funds.
  Where it hit: Arrakis `SimpleManager` contract, `rebalance` function
  Severity: HIGH
  Source: Solodit (row_id 11230)
  Summary: The operator passes a whitelisted router address but targets a pool of tokens it controls. The price deviation check passes because it measures the wrong pool. The operator then executes a large swap in the actual UniV3 pool and backruns to drain the vault. The exploit is self-funded via flash loan. Fix: enforce the price deviation check immediately before liquidity is added, not before the swap.
  Map to: operator

---

- Pattern: Any user agent (UA) can send messages to any endpoint via the relayer, not just the designated bridge UA, enabling DoS and fund freeze.
  Where it hit: LayerZero-style bridge relayer, UA message routing
  Severity: HIGH
  Source: Solodit (row_id 14767)
  Summary: The relayer does not isolate message channels per UA. A malicious UA floods a target endpoint with crafted messages, causing the bridge to freeze and legitimate cross-chain transfers to stall. Recovery requires a protocol-level redesign of channel isolation. Fix: redesign the relayer to enforce per-UA channel separation; warn application developers to validate the source UA.
  Map to: relayer

---

- Pattern: Relayer accepts an unbounded `_toAddress` bytes parameter, allowing an oversized payload to break cross-chain message delivery on destination chains with lower gas limits.
  Where it hit: `OFTCore#sendFrom`, LayerZero OFT bridge
  Severity: HIGH
  Source: Solodit (row_id 13517)
  Summary: A malicious user passes a `_toAddress` of arbitrary size. On the destination chain the message cannot execute due to gas exhaustion, causing the nonce to advance on the source but the action to fail permanently on the destination. Funds are unrecoverable without a stored-message retry. Fix: bound `_toAddress` length (e.g., 32 bytes for Aptos/Solana addresses) at the sending endpoint.
  Map to: relayer

---

- Pattern: A semi-trusted role holding a `WithdrawCap` capability can execute withdrawals even while the protocol is in a paused state, because the pause guard only covers deposit functions.
  Where it hit: `gateway.move`, `withdraw_impl` function
  Severity: MEDIUM
  Source: Solodit (row_id 1579)
  Summary: The deposit path checks a `paused` flag; `withdraw_impl` does not. A `WithdrawCap` holder (or a compromised key) can drain gateway vault balances while legitimate deposits are blocked. The inconsistency also makes the pause invariant impossible to reason about. Fix: add a `paused` check to `withdraw_impl` that mirrors the deposit guard.
  Map to: operator, semi_trusted

---

- Pattern: Move market functions do not validate that the coin types supplied by the caller match the market's registered types, letting an attacker substitute tokens to manipulate order execution.
  Where it hit: `market::place_market_order` and `market::place_limit_order` in a Move DEX
  Severity: HIGH
  Source: Solodit (row_id 13757)
  Summary: The module owner's type parameters for a market are stored at initialization, but per-call coin types are accepted without comparison. An attacker passes incorrect coin types, causing coins to be transferred from an unintended reserve or creating phantom liquidity. Fix: assert that the type arguments on each call match the types stored in the market resource.
  Map to: module_owner, operator

---

- Pattern: Keeper (staking pool crank) computes the operator commission using the *new* commission rate for the current epoch instead of the rate that was in effect at epoch start, causing systematic over- or under-payment.
  Where it hit: `staking_pool::advance_epoch`, Move staking module
  Severity: MEDIUM
  Source: Solodit (row_id 2278)
  Summary: When the operator changes the commission rate mid-epoch the next `advance_epoch` call applies the new rate retroactively to the whole epoch. Operators can increase their rate just before epoch close to extract additional yield from delegators. Fix: snapshot the commission rate at epoch start and use that snapshot in `advance_epoch`.
  Map to: keeper, operator

---

- Pattern: A privileged crank function (`certify_event_blob`) accepts an `ending_checkpoint_sequence_num` parameter with no on-chain validation, allowing a node to record a mismatched blob ID and checkpoint, corrupting event-blob tracking state.
  Where it hit: `certify_event_blob` in a Move node-coordination module
  Severity: MEDIUM
  Source: Solodit (row_id 2279)
  Summary: The node (acting as a trusted crank) supplies the blob ID and checkpoint number together. Because neither is cross-checked against the other on-chain, a faulty or malicious node can certify an incorrect pairing. Downstream consumers of the certified state will diverge from actual chain history. Fix: track both the blob ID and the ending checkpoint together and validate consistency at certification time.
  Map to: keeper, semi_trusted


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Inventory Role Permissions | YES | | |
| 2. Analyze Within-Scope Abuse | YES | | |
| 3. Model Attack Scenarios (A,B,C) | YES | | |
| 4. Assess Mitigations | YES | | |
| 4b. Capability Escalation Analysis | YES | | Aptos-specific |
| 4c. Capability Transfer and Duplication | YES | | Aptos-specific |
| 5. Model User-Side Exploitation (D,E,F,G) | **YES** | | **MANDATORY** -- never skip |
| 6. Precondition Griefability Check | **YES** | | **MANDATORY** -- never skip |
| 6b. Admin Function Griefability | **YES** | | **MANDATORY** -- never skip |

### Cross-Reference Markers

**After Step 4** (Assess Mitigations):
- **DO NOT STOP HERE** -- Steps 5-6 analyze the reverse direction
- IF role has any preconditions depending on user state -> **MUST complete Step 6**

**After Step 4c** (Capability Transfer):
- IF capability has `copy` ability -> document duplication risk explicitly
- IF `SignerCapability` is stored -> trace ALL code paths that access it

**After Step 5** (User-Side Exploitation):
- Cross-reference with `TOKEN_FLOW_TRACING.md` for token-related griefing vectors
- IF keeper actions are predictable -> document MEV/front-running vectors

**After Step 6** (Precondition Griefability):
- IF any precondition is user-griefable -> severity >= MEDIUM
- Document system degradation if keeper is blocked
