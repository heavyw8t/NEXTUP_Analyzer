---
name: "verification-protocol"
description: "How to prove a hypothesis is TRUE or FALSE using C/C++ compilation and sanitizers."
---

# Verification Protocol - C/C++

> How to prove a hypothesis is TRUE or FALSE using compiled test programs and sanitizers.

---

## Evidence Source Tracking (MANDATORY)

### Evidence Source Tags

| Tag | Meaning | Valid for REFUTED? |
|-----|---------|-------------------|
| [CODE] | Audited codebase (in-scope) | YES |
| [SANITIZER] | AddressSanitizer/UBSan/MSan/TSan output | YES (mechanical proof) |
| [TEST] | Project's own test suite | YES |
| [DOC] | Documentation/spec only | NO (needs verification) |
| [EXT-UNV] | External library, unverified behavior | NO |

### Evidence Audit Table (REQUIRED)

Before ANY verdict:
```markdown
### Evidence Audit
| Claim | Evidence Source | Tag | Valid for REFUTED? |
|-------|-----------------|-----|-------------------|
```

## PoC Methodology for C/C++

### Step 1: Write PoC Program

Create a standalone `.cpp` file that:
1. Includes necessary headers from the target project
2. Sets up the precondition state
3. Executes the attack sequence
4. Asserts the expected outcome

### Step 2: Compile with Sanitizers

```bash
g++ -std=c++17 -fsanitize=address,undefined -fno-sanitize-recover=all -g \
    -I{PROJECT_ROOT}/include -I{PROJECT_ROOT}/src \
    -o poc poc.cpp \
    -L{PROJECT_ROOT}/build/lib -l{target_lib} 2>&1
```

**Sanitizer selection by bug type**:
| Bug Type | Sanitizer | Flag |
|----------|----------|------|
| Buffer overflow, use-after-free, double-free | AddressSanitizer | `-fsanitize=address` |
| Integer overflow, null deref, type confusion | UBSan | `-fsanitize=undefined` |
| Uninitialized memory read | MemorySanitizer | `-fsanitize=memory` |
| Data race, deadlock | ThreadSanitizer | `-fsanitize=thread` |

**Note**: ASan and MSan cannot be combined. TSan and ASan cannot be combined. Choose the most relevant.

### Step 3: Execute and Capture Output

```bash
./poc 2>&1
echo "Exit code: $?"
```

**Interpreting results**:
- Sanitizer error message → CONFIRMED (mechanical proof, tag [SANITIZER])
- Clean exit with wrong output → Logic bug confirmed via code trace
- Clean exit with correct output → FALSE_POSITIVE candidate
- Compilation failure → Fall back to manual code trace

### Step 4: Timing Side-Channel Verification (Crypto)

For timing-related findings:
```cpp
#include <chrono>
auto start = std::chrono::high_resolution_clock::now();
// ... operation under test ...
auto end = std::chrono::high_resolution_clock::now();
auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
```

Run 1000+ iterations with different inputs, measure timing variance.
Statistically significant variance (>5% difference) → timing leak confirmed.

### Step 5: Manual Code Trace (Fallback)

If compilation is not possible:
1. Trace execution path with concrete values
2. Show state at each step with exact line numbers
3. Tag as [CODE-TRACE] not [SANITIZER]
4. Verdict: CONTESTED (not CONFIRMED) — code trace is not mechanical proof

## Dual-Perspective Verification

**Phase 1 - ATTACKER**: Complete attack sequence with real values
**Phase 2 - DEFENDER**: What mechanism prevents this? What assumption is wrong?
**Phase 3 - VERDICT**: Which argument won?

## Anti-Hallucination Rules

1. Read actual source files BEFORE writing tests
2. Extract real constants from the code (buffer sizes, limits, thresholds)
3. Use ACTUAL function signatures from source
4. Verify comparison directions (>=, <=, >, <)
5. Before claiming a variable is "not updated" — grep ALL write sites
6. If cannot compile after 3 attempts → manual code trace with [CODE-TRACE] tag

## Mock Rejection Rule

If ANY evidence supporting REFUTED has tag [EXT-UNV]:
- CANNOT return REFUTED
- MUST return CONTESTED
