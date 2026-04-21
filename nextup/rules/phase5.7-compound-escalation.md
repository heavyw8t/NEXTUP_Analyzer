# Phase 5.7: Low/Info Compound Escalation

> **Purpose**: Attempt to combine Low and Informational findings into higher-severity compound exploits. Individual findings may be low-impact, but two or three together can form a viable attack chain that warrants escalation.
> **Trigger**: Always runs after Phase 5.6 (Individual Low Escalation). Skip if fewer than 2 Low+Info findings exist (need at least a pair to combine). Uses the updated severity set — findings upgraded by Phase 5.6 are no longer in the Low pool.
> **Budget**: 2-5 opus agents (combination analysts, Core/Thorough) or sonnet (Light) + standard verification cost for any escalated findings.
> **Failure mode**: If zero escalated findings survive verification, proceed to Phase 6 with the original finding set. This phase is best-effort.

---

## Orchestrator Flow

```
Phase 5.5 (Post-Verification Extraction)
    ↓
Phase 5.6 (Individual Low Escalation — may upgrade some Lows to Medium+)
    ↓
Phase 5.7: Compound Escalation (operates on updated severity set)
    Step 1: Collect Low/Info findings
    Step 2: Generate pair/triple assignments (orchestrator inline)
    Step 3: Spawn combination agents in parallel (non-overlapping batches)
    Step 4: Collect escalated findings
    Step 5: Run Phase 5 verification on escalated findings
    Step 6: Run Phase 5.1 Skeptic-Judge on HIGH/CRIT escalations (Thorough only)
    Step 7: Merge survivors into hypotheses.md
    ↓
Phase 6 (Report)
```

---

## Step 1: Collect Low/Info Findings (Orchestrator Inline)

Read `{SCRATCHPAD}/hypotheses.md` and extract all findings with final severity **Low** or **Informational**.

For each, extract a compact card:

```markdown
| ID | Severity | Title | Location | Root Cause (1 line) | State Touched |
```

The `State Touched` column is critical for combination quality — pull from the finding's postcondition analysis or the original agent output. If unavailable, grep the finding's location for state variable writes.

**Count**: Let `N` = number of Low+Info findings.
- If `N < 2` → skip Phase 5.7 entirely. Log: `"Phase 5.7 SKIPPED: only {N} Low/Info findings (need at least 2)."`
- If `N >= 2` → proceed.

---

## Step 2: Generate Combination Assignments (Orchestrator Inline)

### Step 2a: Build Interaction Graph

For each pair of Low/Info findings, check if they have a plausible interaction link:
- **Shared state**: Both touch the same state variable (from `State Touched` column)
- **Same contract**: Both are in the same contract/module
- **Caller-callee**: One finding's function calls the other's function (check `function_list.md` or `call_graph.md`)
- **Same actor**: Both are triggerable by the same actor type
- **Economic link**: One affects a value that the other reads (e.g., one affects a fee, the other uses that fee)

Keep only pairs where **at least one link exists**. Discard unlinked pairs — they cannot form a compound exploit.

### Step 2b: Add Triples (Core/Thorough only)

For each surviving pair (A, B), check if a third finding C links to BOTH A and B (or links to one while the pair already covers the other). Add triple (A, B, C) if connected.

Cap triples at 2× the number of pairs (triples are less likely to yield results).

### Step 2c: Partition into Non-Overlapping Batches

**Hard rule**: No two agents receive the same combination. Each combination is assigned to exactly one agent.

Partition algorithm:
1. Sort all combinations by interaction strength (more shared state = stronger = higher priority)
2. Determine agent count: `agent_count = min(max(2, ceil(total_combos / 15)), 5)`
3. Round-robin assign combinations to agents in sorted order
4. Each agent receives 8-20 combinations (target ~15)

Write assignments to `{SCRATCHPAD}/compound_assignments.md`:
```markdown
# Compound Escalation Assignments

Total Low/Info findings: {N}
Total combinations (linked): {C} ({P} pairs + {T} triples)
Agents: {agent_count}

## Agent CE-1: {combo_count} combinations
| # | Findings | Link Type | Shared State |
|---|----------|-----------|-------------|

## Agent CE-2: {combo_count} combinations
...
```

---

## Step 3: Spawn Combination Agents (Parallel)

Spawn ALL agents in a SINGLE message (parallel execution):

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are Compound Escalation Agent #{N}. Your job is to determine whether combinations of Low/Informational findings can be chained into higher-severity exploits.

## CRITICAL MINDSET

Each Low/Info finding was individually assessed as low-impact. But vulnerabilities combine:
- A missing zero-check (Low) + a rounding-to-zero path (Info) = withdraw zero tokens for free (High)
- A missing event (Info) + a retroactive parameter change (Low) = undetectable admin rug (Medium)
- A stale cache (Low) + a front-runnable setter (Low) = sandwich attack via parameter manipulation (High)

Your job is to find these compound interactions. Be concrete — describe the full attack sequence with specific function calls, not vague speculation.

## Your Assigned Combinations

{PASTE AGENT'S COMBINATION TABLE FROM compound_assignments.md}

## Finding Details

For each finding referenced in your combinations:

{PASTE COMPACT FINDING CARDS FOR ALL FINDINGS IN THIS AGENT'S BATCH}

## Artifacts Available
- {SCRATCHPAD}/hypotheses.md (full hypothesis details)
- {SCRATCHPAD}/findings_inventory.md (agent findings with evidence)
- {SCRATCHPAD}/design_context.md (protocol design)
- {SCRATCHPAD}/state_variables.md (state variable details)
- {SCRATCHPAD}/function_list.md (all functions)
- Source files at {PROJECT_PATH}

## Your Task

For EACH assigned combination:

### Step A: Read the Code
Read the actual source files at both/all finding locations. Understand the full function context, not just the snippet from the finding.

### Step B: Trace the Compound Path
1. Can Finding A's postcondition enable or worsen Finding B's impact? And vice versa?
2. What is the COMBINED effect that neither produces alone?
3. Is there a concrete sequence of transactions an attacker can execute?
4. What is the combined impact? Quantify where possible (fund loss, DoS duration, manipulation range).

### Step C: Assess Compound Severity
Use the standard severity matrix (Impact × Likelihood):
- The COMBINED impact determines the Impact axis (not the individual findings' impacts)
- The attack sequence complexity determines the Likelihood axis
- Compound severity MUST be strictly HIGHER than the highest individual finding's severity
  (otherwise there is no escalation and the combination is not worth reporting)

### Step D: Verdict
- **ESCALATED**: Compound exploit is feasible AND combined severity > max(individual severities). Produce a full finding.
- **MARGINAL**: Interaction exists but combined severity does not exceed individual severities. Skip.
- **NO_INTERACTION**: Findings do not meaningfully combine despite the shared state link. Skip.

## Output Format

Write to {SCRATCHPAD}/compound_escalation_{N}.md:

For each ESCALATED combination:

```markdown
## Compound Finding [CE-{N}-{M}]: {Title}

**Verdict**: ESCALATED
**Component Findings**: {list of Low/Info finding IDs being combined}
**Compound Severity**: {Medium / High / Critical}
**Individual Severities**: {list, e.g., Low + Low + Info}
**Location**: {all affected locations}

**Combined Attack Sequence**:
1. [Step 1]: {specific function call, actor, parameters}
2. [Step 2]: {what state this creates — linking to Finding A}
3. [Step 3]: {how Finding B exploits this state}
4. [Impact]: {combined effect with quantification}

**Why This Exceeds Individual Severity**:
{2-3 sentences explaining why the combination is worse than either finding alone}

**Preconditions**:
- {condition 1}
- {condition 2}

**Evidence**: {code references — file:line for each step}
```

For combinations that do NOT escalate, write a 1-line summary:
```markdown
## {Finding A} + {Finding B}: NO_INTERACTION — {brief reason}
```

## Rules

1. **Concrete sequences only**: Every ESCALATED finding must have a step-by-step attack with specific function calls. "These could interact" is not sufficient.
2. **Severity must increase**: If combining two Lows still yields a Low, it is NOT an escalation. Skip it.
3. **Read the code**: Do not hypothesize from finding descriptions alone. Read the actual functions.
4. **Existing protections**: Check if other code already guards against the compound path. If a require/assert blocks the combined attack, it is NO_INTERACTION.
5. **No duplicates**: If a compound path is already captured by an existing Medium+ hypothesis in hypotheses.md, note the overlap and skip.

SCOPE: Write ONLY to your assigned output file. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases. Return your findings and stop.

Return: 'DONE: {E} escalated from {T} combinations ({S} skipped, {N} no interaction)'
")
```

---

## Step 4: Collect Escalated Findings (Orchestrator Inline)

After all agents return:

1. Read each `compound_escalation_*.md`
2. Collect all ESCALATED findings
3. **Dedup**: If two agents produced escalations involving overlapping finding sets with the same root cause → keep the one with higher compound severity or stronger evidence
4. **Overlap check**: For each escalation, grep `hypotheses.md` for the same locations. If an existing Medium+ hypothesis already covers this compound path → discard as duplicate
5. Count: Let `E` = surviving escalated findings

If `E == 0` → log `"Phase 5.7: 0 escalations survived dedup. Proceeding to Phase 6."` and skip Steps 5-7.

If `E > 0` → proceed to verification.

---

## Step 5: Verify Escalated Findings

Add escalated findings to `{SCRATCHPAD}/hypotheses.md` with IDs `CE-{N}` and their compound severity.

Spawn verification agents using the SAME Phase 5 verification template (`{NEXTUP_HOME}/prompts/{LANGUAGE}/phase5-verification-prompt.md`):

```
For each escalated finding:
  Task(subagent_type="security-verifier", model="sonnet", prompt="
  Verify hypothesis: CE-{N}

  Location: {LOCATIONS}
  Claim: {Combined attack sequence as IF/THEN/BECAUSE}
  Test type: Compound exploit — test the FULL multi-step sequence, not individual findings.

  Read:
  - {SCRATCHPAD}/design_context.md
  - {NEXTUP_HOME}/agents/skills/{LANGUAGE}/verification-protocol/SKILL.md
  - {NEXTUP_HOME}/rules/phase5-poc-execution.md

  ## COMPOUND-SPECIFIC INSTRUCTIONS

  This is a COMPOUND finding combining {K} individually-Low/Info findings into a higher-severity exploit.
  Your PoC MUST:
  1. Execute the FULL attack sequence — all steps from the compound finding
  2. Assert the COMBINED impact, not just individual steps
  3. Demonstrate that the compound impact exceeds what either finding produces alone
  4. If any step in the sequence is blocked by existing protections, the compound is FALSE_POSITIVE

  A compound finding that only works because of a single step (making the other findings irrelevant)
  should be downgraded to a standalone finding at its original severity, not confirmed as a compound.

  ## PRECISION MODE
  {standard precision mode from Phase 5 template}

  ## DUAL-PERSPECTIVE VERIFICATION (MANDATORY)
  {standard dual-perspective from Phase 5 template}

  ## MANDATORY PoC EXECUTION
  {standard PoC execution rules from phase5-poc-execution.md}

  Write to {SCRATCHPAD}/verify_CE_{N}.md
  ")
```

### Verification Outcomes

| Result | Action |
|--------|--------|
| **CONFIRMED** at compound severity | Keep as-is in hypotheses.md |
| **CONFIRMED** but at lower severity than compound claim | Downgrade. If downgraded to Low/Info → discard (no net escalation) |
| **CONTESTED** | Keep at compound severity with CONTESTED tag |
| **FALSE_POSITIVE** | Remove from hypotheses.md |
| **Single-step only** (compound is redundant) | Convert to standalone finding at original severity if not already covered |

---

## Step 6: Skeptic-Judge for Escalated HIGH/CRIT (Thorough Only)

If `MODE == thorough` AND any escalated finding was CONFIRMED at HIGH or CRITICAL:

Apply the same Phase 5.1 Skeptic-Judge protocol from `{NEXTUP_HOME}/prompts/{LANGUAGE}/phase5-verification-prompt.md`:

1. Spawn skeptic agent (opus) with INVERSION MANDATE for each HIGH/CRIT compound
2. Skeptic tries to disprove the compound path specifically — are all steps actually chainable? Does the combined state actually enable the claimed impact?
3. If skeptic disagrees → sonnet judge adjudicates
4. Apply final verdict

---

## Step 7: Merge Survivors (Orchestrator Inline)

For each escalated finding that survived verification (and Skeptic-Judge if applicable):

1. Ensure it has a proper entry in `{SCRATCHPAD}/hypotheses.md`
2. Add to `{SCRATCHPAD}/chain_hypotheses.md` — compound escalations are structurally similar to chain findings (multiple bugs combining)
3. Update `{SCRATCHPAD}/findings_inventory.md` with the new compound findings
4. Tag each with `[COMPOUND-ESCALATION]` so the report writer can note the origin

Log summary:
```
Phase 5.7 Complete:
  Low/Info findings analyzed: {N}
  Combinations tested: {C}
  Escalations proposed: {P}
  Escalations confirmed: {E}
  Final: {H} High, {M} Medium (from {N_low} Low + {N_info} Info inputs)
```

---

## Mode Behavior

| Mode | Phase 5.7 Behavior |
|------|-------------------|
| **Light** | Pairs only (no triples). 2 sonnet agents. Verify Medium+ escalations only. No Skeptic-Judge. |
| **Core** | Pairs + triples. 2-4 opus agents. Verify Medium+ escalations. No Skeptic-Judge. |
| **Thorough** | Pairs + triples. 3-5 opus agents. Verify ALL escalations. Skeptic-Judge for HIGH/CRIT. |

---

## Budget Impact

| Component | Cost | Model |
|-----------|------|-------|
| Finding collection + assignment | 0 (orchestrator inline) | - |
| Combination agents | 2-5 | opus (Core/Thorough), sonnet (Light) |
| Verification (per escalation) | 1 per finding | sonnet (Medium) / opus (High+) |
| Skeptic-Judge (Thorough, High+) | 1-2 per finding | opus + sonnet |
| **Typical total** | **3-10 agents** | |

If zero findings escalate (common for well-audited codebases), cost is just the 2-5 combination agents.
