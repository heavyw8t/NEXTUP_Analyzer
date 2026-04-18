# C/C++ Puzzle-Piece Taxonomy — Design

Status: design document. A later authoring agent turns this into JSON.
ID prefix: `CPP-`. Inherited categories keep their original letters (A-I) with `CPP-` prepended. New native categories start at J.
Piece-entry schema is preserved (id, type, category, file, function, line_start, line_end, description, state_touched, actor, direction, call_context, contract, depends_on, snippet). The `contract` field is interpreted as `module` or `translation unit` for C/C++.

## 1. Inherited A-I types

The inherited taxonomy is DeFi-centric. Systems C/C++ audits (rippled, validators, signers, embedded nodes, crypto libraries) keep a small subset. Every id below is marked INCLUDED or EXCLUDED. Rationale is given for every EXCLUDED id (not just the interesting ones) so the authoring agent does not re-include by accident.

Category A — Arithmetic & Precision
- A01 ROUNDING_FLOOR — EXCLUDED. Integer division in C always truncates toward zero; it is not a discrete rounding choice worth its own piece type. Related concerns fall under A04 and CPP-N01 (signed overflow UB).
- A02 ROUNDING_CEIL — EXCLUDED. Ceiling macros (`DIV_ROUND_UP`) are common but not a security primitive in systems code. No combinator value.
- A03 MIXED_ROUNDING_DIRECTION — EXCLUDED. DeFi-motivated (favors-protocol vs favors-user). Not a distinguishing pattern in node software.
- A04 PRECISION_TRUNCATION — INCLUDED. Narrowing casts (`(uint32_t)uint64_val`, `static_cast<int>`, `size_t` to `int`) are a recurring source of bugs in parsers and length arithmetic.
- A05 MULT_BEFORE_DIV — INCLUDED. `a * b / c` can overflow in the intermediate on any fixed-width integer type. Pairs naturally with A04 and CPP-N01.
- A06 CHECKED_ARITHMETIC_GAP — INCLUDED. Core C/C++ concern: mix of `__builtin_*_overflow` with raw `+`/`-`/`*`, or `SafeInt<>` wrappers abandoned on one code path. Huge in C. This piece is the primary anchor for any integer-based memory-corruption chain.
- A07 ZERO_AMOUNT_PASSTHROUGH — INCLUDED. Reinterpreted for C: zero-size `malloc` (implementation-defined return), zero-length `memcpy` with an invalid pointer (UB on some platforms), zero-length read into a buffer whose size was not validated.

Category B — Access Control & Authorization
- B01 OWNER_ONLY — EXCLUDED. Systems C has no protocol-level owner concept. Where role checks exist (setuid programs, kernel capability checks), CPP-M (input validation) and Rule 2 (griefable preconditions) cover the hazard.
- B02 SELF_CALLBACK_GATE — EXCLUDED. Callback-from-self has no safety meaning in C; the callback hazard is reentrancy and lock reentry, covered by CPP-L and Rule 3.
- B03 NO_ACCESS_CONTROL — EXCLUDED. An exported C function with no caller validation is not a finding on its own; the library contract decides what callers exist. Real hazards surface via CPP-M (untrusted input) and CPP-K (caller retains aliased pointer).
- B04 GENESIS_BYPASS — EXCLUDED. Init-only paths in C are a construction concern; the relevant hazard (state consumed before init completes) is covered by CPP-L (data race / publication ordering).
- B05 PAUSE_GATE — EXCLUDED. No protocol pause in systems C.

Category C — State & Storage
- C01 LOOP_STORAGE_MUTATION — INCLUDED. Rewritten as the iterator-invalidation / container-mutation-in-loop hook. This is the natural bridge from a loop piece to a CPP-K (aliasing & lifetime) piece.
- C02 UNBOUNDED_ITERATION — INCLUDED. DoS lever. Unbounded `while(!queue.empty())`, linked-list traversal, recursive descent on attacker-shaped data.
- C03 READ_WRITE_GAP — EXCLUDED as an A-I piece, because the C/C++ equivalent (read global → yield / syscall / signal → write global) is covered more precisely by CPP-L02 TOCTOU and CPP-L01 data race. Keeping C03 and CPP-L* together would create duplicate pieces for the same bug.
- C04 DELETE_IN_LOOP — EXCLUDED. Subsumed by CPP-K02 (iterator invalidation) which is a stricter and more specific form.
- C05 COUNTER_INCREMENT — INCLUDED. `next_id++`, `seq++`, `atomic_fetch_add`. Off-by-one and unsigned wrap matter; a counter piece is also a natural bridge to CPP-L01 (non-atomic increment is a data race).
- C06 COLLECT_THEN_ITERATE — EXCLUDED. Idiomatic, not load-bearing for security in C.

Category D — External Dependencies & Oracles
- D01 ORACLE_PRICE_DEP — EXCLUDED. No oracles.
- D02 ORACLE_STALENESS — EXCLUDED. No oracles.
- D03 CROSS_CONTRACT_CALL — INCLUDED, narrowly. In C/C++ this maps to `dlopen`/`dlsym` lookups, function-pointer calls resolved at runtime, plugin entry points, IPC calls. Useful for reentrancy / callback-side-effect chains (Rule 3).
- D04 QUERY_DEPENDENCY — EXCLUDED. The relevant hazard (stale external state) is CPP-L02 TOCTOU plus Rule 8 cached-parameter analysis.
- D05 ORACLE_ERROR_SWALLOWED — EXCLUDED as an oracle concept, but note: a generalized "error swallowed" piece is useful for C (`if (ret) continue;`, `catch (...) {}`). If the authoring agent wants, add this under CPP-O as `RESOURCE_ERROR_SWALLOWED` instead of reusing D05. Not included in this design to keep the piece count tight; Rule 9 already enforces stranded-resource severity floors.

Category E — Economic & DeFi Logic
- E01-E08 — ALL EXCLUDED. No first depositor, no LP shares, no slippage, no fees, no maker/taker, no clearing price, no minimum order size. These are DeFi concepts. Including any of them would waste combinator search on patterns that do not occur in node/embedded/crypto-library code.

Category F — Control Flow & Ordering
- F01 CRON_BATCH — EXCLUDED. No cron/keeper concept. A scheduled timer handler is just a thread with a callback, covered by CPP-L actors and Rule 3.
- F02 CANCEL_BEFORE_CREATE — EXCLUDED. Order-book specific.
- F03 MULTI_HOP_CHAIN — EXCLUDED. The equivalent in systems code is pipeline processing; hazards there are buffer-size propagation (CPP-J, CPP-M) and lock ordering (CPP-L03), not the chain shape itself.
- F04 REPLY_ON_ERROR — EXCLUDED. CosmWasm-specific submessage reply semantics have no C/C++ analog.
- F05 EARLY_RETURN_BRANCH — EXCLUDED as its own piece, because in C/C++ the real hazard is "early return skips cleanup," covered in stronger form by CPP-O01 (RAII bypass / leaked resource on error path).

Category G — Token & Asset Handling
- G01-G04 — ALL EXCLUDED. No tokens, no mint, no burn, no refund, no dust. These do not describe any C/C++ systems pattern.

Category H — Ordering & Timing
- H01 BLOCK_HEIGHT_DISCRIMINATION — EXCLUDED in general C/C++, but KEPT available to the rippled-adjacent instantiation only. For the generic c_cpp taxonomy, exclude. (A rippled-specific overlay can re-enable it; that is out of scope for this design.)
- H02 MAKER_TAKER_SPLIT — EXCLUDED.
- H03 ORDER_ID_MANIPULATION — EXCLUDED. Bit-packing IDs is not a security primitive in systems C outside specific order books.

Category I — Validation & Invariants
- I01 INVARIANT_PRESERVATION — INCLUDED. Where invariants are declared (BOOST_ASSERT, static_assert, runtime assertions like `assert(used + free == total)`), this is the anchor. Pairs with Rule 14 cross-variable invariant analysis.
- I02 BALANCE_ACCOUNTING — EXCLUDED. Balance-accounting as written assumes "inflows == outflows + fees" which is DeFi-shaped. The generic form (aggregate tracks sum of parts) is already captured by I01 plus Rule 14.

Summary: INCLUDED inherited ids are A04, A05, A06, A07, C01, C02, C05, D03, I01. Everything else in A-I is EXCLUDED with rationale above.

## 2. New native categories

Six new native categories: J, K, L, M, N, O. Each type below has `id`, `name`, `category`, `description`, `markers`, `typical_direction`.

Proposed change to the `typical_direction` enum: the current values `favors_protocol`, `favors_user`, `neutral` are DeFi-shaped. For C/C++ pieces, propose three new values, used throughout this section:
- `exploitable` — there is a concrete path from attacker-controlled input or timing to an impact.
- `latent` — the pattern is dangerous but reaching the bug requires a precondition not yet linked to attacker control.
- `neutral` — contextless marker (e.g., a raw `+` on size_t is neutral until linked to an allocation).

The recommendation in section 8 is to extend the `direction` enum with these three additional values, not to replace. See section 8 for rationale.

### J. Memory Safety

J01 USE_AFTER_FREE
- category: J
- description: Read or write of memory after its lifetime ended (`free(p); ... *p;` or `delete obj; obj->m();`).
- markers: CWE-416. ASan `heap-use-after-free`. MSan not applicable. unsafe_function_list: `free`, `delete`, `delete[]`. Compiler flag `-fsanitize=address`. Idioms: `free(p)` without `p = NULL;` on the same path; multi-path control flow where one branch frees and another reads.
- typical_direction: exploitable.

J02 DOUBLE_FREE
- category: J
- description: Two calls to `free`/`delete` on the same pointer, often across an error path and a cleanup path.
- markers: CWE-415. ASan `double-free`. unsafe_function_list: `free`, `delete`. Idiom: two-label cleanup in C (`goto err1; ... goto err2;`) where both labels call `free(buf)`.
- typical_direction: exploitable.

J03 HEAP_BUFFER_OVERFLOW
- category: J
- description: Write or read past the end of a heap allocation. Almost always composed with A06 (unchecked arithmetic) or M04 (unchecked length from external input).
- markers: CWE-122. ASan `heap-buffer-overflow`. unsafe_function_list: `memcpy`, `memmove`, `strcpy`, `strncpy`, `sprintf`, `read`, `recv`, array indexing derived from external input. Compiler flags `-fsanitize=address`, `-D_FORTIFY_SOURCE=2`.
- typical_direction: exploitable.

J04 STACK_BUFFER_OVERFLOW
- category: J
- description: Write past the end of a stack buffer, including via variable-length arrays and `alloca`.
- markers: CWE-121. ASan `stack-buffer-overflow`. unsafe_function_list: `gets`, `scanf("%s", ...)` without width, fixed-size `char buf[N]` with `strcpy`, `alloca(n)` with attacker-controlled `n`. Compiler flag `-fstack-protector-strong`.
- typical_direction: exploitable.

J05 MISSING_NUL_TERMINATOR
- category: J
- description: String treated as NUL-terminated when it is not (classic `strncpy` without explicit terminator; `read()` buffer used by `strlen`).
- markers: CWE-170. ASan `heap-buffer-overflow` on downstream `strlen`. unsafe_function_list: `strncpy`, `read`, `recv`. Idiom: `strncpy(dst, src, sizeof(dst));` with no trailing `dst[sizeof(dst)-1] = '\0';`.
- typical_direction: exploitable.

J06 ZERO_SIZE_ALLOC
- category: J
- description: `malloc(0)` / `calloc(0, n)` / `new T[0]` whose return value is then treated as a valid, non-null, writable allocation. Implementation-defined: may return NULL or a minimum-size chunk.
- markers: CWE-687. ASan may or may not catch. unsafe_function_list: `malloc`, `calloc`, `realloc` with size arithmetic that can evaluate to 0. Idiom: `malloc(count * sizeof(T))` where `count` is attacker-supplied.
- typical_direction: latent (becomes exploitable when paired with A07 and J03).

J07 OOB_READ
- category: J
- description: Read past the end of an allocation or array. Distinct from J03 because reads are often information leaks rather than corruption.
- markers: CWE-125. ASan catches heap-OOB reads; UBSan catches signed pointer-arithmetic OOB. unsafe_function_list: `memcpy` (as source), array indexing with unchecked index.
- typical_direction: exploitable (info leak) / latent.

J08 NULL_DEREF_AFTER_CHECK
- category: J
- description: Pointer is checked against NULL, then dereferenced on a path where the check does not in fact guarantee non-NULL (e.g., check in one branch, use in another; check under one lock, use under none).
- markers: CWE-476. UBSan `null-dereference`. Idiom: `if (p) {...} use(p);` with use outside the guarded block, or `p = get(); if (!p) return; /* intervening call that may reset p */ p->f();`.
- typical_direction: exploitable.

### K. Aliasing & Lifetime

K01 DANGLING_POINTER
- category: K
- description: Pointer or reference whose pointee has been destroyed (stack frame returned, container resized, RAII object went out of scope).
- markers: CWE-825. ASan `stack-use-after-return`, `heap-use-after-free`. Idioms: returning `&local`, `return &v[0];` on a vector that later resizes, raw pointer to `unique_ptr`-owned object after the owner drops.
- typical_direction: exploitable.

K02 ITERATOR_INVALIDATION
- category: K
- description: Iterator or reference into an STL container used after a mutation that the C++ standard marks as invalidating (push_back, insert, erase, reserve, resize).
- markers: CWE-416 (specialization). ASan catches the resulting use-after-free if reallocation occurs. Idiom: `auto it = v.begin(); v.push_back(...); *it;`.
- typical_direction: exploitable.

K03 RETURN_ADDRESS_OF_LOCAL
- category: K
- description: Function returns a pointer or reference to a local (stack) object. Caller reads freed stack.
- markers: CWE-562. Compiler warning `-Wreturn-local-addr`, `-Wdangling-pointer`. ASan `stack-use-after-return` when enabled.
- typical_direction: exploitable.

K04 SHARED_PTR_CYCLE
- category: K
- description: `std::shared_ptr` reference cycle keeps objects live forever; pure memory leak with no sanitizer signal.
- markers: CWE-401. No ASan signal (leak-specific: LSan `-fsanitize=leak`). Idiom: two types each holding `shared_ptr<Other>`; fix is `weak_ptr` on one side.
- typical_direction: latent.

K05 MOVE_FROM_THEN_READ
- category: K
- description: C++ object is moved-from, then read. Standard says moved-from objects are in a valid but unspecified state; reading non-reset fields is a logic bug and occasionally UB.
- markers: CWE-672 (use-after-transfer). Compiler warning clang `-Wmove`. Idiom: `vec2 = std::move(vec1); vec1.size();`.
- typical_direction: latent.

K06 REFERENCE_TO_TEMPORARY
- category: K
- description: `const T& x = f().member;` where `f()` returns a temporary that is destroyed at end of the full expression; `x` dangles.
- markers: CWE-562. Clang `-Wdangling-gsl`, `-Wreturn-stack-address`.
- typical_direction: exploitable.

K07 STRICT_ALIASING_VIOLATION
- category: K
- description: Access to an object through a pointer of an incompatible type (e.g., `float *` reading an `int` object). UB under `-fstrict-aliasing`; compiler may hoist / reorder loads.
- markers: CWE-704. Compiler warning `-Wstrict-aliasing`. Idiom: `int i = 42; float f = *(float*)&i;`. Safe alternative: `memcpy` or `std::bit_cast`.
- typical_direction: latent.

### L. Concurrency

L01 DATA_RACE
- category: L
- description: Concurrent access to the same non-atomic variable from two threads where at least one access is a write, without synchronization. UB under the C and C++ memory models.
- markers: CWE-362. TSan `data race`. unsafe_function_list: raw `++`, `--`, `=` on shared globals. Compiler flag `-fsanitize=thread`.
- typical_direction: exploitable.

L02 TOCTOU
- category: L
- description: Check-then-act sequence where a separate thread, process, or filesystem actor can mutate state between the check and the act. Includes filesystem TOCTOU (`access` then `open`), shared-memory TOCTOU (validated offset then read), and signal-handler races.
- markers: CWE-367. Usually not caught by sanitizers; static analysis via cppcheck. Idioms: `stat(path)` then `open(path)`; `if (*p == 0) *p = 1;` on a shared variable without atomic CAS.
- typical_direction: exploitable.

L03 LOCK_ORDER_INVERSION
- category: L
- description: Two code paths acquire two locks in opposite orders, creating a deadlock potential.
- markers: CWE-833. TSan flags lock-order inversions (`potential deadlock`). std::* idiom: fix is `std::scoped_lock(m1, m2)` which deadlock-avoids.
- typical_direction: exploitable (DoS) / latent.

L04 MISSING_ATOMIC
- category: L
- description: Shared variable read-modify-write implemented with raw `x++` or `x = x | mask;` instead of atomic. Narrower than L01: often silent, not tripped by TSan if the race is infrequent.
- markers: CWE-662. TSan probabilistically. Idiom: plain `int counter; counter++;` accessed from multiple threads. Safe alternative: `std::atomic<int>` or `atomic_fetch_add`.
- typical_direction: exploitable.

L05 SIGNAL_UNSAFE_CALL
- category: L
- description: Signal handler calls functions that are not async-signal-safe (malloc, printf, anything taking a lock, most of libc).
- markers: CWE-479. unsafe_function_list: `malloc`, `free`, `printf`, `fprintf`, `syslog`, any mutex lock. Safe alternative: set a `volatile sig_atomic_t` flag and let the main loop handle it.
- typical_direction: exploitable.

L06 THREAD_CANCEL_IN_CRITICAL
- category: L
- description: `pthread_cancel` or C++ thread termination arrives while a thread holds a mutex or owns a resource with no cleanup handler. Results in stranded locks / leaked resources.
- markers: CWE-667. Idiom: `pthread_cancel` with default cancellation type and no `pthread_cleanup_push` around lock sections. Pairs with Rule 9 (stranded resource floor).
- typical_direction: exploitable (DoS).

### M. Input Validation

M01 FORMAT_STRING
- category: M
- description: Attacker-controlled string passed as the format argument to a variadic format function.
- markers: CWE-134. Compiler flag `-Wformat -Wformat-security`. unsafe_function_list: `printf`, `fprintf`, `sprintf`, `snprintf`, `syslog`, `err`, `warn`. Idiom: `printf(user_input);`. Safe alternative: `printf("%s", user_input);`.
- typical_direction: exploitable.

M02 UNVALIDATED_LENGTH
- category: M
- description: Length field read from untrusted source (network, file, IPC) and used as the size argument to `memcpy`, `read`, a loop bound, or an allocation without being bounded against the actual buffer.
- markers: CWE-20, CWE-805. unsafe_function_list: `memcpy`, `memmove`, `recv`, `fread` when size is from wire. Idiom: `memcpy(dst, src, hdr->len);` with no `hdr->len <= sizeof(dst)` check.
- typical_direction: exploitable.

M03 INTEGER_PARSE_NO_RANGE
- category: M
- description: String-to-integer conversion (`atoi`, `strtol`, `strtoul`, `sscanf %d`) whose result is used without checking `errno`, range, or `LONG_MIN`/`LONG_MAX` saturation. `atoi` has no error signaling at all.
- markers: CWE-190 (integer-side), CWE-20. unsafe_function_list: `atoi`, `atol`. Safe alternative: `strtol` with `errno = 0;` pre-check and `end != str` post-check.
- typical_direction: exploitable.

M04 NUL_TERMINATOR_ASSUMPTION
- category: M
- description: External buffer (network read, file read, IPC) is passed to `strlen`, `strcpy`, `strcmp` etc. without first ensuring a NUL byte exists within the known bounds.
- markers: CWE-126, CWE-170. unsafe_function_list: `strlen`, `strcpy`, `strcmp`, `strchr` against un-validated buffers.
- typical_direction: exploitable.

M05 UNTRUSTED_SIZE_IN_MEMCPY
- category: M
- description: The size argument to `memcpy` / `memmove` / `read` is computed from external data using arithmetic that can overflow or wrap (pair with A06, A05).
- markers: CWE-190 + CWE-787. ASan catches the resulting overflow. unsafe_function_list: `memcpy`, `memmove`, `read`, `recv`.
- typical_direction: exploitable.

M06 PATH_TRAVERSAL
- category: M
- description: External path segment passed to `open`, `fopen`, `stat`, `unlink` etc. without canonicalization or prefix containment. `../` or absolute paths escape the intended directory.
- markers: CWE-22. unsafe_function_list: `open`, `fopen`, `unlink`, `rename` on unsanitized paths. Safe alternative: `realpath` + prefix check, or `openat` with `O_NOFOLLOW` and a directory fd.
- typical_direction: exploitable.

### N. Undefined Behavior

N01 SIGNED_OVERFLOW
- category: N
- description: Signed integer overflow. UB in C and C++. Compilers at -O2 routinely eliminate overflow-check code that assumes signed wrap.
- markers: CWE-190. UBSan `signed-integer-overflow`. Compiler flag `-fsanitize=undefined`. unsafe_function_list: raw `+`, `-`, `*` on `int`/`long`. Safe alternative: `__builtin_add_overflow` etc., or convert to unsigned before the operation.
- typical_direction: exploitable.

N02 SHIFT_EXCESS
- category: N
- description: Left or right shift by an amount greater than or equal to the type's bit width, or left shift that overflows a signed type. UB.
- markers: CWE-1335. UBSan `shift-out-of-bounds`. Idiom: `x << n;` where `n` is attacker-supplied without `n < sizeof(x) * CHAR_BIT` check.
- typical_direction: exploitable.

N03 UNSEQUENCED_SIDE_EFFECT
- category: N
- description: Multiple unsequenced modifications to the same scalar (`i = i++ + ++i;`) or side-effect in a function-call argument list whose order is unspecified.
- markers: CWE-758. Compiler warning `-Wsequence-point`.
- typical_direction: latent.

N04 UNINITIALIZED_READ
- category: N
- description: Read of an object whose value has not been set. `malloc` does not zero; POD members of a no-init constructor are undefined; partial struct initializers leave fields undefined.
- markers: CWE-457, CWE-908. MSan `use-of-uninitialized-value`. Compiler flags `-Wuninitialized -Wmaybe-uninitialized`. Safe alternative: `calloc`, `= {}`, member-init-list.
- typical_direction: exploitable (info leak) / latent.

N05 PTR_ARITH_OOB
- category: N
- description: Pointer arithmetic that produces a pointer outside the object it was derived from (other than one-past-the-end). UB.
- markers: CWE-823. UBSan `pointer-overflow`. Idiom: `p + n` where `n` is attacker-supplied.
- typical_direction: exploitable.

N06 MODIFY_CONST
- category: N
- description: Cast-away-const followed by write; writing to string literals; modifying objects declared `const`.
- markers: CWE-704. UBSan sometimes catches via pointer-overflow. Idiom: `char *s = "literal"; s[0] = 'x';`.
- typical_direction: latent.

### O. Resource Management

O01 RAII_BYPASS
- category: O
- description: Resource acquired with raw allocator (`malloc`, `fopen`, `open`, `socket`, `pthread_mutex_lock`) with no RAII wrapper, and at least one code path (early return, exception, `goto err`) omits the release.
- markers: CWE-401, CWE-404, CWE-772. LSan for memory. std::* idioms: `unique_ptr`, `lock_guard`, `scope_guard` are the safe alternatives.
- typical_direction: exploitable (DoS / resource exhaustion).

O02 FD_LEAK
- category: O
- description: File-descriptor leak on error path. Specialization of O01 with different severity (FD exhaustion denies all new sockets / files system-wide).
- markers: CWE-775. Idiom: `fd = open(...); if (cond) return -1; /* no close(fd) */`.
- typical_direction: exploitable (DoS).

O03 DTOR_THROWS
- category: O
- description: C++ destructor that can throw. If thrown during stack unwinding from another exception, `std::terminate` is called. Post-C++11 destructors are implicitly `noexcept` but explicit `noexcept(false)` or `throw` inside still hazards.
- markers: CWE-248. Compiler warning `-Wterminate`.
- typical_direction: exploitable (crash).

O04 NOEXCEPT_VIOLATION
- category: O
- description: Function declared `noexcept` that calls a function which can throw. Any escaped exception calls `std::terminate`.
- markers: CWE-755. Compiler warning `-Wnoexcept`.
- typical_direction: exploitable (crash).

O05 MUTEX_NOT_UNLOCKED
- category: O
- description: Raw `pthread_mutex_lock` or `mtx.lock()` with a path (error, exception) that returns without unlocking. Subsequent acquires deadlock. Specialization of O01 with concurrency consequence.
- markers: CWE-667. TSan may flag. Safe alternative: `lock_guard`, `unique_lock`, or `pthread_cleanup_push`.
- typical_direction: exploitable (DoS / deadlock).

O06 SECRET_CLEAR_DSE
- category: O
- description: `memset(secret, 0, n);` at end of function that the compiler eliminates as dead-store because `secret` is not subsequently read. Key material remains on the stack.
- markers: CWE-14, CWE-226. Not caught by sanitizers. Safe alternative: `explicit_bzero`, `OPENSSL_cleanse`, `sodium_memzero`, `SecureZeroMemory`, or `volatile` function-pointer trick.
- typical_direction: exploitable (info leak).

## 3. Actor vocabulary

C/C++ has no user-vs-owner split. Actors map to execution contexts. The `actor` field takes one of:

- main_thread — the program's primary thread of execution.
- worker_thread — any secondary thread spawned by the program (pthread, std::thread).
- signal_handler — code running in a POSIX signal-handler context. Severe restrictions (async-signal-safe only).
- interrupt_handler — code running at interrupt context in kernel or embedded (no sleeping, no blocking).
- async_callback — callback invoked by an event loop, `dlopen` plugin, or library hook, typically on an unspecified thread.
- module_init — code run during library load (`__attribute__((constructor))`, static-initializer order, DLL entry point).
- destructor — code run during object destruction, including C++ `~T()`, `__attribute__((destructor))`, `atexit` handlers.
- dtor_chain — specifically C++ stack unwinding where multiple destructors fire in reverse order of construction; distinguished from `destructor` because throw-during-unwind is a separate hazard (O03).
- setuid_caller — code running in a userland program after a privilege drop. Distinguishes pre-drop from post-drop state in TOCTOU analysis.
- kernel — kernelspace code (if auditing a kernel module / driver). Different constraints again (no floating point by default, preemption rules).

## 4. Bridge types

Bridges tie pieces across function boundaries, threads, and trust boundaries. The combinator matches a bridge + two or more anchor pieces to form a chain.

- CPP-K* bridges (alias / lifetime) — when an allocation site and a use site are separated by one or more function calls and the pointer/reference is threaded through them, the aliasing chain itself is the bridge. Anchors: J01 / J07 / K01-K06 at one end, K-family at the other.
- CPP-L* bridges (lock-acquisition) — lock acquisition establishes a cross-thread happens-before edge; releasing it is the corresponding edge. Two pieces in different actors are correlated via a shared mutex. Anchors: L01 / L02 / L03 / L04 at both ends, bridged by the mutex identity.
- CPP-M* bridges (input-boundary) — data crosses from an external channel (socket, file, IPC, env var, command line) into internal state. The bridge captures the taint path. Anchors: M01-M06 at the boundary, J/N/O family at the sink. This is how, for example, `recv` taints a length that later underflows `memcpy` (M02 + A06 + J03).
- CPP-J04 bridge (zero-size alloc) — J06 (ZERO_SIZE_ALLOC) is a bridge by construction: the allocation site and the first write/read site are linked through the zero-length return value. Treated as a dedicated bridge because the alloc-site and the use-site are almost never in the same function.

## 5. Conflicting actor pairs

In systems C/C++, any thread can in principle execute any function. True "actor conflicts" (where one actor must not call a path another actor can) are rare. The one structural conflict is:

- (signal_handler, main_thread) — not a conflict per se, but a constraint: functions reachable from `signal_handler` must be async-signal-safe. Any piece whose `actor` is `signal_handler` that sits on a call graph reaching non-signal-safe code is a finding by itself (L05). The combinator should treat this as a signal-handler REACHABILITY bridge rather than a mutual-exclusion pair.
- (interrupt_handler, anything) — same shape, stricter: interrupt handlers cannot block, cannot take sleeping locks, cannot allocate. Treat as a reachability constraint.
- (module_init, worker_thread) — publication race: if a global is written during `module_init` and read from a worker thread that was started before init completed, the read may see zero bytes. Useful conflict for L01-style pieces.

No other actor pairs conflict. Do not encode `(main_thread, worker_thread)` as a conflict; both can execute anywhere, and the real hazard is captured by L01/L02/L03/L04.

## 6. Extra elimination rules

These rules prune combinator output. They are applied after the A-I rules and before scoring.

- CPP-R1: sanitizer-duplicate pruning. If every piece in a candidate combo is caught by the same sanitizer on the same line (e.g., all three are ASan heap-buffer-overflow primitives inside one function with a single dominating malloc), collapse to one finding. Rationale: the combinator is for compositional bugs, not for repeat reports of the same primitive.
- CPP-R2: template-only pruning. Pieces that sit in header-only template code with no instantiation visible in the audit scope are speculative. Eliminate combos where every piece is in an un-instantiated template, unless a `state_touched` field shows a concrete instantiation was traced.
- CPP-R3: pure-compute pruning. If every piece in a combo is pure compute (no I/O, no alloc, no shared state, no syscall) and there is no input boundary (no CPP-M* bridge), eliminate. A pure-compute chain cannot cross a trust boundary.
- CPP-R4: same-translation-unit static pruning. If every piece references a `static` function or file-scope variable in the same translation unit and there is no CPP-M* or CPP-L* bridge, downgrade confidence. Static-scoped bugs in one TU are usually caught by the project's own tests; the combinator earns its keep on cross-TU bugs.
- CPP-R5: sanitizer-incompatible pruning. If a candidate combo requires TSan to prove one piece and ASan to prove another, and the combo as stated requires them to fire simultaneously on the same binary, mark as `SPLIT-VERIFY` rather than REFUTED. ASan and TSan cannot be combined in one build; verification is two separate PoCs.
- CPP-R6: already-patched pruning. If the fork-ancestry skill found that a CVE covering the same code region has an applied patch in the audit scope, eliminate combos whose pieces match the CVE's pattern unless the combo names a different trigger path.

## 7. Scoring weight recommendations

The scoring pass assigns weight to combos based on category mix and actor spread. Recommended overrides for C/C++:

Base weights (higher = more suspicious):
- Memory Safety (J) piece present: +3.
- Concurrency (L) piece present: +3.
- Aliasing & Lifetime (K) piece present: +2.
- Undefined Behavior (N) piece present: +2.
- Input Validation (M) piece present and on the trust boundary (actor outside main_thread init): +3.
- Resource Management (O) piece present: +1.
- Arithmetic (A04, A05, A06, A07) piece present: +1 each, +2 if paired with a J or M piece.
- C01, C02, C05, D03, I01: +1 each.

Boolean flags (multiplicative where noted):
- has_memory_safety_piece: yes/no. If yes and combo also has an M piece → weight x1.5 (input-to-corruption chain).
- has_concurrency_piece: yes/no. If yes and combo has two or more distinct actors → weight x1.3 (real race rather than single-thread false alarm).
- mixed_actor_threads_bonus: +2 if combo contains at least two of {main_thread, worker_thread, signal_handler, async_callback}.
- has_signal_handler_piece AND has_non_signal_safe_call: +3 (L05 pattern).
- has_raii_bypass AND has_exception_path: +2 (O01 + throwing code path).

Penalties:
- all_pieces_same_function AND no_M_bridge: -2 (likely a local bug already caught by unit tests).
- all_pieces_in_templates: -3 (see CPP-R2).
- combo requires dead-store-elimination to manifest AND no crypto context: -1 (O06 applies to crypto, rare elsewhere).

Threshold (tentative): combos scoring < 3 are deprioritized; >= 6 go to verification; >= 9 are flagged HIGH candidate.

## 8. Cross-check notes

### `nextup/prompts/c_cpp/generic-security-rules.md`

This file defines 17 generic rules plus 10 CC-prefixed rules (CC1-CC10). The native category design above maps to it as follows. Rule CC1 (Buffer Overflow / Underflow) covers J03, J04, J05, M02, M04, M05. Rule CC2 (Use-After-Free / Double-Free) covers J01, J02, K01, K02. Rule CC3 (Integer Overflow / Underflow) covers A06, N01, M03, M05. Rule CC4 (Timing Side Channels) is narrow and crypto-specific; O06 covers the secret-clearing half and a crypto-specific direction extension would cover the comparison half, but for now CC4 is a skill-level audit, not a taxonomy piece (a timing side channel is a property of a function, not a composable chain element). Rule CC5 (Uninitialized Memory Read) is N04. Rule CC6 (Format String) is M01. Rule CC7 (Race Conditions / TOCTOU) is L01, L02, L04. Rule CC8 (Memory Leak) is O01, O02, K04. Rule CC9 (Null Pointer Dereference) is J08 plus N04 when the NULL value came from uninitialized memory. Rule CC10 (Improper Secret Clearing) is O06. Rules 1-17 are orthogonal (they are analysis directives, not piece templates), and they are invoked by the depth-agent templates at combo-evaluation time, not encoded in the taxonomy.

One rule deserves pulled-out treatment: Rule 9 (Stranded Resource Severity Floor). The minimum-MEDIUM floor it imposes should be echoed in the scoring pass: any combo whose anchor includes O01, O02, O05, or L06 receives a severity floor that the combinator does not downgrade.

### `nextup/agents/skills/c_cpp/*/SKILL.md`

Twelve SKILL.md files exist under `nextup/agents/skills/c_cpp/`: `buffer-operations`, `centralization-risk`, `concurrency-safety`, `crypto-constant-time`, `economic-design-audit`, `fork-ancestry`, `integer-safety`, `memory-safety-audit`, `network-protocol-security`, `preprocessor-safety`, `raii-resource-management`, `verification-protocol`. They map as follows. `memory-safety-audit` is the J category plus K01-K02. `buffer-operations` is J03-J05, M02, M04. `concurrency-safety` is the full L category. `integer-safety` is A04-A07 plus N01-N02. `raii-resource-management` is O01, O02, O05, K04 (shared-ptr cycles). `crypto-constant-time` is O06 plus a crypto-timing-comparison piece that is not part of this taxonomy (see Rule CC4 note above). `network-protocol-security` is M02, M04, M05 applied to wire formats, plus C02 (unbounded iteration over attacker-shaped data). `preprocessor-safety` is outside the piece taxonomy; macro hazards (double evaluation, missing do-while) are lint-level and do not compose. `centralization-risk` and `economic-design-audit` are DeFi-shaped and explicitly out of scope for the generic c_cpp taxonomy (see section 1's B and E exclusions). `fork-ancestry` drives CPP-R6 and is a recon-phase skill, not a taxonomy category. `verification-protocol` is the PoC methodology referenced in section 6.

No rippled-specific patterns are hardcoded in the SKILL.md files. rippled-adjacent concepts (ledger sequence comparison, `jtx::Env` test harness) are mentioned in the generic-security-rules prose and in the verification protocol, but they do not warrant their own taxonomy category. If a rippled-specific overlay is ever built, it would re-enable H01 (block-height discrimination, interpreted as ledger-sequence discrimination) and add a narrow CPP-P category for ledger-state invariants, but that is out of scope here.

### `direction` enum discussion

The current `typical_direction` values are `favors_protocol`, `favors_user`, `neutral`. These encode "who benefits from the bug" and are well-fitted to DeFi where there are exactly two parties. In systems C/C++, the axis that matters is "how close to an exploit is this piece," because there is no protocol/user split. The relevant axis is:

- exploitable — the piece, in context, gives an attacker a primitive (corruption, info leak, crash, DoS).
- latent — the piece is dangerous but not yet reachable from attacker input; becomes exploitable if composed with an M-family input piece.
- neutral — the piece is a marker (an arithmetic op, a counter increment) with no intrinsic direction until chained.

Two options:
(a) Keep the existing enum values, always emit `neutral` for C/C++ pieces, and add a new optional field (e.g., `cpp_attack_state`) with the three values above.
(b) Extend the `direction` enum itself to `{ favors_protocol, favors_user, neutral, exploitable, latent }`.

Recommendation: option (b). Extend the enum. Reasons: (1) the current enum is already schema, adding values is backward-compatible, (2) a single enum keeps the per-piece output uniform across languages, (3) the combinator's scoring logic can key on direction values without branching on language. Downside: combinator code that currently assumes exactly three values needs a `default` case. That is a small change.

If the authoring agent prefers option (a) to avoid touching the shared combinator, that is acceptable; in that case emit `typical_direction: neutral` for every CPP piece and put the real state in `cpp_attack_state`. The design above writes directions in the `exploitable` / `latent` / `neutral` vocabulary on the assumption that option (b) is adopted; the authoring agent should adjust if (a) is chosen.
