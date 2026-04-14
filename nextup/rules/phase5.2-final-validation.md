# Phase 5.2: Final Opus Validation

> **Purpose**: One opus agent per surviving finding performs a final independent judgment — incorporating verification results, invalidation hints, and external research — before findings enter the report. The last gate before Phase 6.
> **Trigger**: Always runs after Phase 5.1 (Skeptic-Judge). Processes all findings that are NOT marked FALSE_POSITIVE.
> **Model**: All opus — final judgment requires deep reasoning.
> **Budget**: 1 opus agent per surviving finding, all in parallel.

---

## Orchestrator Flow

```
Phase 5.1 (Skeptic-Judge, Thorough only)
    ↓
Phase 5.2: Final Opus Validation
    Step 1: Collect surviving findings
    Step 2: Spawn one opus agent per finding (all parallel, SINGLE message)
    Step 3: Apply verdicts to hypotheses.md
    ↓
Phase 5.5 (Post-Verification Finding Extraction)
```

---

## Step 1: Collect Surviving Findings (Orchestrator Inline)

Read `{SCRATCHPAD}/hypotheses.md` and collect all findings where:
- Phase 5 verdict is NOT `FALSE_POSITIVE`, AND
- Phase 5.1 final verdict (if applicable) is NOT `FALSE_POSITIVE`

For each surviving finding, gather:
- Hypothesis ID, title, severity, location
- Phase 5 verification verdict + evidence tag + key reasoning
- Phase 5.1 Skeptic-Judge result (if applicable): agree/disagree, final verdict
- Pre-screen invalidation hints (from `prescreen_invalidation_hints.md`)
- Pre-screen external research (from `prescreen_external_research.md`, if relevant)
- PoC execution result summary (PASS/FAIL/NOT_EXECUTED)

Let `N` = number of surviving findings.
- If `N == 0` → skip Phase 5.2. Log: `"Phase 5.2 SKIPPED: 0 surviving findings."`
- If `N >= 1` → proceed.

---

## Step 2: Spawn Final Validation Agents (Parallel)

Spawn ALL agents in a SINGLE message — one opus agent per finding, all in parallel:

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are the Final Validation Agent. You render the FINAL independent judgment on whether this finding is valid, invalid, or should be severity-adjusted. You are the last gate before the report.

## The Finding

**ID**: {HYPOTHESIS_ID}
**Title**: {TITLE}
**Severity**: {SEVERITY}
**Location**: {LOCATION}

**Description**:
{PASTE FINDING DESCRIPTION FROM hypotheses.md}

## Verification History

**Phase 5 Verdict**: {CONFIRMED / CONTESTED / FALSE_POSITIVE}
**Evidence Tag**: {[POC-PASS] / [POC-FAIL] / [CODE-TRACE] / [MEDUSA-PASS]}
**Verification Summary**:
{3-5 sentence summary of Phase 5 verifier's key reasoning and PoC result}

**Phase 5.1 Skeptic-Judge** (if applicable):
{AGREE/DISAGREE, skeptic verdict, judge ruling — or 'Not applicable (not HIGH/CRIT or not Thorough mode)'}

## Adversarial Context

**Invalidation Hints** (from pre-screen library matching):
{PASTE 2-3 HINTS FROM prescreen_invalidation_hints.md FOR THIS FINDING}

**External Protocol Research** (if applicable):
{PASTE RELEVANT RESULTS FROM prescreen_external_research.md, OR 'No external dependencies'}

## Artifacts Available
- Source files at {PROJECT_PATH}
- {SCRATCHPAD}/design_context.md (protocol design, trust model)
- {SCRATCHPAD}/verify_{HYPOTHESIS_ID}.md (full verification details)
- {SCRATCHPAD}/skeptic_{HYPOTHESIS_ID}.md (if exists)

## Your Task

You have the finding, the verification results, and the adversarial hints. Now render YOUR independent judgment. You are not bound by the verifier's verdict — you may agree or disagree.

### 1. Read the Code
Read the source code at the finding location. Understand what the code actually does — not what the finding claims it does, not what the verifier concluded.

### 2. Evaluate the Invalidation Hints
For each pre-screen invalidation hint:
- Does it actually hold when you read the code? Be specific — cite file:line.
- If ANY hint holds with strong evidence, this is significant grounds for invalidation.

### 3. Evaluate the Verification Result
- If `[POC-PASS]`: Does the PoC actually prove the claimed impact? Could the PoC be misleading (wrong setup, unrealistic parameters)?
- If `[POC-FAIL]`: Was the failure due to test setup error or because the attack genuinely doesn't work?
- If `[CODE-TRACE]`: Is the trace complete with real constants? Are there gaps in the reasoning?

### 4. Evaluate External Claims
If the finding depends on external protocol behavior:
- Does the external research confirm or refute the assumption?
- If UNVERIFIABLE: the finding cannot be CONFIRMED — cap at CONTESTED.

### 5. Render Final Verdict

**UPHELD**: The finding is valid at its current severity. The code has the described vulnerability, the impact is correctly assessed, and no invalidation reason holds.

**DOWNGRADED**: The finding is valid but at a lower severity than claimed. Specify the correct severity and why.

**INVALIDATED**: The finding is not a real vulnerability. Specify which invalidation reason(s) hold and provide code evidence.

**CONTESTED**: Genuine ambiguity remains — evidence supports both sides. The finding should be reported with a CONTESTED tag.

## Output

Write to {SCRATCHPAD}/final_validation_{HYPOTHESIS_ID}.md:

```markdown
# Final Validation: {HYPOTHESIS_ID}

**Original Severity**: {SEVERITY}
**Phase 5 Verdict**: {VERDICT}
**Final Validation Verdict**: {UPHELD / DOWNGRADED / INVALIDATED / CONTESTED}
**Final Severity**: {severity — same as original if UPHELD, adjusted if DOWNGRADED, N/A if INVALIDATED}

## Invalidation Hint Assessment
{For each hint: HOLDS or FAILS with 1-2 sentence code-backed reasoning}

## Verification Assessment
{2-3 sentences on whether the Phase 5 PoC/trace is convincing}

## Reasoning
{3-5 sentences — your independent judgment. What convinced you?}

## Code Evidence
{file:line references supporting your verdict}
```

Return: 'DONE: {HYPOTHESIS_ID} → {UPHELD|DOWNGRADED|INVALIDATED|CONTESTED} at {final_severity}'

SCOPE: Validate ONLY your assigned finding. Do NOT read or write other agents' output files. Return and stop.
")
```

---

## Step 3: Apply Verdicts (Orchestrator Inline)

After ALL agents return:

1. Read each `final_validation_{ID}.md`
2. Apply results:

| Verdict | Action |
|---------|--------|
| **UPHELD** | No change. Finding proceeds to report at current severity. |
| **DOWNGRADED** | Update severity in `hypotheses.md`. Tag with `[FINAL-DOWNGRADE]`. |
| **INVALIDATED** | Mark as `FALSE_POSITIVE` in `hypotheses.md`. Tag with `[FINAL-INVALIDATED]`. Add to excluded findings list for Appendix A. |
| **CONTESTED** | Mark as `CONTESTED` in `hypotheses.md` if not already. Finding is reported with CONTESTED tag. |

3. **Override protection**: If Phase 5 returned `[POC-PASS]` (mechanical proof) AND the Final Validation says INVALIDATED, the orchestrator forces `CONTESTED` instead of `FALSE_POSITIVE`. Mechanical evidence cannot be overridden by reasoning alone — only by counter-evidence. Log: `"Override protection: {ID} — [POC-PASS] prevents INVALIDATED, forced to CONTESTED"`

4. Log summary:
```
Phase 5.2 Complete:
  Findings validated: {N}
  Upheld: {U} (no change)
  Downgraded: {D} (list with old → new severity)
  Invalidated: {I} (removed from report)
  Contested: {C}
  Override protections triggered: {O}
```

---

## Scratchpad Artifacts

| File | Written By | Contents |
|------|-----------|----------|
| `final_validation_{ID}.md` | Opus agent (per finding) | Final independent judgment with reasoning |
| `phase5.2_summary.md` | Orchestrator (after Step 3) | Summary: counts, verdicts, overrides |

---

## Budget Impact

| Component | Cost | Model |
|-----------|------|-------|
| Finding collection | 0 (orchestrator inline) | - |
| Final validation agents | 1 per surviving finding | opus |
| Verdict application | 0 (orchestrator inline) | - |
| **Typical total** | **5-25 opus agents** | |

This is the most expensive FP filter in the pipeline but also the most thorough. Every finding gets one final independent opus review before the report.
