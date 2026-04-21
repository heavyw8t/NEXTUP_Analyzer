# NEXTUP Integration Reference

> How Phase 4a.NX fits into the NEXTUP audit pipeline. The orchestrator-facing steps live in `nextup-command.md`; this file explains the contract between NEXTUP and the phases around it.

---

## Ordering

```
Phase 3: Breadth Agents              → analysis_*.md
    ↓
Phase 4a.NX: NEXTUP Combinatorial    → pieces.json
                                       combos_ranked.json
                                       hypotheses_batch_*.json  (Core/Thorough)
                                       investigation_targets.md
    ↓
Phase 4a: Inventory Agent            → findings_inventory.md (deduplicated across breadth + NEXTUP + static)
    ↓
Phase 4a.5: Semantic Invariants      (Core/Thorough, runs after inventory)
    ↓
Phase 4b: Adaptive Depth Loop        (depth agents receive NEXTUP investigation targets)
```

Phase 4a.NX is a mandatory step in all modes. It runs serially after breadth and before inventory; there is no parallel-with-inventory path because inventory depends on the hypothesis output.

---

## Mode Selection

Audit mode drives NEXTUP_MODE and agent budget:

| Audit MODE | NEXTUP_MODE  | k | Top-N | Hypothesis agents |
|------------|--------------|---|-------|-------------------|
| Light      | lightweight  | 2 | 50    | SKIP              |
| Core       | middleweight | 3 | 100   | 5-8 sonnet        |
| Thorough   | heavyw8t     | 4 | 150   | 8-15 sonnet       |

Light mode runs only NX-1 (extract), NX-2 (combine), NX-4 (investigation targets), and NX-5 (inject into depth). NX-3 (hypothesize) is skipped to keep the Pro-plan agent count inside budget.

---

## What NEXTUP Produces

All artifacts land under `{SCRATCHPAD}/nextup/`.

| File | Writer | Consumer |
|------|--------|----------|
| `pieces.json` | NX-1 extraction agent | NX-2 combinator |
| `combos_ranked.json` | NX-2 combinator (Python, zero tokens) | NX-3, NX-4 |
| `combo_batch_N.json` | Orchestrator (split for parallel) | NX-3 hypothesis agents |
| `hypotheses_batch_N.json` | NX-3 hypothesis agents | Phase 4a inventory TASK 1.0 |
| `investigation_targets.md` | NX-4 orchestrator inline | Phase 4b depth agents (via NX-5 injection) |

---

## Phase 4a Inventory Contract

Phase 4a reads `{SCRATCHPAD}/nextup/hypotheses_batch_*.json` as a third finding source alongside breadth `analysis_*.md` and static-analysis promotions (Slither / sanitizers / detectors).

TASK 1.0 (Cross-Source Deduplication) in `prompts/{LANGUAGE}/phase4a-inventory-prompt.md` defines dedup priority:

1. Breadth finding with completed PoC wins outright.
2. Breadth finding without PoC loses only to a NEXTUP hypothesis with stricter source evidence.
3. NEXTUP vs NEXTUP: higher feasibility, then higher severity, then higher combo score.
4. Static-detector survives only when alone.

Survivors keep their original IDs (`[XX-N]` for breadth, `[SLITHER-N]` / `[SD-N]` / `[SAN-N]` for static). NEXTUP survivors with no breadth match get sequential `[NX-N]` IDs. Dropped losers go into a `## Dedup Trail` appendix so chain analysis and the final report can trace origin.

---

## Phase 4b Depth Contract

Phase 4b depth agent prompts append the relevant section from `investigation_targets.md`.

| Depth Agent | Gets Section |
|-------------|--------------|
| depth-token-flow | `## For depth-token-flow` |
| depth-state-trace | `## For depth-state-trace` |
| depth-edge-case | `## For depth-edge-case` |
| depth-external | `## For depth-external` |

Empty sections skip injection. Depth findings originating from a NEXTUP target tag the finding title with `[NX-{TARGET_ID}]`. Severity matrix and evidence standards are unchanged.

---

## Priority Guard (NX-3)

Every hypothesis agent receives this guard in its prompt so hypotheses do not duplicate breadth findings without adding value:

> Puzzle-piece combinations that breadth agents have NOT flagged are higher priority than combinations that re-confirm existing breadth findings. Before emitting a hypothesis, check `{SCRATCHPAD}/analysis_*.md` for a finding at the same location with matching mechanism. If one exists and you cannot add stricter source evidence (direct code trace through the full attack path) or orthogonal attack steps, mark the combination `INFEASIBLE-BREADTH-DUP` rather than hypothesizing a duplicate.

`INFEASIBLE-BREADTH-DUP` counts toward the infeasible total in Phase 4a.NX stats; it does not feed inventory.

---

## Budget Impact

| Component | Light | Core | Thorough |
|-----------|-------|------|----------|
| Extraction agent (NX-1) | 1 sonnet | 1 sonnet | 1 sonnet |
| Combinator (NX-2) | 0 (Python) | 0 (Python) | 0 (Python) |
| Hypothesis agents (NX-3) | 0 (SKIP) | 5-8 sonnet | 8-15 sonnet |
| Investigation targets (NX-4) | 0 (inline) | 0 (inline) | 0 (inline) |
| Injection (NX-5) | 0 (prompt append) | 0 (prompt append) | 0 (prompt append) |
| Phase 4a.NX total | 1 sonnet | 6-9 sonnet | 9-16 sonnet |

---

## Failure Handling

NEXTUP never blocks the pipeline. All failures degrade to running the rest of the pipeline without NEXTUP's contribution:

| Failure | Action |
|---------|--------|
| NX-1 extraction returns 0 pieces | Skip NX-2 through NX-5; inventory runs on breadth + static only. |
| NX-2 combinator returns 0 survivors | Skip NX-3 through NX-5. |
| Python not available | Log `NEXTUP_DISABLED: python_missing` to `violations.md`; skip all of Phase 4a.NX. |
| NX-3 hypothesis agent times out | Split-and-retry per the timeout policy (max 2 lite agents per failed slot). |
| All NX-3 agents fail | Log warning; `investigation_targets.md` still produced; inventory runs without skill hypotheses. |
| `investigation_targets.md` empty | Skip NX-5 injection for that domain; depth agents run without NEXTUP targets. |
