# Phase 1: Recon Agent Prompt Template (C/C++)

> **Usage**: Orchestrator reads this file and spawns recon agents with these prompts.
> Replace `{path}`, `{scratchpad}`, `{docs_path_or_url_if_provided}`, `{scope_file_if_provided}`, `{scope_notes_if_provided}` with actual values. Omit lines for empty placeholders.
>
> **ORCHESTRATOR SPLIT DIRECTIVE**: Do NOT spawn a single monolithic recon agent.
> Split into **4 parallel agents** to prevent timeout:
>
> | Agent | Tasks | Model | Why Separate |
> |-------|-------|-------|-------------|
> | **1A: RAG-only** | TASK 0 steps 1-4 (local vuln-db + web search) | **sonnet** | Mechanical query+format task against local CSV-backed BM25 index. |
> | **1B: Docs + External + Deps** | TASK 3, TASK 9, TASK 11 | opus | Web search can hang; dep CVE lookups are I/O-bound. Opus for design trust model extraction. |
> | **2: Build + Analysis + Tests** | TASK 1, 2, 7, 8 | **sonnet** | Build/compile is blocking; static analysis is fail-fast. Sonnet sufficient - tool execution + output formatting. |
> | **3: Patterns + Surface + Templates** | TASK 4, 5, 6, 10 | opus | Pure codebase analysis, no external deps. Opus needed - attack surface + template selection requires reasoning. |
>
> **RAG POLICY (v2.0.0-csv)**:
> Agent 1A is a normal inline agent. The orchestrator spawns it alongside Agents 1B, 2, and 3 and awaits all four. Local CSV-backed queries are in-process (no embedding model, no network), so there is no need to run 1A in the background.
> - If Agent 1A's probe call to `mcp__unified-vuln-db__get_knowledge_stats` fails (MCP not installed, CSV index manifest missing, schema mismatch), Agent 1A sets `RAG_TOOLS_AVAILABLE=false`, writes a minimal `meta_buffer.md` with `# Meta-Buffer\n## RAG: UNAVAILABLE - MCP probe failed\nPhase 4b.5 RAG Validation Sweep will compensate via WebSearch fallback.`, and returns.
> - The MCP serves only the local CSV-backed index (19,370 MEDIUM + HIGH findings, 12 language shards). There is no live Solodit fallback; when local results are thin, use `WebSearch` / `mcp__tavily-search__tavily_search`.
>
> Agent 1A writes: `meta_buffer.md`
> Agent 1B writes: `design_context.md`, `external_production_behavior.md`, `dependency_audit.md`
> Agent 2 writes: `build_status.md`, `function_list.md`, `state_variables.md`, `event_definitions.md`, `static_analysis.md`, `test_results.md`
> Agent 3 writes: `file_inventory.md`, `attack_surface.md`, `detected_patterns.md`, `global_variables.md`, `template_recommendations.md`
> Orchestrator writes: `recon_summary.md` (after all 4 agents complete)

```
Task(subagent_type="general-purpose", prompt="
You are the Reconnaissance Agent. Gather ALL information needed for the security audit of a C/C++ codebase.

PROJECT_PATH: {path}
SCRATCHPAD: {scratchpad}
DOCUMENTATION: {docs_path_or_url_if_provided}
SCOPE_FILE: {scope_file_if_provided}
SCOPE_NOTES: {scope_notes_if_provided}

## RESILIENCE RULES (apply to ALL tasks)
1. **Tool call fails/times out?** → Document the failure in the relevant output file and CONTINUE to the next task. Never retry more than once.
2. **Web search (Tavily) fails?** → Note 'UNAVAILABLE - web search failed' in output and CONTINUE. Analysis agents will compensate.
3. **Write-first principle**: Before making any slow external call (MCP, web), write whatever results you already have to the scratchpad file FIRST. This ensures partial results survive if the agent is killed.
4. **No task is blocking**: If any task is stuck, skip it, document why, and move to the next. Partial recon is better than no recon.
5. **MCP TIMEOUT POLICY**: When an MCP tool call returns a timeout error or fails, do NOT retry the same call. Record [MCP: TIMEOUT] and skip ALL remaining calls to that provider - switch immediately to fallback (code analysis, grep, WebSearch). Claude Code's tool timeout is set to 300s (5 min) via MCP_TOOL_TIMEOUT in settings.json to accommodate CSV index load. You cannot cancel a pending call, but you control what happens after the error returns.

Execute these tasks IN ORDER:

## TASK 0: RAG Meta-Buffer Retrieval

### Step 1: Classify Software Type

Scan the project root for key indicators before making any MCP calls:

| Software Type | Key Indicators | Query Category |
|---------------|----------------|----------------|
| crypto/blockchain node | secp256k1, sha256, ECDSA, consensus, p2p, peer, block, chain | `memory-safety`, `integer-overflow`, `crypto-side-channel` |
| network server/daemon | socket, accept, recv, send, epoll, TLS, SSL | `buffer-overflow`, `use-after-free`, `format-string` |
| parser/serialization | parse, deserialize, decode, lexer, grammar, varint, protobuf | `integer-overflow`, `heap-overflow`, `type-confusion` |
| cryptographic library | EVP_, AES, RSA, EC_, HMAC, curve, point, scalar | `timing-side-channel`, `constant-time`, `key-material-leak` |
| embedded/system | RTOS, irq, DMA, firmware, driver, ioctl, mmap | `memory-safety`, `race-condition`, `privilege-escalation` |
| general application | none of the above | `memory-safety`, `buffer-operations`, `integer-safety` |

Record the detected type and relevant query categories in `{SCRATCHPAD}/meta_buffer.md` immediately.

### Step 2: Query unified-vuln-db for attack patterns

> **PROBE FIRST**: Before batch calls, make ONE probe call to detect MCP schema incompatibility:
> `mcp__unified-vuln-db__get_knowledge_stats()`
> - If probe **succeeds** → set `RAG_TOOLS_AVAILABLE = true`, proceed with batches below
> - If probe **fails** (API error, schema error, timeout) → set `RAG_TOOLS_AVAILABLE = false`, **skip ALL unified-vuln-db calls**, append to `{SCRATCHPAD}/build_status.md`: `RAG_TOOLS_AVAILABLE: false - unified-vuln-db MCP probe failed: {error}. Phase 4b.5 RAG Sweep will use WebSearch fallback.`
> - If probe succeeds, also append: `RAG_TOOLS_AVAILABLE: true`

> **PARALLELIZATION DIRECTIVE**: Make MCP calls in PARALLEL batches, not sequentially.

**If RAG_TOOLS_AVAILABLE = false**: Skip Batch 1 and Batch 2 entirely. Write to `{SCRATCHPAD}/meta_buffer.md`: `## RAG: UNAVAILABLE - MCP tools failed probe. Phase 4b.5 will compensate.`

**Batch 1** - call ALL of these in a single message:
1. mcp__unified-vuln-db__get_common_vulnerabilities(protocol_type='{detected software type}')
2. mcp__unified-vuln-db__get_attack_vectors(bug_class='{primary vulnerability class from Step 1}')
3. mcp__unified-vuln-db__get_root_cause_analysis(bug_class='{primary vulnerability class}')

**Batch 2** - call ALL of these in a single message (local CSV-backed BM25):
4. mcp__unified-vuln-db__get_similar_findings(pattern='{software type} memory safety integer overflow C/C++', limit=15)
5. If CRYPTO_OPS detected: mcp__unified-vuln-db__get_similar_findings(pattern='constant time side channel timing attack cryptographic', limit=10, severity='high')

### Step 3: Web Search for Known CVEs / Advisories

If WebSearch is available:
1. Search for recent CVEs in identified third-party dependencies (from Conan / CMake find_package)
2. Search for known vulnerabilities in the project itself (if project name is identifiable)
3. Record results in `{SCRATCHPAD}/meta_buffer.md` under "## Known CVEs and Advisories"

If WebSearch fails → note "UNAVAILABLE - web search failed" and continue.

### Step 4: Synthesize into {SCRATCHPAD}/meta_buffer.md

Use this output format:
```markdown
# Meta-Buffer: {PROJECT_NAME} ({SOFTWARE_TYPE})
## Software Classification
- **Type**: {software_type}
- **Key Indicators**: {what patterns led to classification}
## Common Vulnerabilities for {SOFTWARE_TYPE}
| Category | Frequency | Key Functions to Check |
## Attack Vectors
### {ATTACK_CLASS}
- **Bug Class**: {relevant bug class}
- **Attack Steps**: {from get_attack_vectors}
## Root Cause Analysis
### {BUG_CLASS}
- **Why This Happens**: {root cause}
- **What to Look For**: {methodology hints}
## Known CVEs and Advisories
- {CVE-XXXX-XXXX}: {description} (if found)
## Questions for Analysis Agents
1. {question derived from common vulnerabilities}
2. {question derived from attack vectors}
## Code Patterns to Grep
- `{pattern}` - related to {vulnerability class}
```

## TASK 1: Build Environment

1. Check for build system files in this order:
   - `CMakeLists.txt` → CMake project
   - `conanfile.py` or `conanfile.txt` → Conan package manager
   - `Makefile` or `GNUmakefile` → Make project
   - `meson.build` → Meson project
   - `build.ninja` → Ninja project
   - `configure` or `configure.ac` → Autotools project

2. Record detected build system(s) in `{SCRATCHPAD}/build_status.md`.

3. Install dependencies if a package manager is detected:
   - Conan: `conan install . --output-folder=build --build=missing` (from project root)
   - vcpkg: `vcpkg install` (if vcpkg.json present)
   - If dependency install fails, document reason and attempt build anyway.

4. Attempt to build:
   - **CMake**: `mkdir -p {path}/build && cd {path}/build && cmake .. -DCMAKE_BUILD_TYPE=Debug && make -j$(nproc) 2>&1 | tail -100`
   - **Make**: `cd {path} && make -j$(nproc) 2>&1 | tail -100`
   - **Meson**: `cd {path} && meson setup build && ninja -C build 2>&1 | tail -100`
   - **Autotools**: `cd {path} && ./configure && make -j$(nproc) 2>&1 | tail -100`
   - **Ninja (direct)**: `cd {path} && ninja 2>&1 | tail -100`

5. If build fails, apply this recovery ladder (max 5 attempts total):
   - **Missing header/library** → Install via apt/brew: `apt-get install -y lib{name}-dev` or document as unavailable
   - **CMake version too old** → Try `cmake3` binary
   - **Compiler version mismatch** → Check for `.clang-format`, `compile_commands.json`, or version pragma and match
   - **Missing submodule** → `git submodule update --init --recursive`
   - **Linking error (undefined reference)** → Document missing symbol and continue; build failure does not block static analysis
   Retry after each fix.

6. If build fails after 5 attempts, document failure reason and continue. Static analysis can proceed without a successful build.

7. Extract build metadata from CMakeLists.txt (or Makefile):
   - Compiler: `gcc` / `clang` / `cl` (MSVC)
   - C++ standard: `-std=c++14` / `-std=c++17` / `-std=c++20` / etc.
   - Optimization level: `-O0` / `-O1` / `-O2` / `-O3` / `-Os`
   - Warning flags: `-Wall`, `-Wextra`, `-Wpedantic`, `-Werror`, etc.
   - Sanitizer flags: `-fsanitize=address` (ASan), `-fsanitize=undefined` (UBSan), `-fsanitize=thread` (TSan), `-fsanitize=memory` (MSan)
   - Hardening flags: `-fstack-protector-strong`, `-D_FORTIFY_SOURCE=2`, `-pie`, `-fPIE`, `-Wl,-z,relro`, `-Wl,-z,now`

8. Probe fuzzer availability:
   - `which libfuzzer 2>/dev/null || clang -fsanitize=fuzzer /dev/null -o /dev/null 2>&1 | head -1`
   - `which afl-fuzz 2>/dev/null`
   - Record: `LIBFUZZER_AVAILABLE: true/false`, `AFL_AVAILABLE: true/false`
   - Scan source tree for existing fuzz harnesses: `grep -rl 'LLVMFuzzerTestOneInput' {path} 2>/dev/null`
   - Record: `HAS_FUZZ_HARNESSES: true/false` (and list found harness files)

Write build result to `{SCRATCHPAD}/build_status.md`.
Include all metadata: compiler, standard, optimization, warning flags, sanitizer flags, hardening flags, LIBFUZZER_AVAILABLE, AFL_AVAILABLE, HAS_FUZZ_HARNESSES.

## TASK 2: Static Analysis Artifacts

### Static Analysis Fail-Fast Policy

Static analysis tools may be unavailable. Do NOT retry endlessly.

**Step 1 - cppcheck**:
1. Probe: `which cppcheck 2>/dev/null`
2. If available: `cppcheck --enable=all --xml --xml-version=2 --suppress=missingIncludeSystem {path} 2>&1 | head -2000`
   - Parse XML output into findings list
   - Write findings to `{SCRATCHPAD}/static_analysis.md` under "## cppcheck Findings"
   - Set `CPPCHECK_AVAILABLE = true`
3. If not available: set `CPPCHECK_AVAILABLE = false`, document in `{SCRATCHPAD}/static_analysis.md`: "cppcheck not installed - grep fallback used"

**Step 2 - clang-tidy**:
1. Probe: `which clang-tidy 2>/dev/null`
2. Requires `compile_commands.json`: check `{path}/build/compile_commands.json` or `{path}/compile_commands.json`
3. If both available: `clang-tidy -checks='clang-analyzer-*,cert-*,bugprone-*,cppcoreguidelines-*' -p {path}/build {path}/src/**/*.cpp 2>&1 | head -2000`
   - Write findings to `{SCRATCHPAD}/static_analysis.md` under "## clang-tidy Findings"
   - Set `CLANG_TIDY_AVAILABLE = true`
4. If not available or compile_commands.json missing: set `CLANG_TIDY_AVAILABLE = false`

**Step 3 - grep-based fallback** (ALWAYS run, regardless of tool availability):
Run ALL of the following grep checks and append results to `{SCRATCHPAD}/static_analysis.md` under "## Grep-Based Static Analysis":

- Dangerous string functions: `grep -rn '\bstrcpy\b\|\bstrcat\b\|\bsprintf\b\|\bgets\b\|\bscanf\b' {path} --include='*.c' --include='*.cpp' --include='*.cc' | grep -v test | grep -v vendor | head -100`
- Unsafe memcpy/memmove (no bounds): `grep -rn '\bmemcpy\b\|\bmemmove\b\|\bmemset\b' {path} --include='*.c' --include='*.cpp' | grep -v test | head -100`
- Integer cast patterns: `grep -rn '(int)\|(uint32_t)\|(size_t)' {path} --include='*.c' --include='*.cpp' | grep -v test | head -50`
- Use-after-free patterns: free/delete followed by dereference (grep for free() then variable reuse in same scope)
- Format string issues: `grep -rn 'printf\s*([^"]\|fprintf\s*([^,]*,[^"]' {path} --include='*.c' --include='*.cpp' | head -50`
- NULL dereference risk: `grep -rn '\->.*\|->.*\->' {path} --include='*.c' --include='*.cpp' | grep -v 'if\s*(.*null\|NULL\|nullptr' | head -50`
- Uninitialized memory: `grep -rn '\bmalloc\b\|\bcalloc\b\|\brealloc\b' {path} --include='*.c' --include='*.cpp' | grep -v test | head -50`
- Integer overflow candidates: `grep -rn '\*.*size\|size\s*\*\|len\s*\*\|\+.*len\|len\s*+' {path} --include='*.c' --include='*.cpp' | head -50`

**Step 4 - compile_commands.json extraction** (if build succeeded):
- If `compile_commands.json` exists: extract list of all compiled files and compiler flags → append to `{SCRATCHPAD}/build_status.md` under "## Compilation Units"

Also grep for:
- Exported symbols / public API: `grep -rn '^[a-zA-Z].*\s[a-zA-Z_][a-zA-Z0-9_]*\s*(' {path} --include='*.h' --include='*.hpp' | grep -v static | grep -v '//' | head -200` → `{SCRATCHPAD}/external_interfaces.md`

Write consolidated findings to `{SCRATCHPAD}/static_analysis.md`.
Append to `{SCRATCHPAD}/build_status.md`:
- `CPPCHECK_AVAILABLE: true/false`
- `CLANG_TIDY_AVAILABLE: true/false`
- `STATIC_ANALYSIS_COVERAGE: {full/partial/grep-only}`

## TASK 3: Documentation Context

1. Read in order: `README.md`, `README.rst`, `SECURITY.md`, `docs/` folder contents, any provided URL.
2. Extract: project purpose, key invariants, trust model, external dependencies, known limitations, security assumptions.
3. If no docs: note 'Inferring purpose from code'.
4. **Trust Assumption Table** (MANDATORY): From docs, README, code comments, and access control patterns, extract ALL trust assumptions into a structured table in `design_context.md`:

| # | Actor / Component | Trust Level | Assumption | Source |
|---|-------------------|-------------|------------|--------|
| 1 | {role} | FULLY_TRUSTED | Will not send malicious input | {source} |
| 2 | {component} | SEMI_TRUSTED(bounds: {on-stack limit}) | Cannot exceed {stated bounds} | {source} |
| 3 | - | PRECONDITION | {compile-time or runtime state assumed} | {source} |

Trust levels: `FULLY_TRUSTED` (e.g., operating system, hardware, root), `SEMI_TRUSTED(bounds: ...)` (bounded by runtime checks or API contracts), `PRECONDITION` (deployment/configuration state assumption), `UNTRUSTED` (default for network input, user input, file input, IPC).

If no explicit trust documentation exists, infer from code (input validation presence, assertion patterns, capability checks) and note `Source: inferred`.

5. Document any stated security guarantees (e.g., "this library is constant-time", "input is sanitized by caller").

Write to `{SCRATCHPAD}/design_context.md`.

## TASK 4: File and Code Inventory

1. Count source files by extension:
   - `find {path} -name '*.c' -not -path '*/test*' -not -path '*/vendor*' | wc -l`
   - `find {path} -name '*.cpp' -not -path '*/test*' -not -path '*/vendor*' | wc -l`
   - `find {path} -name '*.cc' -not -path '*/test*' -not -path '*/vendor*' | wc -l`
   - `find {path} -name '*.h' | wc -l`
   - `find {path} -name '*.hpp' | wc -l`

2. Count lines of code:
   - `find {path} \( -name '*.c' -o -name '*.cpp' -o -name '*.cc' \) -not -path '*/test*' -not -path '*/vendor*' -not -path '*/third_party*' | xargs wc -l 2>/dev/null | sort -rn | head -30`

3. Identify largest files (top 20 by line count) - these are highest-complexity targets.

4. **Scope filtering**: If SCOPE_FILE is set, read it and mark files as IN_SCOPE or OUT_OF_SCOPE. If SCOPE_NOTES is set, use them to refine scope. If neither is set, all non-vendor/non-test source files are in scope.

5. Count functions:
   - `grep -rn '^\s*[a-zA-Z_][a-zA-Z0-9_* ]*\s\+[a-zA-Z_][a-zA-Z0-9_]*\s*(.*)\s*{' {path} --include='*.c' --include='*.cpp' --include='*.cc' | grep -v test | grep -v vendor | wc -l`

6. Identify module/component structure (top-level directory names under src/).

7. **Inheritance / class hierarchy** (C++ only):
   - `grep -rn 'class\s\+[A-Za-z_][A-Za-z0-9_]*\s*:\s*\(public\|protected\|private\)' {path} --include='*.h' --include='*.hpp' --include='*.cpp' | head -100`
   - Flag classes with virtual methods (vtable dispatch, potential type confusion)
   - Flag pure virtual interfaces (INTERFACE_PATTERN)

Write to `{SCRATCHPAD}/file_inventory.md`.
Format:
```markdown
# File Inventory
## Source File Counts
- .c files: {N}
- .cpp files: {N}
- .cc files: {N}
- .h files: {N}
- .hpp files: {N}
## Total LOC (non-test, non-vendor): {N}
## Largest Files
| File | Lines | In Scope? |
## Module Structure
- {module}: {purpose}
## Class Hierarchy (C++ only)
| Class | Parent(s) | Virtual Methods? | In Scope? |
```

## TASK 5: Attack Surface Discovery

1. **Map public API** (functions declared in headers, non-static):
   - `grep -rn '^[a-zA-Z]' {path} --include='*.h' --include='*.hpp' | grep '(' | grep -v '//' | grep -v '#define' | grep -v 'typedef' | head -200`
   - Tag each function: takes_user_input, modifies_shared_state, allocates_memory, crypto_operation

2. **Map entry points**:
   - `main()` function(s)
   - Network message handlers: `grep -rn 'recv\|recvfrom\|recvmsg\|read.*socket\|on_message\|handle_message\|process_packet' {path} --include='*.c' --include='*.cpp' | head -50`
   - RPC/IPC handlers: `grep -rn 'rpc\|grpc\|dbus\|ipc\|ioctl\|handle_request\|dispatch' {path} --include='*.c' --include='*.cpp' | head -50`
   - Callback registrations: `grep -rn 'register.*callback\|set.*handler\|on_\|_callback\|function_pointer\|\(\*.*\)\s*(' {path} --include='*.h' --include='*.hpp' | head -50`
   - Signal handlers: `grep -rn 'signal(\|sigaction(\|SA_SIGACTION' {path} --include='*.c' --include='*.cpp' | head -30`

3. **For crypto libraries**: map all public cryptographic operations:
   - Key generation, signing, verification, encryption, decryption, hashing
   - Identify operations that MUST be constant-time

4. **For network nodes / servers**: map:
   - Packet/message parsing entry points
   - Peer connection handling
   - Consensus or state machine entry points
   - Serialization/deserialization boundaries

5. **Signal Elevation Tags**:

During attack surface analysis, tag risk signals that warrant explicit follow-up with `[ELEVATE]`:

Apply `[ELEVATE]` when you observe:
- Unchecked return from malloc/calloc/realloc → `[ELEVATE:NULL_DEREF] malloc return value unchecked in {function}`
- Buffer sized from user-controlled length without validation → `[ELEVATE:HEAP_OVERFLOW] {function} allocates {expr} bytes from user input`
- memcpy/strcpy destination size not verified against source → `[ELEVATE:BUFFER_OVERFLOW] {function} copies to fixed-size buffer without length check`
- Shared mutable state accessed from multiple threads without lock → `[ELEVATE:DATA_RACE] {variable} accessed without mutex in {function}`
- Cryptographic operation on non-constant-time path → `[ELEVATE:TIMING_SIDE_CHANNEL] {operation} branches on secret in {function}`
- Function pointer set from external/network input → `[ELEVATE:ARBITRARY_CALL] function pointer {var} controlled by untrusted input`
- `free()` called twice on same pointer path → `[ELEVATE:DOUBLE_FREE] {pointer} freed in {function}, then freed again in {path}`
- Complex macro with side effects (`##`, `__VA_ARGS__`, multi-statement) → `[ELEVATE:MACRO_SIDE_EFFECT] macro {name} has expansion side effects`
- Integer arithmetic used directly as buffer size without overflow check → `[ELEVATE:INTEGER_OVERFLOW] {expr} used as allocation size without overflow guard`

Write `[ELEVATE]` tags directly into the relevant section of `{SCRATCHPAD}/attack_surface.md`.

Write to `{SCRATCHPAD}/attack_surface.md`.

## TASK 6: Pattern Detection

Grep for these patterns (exclude test/, vendor/, third_party/):

| Pattern | Grep | Flag |
|---------|------|------|
| Memory allocation | `malloc\|calloc\|realloc\|new\b\|new\[\|operator new` | MEMORY_ALLOC |
| Memory free | `free(\|delete\b\|delete\[\|operator delete` | MEMORY_FREE |
| Smart pointers | `unique_ptr\|shared_ptr\|weak_ptr\|make_shared\|make_unique` | RAII_PATTERN |
| Unsafe buffer ops | `\bmemcpy\b\|\bmemmove\b\|\bstrcpy\b\|\bstrncpy\b\|\bstrcat\b\|\bstrncat\b\|\bsprintf\b\|\bvsprintf\b` | BUFFER_OPS |
| Crypto - OpenSSL | `EVP_\|BN_\|EC_\|RSA_\|HMAC\|RAND_bytes\|d2i_\|i2d_` | CRYPTO_OPS_OPENSSL |
| Crypto - secp256k1 | `secp256k1_\|secp256k1\.h` | CRYPTO_OPS_SECP256K1 |
| Crypto - libsodium | `crypto_sign\|crypto_box\|crypto_secretbox\|sodium_\|randombytes_` | CRYPTO_OPS_SODIUM |
| Crypto - generic hash | `sha256\|sha512\|sha3\|blake2\|keccak\|ripemd` | CRYPTO_OPS_HASH |
| Threading - pthreads | `pthread_create\|pthread_mutex\|pthread_rwlock\|pthread_cond` | THREADING_POSIX |
| Threading - C++11 | `std::thread\|std::mutex\|std::atomic\|std::condition_variable` | THREADING_CPP |
| Network - sockets | `socket(\|bind(\|listen(\|accept(\|connect(\|recv(\|send(\|recvfrom\|sendto` | NETWORK_IO |
| Network - TLS | `SSL_\|TLS_\|mbedtls_\|wolfSSL_\|WOLFSSL_` | NETWORK_TLS |
| Function pointers | `(\*[a-zA-Z_][a-zA-Z0-9_]*)\s*(\|typedef.*(\*)` | FUNCTION_POINTERS |
| Complex macros | `#define.*do\s*{\|#define.*##\|#define.*\.\.\.' | COMPLEX_MACROS |
| Integer truncation risk | `(int)\s*\w\+\|\s*(uint[0-9]*_t)\s*\w\+\|(size_t)\s*\w` | INTEGER_CAST |
| Inline assembly | `__asm__\|__asm\s\|asm\s*(` | INLINE_ASM |
| Serialization | `serialize\|deserialize\|encode\|decode\|marshal\|unmarshal\|parse\|unpack\|varint` | SERIALIZATION |
| File operations | `fopen\|open(\|read(\|write(\|mmap(\|fread\|fwrite` | FILE_IO |
| Process execution | `execve\|execvp\|system(\|popen(\|fork(\|posix_spawn` | PROCESS_EXEC |
| Fuzzing harnesses | `LLVMFuzzerTestOneInput\|AFL_FUZZ\|afl_fuzz` | HAS_FUZZ |
| Test files | `test_\|_test\.\|_spec\.\|TEST(\|TEST_F(\|BOOST_AUTO_TEST` | HAS_TESTS |

For each detected flag, record:
- Flag name
- Count of matches
- Representative file:line examples (up to 5)

Write detected flags to `{SCRATCHPAD}/detected_patterns.md`.

## TASK 7: Global and Static State Enumeration

1. **Global variables**:
   - `grep -rn '^[a-zA-Z_][a-zA-Z0-9_* ]\+\s\+[a-zA-Z_][a-zA-Z0-9_]*\s*[=;[]' {path} --include='*.c' --include='*.cpp' | grep -v 'const\|constexpr\|//\|#' | grep -v test | head -100`
   - Note which globals are mutable vs const
   - Note which globals hold cryptographic material (keys, seeds, nonces)

2. **Static variables** (function-local statics, especially dangerous in multi-threaded code):
   - `grep -rn '\bstatic\b.*=\|static\s\+[a-zA-Z_]' {path} --include='*.c' --include='*.cpp' | grep -v 'static\s\+inline\|static\s\+const\s\+char\s\+\*\s\+\w\+\s*=\s*"' | head -100`

3. **Struct/class definitions with mutable fields**:
   - `grep -rn '^struct\s\|^class\s' {path} --include='*.h' --include='*.hpp' --include='*.c' --include='*.cpp' | head -100`
   - For each struct/class: note if it contains pointers, dynamically sized arrays, or union types

4. **Shared state across threads** (flag if THREADING detected):
   - Identify global/static variables accessed in functions that also contain mutex/lock patterns
   - Flag globals NOT protected by a mutex as `UNPROTECTED_SHARED_STATE`

5. **Callback registrations and signal handlers** (write to `{SCRATCHPAD}/event_definitions.md`):
   - All signal handlers: `grep -rn 'signal(\|sigaction(' {path} --include='*.c' --include='*.cpp' | head -50`
   - All registered callbacks: `grep -rn 'register.*callback\|set.*handler\|on_connect\|on_data\|on_error\|on_close' {path} --include='*.c' --include='*.cpp' | head -50`
   - All virtual method override registrations

Write to `{SCRATCHPAD}/state_variables.md`.
Format:
```markdown
# State Variables
## Global Mutable Variables
| Variable | Type | File | Thread-Safe? | Holds Secret? |
## Static Variables (function-local)
| Variable | Function | File | Re-entrancy Risk? |
## Key Struct/Class Definitions
| Type | Fields | Contains Pointer? | Contains Union? | In Scope? |
## Unprotected Shared State (THREADING_* detected)
| Variable | Accessed In | Lock Present? | Flag |
```

Write callback/signal handler registrations to `{SCRATCHPAD}/event_definitions.md`.

## TASK 8: Function List and Call Patterns

1. **Extract all function signatures**:
   - `grep -rn '^\s*[a-zA-Z_][a-zA-Z0-9_*& ]\+\s\+[a-zA-Z_][a-zA-Z0-9_]*\s*(.*)\s*{' {path} --include='*.c' --include='*.cpp' --include='*.cc' | grep -v test | grep -v vendor | head -500`

2. For each function, classify:
   - **Visibility**: public (declared in .h), static (file-local), exported (dllexport/visibility=default)
   - **Input source**: takes_user_input (socket/file/argv param), internal_only
   - **Side effects**: modifies_global_state, allocates_memory, crypto_operation, network_io, file_io
   - **Entry point**: yes/no (called from main, event loop, signal handler, or callback)

3. **Identify dangerous function chains**:
   - Functions that accept length/size from caller without validation AND pass to alloc/buffer op
   - Functions that take a pointer AND free it (caller must not free again)
   - Functions called from signal handlers (async-signal-safe check: only signal-safe functions allowed)

4. **Extract setter/admin functions** (write to `{SCRATCHPAD}/setter_list.md`):
   - Functions that modify global configuration state
   - Functions guarded by privilege checks
   - Note: for C/C++, "setters" are configuration-modifying functions, not necessarily named set*

5. **Silent setter check** (append to `{SCRATCHPAD}/setter_list.md`):
   - Functions that modify critical configuration but have NO corresponding log statement or callback notification
   - Flag as ⚠️ SILENT SETTER

Write to `{SCRATCHPAD}/function_list.md`.
Format:
```markdown
# Function List
| Function | File:Line | Visibility | Takes User Input? | Modifies Global? | Allocs Memory? | Entry Point? |
```

## TASK 9: Dependency Analysis

1. **Conan dependencies** (check `conanfile.py` or `conanfile.txt`):
   - List all requires() entries with versions
   - Note: pinned vs floating versions

2. **CMake find_package dependencies** (check `CMakeLists.txt`):
   - `grep -rn 'find_package\|FetchContent_Declare\|ExternalProject_Add' {path}/CMakeLists.txt {path}/**/CMakeLists.txt 2>/dev/null | head -50`
   - List all external packages with required versions

3. **Vendored libraries** (in-tree copies):
   - `find {path} -name '*.h' -path '*/vendor/*' -o -name '*.h' -path '*/third_party/*' -o -name '*.h' -path '*/extern/*' 2>/dev/null | head -50`
   - For each vendored lib: name, version (from header comments or CMakeLists), last update date if available

4. **Git submodules**:
   - `cat {path}/.gitmodules 2>/dev/null`
   - Note any crypto or parsing library submodules

5. **CVE lookup** (if WebSearch available):
   For each identified dependency with a known version, search:
   - `{library_name} {version} CVE vulnerability`
   - Record any HIGH/CRITICAL CVEs

6. **Security-relevant flags**:
   - Are any dependencies known cryptographic libraries without constant-time guarantees?
   - Are any dependencies known to have had heap overflow / buffer overflow CVEs in recent versions?
   - Are any dependencies using deprecated/insecure functions internally?

Write to `{SCRATCHPAD}/dependency_audit.md`.
Format:
```markdown
# Dependency Audit
## Package Manager Dependencies
| Library | Version | Source | Known CVEs |
## CMake External Dependencies
| Package | Required Version | Actual Resolved | Known CVEs |
## Vendored Libraries
| Library | Version | Path | Last Updated | Known CVEs |
## CVE Summary
| CVE | Library | Severity | Description | Fixed In |
## Dependency Risk Flags
- {flag}: {reason}
```

## TASK 10: Template Recommendations

Based on detected patterns and attack surface, recommend analysis templates and skills.

For EACH recommended template, provide instantiation parameters:

### Template: [TEMPLATE_NAME]
**Trigger**: [what pattern triggered this]
**Relevance**: [why this matters for this codebase]
**Instantiation Parameters**:
- {PARAM_1}: [specific value from this project]
- {PARAM_2}: [specific value]
...
**Key Questions**:
1. [Project-specific question]
2. [Project-specific question]

Available C/C++ templates (in `{NEXTUP_HOME}/agents/skills/c_cpp/`):
- MEMORY_SAFETY_AUDIT - for any code using malloc/free/new/delete (trigger: MEMORY_ALLOC or MEMORY_FREE)
- BUFFER_OPERATIONS - for memcpy/strcpy/strncpy usage and fixed-size buffer patterns (trigger: BUFFER_OPS)
- INTEGER_SAFETY - for integer arithmetic used as buffer sizes, offsets, or array indices (trigger: INTEGER_CAST or BUFFER_OPS)
- CRYPTO_CONSTANT_TIME - for cryptographic implementations that MUST NOT branch on secrets (trigger: CRYPTO_OPS_*)
- CONCURRENCY_SAFETY - for multi-threaded code with shared mutable state (trigger: THREADING_POSIX or THREADING_CPP)
- NETWORK_PROTOCOL_SECURITY - for network servers/clients parsing external input (trigger: NETWORK_IO + SERIALIZATION)
- FUNCTION_POINTER_SAFETY - for callback/function pointer patterns sourced from external input (trigger: FUNCTION_POINTERS)
- MACRO_SAFETY - for complex preprocessor macros with side effects (trigger: COMPLEX_MACROS)
- FUZZING_HARNESS_AUDIT - for codebases with existing fuzz harnesses (trigger: HAS_FUZZ)
- DEPENDENCY_VULN_AUDIT - for dependencies with identified CVEs (trigger: dependency_audit.md has HIGH/CRITICAL CVEs)

Always recommend for ALL C/C++ projects:
- MEMORY_SAFETY_AUDIT (universal)
- BUFFER_OPERATIONS (universal)
- INTEGER_SAFETY (universal)

---

## BINDING MANIFEST (MANDATORY)

> **CRITICAL**: This manifest BINDS pattern detection to agent spawning. The orchestrator MUST spawn an agent for every template marked `Required: YES`.

After listing all recommended templates, output this binding manifest:

```markdown
## BINDING MANIFEST

| Template | Pattern Trigger | Required? | Reason |
|----------|-----------------|-----------|--------|
| MEMORY_SAFETY_AUDIT | MEMORY_ALLOC or MEMORY_FREE flag | YES | Universal for C/C++ - always required |
| BUFFER_OPERATIONS | BUFFER_OPS flag | YES | Universal for C/C++ - always required |
| INTEGER_SAFETY | INTEGER_CAST or BUFFER_OPS flag | YES | Universal for C/C++ - always required |
| CRYPTO_CONSTANT_TIME | CRYPTO_OPS_* flag | {YES/NO} | {if YES: specific crypto ops found} |
| CONCURRENCY_SAFETY | THREADING_POSIX or THREADING_CPP flag | {YES/NO} | {if YES: thread + shared state patterns} |
| NETWORK_PROTOCOL_SECURITY | NETWORK_IO + SERIALIZATION flags | {YES/NO} | {if YES: network + parsing patterns found} |
| FUNCTION_POINTER_SAFETY | FUNCTION_POINTERS flag | {YES/NO} | {if YES: callback patterns from external input} |
| MACRO_SAFETY | COMPLEX_MACROS flag | {YES/NO} | {if YES: multi-statement or ## macros found} |
| FUZZING_HARNESS_AUDIT | HAS_FUZZ flag | {YES/NO} | {if YES: LLVMFuzzerTestOneInput found} |
| DEPENDENCY_VULN_AUDIT | CVEs in dependency_audit.md | {YES/NO} | {if YES: N HIGH/CRITICAL CVEs found} |

### Binding Rules
- MEMORY_ALLOC or MEMORY_FREE flag detected → MEMORY_SAFETY_AUDIT **REQUIRED** (always)
- BUFFER_OPS flag detected → BUFFER_OPERATIONS **REQUIRED** (always)
- INTEGER_CAST flag detected → INTEGER_SAFETY **REQUIRED** (always)
- CRYPTO_OPS_* flag detected → CRYPTO_CONSTANT_TIME **REQUIRED**
- THREADING_POSIX or THREADING_CPP flag AND UNPROTECTED_SHARED_STATE detected → CONCURRENCY_SAFETY **REQUIRED**
- NETWORK_IO flag AND (SERIALIZATION flag OR packet parsing functions in attack_surface.md) → NETWORK_PROTOCOL_SECURITY **REQUIRED**
- FUNCTION_POINTERS flag AND function pointers sourced from network/file/user input → FUNCTION_POINTER_SAFETY **REQUIRED**
- COMPLEX_MACROS flag detected → MACRO_SAFETY **REQUIRED**
- HAS_FUZZ flag detected → FUZZING_HARNESS_AUDIT **REQUIRED**
- dependency_audit.md contains HIGH or CRITICAL CVEs → DEPENDENCY_VULN_AUDIT **REQUIRED**

### Niche Agent Binding Rules
- INLINE_ASM flag detected → INLINE_ASSEMBLY_AUDIT **niche agent** REQUIRED
- PROCESS_EXEC flag AND input from untrusted source in call chain → COMMAND_INJECTION_AUDIT **niche agent** REQUIRED
- FILE_IO flag AND path constructed from user input → PATH_TRAVERSAL_AUDIT **niche agent** REQUIRED

### Niche Agents (Phase 4b - standalone focused agents, 1 budget slot each)

| Niche Agent | Trigger | Required? | Reason |
|-------------|---------|-----------|--------|
| INLINE_ASSEMBLY_AUDIT | INLINE_ASM flag (detected_patterns.md) | {YES/NO} | {if YES: __asm__ blocks found in security-sensitive code} |
| COMMAND_INJECTION_AUDIT | PROCESS_EXEC flag + untrusted input path | {YES/NO} | {if YES: execve/system/popen with input-derived argument} |
| PATH_TRAVERSAL_AUDIT | FILE_IO flag + user-controlled path | {YES/NO} | {if YES: fopen/open with path derived from user input} |

### Manifest Summary
- **Total Required Breadth Agents**: {count of YES in skill templates}
- **Total Required Niche Agents**: {count of YES in niche agents}
- **Total Optional Agents**: {count of NO with recommendation}
- **HARD GATE**: Orchestrator MUST spawn agent for each REQUIRED template AND each REQUIRED niche agent
```

---

Write to `{SCRATCHPAD}/template_recommendations.md`.

## TASK 11: External Library and Interface Verification

> **SKIP POLICY**: Steps involving web search or external lookups may fail. If ANY external call fails, skip that step, document "UNAVAILABLE" for that dependency, and continue. Do NOT let a failed lookup block the entire task.

For EACH critical external dependency or interface identified in dependency_audit.md:

1. **Find version pinning**: Is the version pinned exactly, or is it a floating range? Floating ranges = supply chain risk.

2. **Interface contract verification**: For each function the project calls from an external lib:
   | Function | Library | Expected Behavior | Actual Documented Behavior | DIFFERS? |

3. **ABI/API stability**: Does the library have a stable ABI guarantee? If not, note breakage risk on upgrade.

4. **Known behavioral quirks**: For well-known libraries (OpenSSL, libsodium, secp256k1, mbedTLS):
   - Document any known behavioral quirks relevant to the call patterns used (e.g., OpenSSL EVP_* must call EVP_CIPHER_CTX_free or memory leaks)
   - Note: memory ownership rules (who frees which pointer)

5. **Web search** (if available): Search for "{library_name} {version} security advisory" for each dep.

Write to `{SCRATCHPAD}/external_production_behavior.md`.

**If library source unavailable** (vendored with no version info, or system library with unknown version):
- Mark as 'UNVERIFIED' in dependency_audit.md
- Add severity note: UNVERIFIED dependencies with HIGH worst-case → minimum MEDIUM severity floor
- Analysis agents MUST NOT use assumed behavior as evidence to REFUTE findings

---

Write COMPLETE summary to `{SCRATCHPAD}/recon_summary.md`:
1. Build Status: [success/failed/partial] - compiler, standard, sanitizer flags
2. Source Files: [count .c/.cpp/.cc] totaling [lines] lines (non-test, non-vendor)
3. Functions: [count] total, [count] public/exported, [count] entry points
4. External Dependencies: [count] - [names and versions]
5. Detected Patterns: [list all flags with counts]
6. Recommended Templates: [list with brief reason each]
7. Static Analysis Coverage: [full/partial/grep-only] - tools available
8. Build Flags: [sanitizers: yes/no] [hardening: yes/no] [fuzzer: yes/no]
9. Artifacts Written: [list all files]

Return: 'RECON COMPLETE: {N} source files, {M} dependencies, {K} templates recommended, patterns: [flags]'
")
```

## After Recon Agent Returns

1. **Verify artifacts exist**: `ls {scratchpad}/` - must have all files
2. **Read summary**: `{scratchpad}/recon_summary.md` (small, safe to read)
3. **Read template recommendations**: `{scratchpad}/template_recommendations.md`
4. **Read attack surface**: `{scratchpad}/attack_surface.md`

**Hard gate**: ALL artifacts must exist before Phase 2.
