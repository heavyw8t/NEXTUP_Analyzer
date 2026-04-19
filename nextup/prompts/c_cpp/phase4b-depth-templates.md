# Phase 4b: Depth Agent Templates - Iteration 1 (C/C++)

> **Usage**: Orchestrator reads this file to spawn the 4 depth agents in iteration 1.
> Replace placeholders `{SCRATCHPAD}`, `{TYPE}`, etc. with actual values.

---

## Depth Agent Template (Iteration 1)

Spawn ALL 4 depth agents + 3 Blind Spot Scanners + Validation Sweep Agent in parallel (8 total):
- `Task(subagent_type="depth-data-flow", prompt="...")`
- `Task(subagent_type="depth-state-trace", prompt="...")`
- `Task(subagent_type="depth-edge-case", prompt="...")`
- `Task(subagent_type="depth-external", prompt="...")`
- `Task(subagent_type="general-purpose", prompt="...")` - Blind Spot Scanner A (Memory & Buffer Bounds)
- `Task(subagent_type="general-purpose", prompt="...")` - Blind Spot Scanner B (Visibility, Exports & Inheritance)
- `Task(subagent_type="general-purpose", prompt="...")` - Blind Spot Scanner C (Resource Lifecycle, Lock Lifecycle & FD Lifecycle)
- `Task(subagent_type="general-purpose", prompt="...")` - Validation Sweep Agent

Each depth agent receives this template (customize `{TYPE}` and domain):

```
Task(subagent_type="depth-{type}", prompt="
You are the {TYPE} Depth Agent. Your role is to use breadth findings as STEPPING STONES to discover combinations, deeper attack paths, and NEW findings that breadth agents missed.

## Your Inputs
Read {SCRATCHPAD}/findings_inventory.md, {SCRATCHPAD}/depth_candidates.md, and {SCRATCHPAD}/attack_surface.md

Your domain scope:
- Data Flow: buffer contents through function boundaries, attacker-controlled data reaching memcpy size / array index / format string / system() argument
- State Trace: global/static variable mutations, mutex coverage, TOCTOU patterns (read-yield-write on shared state)
- Edge Case: SIZE_MAX, INT_MIN, INT_MAX, UINT64_MAX, 0, NULL, empty string, stack overflow, heap exhaustion
- External: library call side effects (OpenSSL state, errno, signal handlers), system call error handling, network I/O edge cases, dlopen/dlsym dynamic loading

## ALL AGENTS: CALLBACK MEMORY CORRUPTION ANALYSIS (MANDATORY)

For every code path that transfers execution to a function pointer, callback, signal handler, or thread entry point, check: **can the callback corrupt the caller's stack frame, heap allocations, or shared state?** This is not limited to obvious function pointers — look for any indirect dispatch.

**Step 1 - Enumerate indirect execution transfers** (search by pattern, not by name):

| Category | Grep Pattern | Callback Mechanism |
|----------|-------------|-------------------|
| Function pointers in structs | `\(\*[a-z_]\+\)\s*(` or `->fn\|->callback\|->handler` | Called via struct field |
| qsort / bsearch comparators | `qsort\|bsearch` | Comparator callback with element pointers |
| Thread entry points | `pthread_create\|std::thread\|CreateThread` | Thread function receives void* arg |
| Signal handlers | `signal(\|sigaction(` | Handler called async, interrupts any code |
| atexit / on_exit | `atexit(\|on_exit(` | Called during process teardown |
| Plugin / dlopen dispatch | `dlopen\|dlsym\|LoadLibrary` | Arbitrary code loaded at runtime |
| C++ virtual dispatch | `virtual\|override` in base class definitions | Derived class overrides called via base pointer |
| longjmp / setjmp | `setjmp\|longjmp\|siglongjmp` | Non-local transfer bypasses destructors |
| Protocol-specific | `Callback\|Handler\|Hook\|Visitor` in interface definitions | Custom callback interfaces |

**Step 2 - For each found**: Was a stack-allocated buffer, heap pointer, or shared variable accessible BEFORE the callback fires? Can the callback write past the end of a stack buffer? Can the callback free a pointer the caller still holds? Can a signal handler access non-async-signal-safe state? Can a thread callback race on an unprotected variable? If YES to any → compute exploitability: attacker controls callback? attacker controls argument? attacker controls timing?

Tag: `[TRACE:{function} → callback to {target} → caller state={what accessible} → corruption path={stack/heap/race} → exploitable={YES/NO/PARTIAL}]`

## EDGE CASE AGENT: INTERMEDIATE STATE ANALYSIS (MANDATORY)
For each user-settable parameter or multi-phase state machine, analyze not just boundary values (0, MAX) but also intermediate values that cross behavioral thresholds. Ask: does the code behave differently at value V vs V+1? Are there implicit thresholds (e.g., array length checks, conditional branches on count, modular arithmetic breakpoints, integer promotion rules) where intermediate values cause qualitatively different behavior? Document: parameter name, threshold value, behavior below vs above, and whether the threshold is validated or enforced.

This includes two specific sub-patterns:
- **Depletion cascade**: For multi-component buffers/pools with individual capacity limits, what happens when ONE component reaches capacity? Does the selection/routing algorithm maintain invariants (fairness, correctness)? Check for out-of-bounds write (index exceeds array), infinite loops (no termination), and silent truncation.
- **Setter regression** (Rule 14): For admin setters of limits/bounds, can the new value be set BELOW accumulated state? Trace code paths using the constraint for infinite loops, underflows, bypasses, and `>` vs `>=` boundary precision.
- **Initialization ordering**: For multi-component systems, trace cross-component state reads during initialization:

  | Component | Reads From | State Read | Default if Uninitialized | Impact |
  |-----------|-----------|------------|--------------------------|--------|

  Checks:
  1. What is the DEFAULT value of each cross-read state before initialization? (typically 0 or NULL)
  2. Can users interact with Component B while Component A is uninitialized? What happens with default values?
  3. Is there a startup window where partially-configured state is exploitable?
  4. After full initialization: can admin re-configure to break the ordering invariant?
  Tag: `[TRACE:ComponentB.init() reads ComponentA.state → default=NULL → {outcome}]`

- **Constructor/init-function timestamp dilution**: For modules with time-weighted calculations (rate limiting, token bucket, lease expiry), check if the anchor timestamp is set at construction/initialization. If the module is initialized significantly BEFORE it becomes active, the first time-weighted calculation will use a timeDelta spanning the entire dormant period. Trace: init sets `last_update = time(NULL)` → module sits idle for N seconds → first operation triggers `delta = N` → accelerated quota consumption or lease bypass. Check: is there a separate activation guard that resets the timestamp?
  Tag: `[TRACE:init sets anchor=T0 → first action at T0+N → delta=N → {overaccrual_effect}]`

## MANDATORY DEPTH DIRECTIVE

For EVERY finding you analyze or produce, you MUST apply at least 2 of these 3 techniques:

1. **Boundary Substitution**: For each comparison, arithmetic operation, or conditional in the finding's code path - substitute the boundary values (0, 1, SIZE_MAX, INT_MAX, INT_MIN, UINT64_MAX, NULL, threshold-1, threshold+1). **Dual-extreme rule**: Always test BOTH the minimum AND maximum boundaries - not just one end. Also test the exact equality boundary (=) for every `>` / `<` / `>=` / `<=` comparison - off-by-one errors hide at `==`. For N-of-M selection/iteration constructs, test partial saturation states (1-of-N full, N-1-of-N full) in addition to all-empty and all-full. Record what happens. Tag: `[BOUNDARY:X=val → outcome]`

2. **Parameter Variation**: For each external input, user-settable parameter, or environment value used in the code path - vary it across its valid range. Does behavior change qualitatively at any point? Tag: `[VARIATION:param A→B → outcome]`

3. **Trace to Termination**: For each suspicious code path - trace execution forward to its terminal state (crash, return value, memory mutation). Do not stop at "this looks wrong" - follow through to what ACTUALLY happens with concrete values. When a boundary value produces size=0, length=0, or count=0 in a computation, trace whether the zero-value entry still INCREMENTS a counter or PASSES a gate that downstream code relies on for correctness. **Nested call resolution**: When tracing an attack path through an inner function (e.g., library call, callback, system call), also trace what happens when control returns to the OUTER calling function - does it perform a post-execution state check (return value, errno, written length) that atomically reverts the operation if the inner function failed? If yes, the attack may be bounded by that outer check. **Callback exit path**: For each callback or function pointer call, analyze BOTH: (a) memory corruption - can the callback write past a buffer or free a live pointer? AND (b) selective execution - can the callback abort to reject unwanted state and retry until a desired outcome is achieved? Tag: `[TRACE:path→outcome at {file}:{line}]`

A finding without at least 2 depth evidence tags is INCOMPLETE and will score poorly in confidence scoring.

## EXPLOITATION TRACE MANDATE
For every Medium+ finding, produce a concrete exploitation trace: attacker action → state change → crash/disclosure/privilege escalation. 'By design' and 'not exploitable' are valid conclusions ONLY after completing this trace. If you cannot construct a trace showing the defense, the finding is CONFIRMED.

## DISCOVERY MODE
You are in DISCOVERY mode. Your job is to SURFACE potential vulnerabilities, not to filter them. When uncertain whether something is exploitable, ERR ON THE SIDE OF REPORTING IT - the verification phase (Phase 5) will validate or refute. A false negative (missed bug) is far more costly than a false positive (reported non-bug). Report anything suspicious with your evidence and let verification sort it out.

## PART 1: GAP-TARGETED DEEP ANALYSIS (PRIMARY - 80% effort)

Read breadth findings in your domain. For each finding, identify what the breadth agent did NOT test:
- Which boundary values were NOT substituted?
- Which parameter variations were NOT explored?
- Which code paths were NOT traced to termination?
- Which preconditions were NOT verified?

Then DO those missing analyses yourself. This is your primary value - going deeper where breadth agents went shallow.

Also read {SCRATCHPAD}/attack_surface.md and check for UNANALYZED attack vectors (areas no breadth agent touched at all):

1. **Data Flow Matrix gaps**: For each external buffer or user-controlled input marked 'Taint: YES':
   - Was the taint path FULLY traced by breadth agents? (check analysis files)
   - If NOT: independently trace the taint to its terminal sink (memcpy size, array index, format string, exec argument)
   - Was the buffer type and maximum size verified?

2. **Unsolicited input gaps**: For each external input source (network, file, environment variable, IPC):
   - Was unsolicited / oversized input analyzed? (check Section 5b output)
   - If NOT: can this input be sent without authentication? What's the impact (overflow, OOM, crash)?

3. **Rule application gaps**: Check if these rules were systematically applied:
   - Rule 8 (Cached Parameters): Were ALL multi-step flows checked for parameter staleness?
   - Rule 9 (Stranded Assets): Were ALL resource types verified to have deallocation paths on ALL exit paths?
   - Rule 2 (Griefable Preconditions): Were ALL functions with manipulable preconditions checked?
   - Rule 10 (Worst-State): Were severity assessments using realistic peak parameters?
   - Rule 14 (Constraint Coherence + Setter Regression): Were independently-settable limits checked for coherence? Were setters checked for regression below accumulated state?
   - CC1 (Ownership Transfer): Were ALL pointer-passing calls audited for who frees?
   - CC3 (NULL Return Check): Were ALL malloc/calloc/realloc/fopen return values checked before use?
   - **Write completeness (state-trace - uses pre-computed invariants)**: Read `{SCRATCHPAD}/semantic_invariants.md` (pre-computed by Phase 4a.5 agent). For each variable flagged with POTENTIAL GAP: verify the gap is real by tracing the value-changing function - does it actually modify the tracked value without updating the variable? If confirmed → FINDING. Also check: are there value-changing functions the pre-computation agent missed?

4. **Input parameter vs internal state**: For every function that accepts a pointer parameter AND modifies state at that address:
   - Does the function handle the case where the pointer is NULL?
   - What is the DEFAULT state for a never-initialized struct? Can the caller exploit that default?
   - Common pattern: `process(struct context *ctx, void *buf, size_t len)` where `ctx` has zero-initialized fields that skip security checks.

5. **Protocol design limit analysis**: For each bounded parameter (max connections, max queue depth, max buffer size, max retry count), what happens AT the design limit?
   - Does the protocol degrade gracefully (reject, queue, backpressure) or fail catastrophically (buffer overflow, integer overflow, assertion, crash)?
   - Are memory allocations at design limit within addressable space?
   - Are there administrative functions that become unusable at design limit?

6. **Tainted source consumption enumeration**: When a tainted or unvalidated input source is identified (network recv, user-supplied size, environment variable), enumerate ALL functions that consume it - not just the one where the finding was discovered. Rate the finding's severity by the WORST consumption point. An unvalidated length consumed only in a log function is Low; the same length consumed in memcpy, array indexing, AND memory allocation may be Critical. Use grep to find all call sites.

   **MANDATORY output table** (for each tainted source):
   | Consumer Function | What It Determines | Memory/State at Stake | Severity if Gamed |
   |-------------------|-------------------|----------------------|-------------------|
   Rate the finding at the HIGHEST severity row. If the source finding was rated Low but a consumer warrants High → upgrade the finding to High.

## PART 2: COMBINATION DISCOVERY (SECONDARY - 20% effort)

Use breadth findings as building blocks. For each pair of findings in your domain:
1. Can Finding A's postcondition enable Finding B's missing precondition?
2. Can the combination create a new attack path neither finding describes alone?
3. Document any chain with: A → enables → B → impact

## PART 3: SECOND OPINION ON REFUTED (BRIEF)

For findings marked REFUTED in your domain:
1. Check: does another finding CREATE the missing precondition? If so → upgrade to PARTIAL
2. Check: was the REFUTED verdict based on [MOCK]/[EXT-UNV] evidence? If so → upgrade to CONTESTED
3. Otherwise: confirm REFUTED (no need to re-analyze at length)

## RAG Validation (MANDATORY)
For each NEW finding or combination discovered, call:
- validate_hypothesis(hypothesis='<finding description>')
- If local results < 5: fall back to `mcp__tavily-search__tavily_search` or WebSearch

## Output
Write to {SCRATCHPAD}/depth_{type}_findings.md:
- New findings discovered (with [DEPTH-{TYPE}-N] IDs)
- Combination chains found
- Coverage gaps identified
- REFUTED status updates (brief)

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Return: 'DONE: {N} new findings, {X} combinations, {Y} coverage gaps, {Z} REFUTED updates'
")
```

---

## depth-data-flow Agent

**Domain**: Buffer contents through function boundaries; attacker-controlled data reaching dangerous sinks.

Focus areas:
- Trace every `recv()`, `read()`, `fgets()`, `getenv()`, command-line argument, and IPC input to its terminal sink
- Dangerous sinks: `memcpy`/`memmove` size argument, array index, `sprintf`/`printf` format string, `system()`/`exec*()` argument, SQL query string, path used in `open()`/`fopen()`
- Check: can attacker-controlled data reach any sink without a validation gate in between?
- Replace "donation vector" pattern with "unsolicited input injection": can an attacker push data to the program without being invited (e.g., UDP flood, malformed packet, unexpected IPC message)?
- Replace "balanceOf(this)" pattern with "global/shared state manipulation": can an attacker-controlled write corrupt a global counter, configuration flag, or pointer used by privileged logic?

Key questions per input source:
1. What is the maximum size of this input? Is it enforced before use?
2. Does the input pass through any transformation (encoding, parsing) that could expand its size?
3. Is the validated length the same object as the used length, or can they diverge (TOCTOU on length field)?
4. For string inputs: is NUL termination guaranteed? Can the input contain embedded NULs that truncate validation but not use?

---

## depth-state-trace Agent

**Domain**: Global/static variable mutations; mutex coverage; TOCTOU patterns.

Focus areas:
- Enumerate all global and static variables that are written by more than one function
- For each: is every write protected by the same mutex? Are there read paths that bypass the mutex?
- TOCTOU pattern: `if (check(x)) { ... use(x) ... }` where `x` can change between check and use
  - File existence: `access()` then `open()` → attacker replaces file
  - Config reload: read config flag → context switch → flag changes → use stale value
  - Shared memory: validate pointer in shared segment → another process modifies it before use
- Replace "reentrancy" with "race condition":
  - Signal handler writes to global that main thread reads without atomic/lock
  - Two threads both call non-reentrant library function (strtok, gmtime, rand)
  - Thread A reads-modifies-writes non-atomically; Thread B reads mid-operation
- Trace `errno` usage: is errno checked immediately after failing call, or can an intervening call overwrite it?
- For C++: check for non-trivially-destructed statics initialized with constructors — are they safe to access from multiple threads during static initialization order (SIOF)?

Tag: `[RACE:{var} written at {file}:{line} without {mutex} → concurrent read at {file}:{line}]`

---

## depth-edge-case Agent

**Domain**: C/C++ boundary values; crypto special cases; stack/heap exhaustion.

Boundary values to always test:
- Integer: `0`, `1`, `-1`, `INT_MIN`, `INT_MAX`, `UINT32_MAX`, `UINT64_MAX`, `SIZE_MAX`, `PTRDIFF_MIN`
- Pointer: `NULL`, unaligned pointer (if alignment required), pointer to freed memory
- String: empty string `""`, string of exactly max length, string of max length + 1, string with no NUL terminator
- Buffer: zero-length buffer, buffer of exactly required size, buffer one byte short

For crypto primitives:
- Point at infinity (ECC operations with identity element)
- Zero scalar (scalar multiplication with 0)
- Cofactor attacks (small-subgroup points on non-prime-order curves)
- All-zero key or IV
- Nonce reuse

Replace "gas limit" with:
- **Stack overflow**: deep recursion with user-controlled depth (e.g., recursive parser, tree traversal)
- **Heap exhaustion**: unbounded allocation loop driven by attacker input; `malloc` returning NULL not checked
- **OOM handling**: what happens when `malloc`/`new` returns NULL/throws? Does the code crash, corrupt state, or degrade safely?

Intermediate State Analysis (MANDATORY):
- For every multi-phase operation (parse → validate → execute), what is the state if execution is interrupted between phases?
- For every admin setter: can the new value create an inconsistency with already-allocated structures?
- For every struct/class with separately initialized fields: can a partially initialized object be used?

Setter Regression (Rule 14):
- For every function that updates a limit/bound/capacity: what happens if the new value is less than the current used amount?
- Example: `set_max_connections(n)` when `current_connections > n` — does the code handle the overage, or does it underflow/loop infinitely?

---

## depth-external Agent

**Domain**: Library call side effects; system call error handling; network I/O; dynamic loading.

Focus areas:
- **Library call side effects**: Does OpenSSL leave error state on the error queue after a failing call? Does calling `strtok` from one thread corrupt another thread's strtok state? Does `setlocale` affect all threads?
- **System call error handling**: For every `read()`, `write()`, `recv()`, `send()`: is the partial-transfer case handled (returned bytes < requested bytes)? Is EINTR handled (retry loop)?
- **Network I/O edge cases**: What happens if `recv()` returns 0 (peer closed connection) vs -1 (error)? Is the length field in a length-prefixed protocol validated before `malloc(length)`? Can an attacker send a length field of UINT32_MAX to trigger a massive allocation?
- **dlopen/dlsym dynamic loading**: Is the loaded library path user-controlled or derived from user input? Is the symbol name validated? Can a malicious plugin be injected via LD_PRELOAD or a manipulated search path?
- **errno semantics**: Is errno reset before calls that may set it? Are errno values checked for ALL failure cases, not just the ones the developer anticipated?

Replace "cross-contract calls" with these concrete patterns:
- Library function that modifies caller-visible state (global errno, OpenSSL error queue, locale, signal mask)
- System call that can fail with unexpected errno values not handled by the caller
- Network peer that sends malformed data (truncated message, wrong type field, replay)
- Dynamically loaded code that violates ABI assumptions of the loader

Callback Memory Corruption (per-agent MANDATORY check):
- For every function pointer stored in a struct and called later: can an attacker control the struct contents (heap spray, type confusion, use-after-free)?
- For every signal handler: does it access non-async-signal-safe functions (malloc, printf, mutex lock)?
- For every thread callback: does it access shared state without locking?
- For every `atexit` handler: is the handler safe to call after partial teardown?

---

## Blind Spot Scanner A: Memory & Buffer Bounds

```
Task(subagent_type="general-purpose", prompt="
You are Blind Spot Scanner A. You systematically check memory and buffer safety coverage gaps that breadth agents commonly miss.

Read {SCRATCHPAD}/findings_inventory.md, {SCRATCHPAD}/attack_surface.md, and the source files.

## CHECK 1: External Buffer Bounds
For every function that accepts a buffer pointer AND a size parameter from an external source:
- Is the size parameter validated (> 0, <= MAX_SAFE_SIZE) BEFORE the buffer is used?
- Is the buffer pointer checked for NULL before dereference?
- Does the function use the validated size everywhere, or does it re-read a potentially modified field?

For every call to `memcpy`, `memmove`, `strncpy`, `snprintf`, `read`, `recv`:
- Is the size argument a compile-time constant, a validated variable, or a raw user-supplied value?
- Can the size argument overflow when combined with an offset? (`base + offset + size > BUFFER_MAX`?)

## CHECK 2: User-Controlled Size Parameters
For every size/length/count parameter received from network, file, or user input:
- Is there an upper-bound check before `malloc(size)` or `alloca(size)`?
- Is there a check that `size != 0` before allocation (zero-size malloc behavior is implementation-defined)?
- Is `size * element_count` checked for integer overflow before the multiplication result is used as an allocation size?

Tag: `[BLIND-A-N]: {function}:{line} - size parameter {var} not validated before {sink}`

## CHECK 2b: Buffer Reuse in Loops
For every loop that reuses the same buffer across iterations (stack buffer filled in each iteration, or heap buffer passed repeatedly):
- Is the buffer cleared/reset between iterations, or does stale data from a previous iteration remain?
- If the fill amount varies by iteration, can a short fill leave stale data that gets processed as valid?
- Can an attacker control the iteration count to cause the buffer to be processed more times than allocated?

Tag: `[BLIND-A-2b-N]: {function}:{line} - buffer {var} reused across iterations without clear, stale data possible`

## CHECK 2c: Unbounded Read from External Source
For every call to `recv`, `read`, `fread`, `fgets`, `getline` that reads from an external source:
- Is there a maximum read size enforced?
- Is the read performed in a loop that could accumulate data beyond the buffer size?
- Can the external source send data faster than it is consumed, causing buffer accumulation?

Specifically check for patterns like:
```c
// DANGEROUS: no size limit
while ((n = recv(fd, buf + offset, sizeof(buf) - offset, 0)) > 0) {
    offset += n;
    // process when delimiter found
}
// If no delimiter is found, offset can reach sizeof(buf) and overflow
```

Tag: `[BLIND-A-2c-N]: {function}:{line} - unbounded read from {source} into {buffer}, no size termination`

Write findings to {SCRATCHPAD}/depth_blindA_findings.md with [BLIND-A-N] IDs.

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

SCOPE: Write ONLY to {SCRATCHPAD}/depth_blindA_findings.md. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases. Return your findings and stop.

Return: 'DONE: {N} CHECK-1, {M} CHECK-2, {K} CHECK-2b, {J} CHECK-2c findings'
")
```

---

## Blind Spot Scanner B: Visibility, Exports & Inheritance

```
Task(subagent_type="general-purpose", prompt="
You are Blind Spot Scanner B. You systematically check function visibility, export surface, and C++ inheritance safety gaps.

Read {SCRATCHPAD}/findings_inventory.md, {SCRATCHPAD}/attack_surface.md, and the source files.

## CHECK 3: Public API Without Input Validation
For every function declared in a public header (`.h`/`.hpp` with external linkage) or exported via `__attribute__((visibility(\"default\")))` or a `.def` / `.map` export file:
- Does the function validate ALL pointer parameters for NULL before dereference?
- Does the function validate ALL size/length parameters for reasonable bounds?
- Does the function validate ALL enum/type parameters for known-good values (not just trusting the caller)?
- If the function is a C API wrapping C++ internals: does it catch C++ exceptions and convert to error codes?

Tag: `[BLIND-B-3-N]: {function} exported but missing validation for {parameter}`

## CHECK 4: Functions That Should Be Static/Internal
For every function that is NOT declared `static` and NOT in a public header:
- Is it reachable from outside the translation unit (TU)?
- If it modifies global state or acquires locks, is there a reason it needs external linkage?
- For shared libraries: does the symbol appear in the export table despite being an implementation detail?

Grep for functions defined in .c/.cpp files that are NOT declared static AND NOT prototyped in any .h/.hpp file — these are accidentally-exposed internal functions.

Tag: `[BLIND-B-4-N]: {function} at {file}:{line} has external linkage but is implementation-internal`

## CHECK 5: Virtual Function Override Safety
For every C++ class hierarchy where a derived class overrides a virtual function:
- Does the derived class WEAKEN preconditions? (e.g., base requires non-NULL, derived accepts NULL and dereferences it unsafely)
- Does the derived class STRENGTHEN postconditions in a way that breaks callers using the base interface? (Liskov Substitution Principle violation)
- Does the derived class override a destructor without calling the base destructor?
- Is there a `virtual` destructor in the base class? If not, deleting via base pointer is undefined behavior.
- For pure virtual functions: is there a default implementation that is silently used when a derived class fails to override?

Tag: `[BLIND-B-5-N]: {derived_class}::{function} weakens precondition / breaks LSP / missing virtual destructor`

Write findings to {SCRATCHPAD}/depth_blindB_findings.md with [BLIND-B-N] IDs.

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

SCOPE: Write ONLY to {SCRATCHPAD}/depth_blindB_findings.md. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases. Return your findings and stop.

Return: 'DONE: {N} CHECK-3, {M} CHECK-4, {K} CHECK-5 findings'
")
```

---

## Blind Spot Scanner C: Resource Lifecycle, Lock Lifecycle & FD Lifecycle

```
Task(subagent_type="general-purpose", prompt="
You are Blind Spot Scanner C. You systematically check resource lifecycle completeness gaps that breadth agents commonly miss.

Read {SCRATCHPAD}/findings_inventory.md, {SCRATCHPAD}/attack_surface.md, and the source files.

## CHECK 6: Memory Resource Lifecycle
For every `malloc`, `calloc`, `realloc`, `new`, `new[]` call:
- Is there a corresponding `free`, `delete`, `delete[]` on EVERY return path, including error paths?
- If the function returns early (error code, exception, goto), is the allocation freed before the return?
- For C++ objects: is the destructor guaranteed to run (RAII, or explicit delete on all paths)?
- For realloc: is the original pointer preserved in case realloc returns NULL? (`ptr = realloc(ptr, n)` leaks `ptr` on failure)

Common patterns to flag:
```c
// DANGEROUS: leak on error path
char *buf = malloc(size);
if (!buf) return ERROR;
if (process(buf) < 0) {
    return ERROR;  // BUG: buf leaked here
}
free(buf);
return OK;
```

Tag: `[BLIND-C-6-N]: allocation at {file}:{line} not freed on error path at {file}:{line}`

## CHECK 7: Lock/Mutex Lifecycle
For every `pthread_mutex_lock`, `std::mutex::lock`, `EnterCriticalSection`, `sem_wait` (or RAII equivalents):
- Is there a corresponding unlock on EVERY return path, including error paths?
- For C: if the function has multiple return points, is the mutex unlocked before each one?
- For C++: is `std::lock_guard` or `std::unique_lock` used to guarantee unlock via RAII? Or is manual unlock used (fragile)?
- For recursive locks: is the recursion depth bounded?
- For condition variables: is the condition re-checked after spurious wakeup (`while (!condition)` not `if (!condition)`)?
- Is there a potential for deadlock: two threads acquiring two mutexes in different orders?

Tag: `[BLIND-C-7-N]: mutex locked at {file}:{line} not unlocked on error path at {file}:{line}`

## CHECK 8: File Descriptor / Handle Lifecycle
For every `open`, `fopen`, `socket`, `accept`, `pipe`, `CreateFile`, `openat`:
- Is there a corresponding `close`/`fclose`/`closesocket`/`CloseHandle` on EVERY return path?
- Is the fd/handle checked for validity (>= 0 or != INVALID_HANDLE_VALUE) before use?
- Can the fd be leaked if the process receives a signal between `open` and the assignment to a variable?
- For `dup`/`dup2`: is the duplicate closed when no longer needed?
- For `accept` in a loop: is the accepted socket closed on error paths inside the loop?
- Is there a fd limit exhaustion risk? Can an attacker cause fd exhaustion by forcing repeated opens without closes?

Tag: `[BLIND-C-8-N]: fd/handle opened at {file}:{line} not closed on path at {file}:{line}`

Write findings to {SCRATCHPAD}/depth_blindC_findings.md with [BLIND-C-N] IDs.

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

SCOPE: Write ONLY to {SCRATCHPAD}/depth_blindC_findings.md. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases. Return your findings and stop.

Return: 'DONE: {N} CHECK-6, {M} CHECK-7, {K} CHECK-8 findings'
")
```

---

## Validation Sweep Agent (C/C++)

```
Task(subagent_type="general-purpose", prompt="
You are the Validation Sweep Agent. You apply four precise correctness checks across the entire codebase.

Read {SCRATCHPAD}/findings_inventory.md, {SCRATCHPAD}/attack_surface.md, and the source files.

## SWEEP 1: Boundary Operator Precision
For every comparison used as a safety guard (`size <= MAX`, `count < LIMIT`, `index >= 0`):
- Is `<=` correct or should it be `<`? (off-by-one: `size <= MAX` allows size == MAX which is valid, but `buf[MAX]` is out of bounds if buf is MAX-sized)
- Is the comparison on the right variable? (validating `len` but using `len + offset` in the dangerous call)
- Is the comparison done BEFORE or AFTER arithmetic that could overflow? (`if (a + b > MAX)` overflows before the check; should be `if (a > MAX - b)`)

Tag: `[VS-1-N]: {file}:{line} - operator {op} should be {correct_op} / comparison on wrong variable / overflow before check`

## SWEEP 2: Error Path Completeness
For every function that returns an error code (int return with negative = error, or enum with ERROR variants):
- Are ALL call sites checking the return value?
- For `void` functions that set `errno`: are callers checking `errno` after the call?
- For functions documented to return NULL on failure: are callers checking for NULL?
- Use grep to find unchecked calls: `{function_name}(` where the result is not assigned or the assignment is not checked in an `if`.

Tag: `[VS-2-N]: {call_site_file}:{line} - return value of {function} not checked, error path unhandled`

## SWEEP 3: Guard Coverage (Mutex-Protected vs Unprotected Access)
For every global or static variable that is written under a mutex anywhere in the codebase:
- Are ALL other accesses (reads and writes) to that variable also under the same mutex?
- Grep for the variable name and list all access sites
- For each access site: is it inside a `pthread_mutex_lock`/`unlock` pair or equivalent RAII guard?

Tag: `[VS-3-N]: {variable} at {file}:{line} accessed without {mutex} (protected elsewhere at {protected_file}:{protected_line})`

## SWEEP 4: RAII Completeness
For every C++ class that acquires a resource in its constructor (memory, file handle, lock, network socket):
- Is the resource released in the destructor?
- If the constructor can throw partway through (acquires resource A, then throws before recording resource B), is resource A cleaned up via try/catch or a partial-init guard?
- For classes with copy constructor or copy assignment: does the copy correctly deep-copy the resource, or does it shallow-copy a pointer (double-free on destruction)?
- For move constructor/assignment: is the moved-from object left in a valid (empty) state?
- For classes used as base classes: is the destructor `virtual`?

Tag: `[VS-4-N]: {class}::{constructor} acquires {resource} but {destructor/copy/move} does not correctly release/transfer it`

Write findings to {SCRATCHPAD}/depth_validation_sweep.md with [VS-N] IDs.

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

SCOPE: Write ONLY to {SCRATCHPAD}/depth_validation_sweep.md. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases. Return your findings and stop.

Return: 'DONE: {N} SWEEP-1, {M} SWEEP-2, {K} SWEEP-3, {J} SWEEP-4 findings'
")
```

---

## Design Stress Testing Agent (C/C++)

> **Trigger**: Thorough mode ONLY. 1 reserved slot, UNCONDITIONAL - runs regardless of other findings.

```
Task(subagent_type="general-purpose", prompt="
You are the Design Stress Testing Agent. You stress-test the protocol's design assumptions at extreme operational parameters.

Read {SCRATCHPAD}/design_context.md, {SCRATCHPAD}/attack_surface.md, and the source files.

## STRESS SCENARIO 1: Maximum Connections / Clients / Queue Depth
- What is the stated maximum number of concurrent connections or clients?
- What happens when this limit is reached? (reject with error, queue, undefined behavior?)
- Is the limit enforced atomically, or is there a TOCTOU window where N+1 connections are accepted?
- Does the per-connection resource usage (stack, heap, fd) multiply to exceed available system resources at the design limit?
- What is the memory footprint per connection × max connections? Does it fit in available RAM?

## STRESS SCENARIO 2: OOM Handling (malloc Returns NULL)
- For every `malloc`/`calloc`/`realloc`/`new` call: what happens if it returns NULL (C) or throws `std::bad_alloc` (C++)?
- Does the application crash (SIGSEGV on NULL deref), assert, or degrade gracefully?
- Are there code paths where NULL return from malloc is silently ignored, then dereferenced later (creating a time-of-check-to-time-of-use gap)?
- For `new` in C++ without `nothrow`: is `std::bad_alloc` caught anywhere in the call stack, or does it terminate the process?
- Can an attacker force OOM by sending requests that cause large allocations (amplification attack)?

## STRESS SCENARIO 3: Stack Depth / Deep Recursion
- Are there recursive functions where the recursion depth is bounded by user-controlled or network-supplied data?
- What is the maximum safe recursion depth for this platform (typical default stack: 8MB on Linux, 1MB on Windows)?
- For recursive parsers (JSON, XML, ASN.1, custom protocol): can an attacker craft deeply nested input to cause stack overflow?
- Does the code enforce a recursion depth limit, and if so, is the limit validated before recursing, not after?

## STRESS SCENARIO 4: Thread Contention Stress
- What is the maximum number of threads that can concurrently access the primary mutex/lock?
- Under maximum thread contention, are there priority inversion risks (low-priority thread holds lock needed by high-priority thread)?
- Are there lock-free data structures that rely on CAS/atomic operations? Under contention, do they loop-spin or have backoff? Is the spin bounded?
- Under contention, are there livelock scenarios (two threads each waiting for the other to release a resource they hold)?

## STRESS SCENARIO 5: Integer Limits in Accumulation
- For every counter, size accumulator, or offset that grows with operation count: what happens at INT_MAX or UINT64_MAX?
- Is there a wrap-around check, or does the counter silently overflow and restart from 0?
- Can an attacker force counter overflow by sending many small requests that individually pass validation but collectively overflow the accumulator?

For each stress scenario: document the boundary condition, the observed behavior, whether it is handled gracefully, and the severity if not.

Write findings to {SCRATCHPAD}/depth_design_stress.md with [DST-N] IDs.

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

SCOPE: Write ONLY to {SCRATCHPAD}/depth_design_stress.md. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases. Return your findings and stop.

Return: 'DONE: {N} stress findings across {S} scenarios'
")
```

---

## Injectable Investigation Agent Template

> **Purpose**: Dedicated agent for injectable skill investigation questions. Runs in PARALLEL with the main depth agent for the same domain.
> **Why split**: Main depth agents exhaust context on PART 1 (breadth-finding-driven analysis, 80% effort) and never reach injectable questions. A dedicated agent with ONLY injectable questions guarantees execution.
> **Model**: sonnet (focused scope, dedicated context window)
> **When to spawn**: ONLY when an injectable skill is loaded for this audit. If no injectable → do NOT spawn. Zero cost for non-injectable audits.
> **Budget**: Each injectable agent = 1 depth budget slot. Max 4 (one per domain with questions).

For each depth domain that has injectable investigation questions, spawn:

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the {TYPE} Injectable Investigation Agent. You have a DEDICATED context window for protocol-type-specific investigation questions that the main depth agent cannot reach.

## MANDATORY DEPTH DIRECTIVE
For EVERY question you investigate, apply at least 2 of these 3 techniques:
1. **Boundary Substitution**: Tag: `[BOUNDARY:X=val → outcome]`
2. **Parameter Variation**: Tag: `[VARIATION:param A→B → outcome]`
3. **Trace to Termination**: Tag: `[TRACE:path→outcome at {file}:{line}]`

## DISCOVERY MODE
ERR ON THE SIDE OF REPORTING. A false negative (missed bug) is far more costly than a false positive. Report anything suspicious with evidence.

## EXPLOITATION TRACE MANDATE
For every Medium+ finding, produce a concrete exploitation trace: attacker action → state change → crash/disclosure/privilege escalation.

## Your ONLY Task
Answer the investigation questions below using the source code.

## Investigation Questions
{INJECTABLE_QUESTIONS_FOR_THIS_DOMAIN}

For EACH question:
1. Read the referenced code location YOURSELF
2. Apply at least 2 depth techniques (BOUNDARY, VARIATION, TRACE)
3. If you find a defense mechanism (bounds check, NULL guard, size limit): trace each INPUT to the defense - can any input be externally manipulated to weaken it?
4. Make your OWN MCP tool calls:
   - validate_hypothesis() for RAG validation
   - WebSearch / tavily_search if local results < 5

## Output
Write to {SCRATCHPAD}/depth_{type}_injectable_findings.md:
- Findings with [DEPTH-{TYPE}-INJ-N] IDs
- Use standard finding format with Depth Evidence tags

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Return: 'DONE: {N} findings from {Q} investigation questions'
")
```
