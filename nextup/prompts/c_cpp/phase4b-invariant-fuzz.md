# Phase 4b: Sanitizer & Fuzz Campaign - C/C++

> **Usage**: Orchestrator spawns this agent AFTER semantic invariants, BEFORE depth agents.
> **Trigger**: CMakeLists.txt exists AND test files found AND (MODE == thorough OR MODE == core)
> **Budget cost**: Zero (does not count against depth agent budget)
> **Timeout**: 5 minutes for sanitizer run, 15 minutes for fuzz campaign

---

## Sanitizer Analysis Agent

```
Task(subagent_type="general-purpose", prompt="
You are the Sanitizer Analysis Agent. You compile and run the project's test suite with sanitizers
enabled to find memory and undefined behavior bugs mechanically.

## Your Inputs
Read:
- {SCRATCHPAD}/build_status.md (build system, compiler, detected flags)
- {SCRATCHPAD}/semantic_invariants.md (if available - focus sanitizer effort on flagged sites)
- {SCRATCHPAD}/state_variables.md (global/static variables to watch)
- Source files in scope

## STEP 1: Sanitizer Compilation

Build the project with AddressSanitizer and UndefinedBehaviorSanitizer:

```bash
cd {PROJECT_ROOT}
mkdir -p build-sanitizer && cd build-sanitizer
cmake .. \
  -DCMAKE_C_FLAGS='-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1' \
  -DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1' \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined'
make -j$(nproc) 2>&1 | tail -100
```

If CMake is not available, try direct compilation:
```bash
# Find test files
find {PROJECT_ROOT} -name '*test*' -o -name '*spec*' | grep -E '\.(c|cpp)$' | head -20

# Compile directly
gcc -fsanitize=address,undefined -fno-sanitize-recover=all -g -O1 \
    {SOURCE_FILES} {TEST_FILES} -o test_sanitized -lpthread
```

If compilation fails:
- Document the error in sanitizer_fuzz_findings.md
- Try with only -fsanitize=undefined (without address) to isolate the issue
- If still fails: record [BUILD-FAIL] and proceed to STEP 3 (grep-based static analysis fallback)

## STEP 2: Run Tests Under Sanitizers

Execute the test suite:
```bash
cd {PROJECT_ROOT}/build-sanitizer
# Option A: ctest
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 \
UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1 \
ctest --output-on-failure --timeout 300 2>&1 | tail -300

# Option B: make test
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 \
make test 2>&1 | tail -300

# Option C: run test binary directly
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 \
./test_binary 2>&1 | tail -300
```

Parse the output for sanitizer reports. Key patterns to extract:
- `ERROR: AddressSanitizer:` -> heap-buffer-overflow, use-after-free, stack-buffer-overflow, heap-use-after-free, double-free
- `runtime error:` -> UBSan: signed integer overflow, null pointer dereference, misaligned access, shift exponent, divide by zero
- `WARNING: MemorySanitizer:` -> use-of-uninitialized-value
- `WARNING: ThreadSanitizer:` -> data race

For each sanitizer report, extract:
- The ERROR type
- The stack trace (file:line of the violation)
- The allocation/deallocation stack if provided
- Which test triggered it

## STEP 3: ThreadSanitizer Run (if THREADING flag set)

If {SCRATCHPAD}/attack_surface.md indicates multi-threading:
```bash
cd {PROJECT_ROOT}
mkdir -p build-tsan && cd build-tsan
cmake .. \
  -DCMAKE_C_FLAGS='-fsanitize=thread -g -O1' \
  -DCMAKE_CXX_FLAGS='-fsanitize=thread -g -O1' \
  -DCMAKE_BUILD_TYPE=Debug
make -j$(nproc) 2>&1 | tail -50
TSAN_OPTIONS=halt_on_error=1 ctest --output-on-failure --timeout 300 2>&1 | tail -200
```

Note: ThreadSanitizer is NOT compatible with AddressSanitizer in the same build.
Run as a separate build if threading is present.

## STEP 4: LibFuzzer Campaign (if harnesses exist or MODE == thorough)

Check for existing fuzz harnesses:
```bash
grep -rn 'LLVMFuzzerTestOneInput' {PROJECT_ROOT} --include='*.c' --include='*.cpp' -l
```

### If Harnesses Found:
For each harness file:
```bash
# Compile with fuzzer + address sanitizer
clang++ -fsanitize=fuzzer,address,undefined -g -O1 \
        {HARNESS_FILE} {RELEVANT_SOURCES} \
        -I{INCLUDE_DIRS} \
        -o fuzz_{name}

# Create initial corpus directory
mkdir -p {SCRATCHPAD}/corpus_{name}/

# Run with 5-minute timeout per harness
./fuzz_{name} \
  -max_total_time=300 \
  -jobs=2 -workers=2 \
  -artifact_prefix={SCRATCHPAD}/crashes/ \
  {SCRATCHPAD}/corpus_{name}/ \
  2>&1 | tail -50
```

### If No Harnesses Found (Thorough mode only):
Generate basic harness templates for the top 3 public API functions that process external input.
Criteria for selection (priority order):
1. Functions that parse serialized data (JSON, binary protocols, file formats)
2. Functions that process network-received buffers
3. Functions that handle user-supplied strings/lengths

For each selected function, generate:
```cpp
// Auto-generated fuzz harness: fuzz_{function_name}.cpp
#include <stdint.h>
#include <stddef.h>
#include <string.h>
// Include the header for the function under test
// #include "{HEADER_FILE}"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size == 0) return 0;

    // Minimal setup to call {FUNCTION_NAME}
    // TODO: Initialize any required context/state
    // {FUNCTION_NAME}(data, size);

    return 0;
}
```

Write generated harnesses to {PROJECT_ROOT}/fuzz_harnesses/auto_generated/
Attempt compilation and a 2-minute smoke run.

## STEP 5: Report Results

For each sanitizer or fuzzer finding, create a structured finding entry:

```markdown
### [SANITIZER-N] / [FUZZ-N]: {ERROR_TYPE} in {function_name}

**File:Line**: {file.c}:{line_number}
**Sanitizer**: AddressSanitizer / UBSan / TSan / LibFuzzer
**Error Type**: {heap-buffer-overflow / use-after-free / integer-overflow / data-race / etc.}
**Triggered By**: {test_name or fuzz_input_description}

**Sanitizer Output** (exact):
```
{paste sanitizer report here}
```

**Invariant Violated**: {which semantic invariant from semantic_invariants.md this violates, if any}
**Evidence Tag**: [SANITIZER-PASS] (mechanical verification - sanitizer confirmed violation)
**Severity Estimate**: {Critical/High/Medium/Low based on exploitability}
```

If no sanitizer violations found: write a coverage summary only.

If build failed: document the build error and note this as [BUILD-FAIL: sanitizer coverage incomplete].

Write ALL findings to {SCRATCHPAD}/sanitizer_fuzz_findings.md

## Output Summary Table

| Finding ID | Type | File:Line | Sanitizer | Severity | Invariant Violated |
|------------|------|-----------|-----------|----------|-------------------|
| [SANITIZER-1] | heap-buffer-overflow | parse.c:142 | ASan | High | buffer_size_invariant |

Return: 'DONE: {N} sanitizer findings, {M} fuzz findings, compiler={gcc/clang}, build={success/fail}, sanitizers={asan,ubsan,tsan}'
")
```

---

## Skip Conditions Reference

The orchestrator MUST skip this agent (and document the skip) under these conditions:

| Skip Condition | Documentation Required |
|---------------|----------------------|
| No CMakeLists.txt AND no Makefile | Log: "SANITIZER-SKIP: no build system found" |
| No test files found (no *test*, *spec*, ctest) | Log: "SANITIZER-SKIP: no test suite found" |
| LANGUAGE != c_cpp | Log: "SANITIZER-SKIP: language mismatch" |
| MODE == light | Log: "SANITIZER-SKIP: light mode" |
| empty semantic_invariants.md AND MODE == core | Log: "SANITIZER-SKIP: core mode, no invariants" |

ALL OTHER SKIP REASONS ARE VIOLATIONS. Log to {SCRATCHPAD}/violations.md.

---

## Fallback: grep-based Static Analysis (when build fails)

If the sanitizer build fails completely, execute this grep-based fallback:

```bash
# Find dangerous patterns
echo "=== strcpy/gets/sprintf ===" && \
grep -rn 'strcpy\|strcat\|gets\b\|sprintf\b' {PROJECT_ROOT} \
     --include='*.c' --include='*.cpp' | grep -v '//' | head -50

echo "=== malloc without NULL check ===" && \
grep -rn 'malloc\|calloc\|realloc' {PROJECT_ROOT} \
     --include='*.c' --include='*.cpp' | head -50

echo "=== unchecked return values ===" && \
grep -rn 'write\|read\b\|fwrite\|fread\|send\|recv' {PROJECT_ROOT} \
     --include='*.c' --include='*.cpp' | grep -v 'return\|if\|=\s*' | head -30
```

Document grep-based findings as [STATIC-N] with evidence tag [CODE] (not [SANITIZER-PASS]).
Note the fallback in the output: "FALLBACK: grep-based static analysis (sanitizer build failed)"
