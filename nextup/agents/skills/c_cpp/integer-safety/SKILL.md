---
name: "integer-safety"
description: "Trigger Arithmetic on user-influenced values detected - Integer overflow, underflow, and type confusion audit"
---

# Skill: INTEGER_SAFETY

> **Trigger**: Arithmetic on user input or size calculations detected
> **Covers**: Integer overflow/underflow, signed/unsigned confusion, truncation, undefined behavior
> **Required**: YES when arithmetic on external input detected

## Trigger Patterns

```
size_t|uint32_t|uint64_t|int32_t|int64_t|__builtin_.*_overflow|numeric_limits|INT_MAX|UINT_MAX|SIZE_MAX
```

## Reasoning Template

### Step 1: Arithmetic Operation Inventory

Enumerate arithmetic on user-influenced or size-related values:

| # | Operation | Operand Types | User-Influenced? | Overflow Check? | File:Line |
|---|-----------|--------------|-----------------|----------------|-----------|

### Step 2: Signed/Unsigned Confusion

For every comparison or assignment between signed and unsigned:

| # | Expression | Signed Type | Unsigned Type | Implicit Conversion | Risk | File:Line |
|---|-----------|-------------|--------------|--------------------:|------|-----------|

**Critical patterns**:
- `if (signed_val < unsigned_val)` — signed silently converts to unsigned, negative becomes huge
- `unsigned x = negative_value` — wraps to large number
- `int len = unsigned_size` — truncation if size > INT_MAX
- Array indexing with signed index: `arr[signed_idx]` where signed_idx could be negative

### Step 3: Overflow/Underflow Paths

For each arithmetic operation on user-influenced values:
- **Signed overflow**: UNDEFINED BEHAVIOR in C/C++. Compiler can assume it never happens and optimize accordingly.
- **Unsigned overflow**: Wraps modulo 2^N. Not UB but often a logic bug.
- **size_t arithmetic**: `size_a + size_b` can wrap, leading to undersized allocation then buffer overflow

| Operation | Can Overflow? | Consequence | Safe Alternative |
|-----------|-------------|-------------|-----------------|
| a + b | YES/NO | {what happens} | __builtin_add_overflow / SafeInt<> |
| a * b | YES/NO | {what happens} | __builtin_mul_overflow |
| a - b | YES/NO | {unsigned underflow wraps} | check a >= b first |

### Step 4: Truncation Analysis

For every narrowing conversion (explicit or implicit):

| # | From Type | To Type | Can Lose Data? | Checked? | File:Line |
|---|-----------|---------|---------------|---------|-----------|

Common dangerous patterns:
- uint64_t → uint32_t (silent truncation)
- size_t → int (size_t is unsigned, int is signed — double danger)
- double → int (fractional loss + overflow if > INT_MAX)

### Step 5: Allocation Size Calculations

Special focus on size calculations used for memory allocation:

| Allocation | Size Expression | Can Overflow? | Result if Overflow |
|-----------|----------------|-------------|-------------------|
| malloc(n * sizeof(T)) | n * sizeof(T) | YES if n is large | Undersized buffer → heap overflow |

**Rule**: Any `malloc(a * b)` without overflow check is a potential heap overflow.

### Output Format
Use [INTSAFE-N] finding IDs. Severity: integer overflow in allocation size → HIGH/CRITICAL.
