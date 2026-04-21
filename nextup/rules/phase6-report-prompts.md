# Phase 6: Report Generation Prompt Templates

> **Usage**: Orchestrator reads this file and spawns the report pipeline: Index → 3 Tier Writers → Final Dedup Sweep → Assembler.
> Replace placeholders `{SCRATCHPAD}`, `{PROJECT_ROOT}`, `{PASTE_VERDICTS}`, `{REPORT_PRIMER}`, `{REPORT_OUTPUT}`, etc. with actual values.

> **Architecture**: Index Agent → 3 Parallel Tier Writers → Final Dedup Sweep → Assembler Agent
> **Why**: A single report agent gets overwhelmed on 30+ hypotheses, producing catch-all tables and invisible findings. Splitting by severity tier ensures every finding gets a proper write-up. The Final Dedup Sweep catches duplicates introduced by chain analysis, verification observation extraction, and Low-escalation paths that bypass Phase 4a inventory dedup.

> **PRIMER + OUTPUT FOLDER (mandatory, set by wizard Step 0c.7)**:
>
> - `REPORT_PRIMER` selects the report format. Valid values: `default` (single monolithic `AUDIT_REPORT.md`), `sherlock` (one file per finding: `C-01.md`, `H-01.md`, `M-01.md`, `L-01.md`, `I-01.md`, plus `SUMMARY.md` index). Additional primers live at `{NEXTUP_HOME}/primers/{name}.md`.
> - `REPORT_OUTPUT` is the destination. For `default`, this is a full file path ending in `AUDIT_REPORT.md`. For `sherlock` and other per-finding primers, this is a directory path that will contain the per-finding files plus `SUMMARY.md`.
> - EVERY agent below MUST read `{NEXTUP_HOME}/primers/{REPORT_PRIMER}.md` (or handle the `default` case inline for monolithic) BEFORE writing output, and emit the correct filename convention. The tier writers produce one file per finding when the primer is per-finding; they append to a single scratchpad file when the primer is monolithic; the assembler merges scratchpad files into the final deliverable.
> - If `REPORT_PRIMER` is unset, treat it as `default` and warn the orchestrator that the wizard did not collect the primer (this is the pre-fix fallback behavior, preserved for backward compatibility). If `REPORT_OUTPUT` is unset, default to `{PROJECT_ROOT}/AUDIT_REPORT.md` (monolithic) or `{PROJECT_ROOT}/audit/` (per-finding).

---

## Step 6a: Index Agent

> **Model**: sonnet (mechanical task, but haiku truncated on prior runs; sonnet is the minimum-safe floor for consolidation and ID assignment)
> **Purpose**: Creates master index mapping internal hypothesis IDs to clean report IDs. Assigns each hypothesis to exactly one tier.

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the Report Index Agent. You create the master finding index for the audit report.

## Your Inputs
Read:
- {SCRATCHPAD}/hypotheses.md (all grouped hypotheses with final severities)
- {SCRATCHPAD}/chain_hypotheses.md (chain hypotheses with severity upgrades)
- {SCRATCHPAD}/finding_mapping.md (hypothesis → agent finding mapping)
- {SCRATCHPAD}/contract_inventory.md (component list for report header)
- {SCRATCHPAD}/findings_inventory.md (complete agent finding inventory)

Verification verdicts from orchestrator:
{PASTE_VERDICTS}

## Your Task

### STEP 1: Determine Final Severities

For each hypothesis, apply this priority order:
1. If a verifier returned a verdict → use verifier's final severity
2. If chain analysis upgraded severity → use upgraded severity
3. Otherwise → use the severity from hypotheses.md
4. **Apply trust assumption downgrades**: Check {SCRATCHPAD}/findings_inventory.md for `[ASSUMPTION-DEP: TRUSTED-ACTOR]` tags. For tagged findings, apply −1 tier severity downgrade (floor: Informational). Note the original severity and downgrade reason in the Master Finding Index under a "Trust Adj." column. For `[ASSUMPTION-DEP: WITHIN-BOUNDS]` tags: do NOT change severity, but note the flag in the index for tier writers to include as context. **Mechanical enforcement**: The Index Agent MUST NOT override, remove, or selectively skip Inventory Agent tags. If a finding has the `TRUSTED-ACTOR` tag, apply the downgrade. If it does not have the tag, do not downgrade. No exceptions for chain upgrades, verification results, or analytical reasoning - the Inventory Agent is the sole authority on trust tagging.
5. **Proven-only demotion** (if `PROVEN_ONLY = true`): For each finding whose BEST evidence tag is `[CODE-TRACE]` (no `[POC-PASS]`, `[MEDUSA-PASS]`, `[PROD-ONCHAIN]`, `[PROD-SOURCE]`, or `[PROD-FORK]`), cap severity at Low. Record the original severity in the "Trust Adj." column as `PROVEN(original_sev)`. Count total demotions for the report header note: *"Proven-only mode enabled: {N} findings capped at Low from {severities} due to unproven evidence ([CODE-TRACE] only)."*

### STEP 1.5: Root-Cause Consolidation (MANDATORY)

Before assigning report IDs, consolidate hypotheses that share the same root cause into single report findings. This prevents inflated finding counts from pipeline fragmentation.

**Consolidation test** - merge two hypotheses into ONE report finding if ALL of these are true:
1. **Same fix pattern**: Both require the same TYPE of code change (e.g., both need "add zero-value validation to admin setter", both need "emit event on state change")
2. **Same severity tier**: Both are in the same tier after STEP 1 adjustments
3. **Same vulnerability class**: Both are instances of the same bug pattern (e.g., "missing event", "missing input validation", "no staleness check")
4. **Describable together**: A reader can understand all affected locations from a single description + location table

**Do NOT merge if**:
- Findings are in different severity tiers (a Medium and a Low stay separate even if same class)
- The root causes are genuinely different (e.g., "missing event" vs "wrong event parameters" - different fixes)
- Merging would exceed 6 locations per finding (split into 2 findings for readability)

**Common consolidation patterns**:
| Pattern | Example Hypotheses | Consolidated Title |
|---------|-------------------|-------------------|
| Missing events on state changes | "setX no event" + "setY no event" + "setZ no event" | "Missing event emission on admin state changes" |
| Admin setters accept zero/invalid | "paramA accepts zero" + "paramB accepts zero" | "Admin setters lack zero-value validation" |
| Missing staleness checks | "no staleness on X" + "no max staleness on Y" | "Rate provider staleness not validated" |
| Retroactive parameter changes | "paramA retroactive" + "paramB retroactive" | "Global parameter changes retroactively affect pending state" |
| Same-role trust findings | "ROLE can do X" + "ROLE can do Y" (same role, same trust level) | "ROLE capabilities exceed stated trust level" |

**Output**: For each consolidation, record:
```
CONSOLIDATED: H-{A} + H-{B} [+ H-{C}...] → single finding
  Title: {consolidated title}
  Locations: {list all affected locations}
  Severity: {shared severity}
  Internal refs: {all absorbed hypothesis IDs}
```

Hypotheses NOT consolidated remain as standalone findings.

### STEP 2: Assign Report IDs

Sort all findings (consolidated and standalone) by severity tier, then by verification status (VERIFIED first), then by impact.

Assign clean sequential IDs:
- Critical: C-01, C-02, ...
- High: H-01, H-02, ...
- Medium: M-01, M-02, ...
- Low: L-01, L-02, ...
- Informational: I-01, I-02, ...

### STEP 3: Create Tier Assignments

Assign each finding to exactly ONE tier writer:
- **Critical+High Tier**: All C-XX and H-XX findings
- **Medium Tier**: All M-XX findings
- **Low+Info Tier**: All L-XX and I-XX findings

### STEP 4: Create Cross-Reference Map

For chain findings that reference component findings, note the cross-references using REPORT IDs only.
Example: If chain hypothesis CH-1 (now C-01) references standalone hypothesis H-5 (now H-03), record: 'C-01 references H-03'

### STEP 5: Verify Completeness (MANDATORY)

Cross-check: For EVERY hypothesis in hypotheses.md AND every standalone finding
([VS-*], [BLIND-*], [SE-*], [EN-*], [SLITHER-*]) in findings_inventory.md:
- Is it assigned a report ID in the Master Finding Index above?
- If NO and NOT marked FALSE_POSITIVE by a verifier → ASSIGN a report ID and tier

**HARD RULE**: The ONLY valid exclusion reason is an explicit FALSE_POSITIVE verdict
from a Phase 5 verifier OR an explicit duplicate already listed (cite the absorbing
report ID). "Not grouped into a hypothesis" is NOT a valid exclusion reason.

### Excluded Findings (for Appendix A)
| Internal ID | Severity | Title | Exclusion Reason (FALSE_POSITIVE or DUPLICATE OF X-NN only) |

## Output

Write to {SCRATCHPAD}/report_index.md:

```markdown
# Report Index

## Report Header Info
- Project Name: {from design_context.md}
- Date: {today}
- Contracts: {from contract_inventory.md}
- Build Status: {from build_status.md}

## Summary Counts
| Severity | Count |
|----------|-------|
| Critical | {N} |
| High | {N} |
| Medium | {N} |
| Low | {N} |
| Informational | {N} |

## Master Finding Index

| Report ID | Title | Severity | Location | Verification | Trust Adj. | Internal Hypothesis | Agent Sources |
|-----------|-------|----------|----------|--------------|-----------|--------------------|--------------|
| C-01 | [title] | Critical | [location] | VERIFIED | - | [internal ref] | [agents] |
| H-01 | [title] | High | [location] | VERIFIED | - | [internal ref] | [agents] |
| M-01 | [title] | Medium↓H | [location] | UNVERIFIED | TRUSTED-ACTOR | [internal ref] | [agents] |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Tier Assignments

### Critical+High Tier (for Opus writer)
[List of report IDs with their internal hypothesis refs and verification file paths]

### Medium Tier (for Sonnet writer)
[List of report IDs with their internal hypothesis refs]

### Low+Info Tier (for Sonnet writer)
[List of report IDs with their internal hypothesis refs]

## Consolidation Map
| Report ID | Consolidated From | Consolidation Reason |
|-----------|------------------|---------------------|
| L-03 | H-39, H-40, H-55 | Same fix pattern: add zero-value validation to admin setters |
| L-08 | H-70, H-71 | Same fix pattern: add event emission to admin state changes |

## Cross-Reference Map
| Report ID | References | Context |
|-----------|-----------|---------|
| C-01 | H-03, M-05 | Chain: C-01 combines the bugs described in H-03 and M-05 |

## Excluded Findings (for Appendix A)
| Internal ID | Severity | Title | Exclusion Reason (FALSE_POSITIVE or DUPLICATE OF X-NN only) |
```

Return: 'DONE: {N_total} findings indexed ({N_consolidated} consolidated from {N_original} hypotheses) - {C} Critical, {H} High, {M} Medium, {L} Low, {I} Info'
")
```

---

### Step 6a.1: Completeness Verification (Orchestrator Inline)

After Index Agent returns, orchestrator performs:
1. Count hypothesis IDs in `{SCRATCHPAD}/hypotheses.md` (grep for `| H-`)
2. Count report IDs in `{SCRATCHPAD}/report_index.md` Master Finding Index
3. Count excluded IDs in `{SCRATCHPAD}/report_index.md` Excluded Findings
4. Count consolidated IDs (hypotheses absorbed into another report finding via STEP 1.5)
5. **ASSERT**: `hypothesis_count == report_ids + excluded_count + consolidated_absorbed_count`
6. If **MISMATCH**:
   - Diff ID sets to find missing hypotheses
   - Log: `"INDEX COMPLETENESS FAILURE: {missing_list}"`
   - Re-spawn Index Agent with: `"Assign report IDs to these missing hypotheses: {list}"`
   - Re-run this verification after re-spawn

> **This is a mechanical check - the orchestrator does it inline, no new agent needed.**

---

## Step 6b: Tier Writers (3 Parallel Agents)

> **Spawn ALL THREE in a single message as parallel Task calls.**
> Each tier writer receives ONLY its assigned findings from report_index.md.

### Tier Writer Common Rules (referenced by all 3 writers)

All tier writers MUST follow these rules:
1. **NO internal IDs** (hypothesis IDs, chain IDs, agent IDs) anywhere in output
2. **Every finding gets its own ### section** - no tables, no groups, no summaries, no catch-all dumps
3. **Write as if the reader has never seen the audit pipeline** - no references to breadth agents, chain analysis, etc.
4. **Cross-references use report IDs only** - include finding title in parentheses for context: `see H-03 (example title)`
5. **Trust assumption context**: If report_index.md marks a finding with `TRUSTED-ACTOR` in the Trust Adj. column, include after Severity: *"Severity adjusted from {original} - attack requires {actor} to violate stated trust assumption: {assumption}."* For `WITHIN-BOUNDS` flags: include a note in Description that the impact falls within the protocol's stated operational bounds for the semi-trusted actor. Do NOT change the severity for WITHIN-BOUNDS - flag only.

### Critical+High Tier Writer

> **Model**: opus (highest quality for most important findings)

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are the Critical+High Findings Writer. You write the Critical and High severity sections of the audit report.

## Your Inputs
Read:
- {SCRATCHPAD}/report_index.md (your tier assignments under 'Critical+High Tier')
- {SCRATCHPAD}/hypotheses.md (detailed hypothesis descriptions)
- {SCRATCHPAD}/chain_hypotheses.md (chain attack sequences)
- {SCRATCHPAD}/verify_*.md (verification results with PoC details)
- {SCRATCHPAD}/synthesis_full.md (full analysis context)
- {NEXTUP_HOME}/rules/report-template.md (finding format and rules)

## Your Task

For EACH finding assigned to your tier in report_index.md:

1. Write a full finding section using the EXACT format from report-template.md
2. Use the report ID from report_index.md (C-01, H-01, etc.) - NEVER use internal pipeline IDs
3. Include code snippets from the actual source files
4. For chain findings: describe the COMPLETE attack sequence in the Description - the reader should understand the full attack without reading other findings
5. For verified findings: include PoC results from verify_*.md
6. Cross-reference other findings using ONLY report IDs from report_index.md

## HARD RULES
Follow ALL Tier Writer Common Rules above (no internal IDs, own ### per finding, reader-naive perspective, report-ID cross-refs with title).

## Output

Write to {SCRATCHPAD}/report_critical_high.md:

```markdown
## Critical Findings

### [C-01] Title [VERIFIED]
[full section]

...

## High Findings

### [H-01] Title [VERIFIED/UNVERIFIED/CONTESTED]
[full section]

...
```

Return: 'DONE: {C} Critical + {H} High findings written'
")
```

### Medium Tier Writer

> **Model**: sonnet (good quality, cost-effective for medium tier)

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the Medium Findings Writer. You write the Medium severity section of the audit report.

## Your Inputs
Read:
- {SCRATCHPAD}/report_index.md (your tier assignments under 'Medium Tier')
- {SCRATCHPAD}/hypotheses.md (detailed hypothesis descriptions)
- {SCRATCHPAD}/chain_hypotheses.md (if any medium chains)
- {SCRATCHPAD}/synthesis_full.md (full analysis context)
- {SCRATCHPAD}/findings_inventory.md (agent finding details)
- {NEXTUP_HOME}/rules/report-template.md (finding format and rules)

For each finding, also read the relevant analysis_*.md file(s) listed in the agent sources.

## Your Task

For EACH finding assigned to your tier in report_index.md:

1. Write a full finding section using the EXACT format from report-template.md
2. Use the report ID from report_index.md (M-01, M-02, etc.) - NEVER use internal pipeline IDs
3. Include code snippets from the actual source files
4. Include a clear Recommendation with fix guidance

## HARD RULES
Follow ALL Tier Writer Common Rules above. Additionally: do NOT create catch-all sections - every finding is equally important.

## Output

Write to {SCRATCHPAD}/report_medium.md:

```markdown
## Medium Findings

### [M-01] Title [UNVERIFIED]
[full section]

### [M-02] Title [UNVERIFIED]
[full section]

...
```

Return: 'DONE: {M} Medium findings written'
")
```

### Low+Informational Tier Writer

> **Model**: sonnet (good quality, cost-effective for lower tiers)

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the Low+Informational Findings Writer. You write the Low and Informational severity sections of the audit report.

## Your Inputs
Read:
- {SCRATCHPAD}/report_index.md (your tier assignments under 'Low+Info Tier')
- {SCRATCHPAD}/hypotheses.md (detailed hypothesis descriptions)
- {SCRATCHPAD}/synthesis_full.md (full analysis context)
- {SCRATCHPAD}/findings_inventory.md (agent finding details)
- {NEXTUP_HOME}/rules/report-template.md (finding format and rules)

For each finding, also read the relevant analysis_*.md file(s) listed in the agent sources.

## Your Task

For EACH finding assigned to your tier in report_index.md:

1. Write a full finding section using the EXACT format from report-template.md
2. Use the report ID from report_index.md (L-01, I-01, etc.) - NEVER use internal pipeline IDs
3. Include code snippets where relevant
4. For Low findings: Recommendation field is optional but preferred
5. For Informational: PoC Result field is optional

## HARD RULES
Follow ALL Tier Writer Common Rules above. Additionally: even simple Low/Info findings deserve 3-5 sentences of Description and a clear Location.

## Output

Write to {SCRATCHPAD}/report_low_info.md:

```markdown
## Low Findings

### [L-01] Title
[full section]

### [L-02] Title
[full section]

...

## Informational Findings

### [I-01] Title
[full section]

...
```

Return: 'DONE: {L} Low + {I} Informational findings written'
")
```

---

## Step 6b.5: Final Dedup Sweep (one opus agent, unconditional, all modes)

> **Model**: opus. **Trigger**: Always, regardless of audit mode. This is a carve-out from the Light-mode all-sonnet rule.
> **Purpose**: Catch duplicate findings that escaped Phase 4a inventory dedup. Duplicates typically get re-introduced by Phase 4c chain analysis, Phase 5.5 `[VER-NEW-*]` observation extraction, Phase 5.6 individual escalation, and Phase 5.7 compound escalation.
> **Position**: Runs AFTER the three tier writers return (or after the Light-mode single writer returns). Runs BEFORE the assembler.

```
Task(subagent_type="general-purpose", model="opus", prompt="
You are the Final Dedup Sweep Agent. You remove duplicate findings from the report tier files before the assembler runs.

## Your Inputs

Read:
- {SCRATCHPAD}/report_index.md (master finding index with final severities and evidence tags)
- {SCRATCHPAD}/report_critical_high.md (Critical + High tier output)
- {SCRATCHPAD}/report_medium.md (Medium tier output)
- {SCRATCHPAD}/report_low_info.md (Low + Informational tier output)
- {SCRATCHPAD}/findings_inventory.md (root-cause context from Phase 4a)
- {SCRATCHPAD}/chain_hypotheses.md (chain findings, common source of duplicates)

Light-mode input fallback: if the three tier files do not exist, read {SCRATCHPAD}/report_writer_output.md instead (single-writer output). Apply the same dedup logic; rewrite the single file at the end.

## Your Task

### STEP 1: Enumerate all findings

Walk every finding in every tier file (or the single writer file in Light mode). For each finding, capture:
- Report ID (e.g. H-01, M-03, L-07)
- Original severity
- Root-cause one-liner (the actual bug mechanism, not the surface symptom)
- Attack path (summary)
- Locations (file:line refs)
- Evidence tag from report_index.md

### STEP 2: Identify duplicates

Two findings are duplicates when they describe the same underlying bug. Apply ALL of these checks; a duplicate must satisfy ALL to avoid over-merging:

1. Same root cause: the single sentence that explains WHY the bug exists matches (e.g. 'admin setter has no upper bound' vs 'setter allows unbounded value' is a match; 'admin setter has no upper bound' vs 'initialization missing access control' is not).
2. Same exploit mechanism: the concrete way an attacker triggers the bug is the same class (e.g. both require 'attacker calls setFee with a large value', even if one describes a particular victim and the other describes a class of victims).
3. Location overlap: at least one location (file:line anchor, or same function, or same state variable) appears in both findings. If the locations are completely disjoint the findings are likely NOT duplicates even if the mechanism rhymes.

Findings that share a symptom but have different root causes are NOT duplicates. Findings that share a root cause but hit different contracts for different reasons are NOT duplicates. When in doubt, do NOT merge.

### STEP 3: For each duplicate group, pick the survivor

Priority order (first rule that discriminates wins):

1. HIGHEST severity wins. Critical beats High beats Medium beats Low beats Informational. Severity is final severity from report_index.md (after verification, chain, and escalation adjustments).
2. On severity tie, STRONGEST evidence tag wins: `[POC-PASS]` > `[MEDUSA-PASS]` > `[PROD-FORK]` / `[PROD-ONCHAIN]` > `[POC-FAIL]` > `[CODE-TRACE]` > `[CONTESTED]`.
3. On evidence tie, MOST locations wins (a finding that enumerates more affected locations has more value for the reader).
4. On location tie, LOWEST report ID wins (e.g. H-01 beats H-02). Deterministic tiebreaker.

MERGE evidence from losers into the survivor before dropping them:
- Add loser's locations to the survivor's location list (deduplicated).
- If the loser cites attack steps the survivor does not, append them to the survivor's attack path under a 'Additional attack variants:' subheading.
- If the loser's evidence tag is stronger than the survivor's (rare, only happens when severity is higher on the survivor but evidence is stronger on the loser), upgrade the survivor's evidence tag to the loser's and note 'Evidence strengthened by merge of {loser_id}'.

### STEP 4: Rewrite tier files

For each tier file (or the Light single-writer file), write out a new version that:
- Keeps all survivors in place with merged evidence.
- Removes all losers entirely (including their full section, not just an ID reference).

Write to the SAME paths you read from:
- {SCRATCHPAD}/report_critical_high.md
- {SCRATCHPAD}/report_medium.md
- {SCRATCHPAD}/report_low_info.md
(or in Light mode, {SCRATCHPAD}/report_writer_output.md).

### STEP 5: Write dedup log

Write to {SCRATCHPAD}/final_dedup.md:

```markdown
# Phase 6b.5: Final Dedup Sweep Log

## Summary
- Findings before sweep: {N}
- Duplicate groups identified: {G}
- Findings dropped: {D}
- Findings after sweep: {N - D}

## Drop Log

| Group | Kept (ID, Severity, Evidence) | Dropped (ID, Severity, Evidence) | Reason | Locations merged? |
|-------|-------------------------------|----------------------------------|--------|-------------------|
| 1 | H-01 (High, [POC-PASS]) | M-04 (Medium, [CODE-TRACE]) | same root cause: unbounded admin setter; survivor has higher severity and stronger evidence | yes, M-04's 2 locations appended |
| ... | ... | ... | ... | ... |

## Not Deduplicated (for reviewer audit)

List any findings that LOOKED like duplicates on first read but failed the three-part test in STEP 2. One line each with the reason they are distinct.
```

The dedup log is the audit trail. The assembler reads the rewritten tier files, not this log, but the log lets a human reviewer sanity-check the merges.

## Output

Three files rewritten in place (tier files or Light single-writer file) plus {SCRATCHPAD}/final_dedup.md.

Return: 'DONE: {G} duplicate groups resolved, {D} findings dropped, {N - D} survive'

SCOPE: Write ONLY to the paths listed above. Do NOT read or modify the assembler's output, findings_inventory.md, hypotheses.md, or any pre-dedup scratchpad file. Return and stop.
")
```

---

## Step 6c: Assembler Agent

> **Model**: sonnet (always). Haiku has truncated on large reports in prior audits and on stall-prone runs; sonnet is the minimum-safe floor.
> **Purpose**: Merges the three tier sections into the final AUDIT_REPORT.md with header, summary, remediation order, and optional appendix.

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the Report Assembler. You merge the tier sections into the final audit report.

## Your Inputs
Read:
- {SCRATCHPAD}/report_index.md (header info, summary counts, cross-reference map, excluded findings)
- {SCRATCHPAD}/report_critical_high.md (Critical + High sections)
- {SCRATCHPAD}/report_medium.md (Medium section)
- {SCRATCHPAD}/report_low_info.md (Low + Informational sections)
- {NEXTUP_HOME}/rules/report-template.md (report structure template)

## Your Task

### STEP 1: Assemble Report

Combine sections in this order:
1. **Report Header** - from report_index.md header info
2. **Executive Summary** - 2-3 paragraphs summarizing the audit (write this yourself based on the findings)
3. **Summary Table** - from report_index.md counts
4. **Components Audited Table** - from report_index.md
5. **Critical Findings** - paste from report_critical_high.md (Critical section)
6. **High Findings** - paste from report_critical_high.md (High section)
7. **Medium Findings** - paste from report_medium.md
8. **Low Findings** - paste from report_low_info.md (Low section)
9. **Informational Findings** - paste from report_low_info.md (Informational section)
10. **Priority Remediation Order** - generate from report_index.md, ordered: Critical → High → Medium
11. **Appendix A: Internal Audit Traceability** - from report_index.md (Master Finding Index + Excluded Findings)

### STEP 2: Quality Checks

Before writing, verify:
1. **Finding count matches summary** - count ### sections per severity tier, must equal summary table
2. **No internal IDs in body** - scan for [CS-, [AC-, [TF-, [BLIND-, [EN-, [SE-, [VS-, [DEPTH-, [SLITHER-, CH-, and bracketed H- followed by numbers. NONE should appear outside Appendix A.
3. **Cross-references valid** - check the cross-reference map from report_index.md, ensure referenced IDs exist
4. **No duplicate findings** - no two sections describe the same bug
5. **All tier files present** - if any tier file is missing or empty, note it as 'Section pending'

If any quality check fails, fix the issue in the assembled output. Document what was fixed.

### STEP 3: Write Final Report

Write the assembled report to: `{REPORT_OUTPUT}` (path provided by the wizard; see the PRIMER + OUTPUT FOLDER block at the top of this file).

If `REPORT_PRIMER == sherlock` (or any per-finding primer): `REPORT_OUTPUT` is a directory. Do NOT emit a single monolithic file; instead, write each finding as its own file per the primer's naming convention (`C-NN.md`, `H-NN.md`, `M-NN.md`, `L-NN.md`, `I-NN.md`, plus `SUMMARY.md`). Read `{NEXTUP_HOME}/primers/{REPORT_PRIMER}.md` for the exact prose style and file structure. Create the output directory if it does not exist.

If `REPORT_PRIMER == default` (or unset): `REPORT_OUTPUT` is a full file path. Write the assembled monolithic report there.

## Output

Write to `{REPORT_OUTPUT}` per the rule above.

Also write quality check results to {SCRATCHPAD}/report_quality.md:
```markdown
# Report Quality Check
- Finding count: {matches/mismatch} - Summary says X, sections have Y
- Internal ID leak: {CLEAN/FOUND} - [list any found]
- Cross-references: {VALID/BROKEN} - [list any broken]
- Duplicates: {NONE/FOUND} - [list any found]
- Missing tiers: {NONE/list}
- Fixes applied: [list any automatic fixes]
```

Return: 'DONE: Report assembled - {N} Critical, {N} High, {N} Medium, {N} Low, {N} Info - Quality: {PASS/ISSUES}'
")
```

> **Assembler Model Selection**: Always use `model="sonnet"`. Previous guidance conditionally escalated from haiku to sonnet at 25 findings; that escalation is now unconditional because haiku truncated on mid-sized reports and a single-agent fallback stalled at 600s on a 48-finding run. The 5-agent Phase 6 pipeline (index sonnet → 3 tier writers opus/sonnet → assembler sonnet) replaces any single-agent report writer. Never substitute a single opus writer for the 5-agent pipeline, even under orchestrator time pressure; single-writer mode is the stall pattern this rule exists to prevent.
