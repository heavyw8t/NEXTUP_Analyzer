# Generic Security Rules — C/C++

> **Usage**: Analysis agents and depth agents reference these rules during analysis.
> These rules apply to ALL C/C++ codebases regardless of protocol type.

---

## Rule 1: External Call Return Type Verification

**Pattern**: Any external call (library function, system call, IPC, shared library) that returns data or resources
**Check**: Does the ACTUAL return type/format match what the caller EXPECTS?

| Mismatch Type | Example | Impact |
|---------------|---------|--------|
| ABI mismatch | Caller expects `uint32_t`, callee returns `uint64_t` | Truncation, wrong value |
| Encoding mismatch | Caller expects UTF-8, callee returns UTF-16 | Garbled data, buffer overread |
| Struct layout difference | Packed vs. aligned struct passed across library boundary | Field misread, memory corruption |
| Units mismatch | Caller expects bytes, callee returns kilobytes | Arithmetic errors, allocation failures |

**Action**: For every external library/system call returning structured data, verify that the caller's type expectations match the callee's actual output format. Check for platform-specific type size differences (e.g., `long` is 32-bit on Windows x64, 64-bit on Linux x64).

---

## Rule 2: Function Preconditions Are Griefable

**Pattern**: Any function (privileged, worker thread, OR public-facing) with preconditions based on externally-manipulable state
**Check**: Can external actors manipulate state to make the precondition fail or succeed at the wrong time?

```c
void process_queue(worker_ctx_t *ctx) {
    assert(ctx->queue_depth > MIN_THRESHOLD);  // CALLER CAN DRAIN QUEUE TO GRIEF
    // ...
}
```

This includes:
- Privileged/worker functions with user-manipulable preconditions (original scope)
- **Public-facing functions with shared-state-dependent preconditions** (e.g., function requires a global counter > N — can another thread decrement it between check and use?)
- **Functions with resource-based preconditions** (e.g., function requires `malloc` succeeds — can memory pressure cause it to fail at the wrong time?)

**Action**: For every function with a precondition, identify whether the precondition state can be manipulated by:
1. Direct caller action (writing shared state, consuming resources)
2. Concurrent thread action (race condition between check and use)
3. Resource exhaustion (OOM, file descriptor exhaustion, signal interruption)

**Direction 2 - Admin/config parameter impacts on worker functions**: For every configuration setter that modifies a parameter used in worker/processing function preconditions:
4. Can a config change make a worker function behave unexpectedly? (e.g., setting `max_queue_depth = 0` causes immediate assertion failure)
5. Does the config change retroactively affect in-progress operations? (e.g., changing buffer size while a write is mid-execution)

---

## Rule 3: Callback and Function Pointer Side Effects

**Pattern**: Any invocation of a callback, function pointer, `dlopen`/`dlsym`-resolved function, or virtual method
**Check**: Does the invocation trigger unexpected side effects?

Callback/function-pointer types requiring this check:
- Signal handlers modifying shared state
- `atexit()` handlers that access global resources
- C++ destructor chains (RAII objects, `std::shared_ptr` ref-count drops)
- Plugin/module callbacks loaded via `dlopen`
- Observer/event callbacks that re-enter the caller

**Mandatory check**: What happens when the function pointer/callback is invoked?
- [ ] Does it acquire locks already held by caller? (deadlock)
- [ ] Does it modify shared state the caller is iterating? (iterator invalidation)
- [ ] Does it call back into the calling module? (reentrancy)
- [ ] Does it `free()` or `delete` memory the caller still holds a reference to? (use-after-free)

**Output requirement** (in attack_surface.md Callback Flow Matrix):
| Callback/FP | On-Invocation Side Effect | Documented? | Reentrancy-Safe? |
|-------------|--------------------------|-------------|-----------------|

---

## Rule 4: Uncertainty Handling (CONTESTED + Adversarial Assumption)

**CONTESTED is a TRIGGER, not a TERMINAL state.**

When marking any finding as CONTESTED:
1. **Enumerate**: List ALL plausible external behaviors (Scenario A, B, C...)
2. **Assess**: For each scenario, what's the severity IF that behavior is true?
3. **Escalate**: If ANY scenario results in HIGH/CRITICAL → flag for production verification
4. **Default**: Use WORST-CASE severity until production behavior is verified

**For any external library/OS behavior that is UNKNOWN, assume adversarial:**
1. Assume the behavior that causes MAXIMUM harm
2. Produce an impact trace for the adversarial case
3. Mark as CONDITIONAL until verified against the actual library version in use
4. Cannot REFUTE based on documentation alone — library versions differ in behavior

**Workflow integration**:
- CONTESTED findings receive same verification priority as HIGH findings
- CONTESTED findings trigger production verification checkpoint (Step 4a.5)
- Cannot downgrade CONTESTED to REFUTED without version-confirmed evidence

---

## Rule 5: Combinatorial Impact Analysis

**For systems managing N similar entities, analyze cumulative impact.**

When a codebase manages multiple connections, threads, file handles, allocations, or sessions:

**Mandatory analysis**:
1. **Single-entity impact**: What's the impact on ONE entity?
2. **N-entity cumulative**: What's N × single_impact? (check if capped by OS limits)
3. **Time-compound**: What's N × impact × T? (check for accumulation — e.g., memory leak per request)

**Thresholds**:
- If N ≥ 10 AND cumulative impact is a resource leak → analyze further
- If N × per-request allocation growth > available heap → flag as denial-of-service vector

---

## Rule 6: Semi-Trusted Role Bidirectional Analysis

**For any automated or privileged component, analyze BOTH directions.**

**Direction 1**: How can PRIVILEGED COMPONENT harm USERS/CALLERS?
- Timing attacks (inspecting shared state at advantageous times)
- Parameter manipulation (choosing values that maximize harm)
- Omission (failing to release locks, free memory, or signal completion when needed)

**Direction 2**: How can CALLERS exploit PRIVILEGED COMPONENT?
- Front-run predictable privileged actions (TOCTOU)
- Grief preconditions to block the privileged component from operating
- Force suboptimal component decisions by manipulating shared state

**Both directions are equally important. Do NOT stop at Direction 1.**

---

## Rule 7: Resource Exhaustion via Threshold Manipulation

**Pattern**: System has thresholds that determine operational capability (max connections, max open files, buffer limits)
**Check**: Can callers manipulate these thresholds to block operations?

**Attack vectors**:
1. **Below-threshold starvation**: Consume resources so available count falls below required minimum
2. **Above-threshold injection**: Fill a bounded queue/pool to prevent further additions
3. **Counter-based gate inflation**: For every counter-based gate (e.g., `open_connections >= max_allowed`), check: can connections be opened that increment the counter but contribute no useful work? If yes, the gate triggers a DoS with no legitimate activity.
4. **Slow-consumer DoS**: Connect/open but never read/close, exhausting slots for legitimate callers

**Action**: For every operational threshold, check if external callers can manipulate it to cause denial of service. For every counter-based gate, check if zero-work entries can satisfy the count requirement while starving legitimate requests.

---

## Rule 8: Cached Parameters in Multi-Step Operations

**Pattern**: Operation spans multiple function calls or threads with cached initial state
**Check**: Can parameters change between operation start and completion?

**Attack vectors**:
1. **Config staleness**: Config value cached at operation start, changed by admin thread mid-operation
2. **Size staleness**: Buffer size cached before allocation, changed before write completes
3. **Timeout staleness**: Deadline cached at start, system clock adjustment affects validity
4. **External state staleness**: File permissions, process credentials, or IPC endpoint state validated at one point, stored, and relied upon later without re-verification (classic TOCTOU)

**Action**: For multi-step operations AND for any function that stores a snapshot of external/shared state, verify all cached state remains valid or is re-validated at each subsequent consumption point. Pay special attention to: `stat()` → `open()`, `access()` → `fopen()`, credential check → privileged operation.

---

## Rule 9: Stranded Resource Severity Floor

**Pattern**: Resources acquired by the system with no release path after an error, upgrade, or state change
**Check**: Can ALL resource types the system acquires be released on ALL code paths?

**Severity floor enforcement**:
- If NO release path exists (no cleanup handler, no `atexit`, no RAII destructor) AND resource is currently held → minimum **MEDIUM**
- If NO release path AND impact includes file descriptor exhaustion, OOM, or kernel resource leak → minimum **HIGH**
- If resources are theoretical only (not yet acquired) → standard severity matrix applies

**Mandatory analysis for refactored/upgraded modules**:

| Step | Check | If Failed |
|------|-------|-----------|
| 1 | Inventory ALL resource types acquired pre-change | Coverage gap |
| 2 | Does post-change logic handle each resource type? | Check step 3 |
| 3 | Release function exists for each resource? (free, close, munmap, pthread_mutex_destroy) | STRANDED RESOURCE finding |
| 4 | Apply severity floor from above | - |

---

## Rule 10: Worst-State Severity Calibration

**Pattern**: Any severity assessment that references current runtime state
**Check**: Is the assessment using the worst REALISTIC operational state?

When assessing severity, use the WORST REALISTIC operational state, not current snapshot:

- If system can hold 0 to MAX_CONNECTIONS connections → assess at realistic peak load
- If buffer can be 0 to MAX_SIZE bytes → assess at boundary values
- If N worker threads can be 1 to THREAD_POOL_MAX → assess at maximum concurrency
- If time since last operation can be 0 to MAX_IDLE → assess at maximum idle period

**Current runtime state is a SNAPSHOT, not the operational envelope.**

**Action**: For every severity assessment, state the operational parameters assumed and why. Format:
```
Severity assessed at: connections=10000, buffer_size=MAX_SIZE, thread_count=POOL_MAX
Rationale: System configured for up to 10k concurrent connections per deployment docs
```

---

## Rule 11: Unsolicited External Input Impact

**Pattern**: System interacts with external data sources (sockets, files, pipes, shared memory, signals)
**Check**: What happens if unexpected data arrives from external sources unsolicited?

This goes BEYOND validated input paths. Any external data channel whose content the system reads may deliver unexpected data.

**5-Dimension Analysis** (for each external input type):

| Dimension | Question | Impact Pattern |
|-----------|----------|----------------|
| **Receivability** | Can this input arrive without the system explicitly requesting it? | If YES → analyze all 4 dimensions below |
| **Accounting** | Does any system accounting change when unexpected input arrives? (buffer fill level, message queue depth) | Incorrect flow control, processing state corruption |
| **Operation Blocking** | Does the unexpected input create state that blocks system operations? (full queue, locked mutex, consumed file descriptor) | DoS on processing threads |
| **Loop Iteration** | Does the unexpected input create new entries in any enumerated collection? (new signals in signal queue, new messages in processing list) | Unbounded growth, infinite loops |
| **Side Effects** | Does receiving this input trigger callbacks, memory allocations, or state changes? | Stack overflow, heap exhaustion, reentrancy |

**Severity floors**:
- Accounting corruption with no exploitable path → LOW
- Operation blocking on critical processing path → minimum MEDIUM
- Unbounded resource growth via external input → minimum MEDIUM
- Exploitable state corruption via crafted input → standard matrix (usually HIGH)

**Action**: For every external input channel, check if data can arrive unsolicited, and trace the impact through all 5 dimensions.

---

## Rule 12: Exhaustive Enabler Enumeration

**Pattern**: Any finding identifies a dangerous state S that is a precondition for exploitation
**Check**: Have ALL paths to state S been enumerated?

When a finding identifies a dangerous state (e.g., "buffer full", "pointer becomes NULL", "counter wraps to zero"), enumerate ALL paths to that state using these 5 actor categories:

| # | Actor Category | Examples |
|---|----------------|----------|
| 1 | **External attacker** | Malicious input, crafted network packets, adversarial file content |
| 2 | **Semi-trusted component** | Worker thread/process acting within its permissions but with adversarial timing |
| 3 | **Natural operation** | Memory fragmentation, log rotation, cache eviction, timer expiry |
| 4 | **External event** | Signal delivery, OS resource reclaim, library unload, process fork |
| 5 | **User action sequence** | Normal API usage that in combination creates an edge state |

**Mandatory output** (for each dangerous state S identified in any finding):

| # | Path to State S | Actor Category | Existing Finding Covers It? | If Not: New Finding ID |
|---|-----------------|----------------|-----------------------------|----------------------|

**Rules**:
- Fill for ALL 5 categories. If a category cannot reach state S, document WHY (not just "N/A")
- Each MISSING path that IS reachable → new finding or addition to existing finding
- Each new finding inherits severity from the original finding's impact assessment
- Cross-reference with Rule 5 (combinatorial): if N actors × same path → amplified impact

**Action**: For every dangerous precondition state in the findings inventory, verify that all reachable paths have been documented. Missing paths are coverage gaps.

---

## Rule 13: User/Caller Impact Evaluation (Anti-Normalization)

**Pattern**: Any analysis concludes a behavior is "by design", "intended", or "correct architecture"
**Check**: Does this design choice harm callers or downstream consumers?

Before marking any behavior as non-issue because it appears intentional:

**5-Question Test** (ALL must be answered):
1. **Who is harmed** by this design? (specific caller class: application code, system administrators, end users)
2. **Can affected callers avoid** the harm through their own actions? (or is it imposed on them?)
3. **Is the harm documented** in API documentation, header comments, or manpages? (informed consent?)
4. **Could the system achieve the same goal** without this harm? (alternative designs exist?)
5. **Does the function fulfill its stated purpose completely?** (e.g., a `cleanup()` function that only releases heap memory but not file handles is incomplete — callers relying on full cleanup will leak FDs)

**Verdict rules**:
- Harmed AND unavoidable AND undocumented → FINDING (design flaw category, apply severity matrix)
- Harmed AND unavoidable AND documented → INFO finding (callers accepted known risk)
- Harmed AND avoidable → INFO finding (caller choice)
- No one harmed → genuinely non-issue

### Passive Attack Modeling

For ANY finding involving shared state, multi-step timing, or parameter updates:

Model BOTH attack types:

| Attack Type | Description | Example |
|-------------|-------------|---------|
| **Active** | Attacker triggers a specific operation at a controlled moment | Signal injection during critical section, TOCTOU exploit |
| **Passive** | Attacker uses normal API functions at strategically chosen times, waiting for natural state changes | Read shared buffer during reallocation, call function when counter is at boundary |
| **Design gap** | System provides mechanism X for purpose Y, but X does not cover all cases Y requires | Error handler that doesn't release all resource types, cleanup that doesn't handle all thread states |

**Common passive patterns**:
- Allocate → wait for memory pressure → trigger reallocation of neighbor → exploit stale pointer
- Use normal API function when parameter is at a favorable boundary
- Wait for configuration reload then issue request exploiting the window

**Action**: When modeling attacks, do NOT stop at "requires precise timing" (active only). Always also check: "can an attacker achieve a similar result by simply issuing normal API calls when system state is favorable?" (passive).

---

## Rule 14: Cross-Variable Invariant Verification

**Pattern**: Two or more state variables that MUST maintain a relationship for correctness (e.g., `used + free == total`, `array_len == item_count`, `allocated_size >= write_offset`)
**Check**: Can any setter, admin function, or state transition break the invariant?

**Methodology**:
1. For each aggregate variable (total, count, sum, capacity), identify ALL individual variables it should track
2. For each modifier that changes individual variables, verify the aggregate is updated atomically (under lock if multi-threaded)
3. For each modifier that changes the aggregate directly, verify individual variables remain consistent
4. Check: can the aggregate and individuals be modified through DIFFERENT code paths that desync them?
5. **Constraint coherence**: For independently-settable limits that must satisfy a mathematical relationship (e.g., `total_buf_size == sum(per_channel_buf_sizes)`), can one be changed without the other?
6. **Setter regression**: For each configuration setter of a limit/bound/capacity — can the new value be set BELOW already-committed state? If yes, check loops (infinite), comparisons (bypass), arithmetic (underflow/overflow). Also check `>` vs `>=` boundary precision.

**Common invariant classes**:
- Size invariants: `allocated_size >= bytes_written`, `capacity >= length`
- Count invariants: `array.count == active_entries + free_slots`
- Resource invariants: `open_fds <= max_fds`, `locked_pages <= total_pages`
- Pointer invariants: `head <= tail` in ring buffer (before wrap), `write_ptr` within valid range
- Constraint coherence: `global_limit >= sum(per_thread_limits)`

**Action**: For every aggregate/total variable, trace ALL modification paths for both the aggregate AND its components. If any path modifies one without the other → FINDING. For every configuration setter of a limit/bound, verify it cannot regress below already-committed state.

---

## Rule 15: Atomicity Violation in Multi-Step State

**Pattern**: Any multi-step state update that appears atomic but is not protected against concurrent access
**Check**: Can the state be observed or modified between steps of a logically-atomic operation?

| State Type | Manipulation Method | Concurrent Accessible? | Check |
|-----------|-------------------|----------------------|-------|
| Shared counter | Read-modify-write without lock | YES (data race) | Is `++counter` protected? |
| File on disk | Create-then-configure | YES (TOCTOU) | Are permissions set before file is accessible? |
| Linked-list node | Node inserted before initialized | YES | Is node fully initialized before pointer published? |
| Condition variable state | State updated without holding mutex | YES | Is predicate updated atomically with signal? |
| Lazy initialization | Double-checked locking without memory barrier | YES (on some archs) | Is memory barrier placed correctly? |

**Mandatory sequence modeling**: For each non-atomic multi-step state update, model the interleaving:
1. THREAD A reaches step 1 → 2. THREAD B observes partial state → 3. THREAD B acts on partial state → 4. THREAD A completes step 2 → compute: what state corruption results?

**Action**: For every multi-step state transition, check if concurrent threads or signal handlers can observe or modify the intermediate state. See RACE_CONDITION skill for full methodology.

---

## Rule 16: External Data Integrity

**Pattern**: Any system logic that consumes external data (config files, environment variables, IPC messages, network data) for control decisions
**Check**: Is the external data validated for all failure modes?

| Check | What to Verify | Impact if Missing |
|-------|---------------|-------------------|
| Bounds | Input length checked against buffer capacity | Buffer overflow |
| Range | Numeric values checked against valid range | Integer overflow, logic errors |
| Zero/null | Pointers and lengths checked for NULL/zero | Null dereference, division by zero |
| Encoding | String encoding validated before processing | Injection, parser confusion |
| Format | Structured data (JSON, XML, protobuf) validated against schema | Type confusion, unexpected NULL fields |
| Completeness | All required fields present before use | NULL dereference on missing fields |
| Freshness | Timestamps or sequence numbers checked | Replay attacks, stale data processing |
| Source trust | Data source authenticated before acting on privileged commands | Privilege escalation via IPC spoofing |

**Action**: For every external data consumption point, verify ALL applicable checks from the table above. Missing checks → FINDING at severity based on impact. For every configuration setter (file, env var, IPC), check: can the parameter be set to a value that effectively disables a security mechanism? If yes → FINDING (Rule 14 setter regression applies).

---

## Rule R17: State Transition Completeness

**Pattern**: Operations with symmetric branches — allocate/free, open/close, lock/unlock, acquire/release, encode/decode, push/pop
**Check**: All state fields modified in one branch are either (a) also modified in the other branch, or (b) explicitly documented as intentionally asymmetric.

**Methodology**:
1. For each pair of symmetric operations, list ALL state fields modified by the "positive" branch (allocate, open, lock, acquire, push)
2. For the "negative" branch (free, close, unlock, release, pop), verify each field from step 1 is also handled
3. If a field is missing from the negative branch: trace what happens to dependent computations when that field retains its old value while other fields changed
4. Flag branch size asymmetry > 3x in code volume (lines of code) as a review trigger — large asymmetry often indicates incomplete handling

**Common miss patterns**:
- `open()` sets `fd`, `flags`, `offset`, `lock_count`; `close()` clears `fd` and `flags` but not `offset` and `lock_count` → stale state on next open
- `alloc()` sets `ptr`, `size`, `ref_count`; `free()` clears `ptr` but not `size` → stale size used in subsequent size checks
- `lock()` increments `lock_count` and sets `owner_tid`; `unlock()` decrements `lock_count` but doesn't clear `owner_tid` → stale ownership on recursive lock paths

**C/C++-specific**: State may be spread across multiple layers (struct fields, global singletons, OS kernel handles). Ensure ALL state updated in the positive branch is also handled in the negative branch, including kernel-side state (file descriptors, mapped pages, socket state).

**Action**: For every operation pair, produce a field-by-field comparison table. Missing fields in the negative branch that have dependent consumers → FINDING.

---

## Evidence Source Enforcement

**Any REFUTED verdict where ALL external behavior evidence is tagged [MOCK], [EXT-UNV], or [DOC] is automatically escalated to CONTESTED.** Only these evidence types can support REFUTED for external library/OS behavior:

| Tag | Description | Valid for REFUTED? |
|-----|-------------|-------------------|
| [PROD-DEPLOYED] | Observed from deployed production binary/system | YES |
| [PROD-SOURCE] | Verified source from authoritative repository (same version) | YES |
| [PROD-REPRO] | Reproduced on matching OS/library/compiler version | YES |
| [CODE] | From audited codebase source | YES |
| [MOCK] | From stub/mock/test double | **NO** |
| [EXT-UNV] | External, unverified (blog, StackOverflow) | **NO** |
| [DOC] | From documentation only (behavior may differ across versions) | **NO** |

---

## Enforcement Mechanisms

### Devil's Advocate FORCING

When any agent identifies a potential attack path with "could" or "might":
- MUST pursue the path to conclusion (CONFIRMED/REFUTED with evidence)
- "Further investigation needed" → MUST do the investigation NOW

### CONTESTED Triggers Production Fetch

When any finding gets CONTESTED verdict:
1. Orchestrator MUST spawn production verification
2. If production source unavailable → stays CONTESTED (not REFUTED)
3. CONTESTED findings get same verification priority as HIGH severity

### REFUTED Priority Chain Analysis

Before any finding is marked REFUTED:
1. Chain analyzer MUST search ALL other findings for enablers
2. If potential enabler exists → PARTIAL (not REFUTED)
3. Only mark REFUTED if NO plausible enabler exists

### Cross-Validation Before REFUTED

Before marking ANY finding REFUTED, the analyst MUST:
1. State what evidence would PROVE this IS exploitable
2. Confirm they have checked for that evidence
3. If evidence is unavailable (not "doesn't exist") → CONTESTED

---

## Rule CC1: Buffer Overflow / Underflow

**Pattern**: Any buffer operation — `memcpy`, `memmove`, `strcpy`, `strncpy`, `snprintf`, `read()`, `recv()`, array indexing, pointer arithmetic
**Check**: Is the destination buffer size verified to be >= source length at the point of the operation? Is bounds checking performed before every array index derived from external input?

**Dangerous function table**:

| Dangerous Function | Risk | Safe Alternative |
|--------------------|------|-----------------|
| `strcpy(dst, src)` | No bounds check | `strncpy(dst, src, sizeof(dst)-1)` + NUL or `strlcpy` |
| `strcat(dst, src)` | No bounds check | `strncat` with remaining space or `strlcat` |
| `sprintf(buf, fmt, ...)` | No bounds check | `snprintf(buf, sizeof(buf), fmt, ...)` |
| `gets(buf)` | No bounds check | `fgets(buf, sizeof(buf), stdin)` |
| `scanf("%s", buf)` | No width limit | `scanf("%255s", buf)` with explicit width |
| `memcpy(dst, src, n)` | n not validated | Validate `n <= sizeof(dst)` before call |
| `read(fd, buf, n)` | n may exceed buf | Pass `sizeof(buf)` not caller-supplied n |
| `vsprintf(buf, fmt, args)` | No bounds check | `vsnprintf(buf, sizeof(buf), fmt, args)` |

**Off-by-one pattern** (extremely common):
```c
char buf[256];
strncpy(buf, input, sizeof(buf));   // BUG: no NUL termination if input is 256 bytes
// Safe:
strncpy(buf, input, sizeof(buf) - 1);
buf[sizeof(buf) - 1] = '\0';
```

**Integer-driven overflow** (size_t arithmetic):
```c
// BUG: if count is attacker-controlled and large, count * sizeof(T) wraps to small value
void *p = malloc(count * sizeof(struct T));
memcpy(p, src, count * sizeof(struct T));  // then writes beyond allocated region
```

**Action**: For every buffer operation, verify: (1) destination capacity is known and checked, (2) the length argument is derived from the DESTINATION capacity, not from caller-supplied data, (3) NUL termination is explicit for strings. Flag all uses of functions in the dangerous table above for manual review.

---

## Rule CC2: Use-After-Free / Double-Free

**Pattern**: Any `free()` or `delete` / `delete[]` followed by subsequent access to the freed pointer, or any code path that could call `free()` / `delete` on the same pointer more than once
**Check**: Is the pointer set to `NULL` after every `free()`? Are there multiple code paths that could free the same allocation?

**Classic use-after-free**:
```c
struct node *n = get_node();
free(n);
process(n->data);  // BUG: use after free — n->data reads freed memory
// Safe:
free(n);
n = NULL;
```

**Double-free via error path**:
```c
char *buf = malloc(size);
if (!buf) return -ENOMEM;
if (parse(buf) < 0) {
    free(buf);    // first free on error path
    goto cleanup;
}
cleanup:
    free(buf);    // BUG: double-free if parse() failed
// Safe: set buf = NULL after first free, or use a single-exit pattern
```

**C++ iterator invalidation**:
```cpp
std::vector<int> v = {1, 2, 3};
auto it = v.begin();
v.push_back(4);     // BUG: reallocation may invalidate `it`
std::cout << *it;   // use-after-reallocation (dangling iterator)
```

**C++ dangling reference after container modification**:
```cpp
std::vector<std::string> names;
names.push_back("alice");
const std::string &ref = names[0];
names.push_back("bob");   // BUG: reallocation invalidates `ref`
std::cout << ref;         // dangling reference
```

**Action**: For every `free()`/`delete`, verify: (1) the pointer is set to `NULL` immediately after, (2) no other live reference points to the freed allocation, (3) no other code path can reach another `free()` on the same pointer. For C++ containers: verify no iterator or reference is retained across operations that may reallocate (push_back, insert, erase, reserve, resize).

---

## Rule CC3: Integer Overflow / Underflow (Undefined Behavior)

**Pattern**: Arithmetic on `size_t`, `ptrdiff_t`, signed integers, or any user-influenced integer used in allocation sizes, array indices, or loop bounds
**Check**: Unlike languages with checked arithmetic, **C/C++ signed integer overflow is UNDEFINED BEHAVIOR** — the compiler may generate code with any result, including eliminating the overflow check entirely. Unsigned integers wrap silently (defined behavior, but still a logic error in most contexts).

**Signed overflow — UB, compiler may eliminate the guard**:
```c
// BUG: compiler may optimize away the overflow check because signed overflow is UB
int len = get_user_int();
if (len + 1 < 0) return -EINVAL;  // guard eliminated by optimizer
char *buf = malloc(len + 1);       // allocates tiny buffer if len = INT_MAX
```

**size_t wrapping — defined but dangerous**:
```c
size_t count = get_user_size();
size_t total = count * sizeof(uint64_t);
// BUG: if count > SIZE_MAX/8, total wraps to a small value
void *buf = malloc(total);
```

**Safe alternatives using compiler builtins**:
```c
// GCC/Clang: checked arithmetic builtins
size_t total;
if (__builtin_mul_overflow(count, sizeof(uint64_t), &total)) {
    return -EOVERFLOW;
}
void *buf = malloc(total);
if (!buf) return -ENOMEM;

// Or using __builtin_add_overflow for addition
size_t new_size;
if (__builtin_add_overflow(current_size, increment, &new_size)) {
    return -EOVERFLOW;
}
```

**C++ safe approach**:
```cpp
#include <limits>
// Check before multiply
if (count > std::numeric_limits<size_t>::max() / sizeof(T)) {
    throw std::overflow_error("allocation size overflow");
}
```

**Action**: For every arithmetic operation on attacker-influenced integers (especially those used as allocation sizes, offsets, or loop bounds): (1) determine if the type is signed (UB on overflow) or unsigned (silent wrap), (2) apply `__builtin_*_overflow` or explicit pre-check, (3) verify the compiler has not optimized away existing overflow guards (common with `-O2` and signed types).

---

## Rule CC4: Timing Side Channels (Crypto-Specific)

**Pattern**: Comparison operations on secret data — cryptographic keys, nonces, scalars, HMAC tags, session tokens, passwords
**Check**: Is `memcmp()` used to compare secret data? Are there conditional branches that depend on secret bit values? Does the comparison terminate early on first mismatch?

**Vulnerable — `memcmp` is NOT constant-time**:
```c
// BUG: memcmp exits on first differing byte — timing reveals how many bytes match
if (memcmp(provided_mac, expected_mac, MAC_LEN) != 0) {
    return AUTH_FAILURE;
}
```

**Constant-time comparison alternatives**:
```c
// OpenSSL
#include <openssl/crypto.h>
if (CRYPTO_memcmp(provided_mac, expected_mac, MAC_LEN) != 0) { ... }

// libsodium
#include <sodium.h>
if (sodium_memcmp(provided_mac, expected_mac, MAC_LEN) != 0) { ... }

// BSD / glibc (where available)
if (timingsafe_bcmp(provided_mac, expected_mac, MAC_LEN) != 0) { ... }

// Manual (accumulate XOR, never branch on secret)
int diff = 0;
for (size_t i = 0; i < MAC_LEN; i++) {
    diff |= provided_mac[i] ^ expected_mac[i];
}
if (diff != 0) { ... }  // branch only on accumulated result, not per-byte
```

**Compiler optimization caveat**: Even a hand-written constant-time loop can be optimized back into a non-constant-time form by an aggressive compiler. Use `volatile`, compiler memory barriers, or a library function that includes the correct attributes to prevent this.

**Branches on secret bits**:
```c
// BUG: branch timing depends on secret key bit
for (int i = 0; i < 256; i++) {
    if (secret_key[i / 8] & (1 << (i % 8))) {
        point_double(&R);        // different timing from...
    } else {
        point_add(&R, &base);   // ...this branch
    }
}
```

**Action**: For every comparison involving secret data (MAC tags, passwords, session tokens, private key material): (1) replace `memcmp` with a constant-time comparison function, (2) audit for early-exit loops on secret data, (3) audit for conditional branches whose execution depends on secret values, (4) verify the constant-time property survives compiler optimization at the optimization level used in production builds.

---

## Rule CC5: Uninitialized Memory Read

**Pattern**: Any variable declared but used before explicit assignment; any `malloc()` allocation used before `memset()`; any struct with fields that may be read before being written
**Check**: Are all variables initialized before use? Are all heap allocations explicitly cleared before any field is read?

**Stack variable — NOT zero-initialized in C**:
```c
int result;
if (condition) {
    result = compute();
}
// BUG: if condition is false, result is uninitialized
return result;  // reads stack garbage — behavior is undefined
```

**Heap allocation — `malloc` does NOT zero memory**:
```c
struct session *s = malloc(sizeof(*s));
if (!s) return NULL;
// BUG: s->token, s->uid, s->flags are uninitialized garbage
use_session(s);
// Safe: use calloc(), or explicit memset
struct session *s = calloc(1, sizeof(*s));
// OR
struct session *s = malloc(sizeof(*s));
if (s) memset(s, 0, sizeof(*s));
```

**C++ class members without constructor**:
```cpp
class Ctx {
public:
    int fd;           // BUG: not initialized in constructor
    size_t buf_len;   // BUG: not initialized in constructor
    Ctx() {}          // default constructor leaves POD members uninitialized
};
Ctx c;
read(c.fd, buf, c.buf_len);  // reads garbage fd and length
// Safe:
Ctx() : fd(-1), buf_len(0) {}
```

**Partial struct initialization**:
```c
struct request req = { .type = REQ_READ };
// BUG: req.flags, req.size, req.ptr are uninitialized
submit_request(&req);
// Safe:
struct request req = {};  // zero-initializes all fields
req.type = REQ_READ;
```

**Action**: For every local variable and heap allocation: (1) verify initialization before first read, (2) flag `malloc` calls not followed by `memset`/`calloc` before use, (3) verify C++ constructors explicitly initialize all POD members, (4) look for partial struct initializers that leave fields unset. Use `-Wuninitialized` and `-Wmaybe-uninitialized` compiler warnings as a mechanical aid, but note these do not catch all cases.

---

## Rule CC6: Format String Vulnerabilities

**Pattern**: `printf`, `fprintf`, `sprintf`, `snprintf`, `syslog`, `err`, `warn`, or any variadic format function where the FORMAT STRING argument is user-controlled
**Check**: Is user-controlled data EVER passed as the format string argument (second argument to `printf`, etc.) rather than as a format argument?

**Vulnerable — user data as format string**:
```c
// BUG: user input is the format string
char *user_input = get_request_header("Content-Type");
printf(user_input);                   // format string injection

// BUG: same pattern in logging
syslog(LOG_INFO, user_supplied_msg);  // format string injection
```

**Safe — user data as a format argument**:
```c
// Safe: format string is a literal, user data is an argument
printf("%s", user_input);
syslog(LOG_INFO, "%s", user_supplied_msg);
```

**Impact by format specifier**:
| Specifier | Impact |
|-----------|--------|
| `%x`, `%p` | Stack/memory disclosure |
| `%s` | Read from arbitrary pointer (crash or info leak) |
| `%n` | Write to arbitrary address (code execution on some platforms) |
| `%%` | Consume format arguments, misalign stack |

**Indirect injection via chained buffers**:
```c
// BUG: user data was sprintf'd into log_buf, then log_buf used as format string
sprintf(log_buf, user_data);   // first injection
fprintf(log_file, log_buf);    // second: log_buf as format string
```

**Action**: For every call to a variadic format function: (1) verify the format string is a string literal or a compile-time-fixed string, (2) if the format string is built dynamically, verify it contains no `%` characters derived from user input, (3) enable `-Wformat` and `-Wformat-security` compiler warnings, (4) trace any user-influenced string that flows into a logging or output function to check for indirect injection.

---

## Rule CC7: Race Conditions / TOCTOU

**Pattern**: Check-then-act on shared state without atomicity guarantee; read-modify-write on shared variables without synchronization; filesystem operations where the path is checked and then acted on in separate calls
**Check**: Can another thread, process, or signal handler modify the shared state between the check and the act?

**Filesystem TOCTOU**:
```c
// BUG: attacker replaces /tmp/file with a symlink between access() and open()
if (access("/tmp/file", W_OK) == 0) {
    fd = open("/tmp/file", O_WRONLY);  // opens symlink target (e.g., /etc/passwd)
}
// Safe: open with O_NOFOLLOW, then fstat() to verify properties
fd = open("/tmp/file", O_WRONLY | O_NOFOLLOW);
```

**Shared variable race (non-atomic read-modify-write)**:
```c
// BUG: ++counter is NOT atomic — read, increment, write can interleave
int counter;
void increment() { counter++; }  // data race in multi-threaded context
// Safe:
#include <stdatomic.h>
atomic_int counter;
void increment() { atomic_fetch_add(&counter, 1); }
```

**Signal handler data race**:
```c
// BUG: signal handler modifies `g_running` without synchronization
volatile int g_running = 1;  // volatile is NOT sufficient for thread-safety
void sighandler(int sig) { g_running = 0; }
// Safe: use sig_atomic_t
volatile sig_atomic_t g_running = 1;
void sighandler(int sig) { g_running = 0; }
```

**Double-checked locking without memory barrier (C++)**:
```cpp
// BUG: without memory_order, compiler/CPU may reorder writes
static Singleton *instance = nullptr;
Singleton *get_instance() {
    if (!instance) {
        std::lock_guard<std::mutex> lock(mtx);
        if (!instance) {
            instance = new Singleton();  // write to `instance` may be visible before constructor completes
        }
    }
    return instance;
}
// Safe: use std::atomic with acquire/release semantics, or Meyers' singleton
```

**Action**: For every shared state access: (1) identify if a check-then-act sequence exists where another thread/process/signal can modify the state between check and act, (2) replace non-atomic read-modify-write with `atomic_*` operations or mutex-protected sections, (3) for filesystem operations, use `fstat()` on already-opened file descriptors rather than `stat()` on paths, (4) use `O_CREAT | O_EXCL` for atomic file creation.

---

## Rule CC8: Memory Leak

**Pattern**: Any `malloc`, `calloc`, `realloc`, `new`, `new[]`, `fopen`, `open()`, `socket()`, `dlopen()`, or other resource acquisition that does not have a corresponding release on ALL code paths
**Check**: On every code path — including early returns, `goto cleanup`, exception paths, and error branches — is every acquired resource explicitly released?

**Early return without cleanup**:
```c
int process_file(const char *path) {
    char *buf = malloc(BUF_SIZE);
    FILE *fp = fopen(path, "r");
    if (!fp) return -1;              // BUG: buf is leaked on this path
    if (fread(buf, 1, BUF_SIZE, fp) < 0) {
        fclose(fp);
        return -1;                   // BUG: buf is still leaked
    }
    // ... use buf and fp ...
    fclose(fp);
    free(buf);
    return 0;
}
```

**C++ exception path**:
```cpp
void process() {
    char *buf = new char[1024];
    might_throw();    // BUG: if this throws, buf is never deleted
    delete[] buf;
}
// Safe: use RAII
void process() {
    std::unique_ptr<char[]> buf(new char[1024]);
    might_throw();    // destructor releases buf on any exit path
}
```

**RAII wrappers as the canonical solution**:
```cpp
// File handle RAII
struct File {
    FILE *fp;
    File(const char *path, const char *mode) : fp(fopen(path, mode)) {}
    ~File() { if (fp) fclose(fp); }
    operator bool() const { return fp != nullptr; }
};

// Usage: fp released automatically on any exit (return, exception, scope end)
void process(const char *path) {
    File fp(path, "r");
    if (!fp) return;
    auto buf = std::make_unique<char[]>(BUF_SIZE);
    // ...
}
```

**Action**: For every resource acquisition: (1) trace ALL code paths from acquisition to scope exit, (2) verify every path releases the resource, (3) for C code, the `goto cleanup` pattern with a single cleanup label is the standard safe pattern — verify the label handles all resources, (4) for C++ code, prefer `unique_ptr`, `shared_ptr`, `lock_guard`, and other RAII wrappers over manual cleanup.

---

## Rule CC9: Null Pointer Dereference

**Pattern**: Any function that returns a pointer which could be `NULL` (`malloc`, `fopen`, `dlsym`, `getenv`, container `find` operations, custom factory functions) followed by use of that pointer without a `NULL` check
**Check**: Is every pointer-returning function's return value checked for `NULL` before dereference?

**Missing NULL check on allocation**:
```c
char *buf = malloc(size);
memcpy(buf, src, size);   // BUG: dereferences NULL if malloc fails
// Safe:
char *buf = malloc(size);
if (!buf) return -ENOMEM;
memcpy(buf, src, size);
```

**NULL propagation through call chain**:
```c
// BUG: get_config() can return NULL, but callers don't check
config_t *get_config() { return g_config; }  // g_config may be NULL if not initialized
void process() {
    int timeout = get_config()->timeout;  // NULL dereference if g_config == NULL
}
```

**`getenv` / `dlsym` not checked**:
```c
const char *path = getenv("DATA_DIR");
open(path, O_RDONLY);   // BUG: path is NULL if DATA_DIR is unset

void (*fn)(void) = dlsym(handle, "plugin_init");
fn();                   // BUG: fn is NULL if symbol not found
```

**C++ iterator end-check**:
```cpp
auto it = map.find(key);
int value = it->second;   // BUG: if key not found, it == map.end(), dereference is UB
// Safe:
auto it = map.find(key);
if (it != map.end()) {
    int value = it->second;
}
// Or use std::optional / std::expected for safer return types
```

**NULL propagation analysis**: When a function that returns NULL is called N levels deep, the NULL check may be missing at ANY level. Trace the pointer from its source through every function that passes or stores it until the point of dereference, checking each level.

**Action**: For every pointer-returning function call: (1) identify whether the function can return `NULL`, (2) verify a `NULL` check occurs before every dereference on every code path, (3) trace NULL values through call chains to find delayed dereferences, (4) consider `std::optional<T>` or `std::expected<T,E>` (C++23) to encode nullability in the type system and force callers to handle the absent case.

---

## Rule CC10: Improper Secret Clearing

**Pattern**: `memset(secret_buf, 0, len)` used to clear sensitive data (keys, passwords, nonces, session tokens) before `free()` or function return
**Check**: Can the compiler optimize out the `memset` call because the buffer is not subsequently read (dead store elimination)?

**The dead store elimination problem**:
```c
void generate_session_key(user_ctx_t *ctx) {
    uint8_t tmp_key[32];
    derive_key(tmp_key, ctx->password, ctx->salt);  // tmp_key holds sensitive data
    ctx->session_key = encrypt_with(tmp_key);
    memset(tmp_key, 0, sizeof(tmp_key));  // BUG: compiler may optimize this away
    // because tmp_key is not read again after this point (dead store)
}
// The compiled binary may leave key material on the stack
```

**Safe alternatives**:
```c
// Linux / glibc (most portable on Linux)
#include <string.h>
explicit_bzero(tmp_key, sizeof(tmp_key));

// OpenSSL
#include <openssl/crypto.h>
OPENSSL_cleanse(tmp_key, sizeof(tmp_key));

// libsodium
#include <sodium.h>
sodium_memzero(tmp_key, sizeof(tmp_key));

// Windows
SecureZeroMemory(tmp_key, sizeof(tmp_key));

// Portable volatile function pointer trick (C, no library dependency)
static void *(*const volatile memset_ptr)(void *, int, size_t) = memset;
memset_ptr(tmp_key, 0, sizeof(tmp_key));

// C++ with compiler barrier
memset(tmp_key, 0, sizeof(tmp_key));
asm volatile("" ::: "memory");  // GCC/Clang: prevents reorder/elimination
```

**Why this matters for crypto libraries specifically**:
- A compiler running at `-O2` or higher performs dead store elimination as a standard optimization
- If `tmp_key` is on the stack and is not read after `memset`, the optimizer removes the `memset` as "wasted work"
- The key material remains in the stack frame and is readable from the next function's frame, from a core dump, or from a memory disclosure vulnerability
- This affects: private key material, ECDH shared secrets, PBKDF2 intermediate values, password buffers, nonce pools

**Detection approach**:
1. Search for `memset` calls where the buffer is a local variable and there is no subsequent read
2. Check the compiled output (with `-O2`) using `objdump` or `godbolt` to verify the `memset` was not eliminated
3. Any `memset` on a sensitive buffer that IS the last use → flag for replacement with `explicit_bzero` or equivalent

**Action**: For every `memset` intended to clear sensitive data: (1) replace with `explicit_bzero`, `OPENSSL_cleanse`, `sodium_memzero`, or `SecureZeroMemory` as appropriate for the platform/dependencies, (2) verify the replacement function is available in the target build environment, (3) if no library is available, use the volatile function pointer trick, (4) audit all sensitive stack and heap buffers that are `free()`d or go out of scope — verify clearing happens before release, not just before the next operation.
