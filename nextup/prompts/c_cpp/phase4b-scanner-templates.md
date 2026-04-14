# Phase 4b: Scanner & Sweep Templates - C/C++

> **Usage**: Orchestrator reads this file to spawn the 3 Blind Spot Scanners, Validation Sweep Agent, and Design Stress Testing Agent in iteration 1.
> Replace placeholders `{SCRATCHPAD}`, etc. with actual values.

---

## Blind Spot Scanner A: Memory & Buffer Operations

> **Trigger**: Always runs IN PARALLEL with depth agents (iteration 1 only).
> **Purpose**: Check what breadth agents missed in memory management and buffer safety.

```
Task(subagent_type="general-purpose", prompt="
You are Blind Spot Scanner A. Find what breadth agents NEVER LOOKED AT for memory management and buffer operations.

## Your Inputs
Read:
- {SCRATCHPAD}/attack_surface.md (Memory Allocation Map)
- {SCRATCHPAD}/findings_inventory.md (what WAS analyzed)
- {SCRATCHPAD}/function_list.md (complete function inventory)
- Source files in scope

## CHECK 1: Allocation/Deallocation Pairing
Cross-reference every malloc/calloc/new allocation site against deallocation paths:

For each allocation site in the codebase:
| Allocation Site | Function | Freed/Deleted? | All Paths? | Double-Free Risk? | Finding? |
|-----------------|----------|---------------|------------|-------------------|----------|

Methodology:
- Grep for malloc(, calloc(, realloc(, new, new[] in source files
- For each allocation site, trace to its corresponding free()/delete/delete[]
- Check ALL return paths (normal return, early return, exception throw, error goto)
- If ANY path reaches end-of-scope without freeing the allocated pointer -> FINDING (memory leak)
- If pointer is freed then used or freed twice -> FINDING (use-after-free / double-free)
- Special focus: functions that transfer ownership without clear documentation

Tag each finding: [TRACE:alloc@L{N} -> freed@L{M}? missing on path via L{K}]

## CHECK 2: Buffer Size Validation
For every memory copy / string operation:

| Function Call | Destination Size | Source Length | Verified? | Overflow Possible? |
|---------------|-----------------|---------------|-----------|-------------------|

Methodology:
- Grep for memcpy(, memmove(, strcpy(, strcat(, sprintf(, gets(, scanf( in source files
- For each call: is destination buffer size verified against source length BEFORE the copy?
- strcpy/gets/sprintf with no bounds check -> FINDING (HIGH: classic buffer overflow)
- memcpy where size parameter comes from user input without bounds check -> FINDING
- strncat where size argument is src length instead of remaining dest space -> FINDING
- Safe patterns: strncpy/strlcpy with verified sizes, snprintf with explicit size limit

Tag: [BOUNDARY:dest_size={N}, src_len=user_controlled -> overflow at L{K}]

## CHECK 2b: Pointer/Array Bounds Checking
For every array index and pointer dereference:

| Location | Index/Offset Source | Bounds Check Present? | Gap? |
|----------|--------------------|-----------------------|------|

Methodology:
- Grep for array subscript patterns [i], [idx], [n], [offset] in source
- For each index that originates from user input, file data, or network data: is it bounded?
- Off-by-one: does the check use < vs <= correctly for the array size?
- Pointer arithmetic: is the resulting pointer validated before dereference?

Tag: [BOUNDARY:index=user_input, array_size={N} -> out-of-bounds at L{K}]

## CHECK 2c: Realloc Dangling Pointer
For every realloc call:

| realloc Site | Old Pointer Used After? | NULL Return Checked? | Gap? |
|--------------|------------------------|---------------------|------|

Methodology:
- Grep for realloc( in source files
- Pattern: `ptr = realloc(ptr, new_size)` - if realloc returns NULL, original pointer is LOST
- Correct pattern: `tmp = realloc(ptr, new_size); if (tmp) ptr = tmp; else handle_error();`
- Check: is the old pointer variable used after the realloc call on any path?

Tag: [TRACE:realloc@L{N} -> old_ptr dangling if NULL returned]

## Output
- Maximum 5 findings [BLIND-A1] through [BLIND-A5]
- Use standard finding format
- Note WHY breadth agents likely missed each

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Write to {SCRATCHPAD}/blind_spot_A_findings.md

Return: 'DONE: {N} blind spots - Check1: {A} alloc/dealloc gaps, Check2: {B} buffer overflow risks, Check2b: {C} bounds gaps, Check2c: {D} realloc issues'
")
```

---

## Blind Spot Scanner B: Type Safety & Integer Operations

> **Trigger**: Always runs IN PARALLEL with depth agents (iteration 1 only).
> **Purpose**: Check what breadth agents missed in type safety, integer arithmetic, and unsafe casts.

```
Task(subagent_type="general-purpose", prompt="
You are Blind Spot Scanner B. Find what breadth agents NEVER LOOKED AT for type safety, integer operations, and casts.

## Your Inputs
Read:
- {SCRATCHPAD}/findings_inventory.md (what WAS analyzed)
- {SCRATCHPAD}/function_list.md (complete function inventory)
- {SCRATCHPAD}/state_variables.md (all global/static variables)
- Source files in scope

## CHECK 3: Signed/Unsigned Conversion
For every signed-to-unsigned or unsigned-to-signed conversion:

| Location | Signed Type | Unsigned Type | Conversion Direction | Sign Confusion Risk? | Finding? |
|----------|------------|--------------|---------------------|---------------------|----------|

Methodology:
- Grep for (unsigned), (int), (size_t), (ssize_t) casts and implicit conversions in assignments
- Signed negative -> unsigned: value becomes very large (wraps to UINT_MAX - |val| + 1)
- Unsigned large -> signed: value becomes negative if high bit set
- Common dangerous pattern: `size_t len = user_input; if (len > 0)` -- if len comes from
  a signed int that was -1, the conversion makes it SIZE_MAX and the check passes
- Check: function parameters typed as int used where size_t/unsigned expected

Tag: [VARIATION:signed=-1 -> unsigned=SIZE_MAX -> bypasses check at L{K}]

## CHECK 4: Integer Overflow/Underflow on User-Influenced Values
For every arithmetic operation on values derived from user input:

| Location | Operation | Input Source | Overflow Check? | Underflow Check? | Gap? |
|----------|-----------|-------------|----------------|-----------------|------|

Methodology:
- Grep for arithmetic: +, -, *, /, <<, >>  applied to user-supplied variables
- Trace which variables originate from: function parameters, file reads, network reads, env vars
- Multiplication is highest risk: `size_t total = count * element_size` with no overflow check
- Addition in size calculations: `offset + length` with no check before malloc/memcpy
- Left shift: `1 << user_value` where user_value >= 32 (or 64) is undefined behavior
- Safe patterns: explicit overflow check, __builtin_mul_overflow(), SafeInt library

Tag: [BOUNDARY:count=UINT_MAX/size, total=overflow -> malloc(0) at L{K}]

## CHECK 5: Unsafe Cast Safety
For every explicit type cast:

| Location | Cast Type | From Type | To Type | Type Compatibility Guaranteed? | Gap? |
|----------|-----------|-----------|---------|-------------------------------|------|

Methodology:
- Grep for static_cast<, reinterpret_cast<, (TypeName), C-style casts
- reinterpret_cast / C-style to unrelated pointer type: is alignment guaranteed?
- Downcasting (base* -> derived*): is the dynamic type verified before cast?
- Truncating cast (int64 -> int32): is value range validated first?
- Pointer-to-integer or integer-to-pointer: platform assumptions correct?

Tag: [TRACE:cast@L{N} -> undefined if alignment != {M} bytes]

## CHECK 5b: void* Type Tracking
For every void* usage:

| Location | void* Variable | Actual Pointed-To Type | Type Tracked? | Mix-Up Risk? |
|----------|---------------|----------------------|--------------|-------------|

Methodology:
- Grep for void* in variable declarations and function parameters
- Callback patterns that pass void* context: is the pointed-to type consistent on all call paths?
- void* stored in structs (e.g., event userdata): is there a type tag alongside it?
- Cast back from void*: is the type assumption documented and enforced?
- Common bug: void* passed through multiple layers, incorrect type assumed at sink

Tag: [TRACE:void*@L{N} cast to TypeA, but stored as TypeB at L{K} -> type confusion]

## Output
- Maximum 5 findings [BLIND-B1] through [BLIND-B5]
- Use standard finding format
- Note WHY breadth agents likely missed each

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Write to {SCRATCHPAD}/blind_spot_B_findings.md

Return: 'DONE: {N} blind spots - Check3: {A} sign confusion risks, Check4: {B} integer overflow risks, Check5: {C} unsafe cast issues, Check5b: {D} void* type gaps'
")
```

---

## Blind Spot Scanner C: Concurrency & Resource Management

> **Trigger**: Always runs IN PARALLEL with depth agents (iteration 1 only).
> **Purpose**: Check what breadth agents missed in thread safety, resource cleanup, and synchronization.

```
Task(subagent_type="general-purpose", prompt="
You are Blind Spot Scanner C. Find what breadth agents NEVER LOOKED AT for concurrency, resource management, and synchronization.

## Your Inputs
Read:
- {SCRATCHPAD}/findings_inventory.md (what WAS analyzed)
- {SCRATCHPAD}/function_list.md (complete function inventory)
- {SCRATCHPAD}/state_variables.md (all global/static variables)
- Source files in scope

## CHECK 6: Shared Variable Protection
For every global or static variable accessed from multiple threads:

| Variable | Access Locations | Protected By | Mutex/Atomic Used? | All Paths Protected? | Gap? |
|----------|-----------------|-------------|-------------------|---------------------|------|

Methodology:
- Grep for global variables and static variables in source files
- Identify which functions access each global/static variable (read and write)
- Check if any global is written in one thread and read in another without synchronization
- Look for: pthread_mutex_lock/unlock, std::mutex::lock/unlock, atomic<>, _Atomic
- Common bug: double-checked locking without memory barriers (pre-C++11 or C11)
- Common bug: global errno-like variable used in multi-threaded context
- Check: are counters/flags incremented with ++ (non-atomic) instead of atomic increment?

Tag: [TRACE:global@L{N} written without lock, read at L{M} in different thread]

## CHECK 7: File Descriptor / Handle Cleanup
For every file descriptor, socket, handle, or OS resource acquisition:

| Acquisition Site | Resource Type | Closed/Released On All Paths? | Exception/Error Safe? | Gap? |
|-----------------|--------------|------------------------------|----------------------|------|

Methodology:
- Grep for open(, fopen(, socket(, accept(, CreateFile(, malloc( in source files
- For each acquisition: trace ALL exit paths (normal return, early return, goto error, throw)
- Is the resource closed/freed on every path?
- C++ exceptions: is the resource wrapped in RAII (unique_ptr, ifstream, lock_guard)?
  If not: does any exception between acquisition and cleanup cause a leak?
- goto-based error handling: does every error label close previously acquired resources?

Tag: [TRACE:fd=open@L{N} -> not closed on early return at L{K}]

## CHECK 8: Deadlock via Lock Ordering
For every mutex acquisition in the codebase:

| Lock Acquisition | Thread/Context | Other Locks Held at This Point? | Order Consistent? | Deadlock Risk? |
|-----------------|---------------|--------------------------------|------------------|---------------|

Methodology:
- Grep for pthread_mutex_lock(, std::unique_lock<, std::lock_guard< in source
- For each lock acquisition, identify what other locks may be held at that point
- Construct a lock ordering graph: if A->B and B->A are both possible paths -> deadlock
- Check: are there code paths where two threads can acquire the same set of locks in opposite order?
- Common bug: holding lock A while calling a callback that acquires lock B, and another
  code path holds B while acquiring A

Tag: [TRACE:LockA@L{N} while LockB held -> if peer holds B, acquires A -> deadlock]

## CHECK 8b: Condition Variable Spurious Wakeup
For every condition variable wait:

| Location | Condition Variable | Wait Pattern | Spurious Wakeup Handled? | Gap? |
|----------|--------------------|-------------|-------------------------|------|

Methodology:
- Grep for pthread_cond_wait(, condition_variable::wait( in source files
- Pattern: `cond_wait(&cond, &mutex)` in a bare if() instead of a while() loop
- Correct pattern: `while (!condition_met) { cond_wait(&cond, &mutex); }`
- A spurious wakeup without a loop causes the thread to proceed before the condition is true
- Also check: is the condition variable signal sent while holding the mutex? (not required
  by POSIX but prevents lost-wakeup race with some implementations)

Tag: [VARIATION:spurious_wakeup -> condition not true -> proceeds at L{K}]

## Output
- Maximum 5 findings [BLIND-C1] through [BLIND-C5]
- Use standard finding format
- Note WHY breadth agents likely missed each

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Write to {SCRATCHPAD}/blind_spot_C_findings.md

Return: 'DONE: {N} blind spots - Check6: {A} unprotected shared vars, Check7: {B} resource cleanup gaps, Check8: {C} deadlock risks, Check8b: {D} spurious wakeup issues'
")
```

---

## Validation Sweep Agent

> **Trigger**: Always runs IN PARALLEL with the 4 depth agents and Blind Spot Scanners (iteration 1 only).
> **Purpose**: Mechanical sweep of ALL validation logic for deficit patterns that reasoning-based agents consistently miss: boundary operator precision, error return checking, guard coverage completeness, and RAII completeness.

```
Task(subagent_type="general-purpose", prompt="
You are the Validation Sweep Agent. You perform mechanical checks across every function in scope. You do NOT analyze business logic or algorithmic attacks - you check that existing validation code is correct, reachable, and complete.

## Your Inputs
Read:
- {SCRATCHPAD}/function_list.md (complete function inventory)
- {SCRATCHPAD}/findings_inventory.md (what was already found - avoid duplicates)
- {SCRATCHPAD}/semantic_invariants.md (pre-computed invariants)
- Source files for all in-scope code

## INPUT FILTERING
When cross-referencing against findings_inventory.md, focus on Medium+ severity findings only. Low/Info findings do not need cross-validation sweeps - the attention cost of processing 50+ findings outweighs the marginal value of sweeping Low/Info patterns.

## CHECK 1: Boundary Operator Precision

For EVERY comparison operator in validation logic (if, assert, while guards):

| Location | Expression | Operator | Should Be | Off-by-One? |
|----------|-----------|----------|-----------|-------------|

Methodology:
- For each `>` ask: should this be `>=`? What happens at the exact boundary value?
- For each `<` ask: should this be `<=`? What happens at the exact boundary value?
- For each `==` in a range check: does it exclude a valid boundary?
- Buffer size checks: `if (len > sizeof(buf))` should usually be `if (len >= sizeof(buf))`
  since writing len bytes into buf[sizeof(buf)] reads off the end

Concrete test: Substitute the boundary value into the expression. Does the function behave
correctly AT the boundary? If the boundary value should be valid but the operator rejects it
(or vice versa), flag it.

Only flag findings where the off-by-one produces a CONCRETE impact (buffer overflow, read
past end, underrun). Do NOT flag stylistic preferences.

Also check: for each loop with accumulator variables, verify ALL accumulators are updated per
iteration. A loop that increments one counter but not a co-dependent tracking variable
produces incorrect state on subsequent iterations.

## CHECK 2: Error Return Value Checking

For EVERY function that returns an error code or can fail:

| Function | Return Type | Callers That Check Return | Callers That Ignore Return | Gap? |
|----------|------------|--------------------------|---------------------------|------|

Methodology:
- Grep for functions returning int (error code pattern), bool, errno-setting functions
- For each call site: does the caller check the return value?
- Commonly ignored: write(), read(), close(), fclose(), send(), recv(), pthread_mutex_lock()
- If a file write fails silently: data corruption or incomplete output
- If mutex_lock fails silently: unprotected shared access on some platforms
- Check: does ignoring this return value leave the program in an inconsistent state?

Concrete test: For each unchecked error return, trace what the program's behavior is if
the function failed. Is the failure silent (data corruption) or detectable (crash)?

## CHECK 3: Guard Coverage Completeness

For EVERY mutex or access guard applied to at least one function:

| Guard/Mutex | Applied To (write paths) | NOT Applied To (same shared vars) | Missing? |
|-------------|--------------------------|-----------------------------------|----------|

Methodology:
- For each mutex, list ALL functions that lock it before accessing shared state
- Identify ALL other functions that access the SAME shared variables without locking
- If any function accesses shared state without the guard -> flag as potential race condition
- For access control patterns (capability checks, privilege levels): check if any path to
  the protected operation bypasses the check

Concrete test: If functionA holds mutex_X before writing global_var, and functionB writes
global_var without mutex_X, that is a guard gap.

## CHECK 4: RAII Completeness

For each resource acquired in C++ code:

| Resource | Acquisition Site | RAII Wrapper? | Manual Cleanup Present? | Exception-Safe? | Gap? |
|----------|-----------------|--------------|------------------------|----------------|------|

Methodology:
- Identify resources that should use RAII: file handles (ifstream/ofstream), memory (unique_ptr),
  mutexes (lock_guard/unique_lock), sockets (custom RAII wrapper)
- For each raw resource: is it wrapped in RAII or does cleanup happen manually?
- If manual: is cleanup present on ALL paths including exception throws?
- Common gap: `FILE* fp = fopen(...); /* complex code */ fclose(fp);` -- if any code between
  open and close throws, fclose is skipped

Tag: [TRACE:resource=fopen@L{N} -> fclose missing on exception path through L{K}]

## CHECK 5: Function Parameter Validation

For EVERY function that accepts pointer parameters or array+length pairs:

| Function | Parameter | NULL Check? | Length Bounds Check? | Gap? |
|----------|-----------|------------|---------------------|------|

Methodology:
- For each pointer parameter: is NULL dereferenced without a NULL check?
- For each (buffer, length) pair: is length validated against an upper bound before use?
- For each string parameter: is it validated as NULL-terminated before strlen/strcpy?
- Library boundary functions (exported API, callbacks): stricter validation required than
  internal functions

Concrete test: Can a caller pass NULL for any pointer parameter and cause a crash? Can
a caller pass a very large length and cause a buffer overflow?

## CHECK 6: Helper Function Call-Site Parity

For EVERY helper that transforms values (serialization, encoding, scaling, checksum):

| Helper Function | Purpose | Call Sites | Consistent Usage? | Missing/Inconsistent Site |
|----------------|---------|-----------|-------------------|--------------------------|

Methodology:
- Grep for ALL call sites of each helper (serialize, deserialize, encode, decode, checksum,
  encrypt, decrypt, compress, decompress)
- For each PAIR of inverse helpers (encode/decode, encrypt/decrypt): verify every value that
  passes through one also passes through its inverse at the appropriate point
- For each call site: does it apply the helper to the same variable type with the same
  parameters as other call sites?
- Flag: a value that is encoded at entry but not decoded at exit (or vice versa)
- For paired operations (lock/unlock, acquire/release, ref_inc/ref_dec): if either operation
  transforms state before use, verify the paired operation restores it

Concrete test: If `checksum_compute(data, len)` is called at 3 write sites but
`checksum_verify(data, len)` is called at only 2 of 3 corresponding read sites, the missing
site processes data without integrity verification.

## CHECK 7: Write Completeness for Tracked State (uses pre-computed invariants)

Read `{SCRATCHPAD}/semantic_invariants.md` (pre-computed by Phase 4a.5 agent). For each variable with POTENTIAL GAP flagged:

| Variable | Flagged Gap | Confirmed? | Finding? |
|----------|-----------|-----------|----------|

Verify each flagged gap: does the value-changing function actually modify the tracked value
without updating the variable? Filter false positives (e.g., view-only reads, functions
that indirectly trigger an update elsewhere). Confirmed gaps -> FINDING.

## CHECK 8: Conditional Branch State Completeness

For EVERY state-modifying function that contains an if/else or early return:

| Function | Branch Condition | State Written in TRUE Branch | State Written in FALSE Branch | Asymmetry? |
|----------|-----------------|-----------------------------|-----------------------------|------------|

Methodology:
- For each conditional branch in a state-modifying function, enumerate ALL state writes in
  the TRUE path
- Enumerate ALL state writes in the FALSE path (including implicit "nothing happens" for
  early returns)
- If a variable is written in one branch but NOT the other, and both branches represent
  valid execution paths (not error/abort) -> flag as potential stale state
- Special focus: functions where counters, timestamps, or size fields are inside a
  conditional block but downstream code assumes they always execute

Concrete test: If functionA writes `last_update = time(NULL)` inside an `if (len > 0)` block,
what value does `last_update` retain when `len == 0`? Trace all consumers of `last_update`.

Tag: [TRACE:branch=false -> state_var={old_value} -> consumer computes {wrong_result}]

## CHECK 9: Sibling Propagation

For each Medium+ CONFIRMED or PARTIAL finding in findings_inventory.md:

1. Extract the ROOT CAUSE PATTERN in one sentence (e.g., 'missing NULL check before dereference',
   'buffer size not validated before memcpy', 'mutex not held during state read')
2. Grep ALL other functions in scope for the SAME pattern
3. For each sibling function found: does it exhibit the SAME bug?
4. If YES and no existing finding covers it -> new finding [VS-N]

| Finding | Root Cause Pattern | Sibling Functions | Same Bug? | New Finding? |
|---------|-------------------|-------------------|-----------|-------------|

## SELF-CONSISTENCY CHECK (MANDATORY before output)

For each finding you produce: if your own analysis identifies that the missing pattern/check/guard
is FUNCTIONALLY REQUIRED to be absent (e.g., adding it would always return error, break the API
contract, or make the function unreachable), your verdict MUST be REFUTED, not CONFIRMED with
caveats. A finding that says "X is missing" and also explains "adding X would break Y" is
self-contradictory - resolve the contradiction before outputting.

## Output
Write to {SCRATCHPAD}/validation_sweep_findings.md:

### Sweep Summary
| Check | Functions Scanned | Findings | False Positives Filtered |
|-------|------------------|----------|-------------------------|

### Findings
Use finding IDs [VS-1], [VS-2], etc. with standard finding format.
For each finding, include:
- The exact code location and operator/validation/guard
- The concrete impact (not just 'could be wrong')
- Whether any existing finding in findings_inventory.md already covers this

Maximum 12 findings (prioritize by impact). Filter out findings already covered by breadth agents.

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Return: 'DONE: {N} functions swept, {M} boundary issues, {K} unchecked error returns, {J} guard gaps, {P} RAII gaps, {Q} parameter validation gaps, {R} helper parity gaps, {S} conditional branch gaps, {T} sibling propagations'
")
```

---

## Design Stress Testing Agent (Budget Redirect)

> **Trigger**: 1 reserved slot, UNCONDITIONAL at adaptive loop exit (see phase4b-loop.md DONE section).
> **Purpose**: System-level design analysis that per-function agents miss. Checks design limits, OOM handling, and constraint coherence.
> **Budget**: Counts as 1 budget unit (pre-reserved).

```
Task(subagent_type="general-purpose", prompt="
You are the Design Stress Testing Agent. You analyze program-level design limits and constraint coherence,
NOT individual function bugs. Per-function analysis was done by depth and breadth agents - your job is
system-level design review.

## Your Inputs
Read:
- {SCRATCHPAD}/constraint_variables.md
- {SCRATCHPAD}/function_list.md
- {SCRATCHPAD}/attack_surface.md
- {SCRATCHPAD}/findings_inventory.md (avoid duplicates with existing findings)

## CHECK 1: Design Limit Stress
For each bounded parameter (max connections, max threads, max queue depth, max buffer size, capacity limits):

| Parameter | Design Limit | At Limit: Behavior | Graceful Degradation? | Resource Freed? |
|-----------|-------------|-------------------:|----------------------|----------------|

1. What happens AT the design limit? (crash? hang? graceful reject? silent data loss?)
2. Are administrative/monitoring functions still usable at design limit? (shutdown, health check, drain)
3. Is the limit enforced before or after resource allocation? (reject early vs allocate then fail)

Tag: [BOUNDARY:param=MAX_VALUE -> outcome]

## CHECK 2: OOM (Out-of-Memory) Handling
For each malloc/calloc/new call in critical paths:

| Location | Allocation Size | NULL Return Checked? | Recovery Action | Gap? |
|----------|----------------|---------------------|----------------|------|

1. Does the code check for NULL return from malloc/calloc?
2. If NULL: does it recover gracefully (return error, free prior allocs, log) or crash?
3. Cascading failure: if allocation fails mid-function after earlier allocs succeeded, are
   earlier allocs freed before returning error?
4. Does the program handle repeated allocation failures without entering an inconsistent state?

Tag: [TRACE:malloc@L{N} returns NULL -> prior_alloc not freed -> leak on OOM path]

## CHECK 3: Stack Depth Limits
For each recursive function:

| Function | Base Case | Max Recursion Depth | Stack Frame Size | Stack Overflow Risk? |
|----------|-----------|--------------------:|-----------------|---------------------|

1. What is the maximum recursion depth on adversarial input?
2. Is depth bounded before recursion or only at the base case?
3. Stack frame size: large local arrays in recursive functions?
4. Mutual recursion: are all cycles in the call graph bounded?

Tag: [BOUNDARY:depth=user_controlled -> stack_overflow at depth={N}]

## CHECK 4: Thread Contention at Maximum Load
For each thread pool or work queue:

| Component | Max Threads | Contention Point | Behavior at Max | Gap? |
|-----------|------------|-----------------|----------------|------|

1. What happens when all worker threads are busy? (new work rejected? queued indefinitely? blocked?)
2. Is the work queue bounded? If not: can it grow without limit until OOM?
3. Thread creation failure: if pthread_create fails, is the work item requeued or dropped?
4. Shutdown: if shutdown is requested while threads are running, do they drain cleanly?

Tag: [TRACE:thread_count=MAX -> queue=unbounded -> OOM after {N} requests]

## CHECK 5: Queue / Buffer Overflow Under Load
For each message queue, ring buffer, or task queue:

| Queue | Capacity | Overflow Policy | Enforced? | Data Loss Risk? |
|-------|----------|----------------|-----------|----------------|

1. What is the declared capacity of the queue?
2. What is the overflow policy: block producer? drop oldest? drop newest? undefined?
3. Is the overflow policy actually enforced in code or just documented?
4. If overflow drops items: is the caller notified? Is partial data more dangerous than no data?

Tag: [BOUNDARY:queue_depth=CAPACITY -> overflow_policy={drop/block} -> {consequence}]

## Output
Write to {SCRATCHPAD}/design_stress_findings.md:
- Maximum 8 findings [DST-1] through [DST-8]
- Use standard finding format with Depth Evidence tags ([BOUNDARY:*], [TRACE:*])

## Chain Summary (MANDATORY)
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

Return: 'DONE: {N} design stress findings'
")
```
