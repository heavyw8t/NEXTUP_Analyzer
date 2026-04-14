---
name: "economic-design-audit"
description: "Trigger Monetary parameters detected - Economic design review for fee structures, reward mechanisms, and value flows"
---

# Skill: ECONOMIC_DESIGN_AUDIT

> **Trigger**: Fee structures, reward mechanisms, or value flow patterns detected
> **Covers**: Fee bypass, reward manipulation, value extraction, economic DoS
> **Required**: NO (P2 priority, recommended when economic logic detected)

## Trigger Patterns

```
fee|reward|penalty|incentive|stake|deposit|withdraw|balance.*update|transfer.*value|payment
```

## Reasoning Template

### Step 1: Value Flow Map

Map all value entry and exit points:

| # | Entry Point | Exit Point | Value Type | Who Controls | Validated? |
|---|-----------|----------|-----------|-------------|-----------|

**Categorize each flow**:
- **USER_DEPOSIT**: Value entering from external user
- **PROTOCOL_REWARD**: Value emitted by protocol (inflation, yield)
- **FEE_COLLECTION**: Value collected as fees
- **PENALTY_SLASH**: Value destroyed or redistributed as penalty
- **WITHDRAWAL**: Value exiting to external user

### Step 2: Fee Structure Analysis

For each fee mechanism:
- [ ] Can fees be bypassed by splitting transactions into smaller amounts?
- [ ] Can fees be avoided by specific timing (e.g., during maintenance windows)?
- [ ] Are fee calculations vulnerable to rounding exploitation? (integer division truncation)
- [ ] Can fee parameters be manipulated by admin to extract value from users?
- [ ] Is there a minimum fee to prevent dust/griefing transactions?

| Fee Mechanism | Bypass Vector | Rounding Risk | Admin Manipulation | Min Fee Enforced? |
|--------------|--------------|--------------|-------------------|------------------|

### Step 3: Reward/Incentive Analysis

For each reward mechanism:
- [ ] Can rewards be gamed by specific action sequences (deposit, claim, withdraw, repeat)?
- [ ] Is the reward pool bounded? Can it be fully drained by a single actor?
- [ ] Are there front-running opportunities on reward distribution events?
- [ ] Is any time-weighting or epoch mechanism correctly implemented?
- [ ] Can a large actor disproportionately capture rewards at the expense of smaller participants?

| Reward Mechanism | Gaming Vector | Drain Risk | Front-run Risk | Time-weight Correct? |
|----------------|--------------|-----------|---------------|---------------------|

### Step 4: Economic DoS Vectors

- [ ] Can a small cost to the attacker cause large cost to the protocol or other users?
- [ ] Can an attacker block legitimate users from accessing value (queue flooding, slot exhaustion)?
- [ ] Are there griefing vectors where attacker loses X but victim loses 10X?
- [ ] Can reward/fee calculations overflow or underflow at extreme values?

| DoS Vector | Attacker Cost | Victim Cost | Ratio | Mitigation |
|-----------|--------------|------------|-------|-----------|

### Step 5: Integer Arithmetic Integrity

For all value calculations:
- [ ] Are multiplication operations checked for overflow before division? (`a * b / c` vs `a / c * b`)
- [ ] Are there precision loss issues from integer division in intermediate steps?
- [ ] Is value accounting consistent (no value creation or destruction in normal flows)?
- [ ] Are there any off-by-one errors in boundary conditions (>= vs > for fee thresholds)?

| Calculation | Overflow Risk | Precision Loss | Value Conservation? |
|-----------|-------------|--------------|-------------------|

## Output Schema

```markdown
## Finding [ECON-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: checkmark1,2,3,4,5 | xN(reason) | ?N(uncertain)
**Severity**: Critical/High/Medium/Low/Info
**Location**: file.c:LineN

**Economic Category**: FEE_BYPASS / REWARD_GAMING / ECONOMIC_DOS / INTEGER_ARITHMETIC / VALUE_EXTRACTION
**Value Flow Affected**: {entry/exit point name}
**Extractable Value**: {estimate or "unbounded"}

**Description**: What's wrong with the economic design or implementation
**Impact**: What an attacker can extract or what legitimate users lose
**Proof of Concept**: Step-by-step attack sequence showing economic gain
**Recommendation**: Fix the calculation / add bounds / separate roles / add rate limiting
```

## Step Execution Checklist

- [ ] Step 1: ALL value entry and exit points mapped and categorized
- [ ] Step 2: Fee mechanisms audited for bypass vectors and rounding exploitation
- [ ] Step 3: Reward mechanisms audited for gaming, drain, and front-running
- [ ] Step 4: Economic DoS vectors enumerated with cost-ratio analysis
- [ ] Step 5: Integer arithmetic checked for overflow, precision loss, and value conservation
