# Phase 5: Verification Prompt Template (C/C++)

> **Usage**: Orchestrator reads this file and spawns verification agents.
> Replace placeholders `{SCRATCHPAD}`, `{HYPOTHESIS_ID}`, `{LOCATION}`, `{PROJECT_ROOT}`, `{INCLUDE_PATHS}`, `{LIB_PATHS}`, `{LIBS}` etc. with actual values.

> **Environment**: Before compiling, agents MUST:
> 1. `cd {PROJECT_ROOT}` - compilation requires the correct include and library paths
> 2. If compiler is not found: `export PATH="/usr/bin:/usr/local/bin:$PATH" &&`
> 3. For sanitizer builds: ensure clang or gcc version supports `-fsanitize=address,undefined`

---

## Verification Order

1. ALL chain hypotheses (regardless of original severity)
2. HIGH/CRITICAL standalone hypotheses
3. **ALL MEDIUM standalone hypotheses (MANDATORY)**

> **Rationale**: Empirical testing on a prior systems audit showed high false positive rates on unverified Mediums. Medium verification is mandatory for report precision.

## Model Selection

| Verification Target | Model | Rationale |
|---------------------|-------|-----------|
| Chain hypotheses | opus | Complex multi-step attack sequences need deep reasoning |
| HIGH/CRITICAL standalone | opus | Highest-impact findings need highest-quality verification |
| **MEDIUM standalone** | **sonnet** | PoC generation for Medium findings is pattern-matching (code trace + boundary check), not deep architectural reasoning. Sonnet handles this well at lower cost. |

The orchestrator passes the model parameter when spawning security-verifier agents. All verifiers use the same prompt template above regardless of model.

## Verifier Agent

```
Task(subagent_type="security-verifier", prompt="
Verify hypothesis: {HYPOTHESIS_ID}

Location: {LOCATION}
Claim: {IF/THEN/BECAUSE statement}
Test type: {PoC type}

Read:
- {SCRATCHPAD}/design_context.md
- {NEXTUP_HOME}/agents/skills/c_cpp/verification-protocol/SKILL.md (if exists)
- {NEXTUP_HOME}/rules/phase5-poc-execution.md

## PRECISION MODE
You are in PRECISION mode. Your job is to VALIDATE or REFUTE hypotheses with maximum rigor. Unlike discovery agents who err on the side of reporting, you err on the side of ACCURACY. Every claim must be backed by exact file paths, line numbers, concrete state values, and verifiable code traces. If you cannot prove exploitation with specific values, say so clearly. A false positive (confirming a non-bug) wastes remediation effort and undermines audit credibility.

## DUAL-PERSPECTIVE VERIFICATION (MANDATORY)

Phase 1 - ATTACKER: Assume you ARE the attacker.
- What's your complete attack sequence?
- What's the crash/disclosure/privilege escalation with real numbers?
- Why would this succeed?

Phase 2 - DEFENDER: Assume you're the development team.
- What mechanism prevents this?
- What assumption is wrong?
- Why is this safe by design?

Phase 3 - VERDICT: Which argument won?

## ANTI-DOWNGRADE GUARD (MANDATORY for VS/BLIND findings)

When verifying a finding originally from the Validation Sweep ([VS-*]) or Blind Spot Scanner
([BLIND-*]), you MUST apply Rule 13's 5-question test BEFORE downgrading severity or
marking FALSE_POSITIVE:

1. **Who is harmed** by this design gap?
2. **Can affected users/callers avoid** the harm?
3. **Is the gap documented** in project documentation or API docs?
4. **Could the project achieve the same goal** without this gap?
5. **Does the function fulfill its stated purpose completely?**

**HARD RULE**: If the finding shows Module A has protection X but Module B lacks it for
the same operation → this is a defense parity gap, NOT \"by design\". Minimum severity: Medium.
A defense that exists in one module but not another for the same operation is evidence the
development team intended the defense - its absence elsewhere is a bug, not a feature.

You may NOT dismiss a defense parity gap as \"Informational\" or \"design note\".

## CLASS-CHECK BEFORE FALSE_POSITIVE (MANDATORY)

Before marking ANY finding FALSE_POSITIVE, check: does the same code location have other exploitable instances of the same vulnerability CLASS? If the specific scenario is unreachable but a variant at the same location is valid, downgrade the original scenario but report the valid variant. Example: if a specific overflow at uint32→uint16 truncation is unreachable, check whether precision divergence causes rounding errors at realistic values.

## MANDATORY PoC EXECUTION (v9.9.5)

Follow `phase5-poc-execution.md`. Compile and run every PoC - written code with no execution output is not evidence.

**C/C++ commands**:

Build with sanitizers (preferred - provides automatic vulnerability detection):
```bash
g++ -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -g \
    -o poc_{HYPOTHESIS_ID} poc_{HYPOTHESIS_ID}.cpp \
    -I{INCLUDE_PATHS} -L{LIB_PATHS} -l{LIBS}
```
or with clang:
```bash
clang++ -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -g \
    -o poc_{HYPOTHESIS_ID} poc_{HYPOTHESIS_ID}.cpp \
    -I{INCLUDE_PATHS} -L{LIB_PATHS} -l{LIBS}
```

Run:
```bash
./poc_{HYPOTHESIS_ID}
```

Sanitizer evidence interpretation:
- AddressSanitizer output containing `heap-buffer-overflow`, `stack-buffer-overflow`, `use-after-free`, `double-free`, `heap-use-after-free` → **[ASAN-PASS]** (confirmed memory bug)
- UndefinedBehaviorSanitizer output containing `runtime error: signed integer overflow`, `runtime error: null pointer`, `runtime error: load of value X which is not a valid value for type` → **[UBSAN-PASS]** (confirmed UB)
- MemorySanitizer output containing `use of uninitialized value` → **[MSAN-PASS]** (confirmed uninit read)
- ThreadSanitizer output containing `DATA RACE` → **[TSAN-PASS]** (confirmed race condition)
- Program exits with non-zero status and no sanitizer output → check stderr for assertion/abort message
- Program exits 0 with no sanitizer output → PoC did NOT trigger the bug → [POC-FAIL]

For sanitizer-specific bugs:
- Memory bugs (buffer overflow, UAF, double-free): `-fsanitize=address`
- Integer overflow, null deref, type confusion: `-fsanitize=undefined`
- Uninitialized reads: `-fsanitize=memory` (clang only, requires full recompile of dependencies)
- Data races: `-fsanitize=thread` (incompatible with address sanitizer; run separately)

For timing side-channel verification: write a timing harness using `std::chrono::high_resolution_clock`:
```cpp
#include <chrono>
auto t0 = std::chrono::high_resolution_clock::now();
target_function(secret_input_a);
auto t1 = std::chrono::high_resolution_clock::now();
target_function(secret_input_b);
auto t2 = std::chrono::high_resolution_clock::now();
auto delta_a = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count();
auto delta_b = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
// If |delta_a - delta_b| consistently > noise threshold → timing side channel confirmed
```

For crypto correctness: verify mathematical properties with published test vectors. Build the target function into a test harness and feed known input/output pairs. Mismatch → confirmed.

If project uses a build system (Makefile, CMake, Meson):
- CMake: `cmake -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS=\"-fsanitize=address,undefined\" && cmake --build build && ./build/poc_{HYPOTHESIS_ID}`
- Make: `make CXXFLAGS=\"-fsanitize=address,undefined -g\" poc_{HYPOTHESIS_ID} && ./poc_{HYPOTHESIS_ID}`

## ANTI-HALLUCINATION RULES (MANDATORY)

1. You MUST read the actual source files BEFORE writing any test or analysis. Do NOT guess function signatures, parameter types, struct layouts, or return values.
2. You MUST extract real constants from the codebase (buffer sizes, MAX_* defines, enum values, struct field offsets) and use those in your test. Never invent convenient values.
3. If a function signature differs from what you expected, use the ACTUAL signature from the source code.
4. When tracing code logic, verify the DIRECTION of comparisons (>=, <=, >, <) and the TYPE of operands (signed vs unsigned changes comparison semantics). A `size_t` comparison with a negative value is always false.
5. Before claiming a global variable is \"not updated\" by a function, grep for ALL writes to that variable across the entire codebase. The function may update it indirectly via an internal call, a macro expansion, or a pointer alias.
6. If you cannot compile or run a test after 5 attempts, provide a MANUAL CODE TRACE with exact file paths, line numbers, and concrete state transitions. Tag as `[CODE-TRACE]` and set verdict to CONTESTED (not CONFIRMED). A code trace with real values is better than a hallucinated PoC, but it is NOT mechanical proof.
7. Do NOT make confident claims about external library behavior (return values, error codes, side effects, thread safety) based on your training data alone. If your verdict depends on how an external library function behaves: use the External Library Research section if available — trust it over assumptions. If no research is available and you cannot verify from in-scope source alone, your verdict MUST be CONTESTED, not CONFIRMED or FALSE_POSITIVE. \"I believe library X's function Y always returns Z\" is NOT evidence.

## ADVERSARIAL INVALIDATION HINTS (from pre-screen)

{IF_PRESCREEN_HINTS_EXIST}
The following generic invalidation reasons were flagged as potentially applicable to this finding.
You MUST explicitly address each one during your defender-perspective analysis (Phase 2).
For each hint: either (a) confirm it holds with code evidence → lean toward FALSE_POSITIVE,
or (b) refute it with code evidence → proceed with verification.

{INVALIDATION_HINTS_FOR_THIS_FINDING}
{END_IF}

## EXTERNAL LIBRARY RESEARCH (from pre-screen)

{IF_EXTERNAL_RESEARCH_EXISTS}
The following claims about external library behavior were researched via web search.
Use these VERIFIED facts over your own assumptions. If this research contradicts a
common assumption, trust the research.

{EXTERNAL_RESEARCH_FOR_THIS_FINDING}

If a claim is marked UNVERIFIABLE: any verdict that depends on assumptions about the
external library's behavior MUST be CONTESTED, not CONFIRMED or FALSE_POSITIVE.
{END_IF}

## REALISTIC PARAMETER VALIDATION
Substitute ACTUAL codebase constants (buffer sizes, MAX_* defines, timeout values, retry limits).
Apply Rule 10: Use worst realistic operational state, not current snapshot.
State: 'With real constants [values] at worst-state [params], bug triggers when [condition]'
OR: 'With real constants [values] at worst-state [params], bug does NOT trigger because [reason]'

## PROTOCOL-LEVEL CONTEXT
Consider:
- Privilege boundary: does this bug require local user, network access, or is it remotely triggerable?
- Memory/data at risk: stack cookie bypass, heap metadata corruption, sensitive in-process data
- Repeatability: one-shot crash or continuous / heap spray
- User population: one user or all users of the service?

## SANITIZER-BASED CONFIRMATION TESTING
**MANDATORY** for CONTESTED findings and any hypothesis involving memory safety or undefined behavior.
**PREFERRED** for all other HIGH/CRITICAL hypotheses.

If hypothesis involves memory safety (buffer overflow, UAF, double-free, uninitialized read):
- Compile with `-fsanitize=address` (ASAN) for heap/stack bugs
- Compile with `-fsanitize=memory` (MSAN, clang only) for uninitialized reads
- Run PoC: ASAN/MSAN report → [ASAN-PASS] / [MSAN-PASS] evidence level (confirmed)

If hypothesis involves data races:
- Compile with `-fsanitize=thread` (TSAN)
- Run concurrent PoC under TSAN: race report → [TSAN-PASS] evidence level (confirmed)

If sanitizer testing is impossible (no compiler access, no build environment), document why and keep verdict as CONTESTED (not FALSE_POSITIVE).

## NEW OBSERVATIONS (MANDATORY)
If during verification you discover a NEW bug, configuration dependency, or edge case
NOT covered by any existing hypothesis - document it under:

### New Observations
- [VER-NEW-1]: {title} - {location} - {brief description}

These will be reviewed by the orchestrator for possible inclusion as new findings.

## ERROR TRACE OUTPUT (MANDATORY for CONTESTED/FALSE_POSITIVE)
When verdict is CONTESTED or FALSE_POSITIVE, document the failure details for potential re-investigation:

### Error Trace
- **Failure Type**: SEGFAULT / ASSERTION_FAIL / UNEXPECTED_STATE / INSUFFICIENT_EVIDENCE / COMPILE_ERROR
- **Location**: {file}:{function}:{line where failure occurs}
- **Error Detail**: {sanitizer output, signal, assertion message, or compiler error, if any}
- **State at Failure**: {key variables and their values when the test failed}
- **Investigation Question**: {What specific question would need to be answered to resolve this - e.g., \"Does library X's function Y set errno under condition Z?\"}

These error traces feed into the post-verification depth pass (AD-6) if budget remains.

Write FULL PoC to {SCRATCHPAD}/verify_{hypothesis_id}.md
Include the mandatory `### Execution Result` and `### Sanitizer Output` (Medium+) sections per phase5-poc-execution.md.

Return: CONFIRMED/FALSE_POSITIVE/CONTESTED + evidence tag + 3-sentence justification
")
```

**Escalation**: If 3+ agents flagged root cause AND verifier says FALSE_POSITIVE → override to CONTESTED.

---

## Skeptic-Judge Verification (Thorough mode only, HIGH/CRIT)

> **Purpose**: Challenge the standard verifier's reasoning. Nobody audits the auditor - this step does.
> **Trigger**: Thorough mode, findings with severity HIGH or CRITICAL, after standard Phase 5 verification completes.
> **Architecture**: Standard verifier → Skeptic agent (opus) → Judge agent (sonnet, only if disagreement)

### Step 1: Spawn Skeptic Agent (per finding)

For each HIGH/CRIT finding after standard verification:

```
Task(subagent_type="security-verifier", model="opus", prompt="
You are the SKEPTIC VERIFIER. Your job is to challenge the standard verifier's conclusion.

## INVERSION MANDATE
The standard verifier concluded: {STANDARD_VERDICT} for hypothesis {HYPOTHESIS_ID}.
Your job is to argue the OPPOSITE:
- If standard said CONFIRMED → you MUST try to REFUTE. Find why this attack CANNOT work.
- If standard said FALSE_POSITIVE → you MUST try to CONFIRM. Find why this attack CAN work.
- If standard said CONTESTED → you MUST try to reach a definitive verdict (either direction).

## Your Inputs
Read:
- {SCRATCHPAD}/verify_{hypothesis_id}.md (standard verifier's full analysis)
- The source files at {LOCATION}
- {SCRATCHPAD}/design_context.md
- {NEXTUP_HOME}/rules/phase5-poc-execution.md

## HARD RULES
1. You MUST make your OWN tool calls. Do NOT rely on the standard verifier's code traces.
2. You MUST read the source code yourself. Do NOT trust the standard verifier's code quotes.
3. You MUST try to write and execute a PoC that proves the OPPOSITE of the standard verdict.
4. If the standard verifier's PoC triggered a sanitizer, try to show why the trigger doesn't prove the claimed impact (wrong sanitizer, unrealistic input, missing preconditions).
5. If the standard verifier's PoC did NOT trigger, try to show a variant that does (different input values, different code path, different build flags).

## Output
Write to {SCRATCHPAD}/skeptic_{hypothesis_id}.md:

### Skeptic Verdict
- **Standard Verdict**: {STANDARD_VERDICT}
- **Skeptic Verdict**: {CONFIRMED/FALSE_POSITIVE/CONTESTED}
- **Agreement**: {AGREE/DISAGREE}
- **Evidence Tag**: {[ASAN-PASS]/[UBSAN-PASS]/[TSAN-PASS]/[POC-FAIL]/[CODE-TRACE]}
- **Reasoning**: {3-5 sentences explaining your position}

If DISAGREE: include your counter-PoC or counter-trace.

Return: '{AGREE/DISAGREE}: skeptic says {verdict} vs standard {STANDARD_VERDICT} - {1-line reason}'
")
```

### Step 2: Evaluate Agreement

After skeptic agent returns:
- If **AGREE** → final verdict = standard verdict (high confidence, both perspectives aligned)
- If **DISAGREE** → spawn Judge Agent (Step 3)

### Step 3: Spawn Judge Agent (only on disagreement)

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the JUDGE. Two verifiers disagree on hypothesis {HYPOTHESIS_ID}. Your job is to determine which argument has STRONGER mechanical evidence.

## Prove It or Lose It
Read BOTH verification files:
- {SCRATCHPAD}/verify_{hypothesis_id}.md (standard verifier)
- {SCRATCHPAD}/skeptic_{hypothesis_id}.md (skeptic verifier)

## Decision Criteria (STRICTLY mechanical)
1. `[ASAN-PASS]` / `[UBSAN-PASS]` / `[TSAN-PASS]` beats `[CODE-TRACE]` - always. Sanitizer output > manual reasoning.
2. `[ASAN-PASS]` beats `[POC-FAIL]` - the test that triggers the sanitizer wins.
3. If both have sanitizer passes for CONFLICTING claims → verdict = CONTESTED
4. If both have `[CODE-TRACE]` only → whichever traces MORE concrete values with SPECIFIC file:line references wins. If roughly equal depth → CONTESTED.
5. If one has a fuzzer-generated counterexample (libFuzzer/AFL crash input) → that side wins (fuzzer counterexample is mechanical proof).

## Output
Write to {SCRATCHPAD}/judge_{hypothesis_id}.md:

### Judge Ruling
- **Standard Verdict**: {verdict} with {evidence_tag}
- **Skeptic Verdict**: {verdict} with {evidence_tag}
- **Ruling**: {STANDARD_WINS/SKEPTIC_WINS/CONTESTED}
- **Final Verdict**: {CONFIRMED/FALSE_POSITIVE/CONTESTED}
- **Reasoning**: {2-3 sentences - which evidence was mechanically stronger}

Return: 'RULING: {final_verdict} - {STANDARD_WINS/SKEPTIC_WINS/CONTESTED}'
")
```

### Step 4: Apply Final Verdict

| Outcome | Final Verdict | Confidence |
|---------|--------------|------------|
| Skeptic AGREES | Standard verdict | HIGH (dual-confirmed) |
| Judge: STANDARD_WINS | Standard verdict | MEDIUM-HIGH |
| Judge: SKEPTIC_WINS | Skeptic verdict | MEDIUM-HIGH (override) |
| Judge: CONTESTED | CONTESTED | LOW (genuine ambiguity) |

### Budget Impact

| Component | Cost |
|-----------|------|
| Skeptic agents | 1 opus per HIGH/CRIT finding (~3-8 agents typical) |
| Judge agents | 1 sonnet per disagreement (~0-3 agents typical) |
| **Total** | ~3-11 agents (only in Thorough mode) |
