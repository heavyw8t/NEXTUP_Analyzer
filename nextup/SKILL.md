# NEXTUP Skill: Combinatorial Puzzle-Piece Security Auditor

> **Standalone**: `/nextup [lightweight|middleweight|heavyw8t] [path]`
> **NEXTUP seeder**: Called by NEXTUP orchestrator between Phase 4a and 4b (see `nextup-integration.md`)

NEXTUP has two run modes:

| Mode | Trigger | What it does |
|------|---------|-------------|
| **Standalone** | `/nextup` or `/nextup` with args | Full pipeline: Extract → Combine → Hypothesize → Filter → Report |
| **NEXTUP Seeder** | Called by NEXTUP with `nextup-seeder` arg | Extract → Combine only. Outputs investigation targets for NEXTUP depth agents. No hypothesize/filter/report. |

---

## NON-NEGOTIABLE RULES (read these before anything else)

These rules override any later step that appears to conflict with them. If wrapper-launch args pre-fill values that would let you skip a step below, you still MUST honor the intent of the rule.

### R1 — Always ask the user for `REPORT_DIR` (Step 0c.1)
Standalone runs must execute Step 0c.1 via `AskUserQuestion`. Never default, never silently write output into the audited repo. `REPORT_DIR` must be outside `{SCOPE_PATH}` unless the user explicitly confirms otherwise. If wrapper args did not specify a directory, HALT and ask.

### R2 — Always ask the user for the primer (Step 0c.2)
Standalone runs must execute Step 0c.2 via `AskUserQuestion` (Sherlock / Custom / None). Never default to Sherlock. If wrapper args did not specify a primer choice, HALT and ask. Picking a primer based on "most common choice" is forbidden — ask.

### R3 — Never write a combined report file
Phase 6 output is one `.md` file per finding (see primer for filename convention) plus one `SUMMARY.md` index. Do not emit a monolithic `REPORT.md`, `findings.md`, or equivalent — not even as a convenience. If an upstream agent returns a single consolidated document, split it before the final write.

### R4 — Primer may never drop or downgrade a finding
The primer controls **format and prose** only. A finding that does not fit the primer's severity tiers or topical scope MUST be written as `U-NN.md` (Unclassified) with a one-sentence `**Unclassified reason:**` line at the top. Do NOT delete, silently downgrade, or merge such findings. Only Skeptic-Judge **INVALIDATED** and pre-screen **REJECTED** findings may be excluded from the output directory, and those go in the `SUMMARY.md` rejected appendix with a brief rebuttal.

### R5 — Mid-pipeline self-correction is mandatory
If you notice mid-pipeline that a non-negotiable rule was skipped, stop forward progress, ask the user for the missing input, then continue. Do not "fix forward" by guessing.

### R6 — Maintain a local CHANGELOG after every change to the nextup folder
Every rework, bugfix, or feature change inside `~/Desktop/NEXTUP SKILL/nextup/` MUST be appended to `~/Desktop/NEXTUP SKILL/CHANGELOG.md` before the session ends. Entry format: `## YYYY-MM-DD — <short title>` followed by a bullet list of what changed and why. `CHANGELOG.md` is git-ignored (personal log, never pushed). Do not skip this because a change feels small; grep-ability of the history matters more than tidiness.

### R7 — Commit and sync the nextup folder after every rework
After any change to files under `~/Desktop/NEXTUP SKILL/nextup/` (rules, prompts, primers, scripts, agents), the workflow is:
1. `git pull --rebase` (pick up any remote changes first)
2. `git add` the nextup/ paths you touched (never `git add -A` — avoid sweeping up `CHANGELOG.md` or stray repos)
3. `git commit` with a message describing the rework
4. `git push`

Do this at the end of the rework, not at the end of a long multi-step session. If the commit or push fails, surface the error to the user — do not silently retry or force-push. The `CHANGELOG.md` file must stay uncommitted (gitignored).

---

## Phase 0: Setup

### Step 0a: Parse Arguments

Parse `$ARGUMENTS`:
- If args contain `nextup-seeder` → set `RUN_MODE = seeder`. Remove `nextup-seeder` from args.
- If args contain `lightweight`, `middleweight`, or `heavyw8t` → set `NEXTUP_MODE` accordingly.
- Remaining arg as scope path. Default: current working directory.
- If `RUN_MODE != seeder` and no mode was specified in args → run interactive mode selection (Step 0a.1)

### Step 0a.1: Interactive Mode Selection (Standalone only)

If no mode was specified in args and `RUN_MODE != seeder`, present the mode picker:

```
AskUserQuestion(questions=[{
  question: "Which NEXTUP mode do you want to run?",
  header: "Mode",
  multiSelect: false,
  options: [
    {
      label: "Lightweight",
      description: "Pairs of puzzle pieces (k=2). Fast, ~2-4 hypothesis agents.",
      preview: "Combinations: C(n,2)\nTop-N sent to LLM: 50\nHypothesis agents: 2-4\nBest for: quick scan, small codebases"
    },
    {
      label: "Middleweight (Recommended)",
      description: "Triples of puzzle pieces (k=3). Balanced depth and cost.",
      preview: "Combinations: C(n,3)\nTop-N sent to LLM: 100\nHypothesis agents: 5-8\nBest for: standard audits, medium codebases"
    },
    {
      label: "Heavyw8t",
      description: "Quads of puzzle pieces (k=4). Maximum depth, finds complex multi-step interactions.",
      preview: "Combinations: C(n,4)\nTop-N sent to LLM: 150\nHypothesis agents: 8-15\nBest for: thorough audits, complex protocols"
    }
  ]
}])
```

Map selection to `NEXTUP_MODE`:
- "Lightweight" → `lightweight`
- "Middleweight (Recommended)" → `middleweight`
- "Heavyw8t" → `heavyw8t`

### Step 0a.2: Mode Configuration

| NEXTUP_MODE | k | Top-N | Hypothesis Agents |
|-------------|---|-------|-------------------|
| lightweight | 2 | 50 | 2-4 |
| middleweight | 3 | 100 | 5-8 |
| heavyw8t | 4 | 150 | 8-15 |

Default if still unset: `middleweight`

### Step 0b: Detect Language

Scan the scope path for file extensions and framework markers. Resolve `LANGUAGE` to one of `evm`, `solana`, `aptos`, `sui`, `c_cpp`:
- `.sol` → `evm` → pattern hints: `solidity_evm.md`, taxonomy: `evm.json`
- `.rs` + `Cargo.toml` with `anchor-lang` or `solana-program` (or `*.rs` containing `#[program]` / `#[derive(Accounts)]`) → `solana` → pattern hints: `solana.md`, taxonomy: `solana.json`
- `.rs` + `Cargo.toml` with `cosmwasm-std`/`grug`/`sylvia` (no Solana markers) → `solana` pipeline using CosmWasm pattern hints (historical fallback); prefer migrating such targets to a dedicated CosmWasm pipeline when one exists
- `.move` + `Move.toml` containing `aptos-framework` → `aptos` → pattern hints: `move.md`, taxonomy: `aptos.json`
- `.move` + `Move.toml` containing `Sui` → `sui` → pattern hints: `move.md`, taxonomy: `sui.json`
- `.c`/`.cpp`/`.cc`/`.h`/`.hpp` + (`CMakeLists.txt` or `Makefile`) → `c_cpp` → pattern hints: `c_cpp.md`, taxonomy: `c_cpp.json`

If `RUN_MODE == seeder`: language is already known from NEXTUP orchestrator. Read `{SCRATCHPAD}/build_status.md` for language if available.

### Step 0c: Create Scratchpad

- **Standalone**: `SCRATCHPAD = {SCOPE_PATH}/.nextup_scratchpad`
- **Seeder**: Use NEXTUP's scratchpad (passed as `{NEXTUP_SCRATCHPAD}`). NEXTUP writes to a subdirectory: `NEXTUP_DIR = {NEXTUP_SCRATCHPAD}/nextup/`

Create the directory if it doesn't exist.

### Step 0c.1: Ask User for Report Output Directory (Standalone only)

**Skip if `RUN_MODE == seeder`.**

Ask the user where to write the per-finding `.md` report files. Do NOT write into the repo under audit by default.

```
AskUserQuestion(questions=[{
  question: "Where should NEXTUP write the finding .md files? (one file per finding)",
  header: "Report output directory",
  multiSelect: false,
  options: [
    {
      label: "Default: ~/nextup-reports/{scope_basename}-{timestamp}",
      description: "Writes to your home directory, outside the audited repo.",
      preview: "Example: ~/nextup-reports/my-protocol-20260414-1530/NX-01.md"
    },
    {
      label: "Custom path",
      description: "You will be prompted for an absolute path.",
      preview: "e.g. /home/user/audits/my-protocol/findings"
    }
  ]
}])
```

If "Custom path" is chosen, follow up with a free-form `AskUserQuestion` asking for the absolute directory path. Expand `~` and resolve to an absolute path.

Set `REPORT_DIR` to the chosen path. Create it (and any parents) if missing. If the directory already exists and is non-empty, ask the user whether to append (keep existing files) or use a new timestamped subdirectory. Never delete existing files.

**IMPORTANT**: `REPORT_DIR` MUST NOT be inside `{SCOPE_PATH}` unless the user explicitly confirms. Do not write findings into the repo under audit.

### Step 0c.2: Ask User for Report Primer (Standalone only)

**Skip if `RUN_MODE == seeder`.**

Findings are first written as short factual reports by the filter agent. Then each short report is rewritten into a full submission-style report using a **primer** — a style/structure guide that is injected into the rewrite agent's prompt by file path (not pre-loaded into the orchestrator context).

Ask the user which primer to use:

```
AskUserQuestion(questions=[{
  question: "Which report primer should NEXTUP use when rewriting each finding into its final form?",
  header: "Report primer",
  multiSelect: false,
  options: [
    {
      label: "Sherlock",
      description: "Sherlock-contest style (H/M severity, Sherlock thresholds, Title/Summary/Root Cause/Impact/Attack Path/Mitigation).",
      preview: "Primer file: {NEXTUP_HOME}/primers/sherlock.md"
    },
    {
      label: "Custom",
      description: "Provide an absolute path to your own primer .md file.",
      preview: "You will be prompted for the absolute path."
    },
    {
      label: "None",
      description: "Skip the rewrite step. Keep the short factual reports written by the filter agent.",
      preview: "No primer is loaded; Phase 4b is skipped."
    }
  ]
}])
```

Set `PRIMER_PATH` based on the selection:
- **Sherlock** → `PRIMER_PATH = {NEXTUP_HOME}/primers/sherlock.md`
- **Custom** → follow-up `AskUserQuestion` requesting an absolute path to a `.md` file. Expand `~`, resolve to absolute path, verify it exists and is readable. If missing, re-prompt or fall back to Sherlock.
- **None** → `PRIMER_PATH = null` (skip Phase 4b).

**DO NOT read the primer file into the orchestrator context.** The primer is injectable-by-path only; the rewrite agent reads it itself during Phase 4b.

### Step 0d: Print Banner

```
=== NEXTUP: Combinatorial Puzzle-Piece Auditor ===
Mode: {NEXTUP_MODE} (k={k})
Run mode: {standalone|nextup-seeder}
Scope: {path}
Language: {language}
Report dir: {REPORT_DIR}   # standalone only
Primer: {PRIMER_PATH or "none (rewrite skipped)"}   # standalone only
Starting pipeline...
```

---

## Phase 1: EXTRACT (1 Agent)

Read the extraction agent prompt from `{NEXTUP_HOME}/extraction/extract_agent.md`.

**Seeder enhancement**: If `RUN_MODE == seeder`, the extraction agent also receives NEXTUP's recon artifacts as additional context:
- `{NEXTUP_SCRATCHPAD}/state_variables.md` (all state variables already identified)
- `{NEXTUP_SCRATCHPAD}/function_list.md` (all functions already mapped)
- `{NEXTUP_SCRATCHPAD}/attack_surface.md` (attack surface from recon)

This gives the extractor a head start -- it doesn't need to rediscover what recon already found.

Spawn one agent:

```
Agent(subagent_type="general-purpose", model="opus", prompt="
{PASTE EXTRACTION AGENT PROMPT with these replacements:}
- {SCOPE_PATH} = actual scope path
- {TAXONOMY_PATH} = {NEXTUP_HOME}/taxonomy/{language}.json
- {PATTERN_HINTS_PATH} = {NEXTUP_HOME}/extraction/patterns/{pattern_hints_file}
- {LANGUAGE} = evm | solana | aptos | sui | c_cpp
- {OUTPUT_PATH} = {NEXTUP_DIR}/pieces.json

{IF RUN_MODE == seeder:}
## Additional Context from NEXTUP Recon
You have access to recon artifacts that map the codebase. Use them to accelerate extraction:
- {NEXTUP_SCRATCHPAD}/state_variables.md — pre-identified state variables (use for state_touched field)
- {NEXTUP_SCRATCHPAD}/function_list.md — pre-mapped functions (use for call_context field)
- {NEXTUP_SCRATCHPAD}/attack_surface.md — known attack surface (prioritize these areas)
Do NOT limit yourself to what recon found — also look for patterns recon may have missed.
{END IF}

Read the taxonomy file, the pattern hints file, and ALL source files in scope.
Then identify puzzle pieces and write pieces.json.
")
```

**Wait for agent to complete.** Read `{NEXTUP_DIR}/pieces.json` to get piece count. If 0 pieces, abort with message.

---

## Phase 2: COMBINE + ELIMINATE (Python Script, 0 LLM tokens)

Run the combinator:

```bash
python3 {NEXTUP_HOME}/combinator/combine_{language}.py \
  {NEXTUP_DIR}/pieces.json \
  {k} \
  {NEXTUP_DIR}/combos_ranked.json \
  --top {TOP_N}
```

The combinator script is per-language: `combine_evm.py`, `combine_solana.py`, `combine_aptos.py`, `combine_sui.py`, or `combine_c_cpp.py`. Each loads its own rule and weight files from `{NEXTUP_HOME}/combinator/rules/{language}.json` and `{NEXTUP_HOME}/combinator/weights/{language}.json`.

Read the script output for stats. If 0 survivors, abort with message.

**If `RUN_MODE == seeder`**: After this phase, ALSO generate the investigation targets file (Phase 2b) and then STOP. Do not proceed to Phase 3.

### Phase 2b: Generate Investigation Targets (Seeder mode only)

Read `{NEXTUP_DIR}/combos_ranked.json`. Transform the top combinations into investigation questions for NEXTUP depth agents.

Write `{NEXTUP_DIR}/investigation_targets.md`:

```markdown
# NEXTUP Investigation Targets

Generated from {N} puzzle pieces, {S} surviving combinations (k={k}, elimination rate: {E}%).

## For depth-token-flow

[List combinations involving categories A (arithmetic), E (economic), G (token handling)]

### Target NX-TF-1: {combo title}
**Pieces**: P001 (A01_ROUNDING_FLOOR @ xyk.rs:64) + P006 (E04_SLIPPAGE_PROTECTION @ execute.rs:337)
**Shared state**: [output_reserve]
**Investigate**: Does the floor rounding in swap output calculation (P001) interact with the optional slippage check (P006) to allow zero-output swaps when minimum_output is not set?
**Code refs**: xyk.rs:64, execute.rs:337-345

## For depth-state-trace

[List combinations involving categories C (state), F (control flow), H (timing)]

### Target NX-ST-1: ...

## For depth-edge-case

[List combinations involving categories A (arithmetic edge cases), E (economic edge cases)]

### Target NX-EC-1: ...

## For depth-external

[List combinations involving categories D (external deps)]

### Target NX-EX-1: ...
```

**Routing rules** — assign each combination to a depth domain based on its categories:
| Categories in combo | Primary depth domain |
|--------------------|--------------------|
| A + E, A + G, E + G | depth-token-flow |
| C + F, C + H, F + H | depth-state-trace |
| A + I, E + I, any with A07 (zero passthrough) | depth-edge-case |
| D + anything | depth-external |
| Mixed (3+ categories) | assign to domain of the highest-scored piece |

Each target is a focused question, not a conclusion. Tell the depth agent WHAT to investigate, not WHAT to find.

Write the file and return: `'DONE-SEEDER: {N} pieces, {S} combinations, {T} investigation targets across {D} depth domains'`

The NEXTUP orchestrator reads this file and injects targets into depth agent prompts. See `nextup-integration.md`.

---

## Phase 3: HYPOTHESIZE (Standalone only — Parallel Agents)

**Skip if `RUN_MODE == seeder`.** NEXTUP's depth agents handle hypothesis generation using the investigation targets.

### Step 3a: Read Combos and Batch

Read `{NEXTUP_DIR}/combos_ranked.json`. Split the combinations array into batches of 10-15 each.

### Step 3b: Determine Agent Count

Based on number of batches and NEXTUP_MODE:
- **lightweight**: min(num_batches, 4) agents
- **middleweight**: min(num_batches, 8) agents
- **heavyw8t**: min(num_batches, 15) agents

If fewer batches than agent cap, use 1 agent per batch. If more batches than cap, distribute evenly.

### Step 3c: Write Batch Files

For each batch, write `{NEXTUP_DIR}/combo_batch_{N}.json`.

### Step 3d: Spawn Hypothesis Agents IN PARALLEL

Read the hypothesis agent prompt from `{NEXTUP_HOME}/hypothesis/hypothesis_agent.md`.

Spawn ALL hypothesis agents in a SINGLE message (parallel execution):

```
Agent(subagent_type="general-purpose", model="sonnet", prompt="
{PASTE HYPOTHESIS AGENT PROMPT with these replacements:}
- {COMBOS_PATH} = {NEXTUP_DIR}/combo_batch_{N}.json
- {OUTPUT_PATH} = {NEXTUP_DIR}/hypotheses_batch_{N}.json

Read your combo batch file, then for each combination:
1. Read the actual source code at the referenced locations
2. Generate a hypothesis (or mark INFEASIBLE)
3. Write results to your output file

Source files are at: {SCOPE_PATH}
")
```

**Wait for ALL agents to complete.**

---

## Phase 4: FILTER + DEDUP (Standalone only — 1 Agent)

**Skip if `RUN_MODE == seeder`.**

Read the filter agent prompt from `{NEXTUP_HOME}/filter/filter_agent.md`.

Spawn one agent:

```
Agent(subagent_type="general-purpose", model="opus", prompt="
{PASTE FILTER AGENT PROMPT with these replacements:}
- {SCRATCHPAD} = {NEXTUP_DIR}
- {REPORT_DIR} = {REPORT_DIR}   # user-chosen output directory, OUTSIDE the audited repo
- {OUTPUT_INDEX_PATH} = {REPORT_DIR}/SUMMARY.md

Read all hypotheses_batch_*.json files, pieces.json, and relevant source code.
Filter, deduplicate, validate, then write ONE .md file per finding into {REPORT_DIR}
(named NX-01.md, NX-02.md, ...) and a SUMMARY.md index. Do NOT write a combined
findings.md into the audited repo.

CRITICAL RULE — CONFIRMED FINDINGS ONLY:
Only write an individual NX-NN.md file for a finding that you have CONFIRMED by
reading the source code and validating the attack path end-to-end. Do NOT write
individual .md files for:
  - hypotheses marked INFEASIBLE by the hypothesis agents
  - findings you refuted during validation (code path doesn't exist, guard
    rejects the attacker, input constraint prevents the trigger, math doesn't
    work out, etc.)
  - duplicates of another confirmed finding
  - speculative leads you could not verify against the code
Refuted / infeasible / speculative items MUST NOT get their own NX-NN.md.
They may be listed under a single "Refuted / Not Reproduced" appendix section
inside SUMMARY.md (one line each, with the refutation reason), but no per-item
files. The per-finding files are reserved for confirmed issues only.
")
```

**Wait for agent to complete.**

The filter agent produces **short factual reports** (`NX-01.md`, `NX-02.md`, ...) in `{REPORT_DIR}`. These are the raw technical findings. Phase 4b rewrites each into a final submission-style report using the chosen primer.

---

## Phase 4b: REWRITE WITH PRIMER (Standalone only — Parallel Agents)

**Skip if `RUN_MODE == seeder` OR `PRIMER_PATH == null`.**

Each short report written by the filter agent is rewritten into a final report whose structure, tone, and severity framing follow the selected primer. The primer is **injected by file path** — the rewrite agent reads it directly; the orchestrator never loads it.

**PRIMER MAY NEVER DROP OR DOWNGRADE A FINDING.** The primer governs *format and prose style*, not validity or severity. If a finding does not fit the primer's severity tiers, scope (e.g., Sherlock's "direct loss of funds" framing), or topical rubric:

- DO NOT delete the finding.
- DO NOT downgrade its severity to match the primer's allowed tiers.
- DO NOT silently merge it into a related finding.

Instead, write it as an **unclassified** finding to `U-NN.md` in `{REWRITE_DIR}` (and mirrored in `{REPORT_DIR}` if it was filtered there). Numbering for `U-NN` resets per audit, zero-padded. The `U-NN.md` file uses the same technical structure as other findings (Title, Locations, Root Cause, Impact, Attack Path if applicable, Mitigation) AND includes, at the top, a one-sentence `**Unclassified reason:**` line explaining why the primer could not classify it (e.g., "Primer scope limited to direct LP/protocol loss; this finding harms a third-party issuer's compliance revenue.").

Severity verdicts from Skeptic-Judge and the verification agent remain authoritative. The only reasons a finding may be excluded from the output directory entirely are:
- INVALIDATED by Skeptic-Judge (logic-level refutation, with rebuttal noted in SUMMARY.md appendix)
- Pre-screen REJECTED (invalidation-library hit, reason noted in SUMMARY.md appendix)

Those exclusions are never primer-driven.

### Step 4b.1: Enumerate Short Reports

List all `NX-*.md` files in `{REPORT_DIR}` (exclude `SUMMARY.md`). For each file, note the absolute path. If zero findings, skip this phase.

### Step 4b.2: Create Rewrite Output Directory

Set `REWRITE_DIR = {REPORT_DIR}/rewritten`. Create it if missing. Preserve the original short reports in `{REPORT_DIR}` — rewrites go into the subdirectory.

### Step 4b.3: Spawn Rewrite Agents IN PARALLEL

Spawn one agent per short report in a SINGLE message (parallel execution). Cap concurrency at 10 agents; if more findings than the cap, process in waves.

```
Agent(subagent_type="general-purpose", model="sonnet", prompt="
You are rewriting one short NEXTUP finding into its final submission form.

STEP 1 — Read the primer (style/structure guide):
  Read: {PRIMER_PATH}
  Follow its structure, tone, severity rubric, word-count targets, and checklist EXACTLY.

STEP 2 — Read the short finding:
  Read: {SHORT_REPORT_PATH}

STEP 3 — Read source code at any file:line references in the finding so quantitative
  claims (impact, attack path, values) are grounded in the real code. Source root:
  {SCOPE_PATH}

STEP 4 — Rewrite the finding per the primer. Preserve technical facts (file:line
  anchors, root cause, attacker path). Re-frame tone/structure/severity language
  to match the primer. Do not invent facts; if the primer asks for quantification
  the short report does not support, mark it explicitly as an estimate.

STEP 5 — Write the rewritten report to:
  {REWRITE_OUTPUT_PATH}

SCOPE: Write ONLY to your assigned output file. Return 'DONE' and stop.
")
```

Where for each short report `NX-NN.md`:
- `{SHORT_REPORT_PATH}` = `{REPORT_DIR}/NX-NN.md`
- `{REWRITE_OUTPUT_PATH}` = `{REWRITE_DIR}/NX-NN.md`

**Wait for ALL rewrite agents to complete.** If any agent fails, retain the short report as the final artifact for that finding and log the failure.

### Step 4b.4: Write Rewrite Index

Write `{REWRITE_DIR}/SUMMARY.md` listing each rewritten finding with its title, severity (as framed by the primer), and a one-line hook. Keep the original `{REPORT_DIR}/SUMMARY.md` untouched so the short-vs-rewritten correspondence is preserved.

---

## Phase 5: REPORT (Standalone only — Orchestrator Inline)

**Skip if `RUN_MODE == seeder`.**

Read `{REPORT_DIR}/SUMMARY.md` and list the per-finding files in `{REPORT_DIR}` (e.g. `NX-01.md`, `NX-02.md`, ...).

Extract the summary counts and top findings. Print to the user:

```
=== NEXTUP Results ===
Mode: {NEXTUP_MODE}
Scope: {path}
Language: {language}

Pipeline stats:
  Pieces extracted: {N}
  Combinations generated: {N} (elimination rate: {X}%)
  Hypotheses generated: {N}
  Findings after filtering: {N}

Severity distribution:
  Critical: {N}
  High:     {N}
  Medium:   {N}
  Low:      {N}
  Info:     {N}

Report directory: {REPORT_DIR}
  SUMMARY.md + one short factual .md per finding (NX-01.md, NX-02.md, ...)
Rewritten directory: {REWRITE_DIR}   # omitted if primer == None
  SUMMARY.md + one primer-styled .md per finding
Primer used: {PRIMER_PATH or "none"}
```

Then print the `{REPORT_DIR}/SUMMARY.md` content and the list of per-finding file paths (both short and, if present, rewritten) so the user can open them directly. Do NOT paste the full body of every finding inline.

---

## Error Handling

| Error | Action |
|-------|--------|
| No source files in scope | Abort with message |
| Extraction returns 0 pieces | Abort with message |
| Combinator returns 0 survivors | Abort with message |
| Python not available | Try `python` instead of `python3`. If both fail, abort with "Python 3 required for NEXTUP combinator" |
| Hypothesis agent fails | Continue with remaining agents. Log failure. |
| All hypothesis agents fail | Abort with message |
| Filter agent fails | Output raw hypotheses files as fallback |
| Primer file missing/unreadable | Re-prompt user; on second failure fall back to Sherlock primer; if that is also missing, skip Phase 4b |
| Rewrite agent fails for a finding | Retain the short report as final artifact; log the failure; continue with remaining rewrites |

---

## Agent Budget Summary

### Standalone

| Phase | Agents | Model |
|-------|--------|-------|
| Phase 1: Extract | 1 | opus |
| Phase 3: Hypothesize | 2-15 (mode dependent) | sonnet |
| Phase 4: Filter | 1 | opus |
| Phase 4b: Rewrite with primer | 1 per finding (capped at 10 concurrent; skipped if primer = None) | sonnet |
| **Total** | **4-17 + N rewrites** | |

### NEXTUP Seeder

| Phase | Agents | Model |
|-------|--------|-------|
| Phase 1: Extract | 1 | sonnet (matches NEXTUP's Phase 4a model budget) |
| Phase 2b: Generate targets | 0 (orchestrator inline) | - |
| **Total** | **1** | |

In seeder mode, the extraction agent uses sonnet (not opus) to stay within NEXTUP's agent budget. The combinatorial work is free (Python). Investigation targets are plain text injected into existing depth agent prompts — no additional agents needed.
