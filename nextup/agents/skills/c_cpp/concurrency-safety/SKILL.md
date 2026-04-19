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
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sources: Bitcoin Core GitHub (github.com/bitcoin/bitcoin), XRPLF/rippled GitHub (github.com/XRPLF/rippled), bitcoincore.org security advisories, NVD/CVE database.

---

## Example 1: CCheckQueue::IsIdle Race Condition (Bitcoin Core, fixed in 0.14.3)

**Source**: Bitcoin Core commit e207342; bitcoincore.org/en/releases/0.14.3/
**Severity**: High
**Concurrency Category**: race_condition / mutex
**CVE/Reference**: Bitcoin Core 0.14.3 release notes; PR #9495 / commit e207342

`CCheckQueueControl` accessed fields of `CCheckQueue` in its constructor without holding the queue's mutex. If a worker thread was simultaneously modifying `nIdle` or internal bookkeeping, the constructor read stale or torn values, producing an incorrect "is idle" answer. A script-validation control object instantiated on one thread while validation workers were still active on another could conclude the queue was idle and proceed unsafely.

```cpp
// VULNERABLE: constructor reads nIdle without lock
CCheckQueueControl(CCheckQueue* pqueue) : pqueue(pqueue), fDone(false) {
    if (pqueue) {
        ENTER_CRITICAL_SECTION(pqueue->mutex);
        // nIdle checked here but nTotal written by workers without this lock path
        assert(pqueue->nTotal == pqueue->nIdle); // data race on nTotal/nIdle
    }
}

// FIXED: acquire the lock before reading any shared state
CCheckQueueControl(CCheckQueue* pqueue) : pqueue(pqueue), fDone(false) {
    if (pqueue) {
        LOCK(pqueue->mutex);
        assert(pqueue->nTotal == pqueue->nIdle);
    }
}
```

**Mapping**: SKILL.md Step 3 (Lock Analysis — access site without lock held).

---

## Example 2: Chain-Tip Data Race in REST Handler (Bitcoin Core, PR #25077)

**Source**: Bitcoin Core PR #25077 (maflcko, 2022); bitcoincore.reviews/25077
**Severity**: High
**Concurrency Category**: data_race / mutex
**CVE/Reference**: GitHub PR bitcoin/bitcoin#25077

`ActiveTip()` and `ActiveHeight()` in the REST handler were called without holding `cs_main`. Because `CChain::Tip()` and `CChain::Height()` operate on shared state protected by `cs_main`, concurrent calls from the HTTP worker thread while the validation thread was updating the active chain produced torn reads: the returned height could belong to a different tip than the returned block index pointer, corrupting the REST JSON response.

```cpp
// VULNERABLE: REST handler thread calls without cs_main
UniValue getblockchaininfo(HTTPRequest* req, ...) {
    CBlockIndex* tip = ::ChainActive().Tip();   // no lock
    int height = ::ChainActive().Height();      // no lock — may differ from tip above
    // tip and height may now refer to different chain states
}

// FIXED: hold cs_main for the entire read
UniValue getblockchaininfo(HTTPRequest* req, ...) {
    LOCK(cs_main);
    CBlockIndex* tip = ::ChainActive().Tip();
    int height = ::ChainActive().Height();
}
```

**Mapping**: SKILL.md Step 2 (Data Race Detection — concurrent read/write without synchronization) and Step 3 (Lock Analysis).

---

## Example 3: Self-Connect Detection Race (Bitcoin Core 27.2, PR #30394)

**Source**: Bitcoin Core PR #30394 (theStack, 2024); bitcoincore.org/en/releases/27.2/
**Severity**: Medium
**Concurrency Category**: TOCTOU / race_condition
**CVE/Reference**: Bitcoin Core 27.2 release notes; PR bitcoin/bitcoin#30394

When a new outbound connection was established, `InitializeNode` pushed a `VERSION` message and only then added the `CNode` to `m_nodes`. If the local node received and processed that VERSION message (self-connect path) before the object appeared in `m_nodes`, the self-connect detection check found no matching entry and allowed the loopback connection to proceed. The window between message dispatch and node registration was the exploitable race.

```cpp
// VULNERABLE: VERSION sent before node is in m_nodes
void InitializeNode(CNode* pnode, ...) {
    PushNodeVersion(pnode, ...);   // VERSION dispatched here
    // ... later, in caller:
    m_nodes.push_back(pnode);      // node added here — detection window exists
}

// FIXED: defer VERSION until node is in m_nodes
// SendMessages() is only called for nodes already in m_nodes,
// so moving PushNodeVersion there closes the race window.
```

**Mapping**: SKILL.md Step 5 (TOCTOU — check-then-act on shared node list state).

---

## Example 4: BaseIndex Destructor vptr Data Race (Bitcoin Core, Issue #25365 / #27355)

**Source**: Bitcoin Core issues #25365 and #27355; ThreadSanitizer reports on aarch64
**Severity**: Medium
**Concurrency Category**: data_race / thread_safety
**CVE/Reference**: GitHub bitcoin/bitcoin#25365, #27355

ThreadSanitizer (TSAN) detected a data race on the vtable pointer (`vptr`) of `BaseIndex` during node shutdown. When the destructor of a derived index class starts running, it overwrites the vptr with the base class's vptr. If an index-processing thread simultaneously executes a virtual method through the same pointer, it may call the base-class stub instead of the derived implementation. In C++ this is undefined behavior: the compiler may hoist or eliminate the virtual dispatch based on assumed pointer stability.

```cpp
// Race window: destructor in thread A overwrites vptr
~DerivedIndex() {
    // compiler sets vptr = &BaseIndex::vtable here
    stop_threads();    // tries to stop thread B, but thread B may already be in a virtual call
}

// Thread B simultaneously:
void WorkerThread(BaseIndex* idx) {
    idx->CustomMethod();   // virtual call — vptr may now point to BaseIndex stub
}
```

**Mapping**: SKILL.md Step 2 (Data Race Detection — vptr write vs virtual dispatch read).

---

## Example 5: rippled Shard Multiple Race Conditions (PR #4188)

**Source**: XRPLF/rippled PR #4188 (seelabs, ~2021); rippled 1.9.x series
**Severity**: High
**Concurrency Category**: data_race / mutex
**CVE/Reference**: GitHub XRPLF/rippled#4188

Clang ThreadSafetyAnalysis applied to the `Shard` component revealed multiple data members accessed from the shard worker thread without holding the protecting mutex. The race produced rare but reproducible segfaults under unit-test looping. Adding the missing lock annotations and acquiring the lock at all read/write sites eliminated the crashes (10,525 loop iterations with zero segfaults after fix).

```cpp
// VULNERABLE (pre-fix): fields read by worker without lock
class Shard {
    std::mutex mutex_;
    uint32_t lastRotation_;      // GUARDED_BY(mutex_) — annotation missing
    // ...
    void workerThread() {
        if (lastRotation_ > threshold_) { ... }  // no lock — data race
    }
};

// FIXED: acquire lock before accessing guarded fields
void workerThread() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastRotation_ > threshold_) { ... }
}
```

**Mapping**: SKILL.md Step 3 (Lock Analysis — access site without lock held) and Step 1 (Shared State Inventory using GUARDED_BY annotations).

---

## Example 6: rippled Peer Status Change Race (commit 9dbf849, v1.2.1)

**Source**: XRPLF/rippled commit 9dbf849; rippled 1.2.1 release notes
**Severity**: Medium
**Concurrency Category**: race_condition / thread_safety
**CVE/Reference**: XRPLF/rippled@9dbf849; rippled 1.2.1 changelog

`PeerImp` processed incoming status-change messages from the network I/O thread while the peer object's internal state was being modified from the application thread. The result was a window where the I/O thread read `m_inbound` or connection-state fields that the application thread was concurrently writing, with no synchronization between them. The fix (4 additions, 6 deletions in `src/ripple/overlay/impl/PeerImp.cpp`) serialized access through the existing strand.

```cpp
// VULNERABLE: status message handler called directly from I/O thread
void PeerImp::onMessage(std::shared_ptr<protocol::TMStatusChange> const& m) {
    // reads this->m_inbound, this->state_ — written concurrently by app thread
    if (m_inbound) { ... }
}

// FIXED: dispatch through strand to serialize with app-thread writes
void PeerImp::onMessage(std::shared_ptr<protocol::TMStatusChange> const& m) {
    strand_.dispatch([this, m]() {
        if (m_inbound) { ... }   // now serialized
    });
}
```

**Mapping**: SKILL.md Step 2 (Data Race Detection) and Step 5 (TOCTOU — check-then-act on peer connection state).

---

## Example 7: rippled UptimeTimer Data Race on m_elapsedTime (Issue #2487)

**Source**: XRPLF/rippled issue #2487; ThreadSanitizer report in rippled CI
**Severity**: Medium
**Concurrency Category**: data_race / thread_safety
**CVE/Reference**: GitHub XRPLF/rippled#2487

TSAN flagged `UptimeTimer::incrementElapsedTime()` as having a data race: `m_elapsedTime` (a plain `int`) was written by the timer thread and read by multiple query threads with no synchronization primitive. While contributors debated whether a fence was sufficient, the class was ultimately replaced by `UptimeClock` (a `chrono`-compatible clock with a dedicated once-per-second update loop protected by atomic operations). The unprotected field was C++ UB: any plain non-atomic read/write pair on an `int` accessed from multiple threads is a data race regardless of word-size alignment.

```cpp
// VULNERABLE: plain int written and read across threads
class UptimeTimer {
    int m_elapsedTime;  // NOT std::atomic<int>
    void incrementElapsedTime() {
        m_elapsedTime++;       // write — data race with readers
    }
    int getElapsedSeconds() const {
        return m_elapsedTime;  // read — undefined behavior if concurrent write
    }
};

// FIXED pattern (UptimeClock replacement):
class UptimeClock {
    std::atomic<int> elapsed_{0};
    void tick() { elapsed_.fetch_add(1, std::memory_order_relaxed); }
    int seconds() const { return elapsed_.load(std::memory_order_relaxed); }
};
```

**Mapping**: SKILL.md Step 2 (Data Race Detection — NONE-protected shared variable) and Step 6 (Atomic Correctness).

---

## Example 8: Lock-Order Inversion Deadlock in Bitcoin Core Tests (Issue #30764)

**Source**: Bitcoin Core issue #30764 (TSAN report, August 2024); PR #12882
**Severity**: Medium
**Concurrency Category**: mutex / thread_safety (deadlock)
**CVE/Reference**: GitHub bitcoin/bitcoin#30764, #12882

ThreadSanitizer detected a lock-order-inversion between `cs_main` and a secondary lock across multiple code paths. Thread A acquired `cs_main` then the secondary lock; Thread B acquired the secondary lock then `cs_main`. Under concurrent execution this is a classic ABBA deadlock. Bitcoin Core's `DEBUG_LOCKORDER` build flag (`-DDEBUG_LOCKORDER`) instruments `LOCK`/`LOCK2` macros at runtime to detect and log order inversions; without it, the inversion went unnoticed in production builds until TSAN reported it.

```
Thread A:  LOCK(cs_main) → LOCK(cs_secondary)   // e.g., validation path
Thread B:  LOCK(cs_secondary) → LOCK(cs_main)   // e.g., wallet callback path
// → ABBA deadlock if both threads reach their second lock simultaneously
```

Fix: establish and document a global lock ordering (e.g., cs_main always before cs_wallet/cs_secondary) and enforce it with `DEBUG_LOCKORDER` in CI.

**Mapping**: SKILL.md Step 4 (Deadlock Detection — inconsistent lock acquisition order across threads).

---

## Coverage Summary

| # | Finding | Concurrency Category | SKILL.md Step | Severity | Source |
|---|---------|---------------------|---------------|----------|--------|
| 1 | CCheckQueue::IsIdle race — read shared state without lock | mutex / race_condition | Step 3 | High | Bitcoin Core 0.14.3 |
| 2 | Chain-tip data race in REST handler (ActiveTip without cs_main) | data_race / mutex | Step 2, 3 | High | Bitcoin Core PR #25077 |
| 3 | Self-connect TOCTOU — VERSION sent before node in m_nodes | TOCTOU / race_condition | Step 5 | Medium | Bitcoin Core 27.2 |
| 4 | BaseIndex vptr data race during destructor vs virtual call | data_race / thread_safety | Step 2 | Medium | Bitcoin Core #25365/#27355 |
| 5 | rippled Shard multiple data races (TSAN-flagged, segfaults) | data_race / mutex | Step 3, 1 | High | rippled PR #4188 |
| 6 | rippled peer status-change race (I/O thread vs app thread) | race_condition / thread_safety | Step 2, 5 | Medium | rippled commit 9dbf849 |
| 7 | rippled UptimeTimer plain-int data race (m_elapsedTime) | data_race / thread_safety | Step 2, 6 | Medium | rippled issue #2487 |
| 8 | Bitcoin Core lock-order inversion ABBA deadlock (cs_main) | mutex (deadlock) | Step 4 | Medium | Bitcoin Core #30764 |


