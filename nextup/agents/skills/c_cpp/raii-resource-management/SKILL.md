---
name: "raii-resource-management"
description: "Trigger new/malloc/fopen/socket operations detected - RAII pattern completeness and resource lifecycle audit"
---

# Skill: RAII_RESOURCE_MANAGEMENT

> **Trigger**: Dynamic allocation or resource acquisition detected
> **Covers**: Resource leaks, missing cleanup on error paths, RAII violations, exception safety
> **Required**: NO (recommended when mix of raw and RAII resource management detected)

## Trigger Patterns

```
fopen|fclose|open\(|close\(|socket\(|accept\(|FILE\s*\*|unique_ptr|shared_ptr|lock_guard|new\s|delete\s
```

## Reasoning Template

### Step 1: Resource Acquisition Inventory

| # | Resource Type | Acquisition | Release | RAII Wrapped? | File:Line |
|---|-------------|------------|---------|--------------|-----------|
| 1 | File handle | fopen() | fclose() | NO / std::fstream | {loc} |
| 2 | Socket | socket() | close() | NO / custom RAII | {loc} |
| 3 | Memory | malloc() | free() | NO / unique_ptr | {loc} |
| 4 | Lock | pthread_mutex_lock | pthread_mutex_unlock | NO / lock_guard | {loc} |

### Step 2: Exception Safety Audit

For each function that acquires resources:
- [ ] If an exception is thrown between acquire and release, is the resource leaked?
- [ ] Are there early return paths that skip release?
- [ ] Is the function marked noexcept but calls functions that can throw?

**Exception safety levels**:
- **No-throw**: Cannot fail (noexcept, C functions)
- **Strong**: Operation succeeds completely or has no effect
- **Basic**: Invariants preserved but state may change
- **None**: Resource leak on exception

### Step 3: Error Path Audit

For each resource acquisition:
- Trace ALL code paths from acquisition to function exit
- On each path: is the resource released?
- Special attention to: `if (error) return;` paths, `goto cleanup;` patterns, nested acquisitions

| Resource | Error Path | Released? | Leak? |
|---------|-----------|----------|-------|

### Step 4: RAII Correctness

For each RAII wrapper:
- [ ] Is the destructor called in the correct order? (reverse of construction)
- [ ] Are move semantics correct? (moved-from object in valid state?)
- [ ] Is the Rule of Five followed? (destructor + copy ctor/assign + move ctor/assign)
- [ ] Are there raw pointer escapes from smart pointers that outlive the smart pointer?

## Output Schema

```markdown
## Finding [RAII-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: checkmark1,2,3,4 | xN(reason) | ?N(uncertain)
**Severity**: Critical/High/Medium/Low/Info
**Location**: file.cpp:LineN

**Resource Type**: File / Socket / Memory / Lock / Other
**RAII Wrapped**: YES / NO
**Leak Path**: {describe the code path that causes the leak}

**Description**: What's wrong
**Impact**: What can happen (crash, fd exhaustion, memory exhaustion, deadlock)
**Recommendation**: Use RAII wrapper / add cleanup on error path / use unique_ptr
```

## Step Execution Checklist

- [ ] Step 1: ALL resource acquisitions enumerated (grep for malloc/fopen/new/socket/open)
- [ ] Step 2: Exception safety level assessed for each function
- [ ] Step 3: ALL code paths from acquisition to exit traced for each resource
- [ ] Step 4: RAII wrapper correctness verified (Rule of Five, move semantics)
