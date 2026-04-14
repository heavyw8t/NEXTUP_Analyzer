---
name: "memory-safety-audit"
description: "Trigger Always (C/C++) - Systematic audit of memory allocation, deallocation, and pointer safety"
---

# Skill: MEMORY_SAFETY_AUDIT

> **Trigger**: Always required for C/C++ audits
> **Covers**: Use-after-free, double-free, memory leaks, dangling pointers, uninitialized memory
> **Required**: YES (foundational C/C++ security check)

## Trigger Patterns

```
malloc|calloc|realloc|free|new |new\[|delete |delete\[|unique_ptr|shared_ptr|make_unique|make_shared
```

## Reasoning Template

### Step 1: Allocation Inventory

Enumerate ALL dynamic allocations using grep:

| # | Allocation Site | Type | Size Source | Allocation Function | File:Line |
|---|----------------|------|-------------|--------------------:|-----------|
| 1 | {variable} | {type} | {how size is determined} | malloc/new/etc | {file:line} |

**Categorize each**:
- **HEAP_RAW**: malloc/calloc/realloc (C-style, manual free required)
- **HEAP_CPP**: new/new[] (C++-style, manual delete required)
- **SMART_PTR**: unique_ptr/shared_ptr (RAII-managed)
- **STACK**: VLA or alloca (stack-allocated, auto-freed but overflow risk)

### Step 2: Deallocation Tracing

For each HEAP_RAW and HEAP_CPP allocation, trace ALL paths to deallocation:

| Allocation | Dealloc Function | Dealloc Site | All Paths Covered? | Missing Paths |
|-----------|-----------------|-------------|-------------------:|--------------|
| {var} | free/delete | {file:line} | YES/NO | {error path, early return, exception} |

**Check for each**:
- [ ] Is pointer set to NULL after free? (prevents use-after-free)
- [ ] Are there multiple code paths that could free the same pointer? (double-free)
- [ ] Is the correct deallocator used? (malloc→free, new→delete, new[]→delete[])
- [ ] On error/exception paths, is the allocation freed?

### Step 3: Use-After-Free Detection

For each free/delete call, trace ALL subsequent uses of the pointer:

| Free Site | Pointer | Subsequent Uses | Use-After-Free? | File:Line |
|----------|---------|-----------------|----------------:|-----------|

**Patterns to check**:
- free(ptr) followed by ptr->field access
- delete obj followed by obj->method() call
- Iterator invalidation: container.erase() followed by iterator use
- Vector reallocation: push_back() invalidating previously stored references/pointers

### Step 4: Uninitialized Memory Detection

For each allocation WITHOUT immediate initialization:

| Allocation | Initialized Before Use? | First Read Site | Risk |
|-----------|------------------------|----------------|------|
| malloc(n) | memset/explicit init? | {file:line} | Information leak / undefined behavior |
| stack var | assigned before read? | {file:line} | Undefined behavior |

**Note**: calloc zero-initializes. malloc does NOT. new with constructor initializes. Placement new may not.

### Step 5: Smart Pointer Correctness

For SMART_PTR allocations:
- [ ] Is shared_ptr used where unique_ptr suffices? (unnecessary overhead)
- [ ] Are there raw pointer escapes from smart pointers (.get() stored separately)?
- [ ] Are there circular references with shared_ptr? (memory leak)
- [ ] Is make_shared/make_unique used? (exception safety)

### Step 6: Buffer Overflow Proximity

For each allocation, check if the allocated buffer is used in:
- memcpy/memmove (is copy size ≤ buffer size?)
- strcpy/strncpy (is source length ≤ destination size?)
- Array indexing (is index < allocated count?)

### Output Format

For each finding, use standard format with [MEMSAFE-N] IDs.
Severity guide:
- Use-after-free with attacker-controlled data → HIGH/CRITICAL
- Double-free → MEDIUM/HIGH (heap corruption)
- Memory leak in hot path → MEDIUM (DoS via resource exhaustion)
- Memory leak in one-time path → LOW/INFO
- Missing NULL check after malloc → MEDIUM (null deref → crash)
- Uninitialized read of sensitive data → MEDIUM/HIGH (information disclosure)
