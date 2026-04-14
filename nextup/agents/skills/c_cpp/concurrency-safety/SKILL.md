---
name: "concurrency-safety"
description: "Trigger mutex/pthread/std::thread/atomic detected - Race conditions, deadlocks, and thread safety audit"
---

# Skill: CONCURRENCY_SAFETY

> **Trigger**: Multi-threaded code detected (mutex, pthread, std::thread, atomic)
> **Covers**: Data races, deadlocks, TOCTOU, lock ordering violations, atomic correctness
> **Required**: YES when threading primitives detected

## Trigger Patterns

```
mutex|pthread_|std::thread|std::async|std::atomic|lock_guard|unique_lock|shared_lock|condition_variable|sem_wait|sem_post
```

## Reasoning Template

### Step 1: Shared State Inventory

Enumerate ALL mutable state accessed from multiple threads:

| # | Variable | Type | Accessed By Threads | Protection | File:Line |
|---|----------|------|-------------------|-----------|-----------|

**Protection categories**:
- MUTEX: Protected by mutex/lock_guard
- ATOMIC: std::atomic or __atomic builtins
- NONE: Unprotected (DATA RACE → UB)
- VOLATILE: volatile keyword (NOT thread-safe in C/C++!)

### Step 2: Data Race Detection

For each NONE-protected shared variable:

| # | Variable | Read Sites | Write Sites | Race Condition? | Impact |
|---|----------|-----------|------------|----------------:|--------|

**Critical**: In C/C++, a data race (concurrent access where at least one is a write, without synchronization) is UNDEFINED BEHAVIOR. Not just a logic bug — the compiler is free to do anything.

### Step 3: Lock Analysis

For each mutex/lock:
- Map which variables are protected by which lock
- Check: Is the SAME lock consistently used for the SAME variable?
- Check: Are there paths that access the variable WITHOUT holding the lock?

| Variable | Expected Lock | Access Site | Lock Held? | Gap? |
|---------|--------------|-------------|-----------|------|

### Step 4: Deadlock Detection

Enumerate all lock acquisition orders:

| Thread/Function | Lock Order | File:Line |
|----------------|-----------|-----------|

**Check**: If Thread A acquires Lock1 then Lock2, and Thread B acquires Lock2 then Lock1 → DEADLOCK.
- [ ] Is there a documented lock ordering policy?
- [ ] Are all acquisition sites consistent with the ordering?
- [ ] Are there nested lock acquisitions?

### Step 5: TOCTOU (Time-of-Check-Time-of-Use)

For each check-then-act pattern on shared state:

| Check | Act | Thread-Safe? | Can State Change Between? |
|-------|-----|-------------|--------------------------|

Common TOCTOU patterns:
- `if (map.contains(key)) { map[key].do_something(); }` — key could be removed between check and use
- `if (ptr != nullptr) { ptr->method(); }` — ptr could become null
- `stat(file) then open(file)` — file could be replaced (filesystem TOCTOU)

### Step 6: Atomic Correctness

For each std::atomic usage:
- [ ] Is the memory ordering correct? (relaxed vs acquire/release vs seq_cst)
- [ ] Are compound operations (check-then-modify) using compare_exchange, not separate load+store?
- [ ] Is atomic used for a single variable that should be protected with a mutex (multi-variable invariant)?

### Step 7: Condition Variable Safety

For each condition_variable:
- [ ] Is wait() called inside a while loop (spurious wakeup protection)?
- [ ] Is the predicate checked under the same lock?
- [ ] Is notify called after modifying the predicate?

### Output Format
Use [CONCUR-N] finding IDs. Severity: data race with potential corruption → HIGH. Deadlock → MEDIUM. TOCTOU → depends on impact.
