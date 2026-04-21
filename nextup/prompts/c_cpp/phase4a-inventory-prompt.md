# Phase 4a: Inventory Agent Prompt Template (C/C++)

> **Usage**: Orchestrator reads this file and spawns the Inventory Agent with this prompt.
> Replace placeholders `{SCRATCHPAD}`, `{list...}`, etc. with actual values.
> **Includes**: Memory Ownership Trace audit (merged from Phase 3.5 to eliminate a sequential gate).
> **Note**: Confidence scoring is computed by the orchestrator's scoring agent AFTER Phase 4b iteration 1, not during inventory. The inventory agent's job is unchanged - it inventories findings and prepares depth candidates.

---

## Inventory Agent

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are the Inventory Agent. You inventory ALL breadth findings AND audit memory ownership trace coverage in a single pass.

Read ALL files matching {SCRATCHPAD}/analysis_*.md

For each file:
- Extract all findings from ## FINDING INDEX or scan for [{XX}-N] patterns
- Extract ## DEPTH_TARGETS section
- Extract Step Execution fields - flag findings with ✗ or ? without valid reasons
- Extract Rules Applied field - flag missing rule applications

Also read ALL files matching {SCRATCHPAD}/nextup/hypotheses_batch_*.json. These are the NEXTUP combinatorial hypothesis outputs from Phase 4a.NX.

For each hypothesis:
- Skip entries where `feasibility == "INFEASIBLE"`.
- Keep FEASIBLE and CONDITIONAL. Each becomes a candidate finding with source="NEXTUP", carrying the fields: title, severity, code_refs (as Location), puzzle_pieces (as evidence), attack_steps, preconditions.

## TASK 1.0: Cross-Source Deduplication (MANDATORY)

Two candidates are duplicates when they describe the same underlying bug, even if:
- Sources differ (breadth analysis, NEXTUP hypothesis, sanitizer detector)
- Wording differs
- Severity ratings differ
- Locations overlap but are not identical (same function, different lines; same memory region, different access sites)

For each duplicate group, select the survivor by this priority:
1. A breadth finding with completed PoC or sanitizer reproduction is always the survivor.
2. A breadth finding without PoC loses only to a NEXTUP hypothesis that cites stricter source evidence (direct code trace through the full attack path, matching puzzle-piece categories that explain the mechanism).
3. NEXTUP vs NEXTUP: higher feasibility beats lower; ties go to higher severity; remaining ties go to higher combo score.
4. Sanitizer-promoted findings defer to any manual finding (breadth or NEXTUP) covering the same root cause. They survive only when alone.

Merge evidence into the survivor:
- Append non-duplicate Location entries from losers as `Related locations:` on the survivor.
- For NEXTUP losers merged into breadth survivors, append `Puzzle-piece evidence: <piece ids>` to cite the static combo that also flagged the issue.
- If a NEXTUP hypothesis contributes attack steps or preconditions the breadth finding missed, merge them into the survivor's attack path section.
- Losers are not deleted. List them in a `## Dedup Trail` table at the end of findings_inventory.md (columns: Loser ID, Source, Merged Into, Reason) so chain analysis and the final report can trace origin.

ID assignment after dedup:
- Breadth survivors keep their original `[XX-N]` IDs.
- Sanitizer survivors use `[SAN-N]`.
- NEXTUP survivors with no breadth match get sequential `[NX-N]` IDs starting at 1.
- Dropped losers retain their original ID in the Dedup Trail only.

## TASK 1: Findings Inventory

Write to {SCRATCHPAD}/findings_inventory.md:
## Findings Inventory
**Total: {N} findings from {M} agents**
| # | Finding ID | Agent | Severity | Location | Title | Verdict | Step Execution | Rules Applied | RAG Confidence |

## Chain Summary
| Finding ID | Location | Root Cause (1-line) | Verdict | Severity | Precondition Type | Postcondition Type |
|------------|----------|--------------------:|---------|----------|-------------------|-------------------|

## REFUTED Findings (for Depth Second Opinion)
| Finding ID | Agent | Reason for REFUTED | Missing Precondition | Domain |

## CONTESTED Findings (for Depth Priority)
| Finding ID | Agent | External Dep Involved | Worst-Case Severity | Notes |

## Incomplete Analysis Flags
| Finding ID | Missing Steps | Reason Invalid? | Flag for Depth? |

## Rule Application Violations
| Finding ID | Rule | Expected | Actual | Violation? |
Check these rules:
- R6 (Bidirectional Role): If SEMI_TRUSTED_ROLE detected AND finding involves role → both directions required
- R8 (Cached Params): If multi-step operation detected → staleness check required
- R10 (Worst-State): If severity uses current observed state → flag for recalibration
- R14 (Constraint Coherence + Setter Regression): If admin setter modifies limit/bound → regression check and coherence check required
- CC1 (Ownership Transfer): If pointer/buffer passed to external function → ownership must be explicit
- CC2 (Error Path Dealloc): If allocation occurs before a potential error → all error paths must free
- CC3 (NULL Return Check): If function can return NULL → every call site must check before dereference
- CC5 (Integer Width): If arithmetic on user-controlled input → check for truncation/promotion issues
- CC7 (Format String): If user input reaches printf-family call → check for format string injection

## TASK 1.5: Assumption Dependency Cross-Reference

Read {SCRATCHPAD}/design_context.md - specifically the Trust Assumption Table.

For each finding in the Findings Inventory above, identify the actor required to execute the attack path, then cross-reference against the Trust Assumption Table:

| Condition | Tag | Severity Effect |
|-----------|-----|----------------|
| Attack requires `FULLY_TRUSTED` actor to act maliciously | `[ASSUMPTION-DEP: TRUSTED-ACTOR]` | −1 tier (applied by Index Agent) |
| Attack requires `SEMI_TRUSTED` actor to act maliciously | No tag | No change - severity matrix Likelihood axis already captures "specific conditions/complex setup" |
| Attack requires `SEMI_TRUSTED` actor to act WITHIN stated bounds | `[ASSUMPTION-DEP: WITHIN-BOUNDS]` | Flag only - no severity change |
| Attack requires `SEMI_TRUSTED` actor to EXCEED stated bounds | No tag | Real finding - no change |
| Attack requires `UNTRUSTED` actor or exploits `PRECONDITION` violation | No tag | Real finding - no change |

**Rules**:
- `TRUSTED-ACTOR` tag is ONLY for `FULLY_TRUSTED` actors (e.g., root process, privileged daemon, admin service). NEVER tag `SEMI_TRUSTED` actors as `TRUSTED-ACTOR` - their findings are calibrated through the severity matrix Likelihood axis instead.
- Only tag if the finding's ENTIRE attack path depends on the assumption. If the attack has BOTH a trusted-actor path AND an untrusted-actor path → no tag.
- `WITHIN-BOUNDS` means the attack's impact does not exceed what the stated bounds already allow. If the finding shows impact BEYOND stated bounds → no tag (real bug).
- When uncertain whether impact exceeds bounds → do NOT tag. Err on the side of preserving severity.

Append to {SCRATCHPAD}/findings_inventory.md:

## Assumption Dependency Audit
| Finding ID | Attack Actor | Actor Trust Level | Within Bounds? | Tag | Original Severity |
|------------|-------------|-------------------|---------------|-----|-------------------|

---

## Static Analysis Finding Promotion
Read {SCRATCHPAD}/static_analysis.md (from cppcheck/clang-tidy/other static analysis tools)
For each detector finding:
- buffer-overflow → Check if write exceeds buffer bounds (user-controlled index or size). Check if strcpy/sprintf/gets used with external input. If YES → create buffer overflow hypothesis.
- null-dereference → Check if return value of malloc/calloc/realloc/fopen/getenv used before NULL check. If YES → create null deref hypothesis.
- use-after-free → Check if pointer used after free() call. Check if free() called in a destructor while pointer still cached elsewhere. If YES → create UAF hypothesis.
- uninitialized-variable → Check if variable read before guaranteed write on all paths. If YES → create uninitialized read hypothesis.
- integer-overflow → Check if arithmetic on user-controlled integer can overflow before bounds check. If YES → create integer overflow hypothesis.
- memory-leak → Check if allocation on every return path has a corresponding dealloc. Check if exception path skips free/delete. If YES → create resource leak hypothesis.
Add promoted findings to inventory with [STATIC-N] IDs and Severity: Medium (pending verification).

---

## TASK 2: Memory Ownership Trace Audit

Read {SCRATCHPAD}/attack_surface.md (Memory Flow Matrix - look for Ownership-Transfer? = YES or UNKNOWN).

For EACH pointer/buffer where the Memory Flow Matrix shows Ownership-Transfer = YES or UNKNOWN, cross-reference against the breadth analysis files you already read:

### Trace Template (fill for each ownership transfer)

| # | Question | Answer |
|---|----------|--------|
| 1 | What function allocates this buffer/pointer? | {file}:{function}:{line} |
| 2 | What side effects can passing it to an external function produce? | {list all: ownership transfer, aliasing, partial write, reallocation} |
| 3a | Who receives ownership of the pointer after the call? | {caller retains / callee owns / shared / AMBIGUOUS} |
| 3b | Where does the pointer LAND after the call returns? | {stored in struct, returned to caller, passed deeper, discarded} |
| 3c | What code paths CONSUME that pointer location? | {list all functions that dereference or free at that location} |
| 3d | Does the consuming code HANDLE this specific ownership state? | YES (it owns and frees) / NO (double-free or leak possible) / UNKNOWN |
| 3e | Does the call ADD ENTRIES to any data structure that could grow unboundedly? | YES (new node, new entry, new allocation) / NO |
| 3f | Is there a FREE PATH for this allocation on all exit paths? | {function/code path that frees} / NONE (leak) |
| 3g | Can a callback/function pointer CORRUPT the caller's stack or heap? | Check: Does the callee write through a pointer to caller's stack frame? Does a realloc invalidate a pointer held by the caller? Does the callee free a pointer the caller still holds? If YES → trace what memory state the caller is left in. |

### Trace Termination
Continue tracing until ONE of:
- The allocation is freed on all paths (caller or callee owns, correctly frees)
- The allocation is consumed by protocol logic correctly (transferred to persistent storage, returned to user)
- The allocation is LEAKED (no free path on one or more return paths) → **FINDING**
- The allocation is DOUBLE-FREED (freed by both caller and callee, or freed twice in same path) → **FINDING**
- The callback corrupts caller's memory (realloc invalidates cached pointer, callee writes past bounds, signal handler races) → **FINDING**
- The allocation creates unbounded growth (no upper limit on cumulative allocations) → **FINDING**

### Cross-Reference with Breadth
For each trace, check if breadth agents already identified a finding covering this path:
- If YES: note 'Covered by [XX-N]' and verify the breadth finding traced to the SAME termination point
- If NO: this is a NEW gap - create finding [MO-N]

### Memory Ownership Trace Output
Append to {SCRATCHPAD}/findings_inventory.md:

## Memory Ownership Trace Audit
### Memory Ownership Trace Summary
| # | Allocation Site | External Call | Ownership After | Landing | Consuming Code | Handled? | Breadth Coverage | Finding |
|---|-----------------|---------------|-----------------|---------|----------------|----------|------------------|---------|

### Memory Ownership Findings (if any)
Use finding IDs [MO-1], [MO-2], etc. with standard finding format.

### Memory Ownership Coverage Gaps
List any Ownership-Transfer = UNKNOWN entries that could not be resolved without runtime verification.

---

## TASK 3: Elevated Signal Audit

Read `{SCRATCHPAD}/attack_surface.md` and extract all `[ELEVATE]` tags.

For each `[ELEVATE]` tag:

| # | Signal | Tag Type | Addressed by Finding? | Finding ID | If Not Addressed |
|---|--------|----------|----------------------|-----------|-----------------|
| 1 | {signal text} | {tag type} | YES/NO | {ID or NONE} | Flag for depth |

**Rules**:
- Every `[ELEVATE]` tag MUST be explicitly addressed - either covered by an existing finding or flagged for depth review
- If NO finding addresses the signal → add to `depth_candidates.md` as HIGH priority investigation target
- \"Addressed\" means a finding explicitly analyzed the risk described by the signal, not just mentioned the same code location

Append to `{SCRATCHPAD}/findings_inventory.md`:

## Elevated Signal Audit
| Signal | Tag | Addressed? | Finding ID / Depth Flag |

---

## TASK 4: Depth Candidates

Write to {SCRATCHPAD}/depth_candidates.md:
## Depth Candidates
Categorize ALL findings by depth domain:
- Data Flow: buffer contents through function boundaries, attacker-controlled data reaching dangerous sinks
- State Trace: global/static variable mutations, mutex coverage, TOCTOU patterns
- Edge Case: SIZE_MAX, INT_MIN, INT_MAX, UINT64_MAX, 0, NULL, stack/heap exhaustion
- External: library call side effects, system call error handling, network I/O, dynamic loading

## Second Opinion Targets
List ALL REFUTED findings that depth agents MUST re-evaluate:
| Finding ID | Domain | Breadth Reasoning | Potential Enablers |

## TASK 4.5: Quick Chain Pre-Scan (Dependency-Aware Severity)

For each finding with Severity=Low AND a non-empty Postcondition Type in the Chain Summary:

1. Search ALL findings with Severity >= Medium that have a Missing Precondition matching this Low finding's Postcondition Type
2. If MATCH FOUND (same type AND compatible description):
   - Tag the Low finding as `CHAIN_ESCALATED: enables {Medium+ finding ID}`
   - Set `effective_severity = Medium` (for depth budget allocation ONLY - reported severity unchanged)
3. Write escalated findings to depth_candidates.md under '## Chain-Escalated Findings'

| Low Finding | Postcondition | Matching Medium+ Finding | Missing Precondition | Escalation |
|-------------|---------------|--------------------------|---------------------|------------|

**HARD RULE**: This does NOT change the finding's actual severity. It only affects depth budget priority. The chain analysis agent (Phase 4c) determines final severity.

**Cap**: Maximum 5 escalations per audit. If more than 5 match, prioritize by the highest severity of the matching Medium+ finding.

## Skip Depth? (RARE)
Depth skips ONLY if ALL conditions met:
- [ ] 0 REFUTED findings
- [ ] 0 PARTIAL findings
- [ ] 0 CONTESTED findings
- [ ] 0 findings with incomplete step execution
- [ ] 0 rule application violations
- [ ] 0 promoted static analysis findings
- [ ] All findings have RAG confidence > 0.8
- [ ] No UNVERIFIED external deps
- [ ] 0 memory ownership coverage gaps

If ANY checkbox unchecked → SPAWN ALL DEPTH AGENTS

---

## Gate File Output (MANDATORY)

Write to {SCRATCHPAD}/phase4_gates.md:

# Phase 4 Gate Status

## Gate 1: Spawn Verification
- **BINDING MANIFEST checked**: YES/NO
- **Missing required agents**: [list or NONE]
- **Status**: BLOCKED if missing > 0, else OPEN

## Memory Ownership Trace Status
- **Pointers/buffers with Ownership-Transfer=YES/UNKNOWN**: {count}
- **Fully traced**: {count}
- **New [MO-N] findings**: {count}
- **Coverage gaps (UNKNOWN)**: {count}

## Proceed to Step 4b?
- Gate 1: {OPEN/BLOCKED}
- **Decision**: PROCEED if OPEN, else RE-SPAWN MISSING AGENTS FIRST

> **Note**: After Phase 4b iteration 1 completes, the orchestrator will run a scoring agent to compute confidence scores for all findings. This scoring step is handled by the orchestrator's adaptive loop, not by the inventory agent.

Return: 'DONE: {N} findings inventoried, {M} REFUTED for second opinion, {K} CONTESTED, {J} static analysis promoted, {S} memory ownership paths traced ({MO} new findings), gate: {status}, depth: MANDATORY/SKIP'
")
```
