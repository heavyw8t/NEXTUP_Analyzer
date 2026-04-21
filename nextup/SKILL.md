# NEXTUP Combinatorial Analysis (Internal Reference)

> This module is invoked by the NEXTUP audit pipeline at Phase 4a.NX. It is not a standalone skill. See `nextup-command.md` Phase 4a.NX for the orchestrator-facing entry. This file is a language-agnostic technical reference for the extract, combine, and hypothesize steps plus the downstream contract with Phase 4a inventory.

---

## Scope

Phase 4a.NX produces four artifacts in `{SCRATCHPAD}/nextup/`:

- `pieces.json` (typed puzzle pieces extracted from source)
- `combos_ranked.json` (surviving combinations after static elimination)
- `hypotheses_batch_*.json` (LLM hypotheses from surviving combos, parallel batches; skipped in Light)
- `investigation_targets.md` (combos routed to Phase 4b depth domains)

Phase 4a inventory consumes `hypotheses_batch_*.json` and dedups skill hypotheses into `findings_inventory.md` alongside breadth and static-analysis findings. See `prompts/{LANGUAGE}/phase4a-inventory-prompt.md` TASK 1.0 for the dedup rules.

---

## Non-negotiable rules

### R5 — Mid-pipeline self-correction is mandatory
If you notice mid-pipeline that a step was skipped, stop forward progress, ask the user for the missing input, then continue. Do not fix forward by guessing.

### R6 — Append a CHANGELOG entry before every commit that touches nextup/
Every commit under `~/Desktop/NEXTUP SKILL/nextup/` MUST be preceded by a dated entry appended to `~/Desktop/NEXTUP SKILL/CHANGELOG.md`. Format: `## YYYY-MM-DD — <short title>` followed by a bullet list. `CHANGELOG.md` is git-ignored.

### R7 — Commit and sync workflow
After any change under `nextup/`: append CHANGELOG entry (R6), `git pull --rebase`, `git add` specific paths (never `git add -A`), `git commit`, `git push`. Commit at the end of the rework, not the end of a long session. Surface errors to the user; never force-push.

Standalone-only rules R1 (REPORT_DIR prompt), R2 (primer prompt), R3 (no combined report), and R4 (primer may never drop a finding) are retired. The audit pipeline owns report location, report style (via `rules/report-template.md` and `rules/phase6-report-prompts.md`), and severity calibration.

---

## Language detection

Phase 1 recon resolves `LANGUAGE` to one of `evm`, `solana`, `aptos`, `sui`, `c_cpp`. NEXTUP reads the result from `{SCRATCHPAD}/build_status.md`. Detection rules:

- `.sol` → `evm` (pattern hints: `solidity_evm.md`, taxonomy: `evm.json`)
- `.rs` + Cargo.toml with `anchor-lang` or `solana-program` → `solana` (`solana.md`, `solana.json`)
- `.move` + Move.toml with `aptos-framework` → `aptos` (`move.md`, `aptos.json`)
- `.move` + Move.toml with `Sui` → `sui` (`move.md`, `sui.json`)
- `.c`/`.cpp`/`.cc`/`.h`/`.hpp` + `CMakeLists.txt` or `Makefile` → `c_cpp` (`c_cpp.md`, `c_cpp.json`)

---

## Phase NX-1: EXTRACT

One sonnet agent runs `{NEXTUP_HOME}/extraction/extract_agent.md` against the language's taxonomy (`taxonomy/{LANGUAGE}.json`), pattern hints (`extraction/patterns/{hints_file}`), and all source files in scope. Recon artifacts (`state_variables.md`, `function_list.md`, `attack_surface.md`) are additional context.

Output: `pieces.json` listing typed puzzle pieces with file:line anchors, category (A-I shared plus language-native J+), `state_touched`, and `call_context`.

---

## Phase NX-2: COMBINE + ELIMINATE

Zero LLM tokens. Per-language Python script loaded from `combinator/combine_{LANGUAGE}.py`:

```bash
python3 {NEXTUP_HOME}/combinator/combine_{LANGUAGE}.py \
  {NEXTUP_DIR}/pieces.json \
  {k} \
  {NEXTUP_DIR}/combos_ranked.json \
  --top {TOP_N}
```

Shared BFS and scoring scaffolding in `combinator/shared.py`. Per-language rules at `combinator/rules/{LANGUAGE}.json` and weights at `combinator/weights/{LANGUAGE}.json`. Elimination applies static rules and graph connectivity; typical survival rate is 5 to 30 percent.

---

## Phase NX-3: HYPOTHESIZE

Skipped in Light mode. In Core and Thorough, the orchestrator splits `combos_ranked.json` into batches of 10 to 15 and spawns N sonnet agents in a single parallel message. Each agent reads `hypothesis/hypothesis_agent.md`, its combo batch, and the source at every referenced location, then writes one `hypotheses_batch_N.json`.

Mode configuration:

| NEXTUP_MODE  | k | Top-N | Hypothesis agents |
|--------------|---|-------|-------------------|
| lightweight  | 2 | 50    | SKIP              |
| middleweight | 3 | 100   | 5-8 sonnet        |
| heavyw8t     | 4 | 150   | 8-15 sonnet       |

Priority guard injected into every hypothesis agent prompt:

> Puzzle-piece combinations that breadth agents have NOT flagged are higher priority than combinations that re-confirm existing breadth findings. Before emitting a hypothesis, check `{SCRATCHPAD}/analysis_*.md` for a finding at the same location with matching mechanism. If one exists and you cannot add stricter source evidence (direct code trace through the full attack path) or orthogonal attack steps, mark the combination `INFEASIBLE-BREADTH-DUP` rather than hypothesizing a duplicate.

This keeps Phase 4a inventory dedup tractable: duplicates are suppressed at the source rather than after the fact.

Hypothesis schema (per combination in the output array):

```json
{
  "combo_id": "...",
  "puzzle_pieces": ["P001", "P004"],
  "title": "...",
  "severity": "Critical | High | Medium | Low | Info",
  "feasibility": "FEASIBLE | CONDITIONAL | INFEASIBLE | INFEASIBLE-BREADTH-DUP",
  "code_refs": ["file.sol:64", "..."],
  "attack_steps": ["step 1", "..."],
  "preconditions": ["..."],
  "confidence": 0-100
}
```

---

## Phase NX-4: Investigation Targets

Orchestrator-inline. Each combination is routed to a Phase 4b depth domain based on `combo.categories`.

Pass 1 (priority, first match wins):

1. contains `D` → depth-external
2. contains `A07` (zero passthrough) → depth-edge-case
3. ≥ 2 of `{A, E, G}` → depth-token-flow
4. ≥ 2 of `{C, F, H}` → depth-state-trace
5. `A`+`I` or `E`+`I` → depth-edge-case
6. fallback → depth-state-trace

Pass 2 (empty-bucket rebalance, MANDATORY): if any bucket is empty and another has > 40 entries, spill lowest-scored combos from the donor to the empty bucket round-robin until no bucket is empty. Cap donor overflow at 40 per round.

Pass 3 (imbalance redistribution, conditional): if `max(bucket_sizes) / min(bucket_sizes) > 3` after Pass 2, redistribute the entire target set round-robin by score rank so each of the four buckets gets roughly `total / 4` combos.

Output: `{NEXTUP_DIR}/investigation_targets.md` with four sections, one per depth domain.

Reference implementation:

```python
def route(combo_cats: set[str]) -> str:
    if "D" in combo_cats: return "depth-external"
    if "A07" in combo_cats: return "depth-edge-case"
    if sum(c in combo_cats for c in ("A","E","G")) >= 2: return "depth-token-flow"
    if sum(c in combo_cats for c in ("C","F","H")) >= 2: return "depth-state-trace"
    if "I" in combo_cats and ("A" in combo_cats or "E" in combo_cats): return "depth-edge-case"
    return "depth-state-trace"
```

---

## Phase NX-5: Inject into Depth

Phase 4b depth agent prompts append the relevant section from `investigation_targets.md`. Each domain agent gets its own subsection. Empty sections skip injection.

Targets are phrased as investigation questions (what to look at), not conclusions (what to find). Depth agents tag findings originating from NEXTUP targets with `[NX-{ID}]` in the title; severity matrix and evidence standards are unchanged.

---

## Downstream Contract

- Phase 4a inventory reads `{SCRATCHPAD}/nextup/hypotheses_batch_*.json` as a third finding source alongside breadth `analysis_*.md` and static-analysis promotions. Dedup and ID assignment are specified in `prompts/{LANGUAGE}/phase4a-inventory-prompt.md` TASK 1.0.
- Surviving NEXTUP hypotheses enter the pipeline as `[NX-N]` findings. They flow through Phase 4a.5 semantic invariants, Phase 4b depth, Phase 4c chain, Phase 5 verification (PoC execution per `rules/phase5-poc-execution.md`), and Phase 6 report exactly like breadth findings.
- Hypotheses that dedup into an existing breadth finding are merged as `Related locations:` and `Puzzle-piece evidence:` footer on the breadth survivor. Dropped losers are listed in the `## Dedup Trail` appendix of `findings_inventory.md` so chain analysis and the final report can trace their origin.

---

## Error Handling

| Error | Action |
|-------|--------|
| Extraction returns 0 pieces | Log warning; skip NX-2 through NX-5; inventory runs on breadth + static only. |
| Combinator returns 0 survivors | Log warning; skip NX-3 through NX-5. |
| Python not available | Try `python` then `python3`; if both fail, log `NEXTUP_DISABLED: python_missing` to violations.md and skip. |
| Hypothesis agent times out | Split-and-retry per the standard timeout policy (max 2 lite agents per failed slot). |
| All hypothesis agents fail | Log warning; investigation_targets.md still produced; inventory runs without skill hypotheses. |

NEXTUP failure never blocks the audit pipeline. The pipeline degrades to breadth + static-only analysis.

---

## Files

| Purpose | Path |
|---------|------|
| Orchestrator entry | `nextup-command.md` Phase 4a.NX |
| Extraction agent | `extraction/extract_agent.md` |
| Hypothesis agent | `hypothesis/hypothesis_agent.md` |
| Combinator dispatcher | `combinator/combine.py` |
| Per-language combinator | `combinator/combine_{LANGUAGE}.py` |
| Per-language rules | `combinator/rules/{LANGUAGE}.json` |
| Per-language weights | `combinator/weights/{LANGUAGE}.json` |
| Taxonomy | `taxonomy/{LANGUAGE}.json` |
| Pattern hints | `extraction/patterns/{hints_file}` |
| Inventory dedup | `prompts/{LANGUAGE}/phase4a-inventory-prompt.md` TASK 1.0 |

The standalone filter agent (`filter/filter_agent.md`) is retired; its dedup logic moved into Phase 4a inventory TASK 1.0. The primer rewrite step (`primers/sherlock.md`) is retired; report style is owned by `rules/phase6-report-prompts.md` and `rules/report-template.md`.
