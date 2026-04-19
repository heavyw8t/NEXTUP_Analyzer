---
name: "centralization-risk"
description: "Trigger Protocol has privileged roles (admin, owner, operator, governance, multisig) - Covers Single points of failure, privilege escalation, external governance dependencies"
---

# Skill: CENTRALIZATION_RISK

> **Trigger**: Protocol has privileged roles (admin, owner, operator, governance, multisig)
> **Covers**: Single points of failure, privilege escalation, external governance dependencies
> **Required**: NO (optional -- recommended when protocol has 3+ distinct privileged roles)

## Trigger Patterns

```
onlyOwner|onlyAdmin|onlyGovernance|DEFAULT_ADMIN_ROLE|OPERATOR_ROLE|timelock|multisig|governance
```

## Reasoning Template

### Step 1: Privilege Inventory

Enumerate ALL privileged functions using Slither (`list_functions` + `analyze_modifiers`):

| # | Function | Contract | Modifier/Role | What It Controls | Impact If Abused |
|---|----------|----------|---------------|------------------|-----------------|
| 1 | {func} | {contract} | {role} | {parameter/state} | {worst case} |

**Categorize each by impact**:
- **FUND_CONTROL**: Can move, lock, or destroy user funds
- **PARAMETER_CONTROL**: Can change fees, rates, thresholds, delays
- **OPERATIONAL_CONTROL**: Can pause, unpause, add/remove components
- **UPGRADE_CONTROL**: Can change contract logic

### Step 2: Role Hierarchy and Separation

Map the role hierarchy:

| Role | Granted By | Can Grant Others? | Revocable? | Timelock? |
|------|-----------|-------------------|-----------|-----------|
| {role} | {grantor} | YES/NO | YES/NO | YES/NO ({duration}) |

**Check**:
- [ ] Are FUND_CONTROL and UPGRADE_CONTROL separated into different roles?
- [ ] Does any single role have both PARAMETER_CONTROL and FUND_CONTROL?
- [ ] Are role assignments behind timelocks?
- [ ] Can roles be revoked, and by whom?

### Step 3: Single Points of Failure

For each privileged role:

| Role | Key Compromise Impact | Mitigation | Residual Risk |
|------|----------------------|------------|---------------|
| {role} | {what attacker can do} | {multisig? timelock? guardian?} | {what remains} |

**Severity assessment**:
- Single EOA with FUND_CONTROL -> HIGH centralization risk
- Multisig with FUND_CONTROL but no timelock -> MEDIUM
- Multisig + timelock with FUND_CONTROL -> LOW (but document)
- No FUND_CONTROL -> INFO

### Step 4: External Governance Dependencies

Identify parameters or behaviors controlled by EXTERNAL governance:

| Dependency | External Entity | What They Control | Protocol Impact If Changed | Notification? |
|------------|----------------|-------------------|---------------------------|---------------|
| {dep} | {entity} | {parameter/behavior} | {impact on this protocol} | YES/NO |

**Pattern**: Protocol depends on external governance decisions (e.g., external protocol upgrades, token migrations, parameter changes) that can silently affect this protocol's behavior without any on-chain notification.

**Check**:
- Can external governance changes break protocol invariants?
- Does the protocol have circuit breakers for external changes?
- Are external governance timelines aligned with this protocol's operational timelines?

### Step 5: Emergency Powers

Document emergency/pause capabilities:

| Emergency Function | Who Can Call | What It Affects | Recovery Path | Time to Recover |
|-------------------|-------------|-----------------|---------------|-----------------|
| {func} | {role} | {scope} | {how to resume} | {estimate} |

**Check**:
- [ ] Can pausing strand user funds permanently?
- [ ] Is there a maximum pause duration?
- [ ] Can users exit during pause (emergency withdraw)?
- [ ] If no exit during pause -> apply Rule 9 (stranded asset severity floor)

## Output Schema

```markdown
## Finding [CR-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: checkmark1,2,3,4,5 | xN(reason) | ?N(uncertain)
**Severity**: Critical/High/Medium/Low/Info
**Location**: Contract.sol:LineN

**Centralization Type**: FUND_CONTROL / PARAMETER_CONTROL / OPERATIONAL_CONTROL / UPGRADE_CONTROL
**Affected Role**: {role_name}
**Mitigation Present**: {multisig/timelock/guardian/NONE}

**Description**: What's wrong
**Impact**: What can happen if role is compromised or acts maliciously
**Recommendation**: How to mitigate (add timelock, separate roles, add guardian)
```

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

---

- Pattern: Upgradeable contract missing `onlyOwner` on `_authorizeUpgrade`, allowing any caller to upgrade to a malicious implementation and drain all funds.
  Where it hit: `WellUpgradeable` contract, `_authorizeUpgrade` function
  Severity: HIGH
  Source: Solodit (row_id 5359)
  Summary: The `WellUpgradeable` contract omits the `onlyOwner` modifier on `_authorizeUpgrade`, so any address can upgrade the proxy to a malicious implementation. Total fund loss for all wells deployed in the system is the worst-case outcome. Fix: add `onlyOwner` to `_authorizeUpgrade`.
  Map to: onlyOwner, upgrade_authority

---

- Pattern: Single governance EOA holds all privileged roles (register products, set economic params, change yield providers, grant/revoke roles) with no separation or timelock. Compromise of that one address lets an attacker drain the protocol.
  Where it hit: Atlendis Labs lending protocol, `governance` role across pool contracts
  Severity: HIGH
  Source: Solodit (row_id 12227)
  Summary: The governance address is the single point of failure for every critical operation in the protocol: it can change yield providers to an attacker-controlled contract and steal all funds. No separation of duties and no timelock are present. Short-term fix: split privileges; long-term: add timelock and incident response plan.
  Map to: onlyOwner, admin_drain, timelock_bypass

---

- Pattern: Owner-controlled `emergencyWithdraw` (or equivalent drain function) callable at any time with no timelock, allowing the owner to pull all user funds instantly.
  Where it hit: `Insure` project, `Vault.setController()` + `utilize()`
  Severity: HIGH
  Source: Solodit (row_id 16765)
  Summary: The vault owner can call `setController()` to point to a malicious contract, then call `utilize()` to transfer the full vault balance there. No timelock guards `setController`. Fix: disallow changing an already-set controller, or require a timelock before the change takes effect.
  Map to: onlyOwner, admin_drain, timelock_bypass

---

- Pattern: Owner can change critical protocol parameters (fee percentages, exchange addresses) instantly without a timelock, enabling sandwich or front-run attacks on users.
  Where it hit: PancakeSwap Compounding Strategy (`gulp`, `setDepositFee`, `setExchange`), BakerFi
  Severity: HIGH
  Source: Solodit (row_id 17816)
  Summary: The contract owner can raise deposit fees from 0 to 5% or swap in a malicious exchange address immediately before a large `gulp` call, extracting tokens from the strategy. A timelock on parameter changes would give users time to exit. Fix: add a timelock before any fee or address update takes effect.
  Map to: onlyOwner, timelock_bypass

---

- Pattern: Timelock bypass: governor can replace itself or set delay to zero in a single untimelocked transaction, gaining unrestricted minting or upgrade authority immediately.
  Where it hit: Malt Finance `Timelock` contract, `setGovernor` / `setDelay`
  Severity: HIGH
  Source: Solodit (row_id 17098)
  Summary: The governor calls `Timelock.setGovernor(attacker)` effective immediately, then the new governor sets `delay = 0`, removing all timelock protection. The governor can then mint unlimited MALT. Fix: make `setGovernor` and `setDelay` callable only from `address(this)` so they must go through the timelock queue.
  Map to: timelock_bypass, upgrade_authority

---

- Pattern: Community Multisig (CM) can use `delegatecall` to bypass protocol-level access control guards, gaining unrestricted control over the entire protocol.
  Where it hit: `GuardCM` contract
  Severity: HIGH
  Source: Solodit (row_id 9224)
  Summary: The guard restricts CM actions to specific contracts and methods but does not block `delegatecall` to arbitrary addresses (other than the timelock). An attacker can exploit `delegatecall` to execute any logic with CM's storage context, bypassing all guards. Fix: disallow `delegatecall` entirely in the guard.
  Map to: onlyOwner, timelock_bypass, multisig_threshold

---

- Pattern: Deployer retains privileged roles (`DAO`, `GOV`) after deployment; if the private key is compromised the attacker can execute any governance action immediately.
  Where it hit: Lybra Finance `GovernanceTimelock` contract, constructor role assignment
  Severity: HIGH
  Source: Solodit (row_id 10769)
  Summary: The constructor grants `DAO` and `GOV` roles to the deployer address. Until those roles are revoked, a compromised deployer key has full governance power. The team fixed this by revoking deployer permissions post-deployment and introducing a multisig for the `ADMIN` role. Best practice: transfer/revoke deployer roles atomically in the deployment script.
  Map to: onlyOwner, admin_drain, multisig_threshold

---

- Pattern: Single EOA owner can pause the protocol indefinitely with no maximum pause duration and no emergency-exit path for users, stranding funds.
  Where it hit: `StakerLight` contract (`pause`/`unpause`, `addRewards`, `recoverERC20` all `onlyOwner`)
  Severity: MEDIUM
  Source: Solodit (row_id 2220)
  Summary: The owner can pause the contract, preventing withdrawals, while also being able to call `recoverERC20` to remove tokens. There is no cap on pause duration and no emergency-withdraw for users. Fix: add a maximum pause window, allow users to exit during a pause, and use a multisig or timelock for owner actions.
  Map to: onlyOwner, Ownable, timelock_bypass

---

- Pattern: Admin can change a critical address (LP token, controller, yield provider) to an arbitrary value without any timelock, allowing immediate rug of staked user funds.
  Where it hit: `veGUAN.sol` (`setLpToken`), various vault/strategy contracts
  Severity: MEDIUM
  Source: Solodit (row_id 2794)
  Summary: The owner can call `setLpToken` to replace the staking token with a worthless address. Users who then unstake receive a different token with no value instead of their original GUAN. Fix: protect critical address setters with a timelock or multisig to give users time to observe and exit.
  Map to: onlyOwner, admin_drain, timelock_bypass

---

- Pattern: `DEFAULT_ADMIN_ROLE` can set `_minDelay` in a timelock to an arbitrarily large value (e.g., max uint256), effectively freezing all future governance proposals with no recovery path.
  Where it hit: `TimelockSafeGuard.updateMinDelay`
  Severity: MEDIUM
  Source: Solodit (row_id 1485)
  Summary: The admin role can call `updateMinDelay` with no upper bound check, setting a delay so large that no proposal can ever be executed, bricking governance. There is also no mechanism to cancel the locked state. Fix: cap `_minDelay` at a reasonable maximum (e.g., 30 days) and prevent setting it to zero.
  Map to: onlyOwner, timelock_bypass, admin_drain


## Step Execution Checklist

- [ ] Step 1: ALL privileged functions enumerated (via Slither, not manual scan)
- [ ] Step 2: Role hierarchy mapped with separation analysis
- [ ] Step 3: Single points of failure identified for each role
- [ ] Step 4: External governance dependencies documented
- [ ] Step 5: Emergency powers and recovery paths assessed
