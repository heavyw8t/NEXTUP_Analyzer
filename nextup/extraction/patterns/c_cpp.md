# C/C++ Pattern Hints

Language-specific markers for puzzle piece extraction in C and C++ codebases (blockchain nodes, crypto libraries, systems software).

## Arithmetic & Precision (Category A)

- **Floor rounding**: Integer division `a / b` (always truncates in C/C++), `trunc()`, `floor()`, `(int)float_val`
- **Ceil rounding**: `ceil()`, `ceilf()`, `(a + b - 1) / b`, `DIV_ROUND_UP` macros
- **Precision loss**: Downcasting `(uint32_t)uint64_val`, `static_cast<int>`, `narrow_cast`, float-to-int conversion
- **Unchecked ops**: Raw `+`, `-`, `*` without `__builtin_add_overflow`/`__builtin_mul_overflow`, no `SafeInt<>` wrapper
- **Zero checks**: Missing `assert(size > 0)`, no null pointer check before dereference, no zero-divisor guard

## Access Control (Category B)

- **Permission check**: `if (role != ADMIN)`, `assert(is_authorized())`, `require_permission()`, capability/role validation
- **Self-callback**: Callback from self via function pointer, internal-only function accessed via vtable
- **No check**: Public API function (exported via header) without caller validation that modifies state
- **Pause gate**: `if (is_paused) return`, `assert(!shutdown)`, `check_not_halted()`, circuit breaker pattern

## State & Storage (Category C)

- **Global/static in loop**: Write to global or static variable inside `for`/`while`, shared state mutation per iteration
- **Unbounded iteration**: `for(i=0; i<vec.size(); i++)` on dynamic container, `while(!queue.empty())`, unbounded linked list traversal
- **Read-write gap**: Read global → external/system call or thread yield → write global (TOCTOU, race condition)
- **Delete in loop**: `erase()` inside iterator loop, `free()` inside iteration, `vector::erase` in `for` loop
- **Counter**: `next_id++`, `sequence_number++`, `atomic_fetch_add(&counter, 1)`

## External Dependencies (Category D)

- **External call**: `dlopen`/`dlsym`, callback function pointers, RPC calls, `extern` function calls, IPC
- **System calls**: `open()`, `read()`, `write()`, `socket()`, `connect()`, `recv()`, `send()`
- **Library dependency**: OpenSSL `EVP_*`, libsecp256k1 `secp256k1_*`, Boost, system library calls
- **Error swallowed**: `if (ret != 0) continue`, error logged but not propagated, `catch (...) { /* ignore */ }`
- **Stale data**: Cached external state without refresh, timestamp check missing on fetched data

## Economic Logic (Category E)

- **First-use path**: `if (total == 0)`, empty state special case, first initialization distinct from steady state
- **Proportional share**: `amount * total / pool_size`, weighted allocation calculation
- **Fee**: `amount * fee_rate / FEE_BASE`, `fee = value * bps / 10000`
- **Slippage/bounds**: `assert(output >= min_output)`, minimum/maximum amount validation
- **Price from ratio**: `reserve_a / reserve_b`, `numerator / denominator` for price

## Control Flow (Category F)

- **Cron/batch**: Timer handler, `batch_process()`, scheduled task, event loop callback
- **Multi-hop chain**: Output of step N feeds input of step N+1, pipeline processing, route iteration
- **Callback/function pointer**: `typedef void (*callback_t)(...)`, `std::function<>`, virtual dispatch, vtable calls
- **Error handling**: `try/catch` with partial state, `errno` check after system call, signal handler state
- **Early return**: `if (...) return early` skipping cleanup, guard clause before resource release

## Token/Asset Handling (Category G)

- **Buffer management**: `malloc`/`calloc`/`realloc` paired with `free`, buffer size tracking, `new`/`delete`
- **Resource cleanup**: `fclose()`, `close()`, RAII destructor, `atexit()` handler, scope guard
- **Allocation verification**: `assert(ptr != NULL)`, `if (malloc(...) == NULL)`, allocation failure handling
- **Dust/residual**: Truncation per iteration in loop, repeated rounding accumulating residual

## Ordering & Timing (Category H)

- **Timestamp/sequence**: Ledger sequence comparison, `time()` or `clock_gettime()` for ordering, sequence numbers
- **Thread ordering**: `std::memory_order_*`, `__sync_*` builtins, fence/barrier instructions
- **Priority encoding**: Bit manipulation for priority sorting, packed ID encoding `id << bits | data`

## Validation & Invariants (Category I)

- **Invariant assertion**: `assert(a + b == total)`, `BOOST_ASSERT`, consistency check after mutation
- **Balance reconciliation**: Inflows == outflows check, pre/post operation balance verification
- **Bounds validation**: `assert(index < size)`, `assert(offset + len <= buffer_size)`, range checks

## C/C++ Specific Patterns (Not in Other Languages)

- **Memory safety**: `memcpy(dst, src, len)` — is `len <= dst_size`? `strcpy` without bounds. `strncpy` without null termination check
- **Use-after-free**: `free(ptr); ... use(ptr)`, dangling pointer after `delete`, iterator invalidation
- **Double-free**: Multiple `free()` on same pointer, exception path freeing already-freed resource
- **Uninitialized read**: Variable declared but not initialized before use, `malloc` without `memset`
- **Format string**: `printf(user_input)` without format specifier, `snprintf(buf, sz, user_data)`
- **Integer overflow**: `size_t + size_t` wrap-around, `int * int` exceeding INT_MAX, signed overflow (UB)
- **Signed/unsigned confusion**: Comparison `signed < unsigned`, negative value passed to `size_t` parameter
- **Constant-time crypto**: `memcmp()` for secret comparison (NOT constant-time), branching on secret data
- **Secret clearing**: `memset(secret, 0, len)` (compiler can optimize out) vs `explicit_bzero()` or `OPENSSL_cleanse()`
- **Race condition**: Shared variable without mutex, TOCTOU on filesystem operations, signal handler data race
- **Null dereference**: Pointer used without null check after function that can return NULL
