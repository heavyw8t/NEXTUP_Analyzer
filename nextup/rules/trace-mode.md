# Trace Mode: Post-Hoc Finding Lifecycle Reconstruction

This file is read by the orchestrator only when `TRACE_MODE == true`. When trace mode is disabled, this file is never opened and nothing in this document runs. The feature adds zero tokens and zero agent spawns to the pipeline when off.

## Invocation Contract

The orchestrator invokes trace reconstruction exactly once, after Phase 6 (the Report Assembler) completes and `{PROJECT_ROOT}/AUDIT_REPORT.md` has been written. The orchestrator passes:

- `{SCRATCHPAD}`: absolute path to the run's scratchpad directory.
- `{PROJECT_ROOT}`: absolute path to the audited project (where `AUDIT_REPORT.md` lives).
- `{MODE}`: `light`, `core`, or `thorough`.
- `{NEXTUP_MODE}`: `lightweight`, `middleweight`, or `heavyw8t`.

## Agent Spawn

Spawn ONE agent. Model: `haiku`. Subagent type: `general-purpose` (required for Write tool per CLAUDE.md rule). Use the prompt template below verbatim, substituting placeholders.

```
Task(subagent_type="general-purpose", model="haiku", prompt="
You are the Trace Reconstruction Agent for NEXTUP. The audit has already finished and AUDIT_REPORT.md has been written. Your job is to reconstruct the full lifecycle of every finding from the scratchpad files that already exist, then write a single trace document.

You do NOT analyze code. You do NOT produce new findings. You only read existing scratchpad files, stitch their contents into a lifecycle narrative per finding, and emit a summary.

## Inputs

Run context:
- SCRATCHPAD: {SCRATCHPAD}
- PROJECT_ROOT: {PROJECT_ROOT}
- MODE: {MODE}
- NEXTUP_MODE: {NEXTUP_MODE}

## Files to Read (in this order)

For each file listed, if it does not exist, note `[phase not run in {MODE} mode]` in the corresponding section of the trace and continue. Do NOT fail the run because a file is missing.

1. Origin provenance
   - Every file matching `{SCRATCHPAD}/agent_*_findings.md`. The filename tells you which agent surfaced the finding. The `Source:` field inside each finding (if present) tells you which earlier finding triggered it.
   - `{SCRATCHPAD}/findings_inventory.md`: consolidated breadth table with explicit agent attribution. This is the authoritative map from a finding ID (e.g. `[BREADTH-3]`, `[TF-1]`, `[SE-2]`) to the agent that produced it.

2. Stage transitions
   - `{SCRATCHPAD}/hypotheses.md`: master hypothesis table. Findings here carry final-state tags: `[FINAL-DOWNGRADE]`, `[FINAL-INVALIDATED]`, `[INDIVIDUAL-ESCALATION]`, `[CONTESTED]`. The hypothesis ID (`[H-N]`) is the stable spine.
   - `{SCRATCHPAD}/chain_hypotheses.md`: chain analysis merges and chain-driven severity upgrades.
   - Every file matching `{SCRATCHPAD}/verify_*.md` and `{SCRATCHPAD}/verify_batch*.md`: per-hypothesis verification verdicts (CONFIRMED / PARTIAL / REFUTED / CONTESTED), evidence tag, and PoC path if any.
   - `{SCRATCHPAD}/verification_summary.md`: consolidated verdict list (if present).
   - Every file matching `{SCRATCHPAD}/escalation_verify_*.md`: Phase 5.6 individual escalations.
   - `{SCRATCHPAD}/skeptic_judge_verdicts.md`: Phase 5.1 upgrades/downgrades with reasons (Thorough mode only).

3. Final disposition
   - `{SCRATCHPAD}/report_index.md`: internal-hypothesis-ID to report-ID mapping AND the excluded-findings block with exclusion reasons.
   - `{PROJECT_ROOT}/AUDIT_REPORT.md`: cross-check final severities and confirm which report IDs actually appear.

4. Agent-surfaced issues
   - `{SCRATCHPAD}/trace_issues.md` (may not exist if no agent hit an issue). Each line is one issue in the format `[ISO-timestamp] [agent-name] [severity] message | fallback: ... | impact: ...`. Parse every line. Group by severity (error / warn / info) and by agent.

Do NOT read source code, test files, or anything outside `{SCRATCHPAD}` and `{PROJECT_ROOT}/AUDIT_REPORT.md`.

## Reconstruction Method

For each finding the audit ever considered (union of IDs across all files above):

1. ORIGIN: identify the earliest file that mentions the ID. Record the agent (from filename plus any Source: field), the phase (breadth / depth / chain / scanner), and the initial severity claimed there.

2. EVOLUTION: in chronological pipeline order (breadth, inventory, depth, chain, verification, skeptic-judge, final-validation), list every event that changed the finding's severity, verdict, or identity. For each event record:
   - Which agent/phase produced the change (inferred from the file it came from: `verify_*.md` to verifier, `chain_hypotheses.md` to chain agent, `skeptic_judge_verdicts.md` to skeptic-judge, etc.).
   - What changed (severity, verdict, merged-into-[H-N]).
   - The reason, quoted verbatim from the source file when a reason is present. If the source file gives no reason, write `Reason: (not recorded in scratchpad)`.

3. RESOLUTION: final fate, one of:
   - IN REPORT as `{report-id}` with severity `{severity}`.
   - DOWNGRADED BELOW REPORT THRESHOLD (reason from hypotheses.md tag or final-validation verdict).
   - REFUTED / INVALIDATED (reason from verifier or final-validation).
   - EXCLUDED AS DUPLICATE OF `{other-id}` (reason from report_index.md exclusion block).
   - UNKNOWN FATE: the ID appears in early scratchpad files but no mapping to a final disposition exists. This is itself a useful signal; emit it rather than silently dropping the finding.

## Output File

Write to `{PROJECT_ROOT}/AUDIT_TRACE.md` using this structure:

```markdown
# NEXTUP Audit Trace

- Project: {PROJECT_ROOT}
- Audit mode: {MODE}
- NEXTUP depth: {NEXTUP_MODE}
- Generated: {ISO timestamp}

## Summary

- Total ideas surfaced: N
- Reached report: K (C critical, H high, M medium, L low, I informational)
- Eliminated: E (refuted R, downgraded D, deduplicated X)
- Unknown fate: U
- Agent-surfaced issues: X errors, Y warnings, Z info (from trace_issues.md)

## Agent-Reported Issues

This section comes FIRST in the trace (before per-finding lifecycle) so any real problems are visible immediately. If `{SCRATCHPAD}/trace_issues.md` does not exist, write `No agent surfaced any issue during this run.` and skip the tables.

### Errors (severity: error)

| Time | Agent | Message | Fallback | Impact |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Warnings (severity: warn)

| Time | Agent | Message | Fallback | Impact |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Informational (severity: info)

| Time | Agent | Message |
|---|---|---|
| ... | ... | ... |

### Issues grouped by agent

For each agent that surfaced at least one issue, a one-line summary: `agent-name: X errors, Y warnings, Z info`. Helps the user see which agents are hitting problems repeatedly.

### Top origin agents (ideas surfaced)

| Agent | Ideas | Reached report | Refuted | Downgraded |
|---|---|---|---|---|
| ...   | ...   | ...            | ...     | ...        |

### Top elimination reasons

| Reason | Count |
|---|---|
| ...    | ...   |

## Findings: In Report

### {report-id}: {title}
- ORIGIN: agent `{agent}` in phase `{phase}`, initial severity `{sev}`
- EVOLUTION:
  - [phase] `{agent}`: {what changed}. Reason: {verbatim reason, or 'not recorded'}
  - ...
- RESOLUTION: IN REPORT as `{report-id}`, final severity `{sev}`

(one block per finding, ordered by severity desc)

## Findings: Downgraded Below Report Threshold

(same block shape, grouped by final fate)

## Findings: Refuted / Invalidated

## Findings: Excluded As Duplicate

## Findings: Unknown Fate

(each entry here is a provenance break; include which file first mentioned the ID and the last file that did)
```

Keep each per-finding block to at most 15 lines. Do NOT copy code snippets, proofs of concept, or long verbatim finding descriptions. The report already holds those. Reasons may be quoted but should be trimmed to a single sentence when longer.

## Return Contract

Return exactly this line (substituting counts), nothing else:

`DONE: AUDIT_TRACE.md written - {N} findings tracked, {K} reached report, {E} eliminated, {U} unknown fate.`

SCOPE: Write ONLY to `{PROJECT_ROOT}/AUDIT_TRACE.md`. Do NOT modify any scratchpad file. Do NOT modify `AUDIT_REPORT.md`. Do NOT proceed to any subsequent pipeline phase. Return your one-line summary and stop.
")
```

## Orchestrator Post-Step

After the trace agent returns, print to the user:

```
Audit complete.
  Report: {PROJECT_ROOT}/AUDIT_REPORT.md
  Trace:  {PROJECT_ROOT}/AUDIT_TRACE.md
  {summary line returned by the trace agent}
```

If the agent's summary line reports any errors or warnings, also print one extra line: `Agent-surfaced issues detected. See the "Agent-Reported Issues" section at the top of AUDIT_TRACE.md.`

Do not spawn any further agents. Do not modify any scratchpad file. Trace reconstruction is terminal.

## Agent Error Surfacing Directive

This section holds the text the orchestrator appends to every agent prompt when `TRACE_MODE == true`. When trace mode is off, this text is never loaded and never appended. It is the mechanism that makes agent-level silent failures visible.

The orchestrator's rule: for every `Task(...)` call it spawns during the audit (recon, breadth, depth, scanner, chain, verifier, skeptic-judge, report tier writers, assembler, and NEXTUP seeder/combinator agents), append the block below verbatim at the end of the `prompt` field, after any existing SCOPE directive. Substitute `{SCRATCHPAD}` with the run's scratchpad path.

```
## Trace Mode: Error Surfacing (appended by orchestrator; do not remove)

This audit is running with TRACE_MODE = true. If you encounter any non-fatal issue while doing your work, surface it by appending ONE line to {SCRATCHPAD}/trace_issues.md using Bash, then CONTINUE your task.

Append command (atomic single-line append):

  bash: echo "[$(date -Iseconds)] [<your-agent-name>] [<severity>] <what happened> | fallback: <what you did instead> | impact: <effect on your output>" >> "{SCRATCHPAD}/trace_issues.md"

<severity> is one of: info, warn, error.

Log when:
- An expected input file is missing.
- A tool, MCP call, or script exits non-zero, times out, or returns unusable output.
- A feature that is documented to work does not work as described and you had to work around it.
- A fallback path was used instead of the primary path.
- You received inputs that contradict documentation and you had to pick an interpretation.

Do NOT log when:
- A file is genuinely optional and its absence is the expected path.
- You simply chose between several valid approaches.
- Your task completed normally with no deviation.

Rules:
1. Log the issue FIRST, then continue. Do not revert your work, do not early-return, do not skip subsequent steps unless your task is genuinely impossible.
2. Your normal output file is still the primary deliverable. This error surfacing is additive to your SCOPE, not a replacement for it. Writing to trace_issues.md is an explicit exception to the "write only to your assigned output file" rule.
3. If your task is genuinely impossible (all fallbacks failed), log one final `[error]` line explaining the total failure and what you produced partially. Then return whatever partial output you have with a clear note at the top that it is incomplete. Do not refuse. Do not return empty.
4. Keep each line under 500 characters. If more detail is useful, write a companion note into your normal output file and reference it from the issue line.
5. Use your canonical agent name (the name under which you were spawned, e.g. `depth-token-flow`, `verifier-h3`, `chain-agent-1`). If unsure, use your subagent role plus a short disambiguator.
```

## Final Reconstructor Extension

When reading `{SCRATCHPAD}/trace_issues.md`, the trace-reconstructor agent must also:
- If more than 5 errors of the same message-prefix come from the same agent, collapse them into a single row with a `(N occurrences)` suffix and list the first and last timestamps.
- If an agent appears in trace_issues.md but produced no output file in scratchpad, flag it explicitly in the "Issues grouped by agent" summary as `agent-name: FAILED TO PRODUCE OUTPUT`.

This extension is part of the haiku agent's workload and adds no extra spawns.

