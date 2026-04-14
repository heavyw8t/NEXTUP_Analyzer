# MCP Tools Reference - C/C++

> **No C/C++ MCP servers exist.** Unlike EVM (slither-analyzer) or Solana (solana-fender), C/C++ analysis
> uses Bash-based tools directly. This document describes the Bash-based equivalents and which MCP tools
> remain useful for C/C++ audits.

> **MCP TIMEOUT POLICY (MANDATORY)**: When an MCP tool call returns a timeout error or fails, do NOT retry
> the same call. Record `[MCP: TIMEOUT]` and skip ALL remaining calls to that provider. Switch immediately
> to fallback (code analysis, grep, WebSearch). Claude Code's tool timeout is set to 300s (5 min) via
> MCP_TOOL_TIMEOUT in settings.json. You cannot cancel a pending call - but you control what happens
> after the error returns.

---

## Static Analysis (Bash-Based, NOT MCP)

C/C++ static analysis tools are invoked via the Bash tool, not through MCP servers.

### cppcheck (Primary Static Analyzer)

```bash
# Full analysis with all checks enabled
cppcheck --enable=all --xml --xml-version=2 \
         --suppress=missingIncludeSystem \
         {SCOPE_PATH} 2>&1 | head -2000

# Or with human-readable output
cppcheck --enable=all --inconclusive \
         --suppress=missingIncludeSystem \
         {SCOPE_PATH} 2>&1 | grep -E '(error|warning|style|performance|portability)' | head -200
```

If not installed: `sudo apt-get install cppcheck` (requires user permission to install).
Fallback if unavailable: grep-based pattern analysis (see Grep-Based Patterns below).

Key check categories:
- `--enable=all`: enables all checkers including style, performance, portability
- `--inconclusive`: enables checks that may produce false positives but catch more bugs
- `--suppress=missingIncludeSystem`: suppress noise from system header includes

### clang-tidy (Secondary Static Analyzer)

```bash
# Generate compile_commands.json first
cd {PROJECT_ROOT}
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -B build_tidy .
cp build_tidy/compile_commands.json .

# Run clang-tidy
clang-tidy -checks='clang-analyzer-*,cert-*,bugprone-*,performance-*,portability-*,readability-*' \
           -header-filter='.*' \
           {SOURCE_FILES} \
           2>&1 | head -2000
```

Key check categories for security:
- `clang-analyzer-security.*`: security-focused static checks
- `clang-analyzer-cplusplus.*`: C++ memory safety, use-after-move
- `cert-*`: CERT coding standard violations (includes many security rules)
- `bugprone-*`: common bugprone patterns (integer overflow, suspicious string usage)

If compile_commands.json unavailable, pass compile flags manually:
```bash
clang-tidy -checks='clang-analyzer-*,bugprone-*' {SOURCE_FILE} -- \
           -I{INCLUDE_DIR} -std=c++17 2>&1 | head -500
```

### Sanitizer Compilation (Bash-Based)

```bash
# AddressSanitizer + UndefinedBehaviorSanitizer
cmake {PROJECT_ROOT} -B build-asan \
  -DCMAKE_C_FLAGS='-fsanitize=address,undefined -g -O1' \
  -DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -g -O1'
make -C build-asan -j$(nproc)
cd build-asan && ctest --output-on-failure --timeout 300 2>&1 | tail -200

# ThreadSanitizer (separate build - incompatible with ASan)
cmake {PROJECT_ROOT} -B build-tsan \
  -DCMAKE_C_FLAGS='-fsanitize=thread -g -O1' \
  -DCMAKE_CXX_FLAGS='-fsanitize=thread -g -O1'
make -C build-tsan -j$(nproc)
cd build-tsan && ctest --output-on-failure --timeout 300 2>&1 | tail -200

# MemorySanitizer (clang only)
cmake {PROJECT_ROOT} -B build-msan \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_C_FLAGS='-fsanitize=memory -fsanitize-memory-track-origins -g -O1' \
  -DCMAKE_CXX_FLAGS='-fsanitize=memory -fsanitize-memory-track-origins -g -O1'
make -C build-msan -j$(nproc)
cd build-msan && ctest --output-on-failure --timeout 300 2>&1 | tail -200
```

### Valgrind (Alternative to ASan when recompilation is not possible)

```bash
# Memory error detection
valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all \
         --track-origins=yes --error-exitcode=1 \
         {BINARY} {TEST_ARGS} 2>&1 | head -300

# Thread error detection
valgrind --tool=helgrind {BINARY} {TEST_ARGS} 2>&1 | head -300

# Cache profiling
valgrind --tool=callgrind --cache-sim=yes {BINARY} {TEST_ARGS} 2>&1 | head -100
```

---

## Grep-Based Function Enumeration (Slither Substitute)

When cppcheck/clang-tidy are unavailable, use these grep patterns as fallback:

| Analysis Goal | Grep Command |
|--------------|-------------|
| List public functions | `grep -rn '^[a-zA-Z_][a-zA-Z0-9_* ]*\s\+[a-zA-Z_][a-zA-Z0-9_]*\s*(' --include='*.c' --include='*.cpp' --include='*.h'` |
| Find global/static variables | `grep -rn '^\(static\s\+\|extern\s\+\)\?[a-zA-Z_].*[^(;]*;' --include='*.c' --include='*.cpp'` |
| Find malloc/free sites | `grep -rn 'malloc\|calloc\|realloc\|free(' --include='*.c' --include='*.cpp'` |
| Find string operations | `grep -rn 'strcpy\|strcat\|sprintf\b\|gets\b\|scanf\b' --include='*.c' --include='*.cpp'` |
| Find mutex usage | `grep -rn 'pthread_mutex\|std::mutex\|lock_guard\|unique_lock' --include='*.c' --include='*.cpp'` |
| Find integer overflow candidates | `grep -rn '\*.*user\|user.*\*\|\+.*input\|input.*+\|\*.*len\|len.*\*' --include='*.c' --include='*.cpp'` |
| Find format string usage | `grep -rn 'printf\|fprintf\|syslog\|sprintf' --include='*.c' --include='*.cpp'` |
| Find function pointers | `grep -rn '(\*[a-zA-Z_][a-zA-Z0-9_]*)(' --include='*.c' --include='*.cpp'` |
| List #include dependencies | `grep -rn '^#include' --include='*.c' --include='*.cpp' --include='*.h' | sort | uniq -c | sort -rn | head -50` |
| Find error return sites | `grep -rn 'return -1\|return NULL\|return false\|return ERROR' --include='*.c' --include='*.cpp'` |

### Caller Tracing (cscope substitute)

```bash
# Build cscope database if available
cscope -R -b -q 2>/dev/null && \
cscope -d -L -3 {FUNCTION_NAME} 2>/dev/null | head -50

# Grep-based caller search (fallback)
grep -rn '{FUNCTION_NAME}(' {PROJECT_ROOT} \
     --include='*.c' --include='*.cpp' --include='*.h' | head -50
```

---

## unified-vuln-db - Vulnerability Pattern Library (MCP)

These MCP tools are language-agnostic and remain useful for C/C++ audits:

| Tool | When to Use | C/C++ Query Tips |
|------|-------------|-----------------|
| `search_solodit_live(keywords, language="C++")` | Search for known C/C++ vulnerability patterns | Use CVE IDs, CWE IDs, or bug class names |
| `get_root_cause_analysis(bug_class)` | Understand bug class mechanics | e.g., "buffer-overflow", "use-after-free", "integer-overflow" |
| `get_attack_vectors(bug_class)` | Exploit patterns | e.g., "heap-spray", "type-confusion", "race-condition" |
| `validate_hypothesis(hypothesis)` | Cross-reference against known bugs | e.g., "integer overflow in length calculation before malloc" |
| `analyze_code_pattern(pattern, code_context)` | Pattern matching | Paste suspect C/C++ code snippet |

Relevant bug classes for C/C++ audits:
- buffer-overflow, stack-buffer-overflow, heap-buffer-overflow
- use-after-free, double-free, heap-use-after-free
- integer-overflow, integer-underflow, signed-integer-overflow
- race-condition, data-race, TOCTOU
- format-string, command-injection
- null-pointer-dereference, uninitialized-memory
- memory-leak, resource-leak
- crypto-misuse, weak-crypto, timing-side-channel

Note: Solodit coverage of C/C++ vulnerabilities is more limited than Solidity. Supplement with:
- WebSearch for CVE databases: `site:cve.mitre.org {library_name}` or NVD search
- WebSearch for security advisories: `{library_name} security advisory`
- CWE reference: `site:cwe.mitre.org CWE-{number}` for bug class details

---

## Static Analysis Escalation Ladder

1. **cppcheck** → primary static analyzer (if installed, runs in seconds)
2. **clang-tidy** → secondary, especially for C++ memory safety and CERT violations
3. **Sanitizers (ASan/UBSan/TSan)** → mechanical proof via test suite execution
4. **Valgrind** → alternative when recompilation is not possible
5. **LibFuzzer/AFL++** → fuzz testing for parser and input-handling code
6. **Grep-based analysis** → fallback if tools unavailable, always available
7. **Manual code review** → always available, highest quality

Unlike EVM where Slither MCP failure is a significant capability loss, C/C++ analysis
relies primarily on direct tool invocation via Bash and manual code review. Grep-based
analysis is always available and sufficient for finding most vulnerability patterns.

The absence of a specialized MCP server for C/C++ means:
- Recon agents use cppcheck + clang-tidy + grep (not MCP calls) for initial scan
- Depth agents use Read + grep + sanitizer output (not MCP calls) for deep analysis
- RAG validation uses unified-vuln-db (MCP) + WebSearch for CVE cross-referencing
- MCP timeouts have less impact: the primary analysis pipeline does not depend on MCP

---

## CVE / Advisory Research Commands

```bash
# Search for CVEs in a specific library version (using web search)
# WebSearch: "{library_name} {version} CVE site:cve.mitre.org"
# WebSearch: "{library_name} {version} security vulnerability"

# Check if library has known CVEs in NIST NVD
# WebSearch: "site:nvd.nist.gov {library_name}"

# Check GitHub security advisories
# WebSearch: "site:github.com/advisories {library_name}"

# Debian/Ubuntu security tracker
# WebSearch: "site:security-tracker.debian.org {library_name}"
```
