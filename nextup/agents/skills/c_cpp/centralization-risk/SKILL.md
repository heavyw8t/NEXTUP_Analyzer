---
name: "centralization-risk"
description: "Trigger Protocol has privileged roles or admin configuration - Covers single points of failure, privilege escalation"
---

# Skill: CENTRALIZATION_RISK

> **Trigger**: Protocol has privileged roles, admin APIs, or configuration authority
> **Covers**: Single points of failure, privilege escalation, configuration manipulation
> **Required**: NO (recommended when admin/config patterns detected)

## Trigger Patterns

```
admin|root|superuser|privilege|permission|role.*check|authorize|config.*set|set.*config|is_admin|require_auth
```

## Reasoning Template

### Step 1: Privilege Inventory

Enumerate ALL privileged functions using grep:

| # | Function | File | Permission Check | What It Controls | Impact If Abused |
|---|----------|------|-----------------|------------------|-----------------|

**Categorize**:
- **FUND_CONTROL**: Can move/lock/destroy user funds or assets
- **PARAMETER_CONTROL**: Can change fees, rates, thresholds, limits
- **OPERATIONAL_CONTROL**: Can pause, shutdown, enable/disable features
- **KEY_CONTROL**: Can rotate keys, change crypto parameters

### Step 2: Configuration Authority

For each admin-settable parameter:

| Parameter | Setter Function | Range Validation? | Can Break Users? | Timelock? |
|-----------|----------------|------------------|-----------------|-----------|

**Check**:
- [ ] Can admin set parameters that make user operations fail?
- [ ] Can admin change crypto parameters that invalidate existing proofs/signatures?
- [ ] Are parameter changes retroactive (affecting in-progress operations)?

### Step 3: Key Management

For cryptographic systems:

| Key Type | Who Holds | Rotation Mechanism | Compromise Impact |
|---------|---------|-------------------|------------------|

### Step 4: Single Points of Failure

For each privileged role or key:

| Role/Key | Compromise Impact | Mitigation Present | Residual Risk |
|---------|------------------|-------------------|---------------|

**Severity assessment**:
- Single process/account with FUND_CONTROL, no backup -> HIGH centralization risk
- Shared secret or HSM with FUND_CONTROL but no rotation -> MEDIUM
- Properly rotatable key with audit log -> LOW (but document)
- No FUND_CONTROL -> INFO

### Step 5: Emergency Controls

Document emergency/shutdown capabilities:

| Emergency Function | Who Can Trigger | What It Affects | Recovery Path | Time to Recover |
|-------------------|----------------|-----------------|---------------|-----------------|

**Check**:
- [ ] Can shutdown strand user data or funds permanently?
- [ ] Is there a maximum lockout duration?
- [ ] Can users retrieve their data/funds during a lockout?

## Output Schema

```markdown
## Finding [CENTRAL-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: checkmark1,2,3,4,5 | xN(reason) | ?N(uncertain)
**Severity**: Critical/High/Medium/Low/Info
**Location**: file.c:LineN

**Centralization Type**: FUND_CONTROL / PARAMETER_CONTROL / OPERATIONAL_CONTROL / KEY_CONTROL
**Affected Role/Key**: {name}
**Mitigation Present**: {HSM / key rotation / audit log / NONE}

**Description**: What's wrong
**Impact**: What can happen if role is compromised or acts maliciously
**Recommendation**: How to mitigate (add audit logging, enforce key rotation, separate roles)
```

## Step Execution Checklist

- [ ] Step 1: ALL privileged functions enumerated (grep for admin/auth/permission patterns)
- [ ] Step 2: Configuration authority mapped with range validation analysis
- [ ] Step 3: Key management lifecycle documented for all cryptographic keys
- [ ] Step 4: Single points of failure identified for each role and key
- [ ] Step 5: Emergency controls and recovery paths assessed
