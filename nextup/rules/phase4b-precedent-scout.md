# Phase 4b.4: Injectable example-precedent scout

After an injectable investigation agent produces findings, the orchestrator spawns one precedent-scout agent per finding. Each scout uses the parent skill's spliced `## Real-world examples` section as a pattern library and sweeps the scope code for OTHER locations that may be vulnerable to the same problem.

Runs in Core and Thorough modes. Skipped in Light (injectable investigation agents don't run there).

## Trigger

For each finding in `{SCRATCHPAD}/analysis_<injectable_skill>.md`:
- Parse the finding's `id`, `location`, and `Pattern` / mechanism description.
- Read the parent skill's `## Real-world examples` section from `agents/skills/injectable/{skill_name}/SKILL.md`.
- Spawn one scout agent with the prompt below.

## Scout agent prompt template

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are a PRECEDENT-SCOUT agent. Your job is to find OTHER locations in the scope that may be vulnerable to the same class of problem as the parent finding.

PARENT FINDING:
- ID: {FINDING_ID}
- Location: {FILE_PATH}:{LINE_START}-{LINE_END}
- Skill: {SKILL_NAME}
- Mechanism: {ONE_LINE_MECHANISM}

SCOPE: {SCOPE_PATH}

REAL-WORLD EXAMPLES (from the parent skill's ## Real-world examples section):
{INLINED_EXAMPLES_BLOCK}

## Your steps

1. For each example in the examples block, extract grep-friendly tokens from:
   - `Pattern:` line (the mechanism keywords)
   - `Where it hit:` line (function / file / protocol names)
   - `Map to:` line (taxonomy markers / identifiers)

2. Build per-example search queries (2-5 tokens each). Use `Grep` with these queries against the scope. Skip the parent finding's file unless the scope has other regions of that same file.

3. For each hit, classify confidence:
   - HIGH: same mechanism, similar surrounding context (call-site, state variable, modifier scope). Likely another instance of the bug.
   - MEDIUM: keyword match only; context unclear from the grep snippet alone. Worth manual review.
   - LOW: tangential hit (keyword appears in a comment, test file, or unrelated function). Exclude.

4. De-duplicate: never report the parent finding's own location; never report the same file:line twice.

## Output

Write `{SCRATCHPAD}/precedent_{FINDING_ID}.md`:

```markdown
# Precedent scout report for {FINDING_ID}

## Parent
- Location: {FILE_PATH}:{LINE_START}-{LINE_END}
- Skill: {SKILL_NAME}

## HIGH-confidence candidates
- `<file>:<line>` — <one-line why this looks like the same problem> (matched example: <Pattern / row_id or URL>)
- ...

## MEDIUM-confidence candidates
- `<file>:<line>` — <one-line reason> (matched example: ...)
- ...

## Not pursued
- <brief note on any example that produced only LOW hits or no hits at all>
```

If no HIGH or MEDIUM hits are found, still write the file with empty sections and a one-line `no precedent hits` note.

## Rules

- Report HIGH-confidence hits only when you can quote a code-level reason (e.g., identical function name structure, same missing check pattern, same modifier gap).
- Never invent a location. Every reported hit must come from an actual Grep result in the scope.
- Do not proceed to verification, scoring, or chain analysis. Return after writing the report.
- Tool budget: no more than 30 Grep/Read calls total per scout. If you exceed, stop and document which examples were not searched.
- SCOPE: Write ONLY to your assigned output file. Do NOT read or write other agents' output files. Do NOT proceed to subsequent pipeline phases (chain analysis, verification, report). Return your findings and stop.
")
```

## Orchestrator post-processing

After all scouts return, the orchestrator reads every `precedent_*.md` and updates `findings_inventory.md`:

- For each HIGH-confidence candidate, append a NEW finding entry (severity unknown; inherits the parent skill's domain tag) with `Example precedent: <matched example citation>` and a pointer to the parent finding id. These are candidate findings for the next depth or verification pass, not confirmed bugs.
- For each MEDIUM-confidence candidate, append a `Related locations:` footer to the parent finding's entry. Verification agents in Phase 5 visit these locations as part of the parent finding's proof-or-refute sweep.
- LOW-confidence hits are discarded.

## Confidence scoring impact

Per `rules/phase4-confidence-scoring.md`:
- A finding with a documented HIGH-confidence precedent scout hit elsewhere in the scope AND a matched real-world example gets a `precedent_match` signal in the RAG Match axis.
- A finding with only a real-world example match (no scope-level precedent) still gets the `precedent_match` signal at half weight.

## Cost

One sonnet per injectable-skill finding. A typical Core run produces 4-10 injectable findings, Thorough 8-20. Total added cost: 4-20 sonnet agents per audit. Each scout is capped at 30 Grep/Read calls and finishes in under 60s.

## Light-mode behavior

Skipped. Injectable skills in Light mode are summary snippets consumed by the main breadth agent; no dedicated injectable investigation agent runs, so there are no findings to scout against.
