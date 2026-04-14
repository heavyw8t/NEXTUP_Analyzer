---
name: "buffer-operations"
description: "Trigger memcpy/strcpy/strncpy/snprintf detected - Buffer boundary and bounds checking audit"
---

# Skill: BUFFER_OPERATIONS

> **Trigger**: memcpy/memmove/strcpy/strncpy/snprintf/sprintf usage detected
> **Covers**: Buffer overflows, off-by-one errors, null termination, format string issues
> **Required**: YES when buffer operation patterns detected

## Trigger Patterns

```
memcpy|memmove|strcpy|strncpy|strcat|strncat|sprintf|snprintf|gets|fgets|scanf|sscanf|vsprintf
```

## Reasoning Template

### Step 1: Dangerous Function Inventory

Enumerate ALL buffer operation call sites:

| # | Function | Source | Destination | Size | Bounds Verified? | File:Line |
|---|----------|--------|-------------|------|-----------------|-----------|

**Danger levels**:
- **CRITICAL**: gets(), sprintf(), strcpy() — unbounded by design
- **HIGH**: scanf("%s"), strcat() — commonly misused
- **MEDIUM**: memcpy(), strncpy(), snprintf() — safe IF size is correct
- **LOW**: fgets(), strncat() with verified bounds

### Step 2: Size Validation Trace

For each CRITICAL/HIGH function call:

| Call Site | Size/Bound Parameter | Source of Size | User-Controlled? | Overflow Possible? |
|----------|---------------------|---------------|-----------------|-------------------|

**Check**:
- [ ] Is the size parameter derived from the source buffer or destination buffer?
- [ ] Can an attacker control the size parameter?
- [ ] Is there an integer overflow in the size calculation? (e.g., `len1 + len2` wrapping)
- [ ] For strncpy: is null termination guaranteed? (strncpy does NOT null-terminate if src >= n)

### Step 3: Off-by-One Analysis

For each bounded operation:
- [ ] Does the bound include or exclude the null terminator?
- [ ] Is the comparison `<` or `<=`? (fencepost error)
- [ ] For loops: is the index 0-based with `< size` or 1-based with `<= size`?

### Step 4: Format String Audit

For every printf-family call:
- [ ] Is the format string a compile-time constant? (SAFE)
- [ ] Is user input passed as the format string? (CRITICAL: format string vulnerability)
- [ ] Do format specifiers match argument types? (type confusion)
- [ ] Is `%n` used anywhere? (write primitive)

### Step 5: Safe Alternative Recommendations

For each finding, recommend the safe alternative:
| Dangerous | Safe Alternative | Notes |
|-----------|-----------------|-------|
| strcpy | strlcpy or snprintf | strlcpy not in C standard but widely available |
| sprintf | snprintf | Always use snprintf with explicit size |
| strcat | strlcat or snprintf | Track remaining buffer space |
| gets | fgets | Always specify max length |
| scanf("%s") | scanf("%Ns") or fgets | Specify field width |

### Output Format
Use [BUFOP-N] finding IDs. Severity: buffer overflow with attacker-controlled input → HIGH/CRITICAL.
