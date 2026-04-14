# Phase 5.6: Individual Low Escalation

> **Purpose**: Give each Low finding a dedicated opus agent that tries to escalate it to Medium by finding unexplored attack angles, missed impact, or overlooked preconditions. A second wave of opus agents then independently verifies whether each proposed upgrade is justified.
> **Trigger**: Always runs after Phase 5.5. Skip if zero Low findings exist.
> **Models**: All opus — escalation requires deep reasoning about impact and attack paths.
> **Budget**: 1 opus agent per Low finding (Wave 1) + 1 opus agent per proposed upgrade (Wave 2). Wave 2 only fires for findings where Wave 1 proposed an upgrade.

---

## Orchestrator Flow

```
Phase 5.5 (Post-Verification Extraction)
    ↓
Phase 5.6: Individual Low Escalation
    Step 1: Collect all Low findings
    Step 2: Spawn Wave 1 — one escalation agent per Low finding (parallel)
    Step 3: Collect proposed upgrades
    Step 4: Spawn Wave 2 — one verification agent per proposed upgrade (parallel)
    Step 5: Apply confirmed upgrades to hypotheses.md
    ↓
Phase 5.7 (Compound Escalation — operates on updated severity set)
```

---

## Step 1: Collect Low Findings (Orchestrator Inline)

Read `{SCRATCHPAD}/hypotheses.md` and extract all findings with final severity **Low**.

Let `N` = number of Low findings.
- If `N == 0` → skip Phase 5.6 entirely. Log: `"Phase 5.6 SKIPPED: 0 Low findings."`
- If `N >= 1` → proceed.

For each Low finding, extract:
- Hypothesis ID
- Title
- Location (file:line)
- Root cause (1 line)
- Current verdict (CONFIRMED / CONTESTED / UNVERIFIED)
- Verification result summary (from `verify_*.md` if exists)
- Original agent source(s)

---

## Step 2: Wave 1 — Escalation Agents (Parallel)

Spawn ALL agents in a SINGLE message — one opus agent per Low finding, all in parallel:

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are an Individual Escalation Agent. You have ONE job: determine whether this Low-severity finding should be upgraded to Medium.

## The Finding

**ID**: {HYPOTHESIS_ID}
**Title**: {TITLE}
**Severity**: Low
**Verdict**: {VERDICT}
**Location**: {LOCATION}
**Root Cause**: {ROOT_CAUSE}

**Full Details**:
{PASTE FULL HYPOTHESIS TEXT FROM hypotheses.md}

**Verification Result** (if available):
{PASTE FROM verify_{ID}.md OR 'Not yet verified'}

## Artifacts Available
- {SCRATCHPAD}/design_context.md (protocol design, trust model)
- {SCRATCHPAD}/attack_surface.md (attack surface)
- {SCRATCHPAD}/state_variables.md (all state variables)
- {SCRATCHPAD}/function_list.md (all functions)
- {SCRATCHPAD}/findings_inventory.md (all findings for cross-reference)
- Source files at {PROJECT_PATH}

## Your Task

This finding was classified as Low. Investigate whether the severity should be Medium instead. Specifically:

### 1. Re-examine Impact
Read the actual source code at the finding location. Ask:
- Is the impact understated? Could the dollar value be higher than originally assessed?
- Does this affect more users or more transactions than the original analysis considered?
- Are there downstream effects the original analysis missed? (e.g., a 'Low' accounting error that propagates into oracle prices, share calculations, or liquidation thresholds)
- Could this be triggered repeatedly or at scale to amplify the damage?

### 2. Re-examine Likelihood
- Are the preconditions easier to satisfy than originally assessed?
- Can an attacker deliberately create the preconditions (vs. waiting for them naturally)?
- Is the vulnerable path hit during normal protocol operation (not just edge cases)?

### 3. Re-examine the Severity Matrix
Apply the standard matrix with your revised impact and likelihood:

| | Likelihood: High | Likelihood: Medium | Likelihood: Low |
|---|---|---|---|
| **Impact: High** | Critical | High | Medium |
| **Impact: Medium** | High | **Medium** | **Medium** |
| **Impact: Low** | **Medium** | Low | Low |

If your revised assessment puts this at Medium or above in the matrix, propose the upgrade.

### 4. Check for Missed Attack Angles
- Can this finding be triggered via flash loan?
- Can this finding be exploited via MEV (sandwich, frontrun, backrun)?
- Is there a governance/admin action that makes this worse?
- Does this interact with protocol pause/unpause, migration, or upgrade paths?

## Rules

1. **Read the code.** Do not reason from the finding description alone.
2. **Be specific.** If you propose an upgrade, provide the exact attack scenario with concrete values.
3. **Don't inflate.** If it's genuinely Low, say so. Unjustified upgrades waste verification budget.
4. **New evidence required.** The upgrade must be based on something the original analysis MISSED — a new attack angle, a missed downstream effect, or a corrected impact estimate. Restating the same finding with scarier language is not an upgrade.

## Output

Write to {SCRATCHPAD}/escalation_{HYPOTHESIS_ID}.md:

```markdown
# Escalation Assessment: {HYPOTHESIS_ID}

**Original Severity**: Low
**Proposed Severity**: {Low (no change) | Medium | High}
**Verdict**: {UPGRADE_PROPOSED | NO_UPGRADE}

## If UPGRADE_PROPOSED:

**Upgrade Justification**:
{3-5 sentences explaining what was missed and why the severity should be higher}

**Revised Impact**: {what can happen — quantified}
**Revised Likelihood**: {High / Medium / Low — with reasoning}
**Severity Matrix Result**: Impact {X} × Likelihood {Y} = {severity}

**New Attack Scenario** (if different from original):
1. {step 1}
2. {step 2}
3. {impact}

**Evidence**: {file:line references supporting the upgrade}

## If NO_UPGRADE:

**Reason**: {1-2 sentences confirming why Low is correct}
```

Return: 'DONE: {HYPOTHESIS_ID} → {UPGRADE_PROPOSED|NO_UPGRADE} {proposed_severity}'

SCOPE: Analyze ONLY your assigned finding. Do NOT read or write other agents' output files. Return and stop.
")
```

---

## Step 3: Collect Proposed Upgrades (Orchestrator Inline)

After ALL Wave 1 agents return:

1. Read each `escalation_{ID}.md`
2. Collect all findings where verdict = `UPGRADE_PROPOSED`
3. Let `U` = number of proposed upgrades

If `U == 0` → log `"Phase 5.6: 0 upgrades proposed. All Lows confirmed."` and skip to Phase 5.7.
If `U > 0` → proceed to Wave 2.

---

## Step 4: Wave 2 — Verification Agents (Parallel)

Spawn ALL verification agents in a SINGLE message — one opus agent per proposed upgrade, all in parallel:

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are an Escalation Verifier. An escalation agent proposed upgrading a Low finding to {PROPOSED_SEVERITY}. Your job is to independently determine whether this upgrade is justified.

## The Original Finding

**ID**: {HYPOTHESIS_ID}
**Title**: {TITLE}
**Original Severity**: Low
**Location**: {LOCATION}

**Full Details**:
{PASTE FULL HYPOTHESIS TEXT FROM hypotheses.md}

## The Proposed Upgrade

{PASTE FULL CONTENT OF escalation_{HYPOTHESIS_ID}.md — justification, revised impact/likelihood, new attack scenario, evidence}

## Artifacts Available
- {SCRATCHPAD}/design_context.md
- {SCRATCHPAD}/attack_surface.md
- {SCRATCHPAD}/state_variables.md
- {SCRATCHPAD}/function_list.md
- Source files at {PROJECT_PATH}

## Your Task

You are an INDEPENDENT VERIFIER. You have NOT seen the original analysis that led to the Low classification. You have NOT seen the escalation agent's reasoning process — only its conclusion. Your job is to determine the truth.

### 1. Verify the New Evidence
- Read the source code at all referenced locations
- Confirm the escalation agent's claims about code behavior, state transitions, and impact
- Check: does the code ACTUALLY do what the escalation agent says it does?

### 2. Verify the Attack Scenario
- Is the proposed attack sequence actually executable?
- Are the preconditions satisfiable?
- Are there guards or protections the escalation agent missed?
- Compute concrete values: attacker cost vs. profit, affected amount, likelihood of triggering

### 3. Verify the Severity
- Apply the severity matrix independently with YOUR assessment of impact and likelihood
- Does YOUR matrix result match the proposed severity?
- Check for downgrade modifiers: on-chain-only exploit (−1 tier), view-function-only (cap at Medium), fully-trusted actor required (−1 tier)

### 4. Render Verdict

**CONFIRMED**: The upgrade is justified. The escalation agent found genuine new evidence or a missed attack angle, and the revised severity is correct per the matrix.

**PARTIAL**: The finding deserves some upgrade but not to the proposed level. (e.g., proposed High but you assess Medium)

**REJECTED**: The upgrade is not justified. The escalation agent either:
- Overstated the impact
- Assumed preconditions that are not satisfiable
- Missed existing protections
- Restated the same finding without genuinely new evidence

## Output

Write to {SCRATCHPAD}/escalation_verify_{HYPOTHESIS_ID}.md:

```markdown
# Escalation Verification: {HYPOTHESIS_ID}

**Proposed Upgrade**: Low → {PROPOSED_SEVERITY}
**Verification Verdict**: {CONFIRMED | PARTIAL | REJECTED}
**Final Severity**: {the severity YOU assess — may differ from proposal}

**Reasoning**:
{3-5 sentences. If REJECTED, explain specifically what is wrong with the upgrade justification. If CONFIRMED, explain what convinced you. If PARTIAL, explain the correct severity.}

**Code Verification**:
{Confirm or refute each code claim from the escalation agent, with file:line references}
```

Return: 'DONE: {HYPOTHESIS_ID} → {CONFIRMED|PARTIAL|REJECTED} at {final_severity}'

SCOPE: Verify ONLY your assigned finding. Do NOT read or write other agents' output files. Return and stop.
")
```

---

## Step 5: Apply Confirmed Upgrades (Orchestrator Inline)

After ALL Wave 2 agents return:

1. Read each `escalation_verify_{ID}.md`
2. Apply results:

| Wave 2 Verdict | Action |
|----------------|--------|
| **CONFIRMED** | Update finding's severity in `hypotheses.md` to the proposed level. Tag with `[INDIVIDUAL-ESCALATION]`. |
| **PARTIAL** | Update finding's severity in `hypotheses.md` to the verifier's assessed level (must be > Low). Tag with `[INDIVIDUAL-ESCALATION]`. |
| **REJECTED** | No change. Finding stays at Low. |

3. Log summary:
```
Phase 5.6 Complete:
  Low findings analyzed: {N}
  Upgrades proposed (Wave 1): {U}
  Upgrades confirmed (Wave 2): {C} ({P} partial)
  Upgrades rejected: {R}
  Final: {list of upgraded findings with old → new severity}
```

4. **Important**: Findings upgraded to Medium+ in this phase will now be eligible for Phase 5.7 compound escalation at their NEW severity. They are no longer in the Low/Info pool for Phase 5.7 — they are Medium+ findings that may combine with OTHER Medium+ findings via the existing chain analysis path, or they may participate in compound escalation as the higher-severity anchor.

---

## Scratchpad Artifacts

| File | Written By | Contents |
|------|-----------|----------|
| `escalation_{ID}.md` | Wave 1 agent (per finding) | Upgrade proposal or no-upgrade confirmation |
| `escalation_verify_{ID}.md` | Wave 2 agent (per proposed upgrade) | Independent verification verdict |
| `phase5.6_summary.md` | Orchestrator (after Step 5) | Summary: counts, upgraded findings, final severities |
