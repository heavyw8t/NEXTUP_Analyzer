# NEXTUP Pipeline Reference

Single-source overview of the NEXTUP audit pipeline (`/nextup` with `light | core | thorough`). The combinatorial puzzle-piece analysis that used to run as a standalone skill is now Phase 4a.NX of this pipeline; its extract, combine, and hypothesize steps run serially between Phase 3 breadth and Phase 4a inventory, and its hypotheses flow into inventory dedup as a third finding source alongside breadth and static analysis.

The `lightweight | middleweight | heavyw8t` flag now controls Phase 4a.NX depth only (k=2 / k=3 / k=4 combo size plus hypothesis-agent budget). There is no separate standalone entry.

---

## PART 1: NEXTUP AUDIT PIPELINE (OVERVIEW)

One line per step. Expanded section below.

### Phase 0: Setup
- Step 0a: Banner, toolchain probe, audit mode selection (Light, Core, Thorough, Compare).
- Step 0a.2: NEXTUP combinatorial depth selection (lightweight, middleweight, heavyw8t).
- Step 0b: Target project confirmation via `AskUserQuestion`.
- Step 0c: Documentation source prompt (no docs, local file, URL).
- Step 0c.5: Scope selection (full project, scope file, scope notes).
- Step 0c.6: Proven-only mode toggle (cap unproven findings at Low).
- Step 0d: Cost estimate, launch summary, user confirmation.
- Step 0e: Compare flow (diff NEXTUP report against ground truth, bypasses audit).
- Step 0.5: EVM network resolution to RPC URL (if `NETWORK` set and language is EVM).

### Phase 1: Language Detection and Reconnaissance
- Step 1: Detect target language (`evm`, `solana`, `aptos`, `sui`, `c_cpp`).
- Step 1b: Split recon into 4 parallel agents (1A RAG, 1B docs + external, 2 build + slither, 3 patterns + surface). Light mode merges to 2.
- Step 1c: Verify recon artifacts exist. Enforce hard gate before Phase 2.

### Phase 2: Orchestrator Instantiation
- Step 2a: Size breadth agent count from complexity (simple / medium / complex).
- Step 2a.1: Apply merge hierarchy when templates exceed target count.
- Step 2b: Instantiate skill templates with `{PLACEHOLDERS}` and conditional sections.
- Step 2b.1: Load injectable skills for breadth and dedicated injectable investigation agents for depth.
- Step 2c: Compose agent prompt structure.
- Step 2d: Write spawn manifest and enforce template verification gate.

### Phase 3: Parallel Breadth Analysis
- Step 3: Spawn all breadth agents in one message, verify each produced a findings file.
- Step 3b: Breadth re-scan (Thorough only, 2 iters).
- Step 3c: Per-contract analysis (Thorough only).

### Phase 4: Synthesis, Depth, Chains
- Step 4a.NX: NEXTUP combinatorial analysis runs BEFORE inventory. Extract puzzle pieces (1 sonnet), combine + eliminate (Python, zero tokens), hypothesize (Core: 5-8 sonnet, Thorough: 8-15 sonnet; skipped in Light), write `investigation_targets.md` (Part 2).
- Step 4a: Inventory agent (opus, all modes) merges breadth findings, NEXTUP hypotheses, and static-analysis promotions. Dedups by root cause (see `prompts/{LANGUAGE}/phase4a-inventory-prompt.md` TASK 1.0). Emits the side-effect trace.
- Step 4a.5: Semantic invariant pre-computation (Pass 1 Core + Thorough, Pass 2 Thorough).
- Step 4b iter 1: Spawn 4 depth agents + 3 scanners + validation sweep + niche agents.
- Step 4b.4: Injectable example-precedent scout (Core, Thorough). One sonnet per injectable finding, writes `precedent_{id}.md`, post-processed into findings_inventory.md as new candidates or Related locations footers. Feeds the Axis 4 RAG Match precedent bonus.
- Step 4b scoring: Sonnet scoring agent writes `confidence_scores.md` (2-axis Core, 4-axis Thorough). Reads precedent output for Axis 4 bonus.
- Step 4b iter 2 gate (mechanical): `iter2_required = exists uncertain f with severity >= Medium`. Fires Devil's Advocate depth agents only when the gate passes (Thorough only).
- Step 4b iter 3 gate (mechanical): Fires iff `progress(iter_2)` = at least one uncertain Medium+ finding's composite confidence rose by >= 0.10 with NEW evidence per AD-5 (Thorough only). Otherwise remaining uncertain are forced to CONTESTED.
- Step 4b design stress: Unconditional 1-slot Design Stress Testing Agent (Thorough only).
- Step 4b fuzz (EVM Thorough): Invariant fuzz campaign + Medusa stateful fuzz in parallel.
- Step 4b.5: RAG validation sweep (Core, Thorough).
- Step 4c: Chain analysis, enabler enumeration, variable-finding cross-reference.

### Phase 5: Pre-Screen, Verification, Validation, Escalation
- Step 5 pre Step 0a: Early exit writes `prescreen_early_exit.md` (broken refs → FALSE_POSITIVE, pure trusted-actor → Low cap).
- Step 5 pre Step 0a.filter: MANDATORY orchestrator step that builds `verification_queue.md` = hypotheses.md MINUS FALSE_POSITIVE. Phase 5 verifier spawning uses the queue, not hypotheses.md.
- Step 5 pre Step 0b: Invalidation selector writes `prescreen_invalidation_hints.md` (sonnet, 2-3 hints per surviving finding).
- Step 5 pre Step 0c: External protocol research writes `prescreen_external_research.md` (sonnet, conditional on external deps).
- Step 5 pre Step 0d: MANDATORY orchestrator substitution of `{INVALIDATION_HINTS_FOR_THIS_FINDING}`, `{EXTERNAL_RESEARCH_FOR_THIS_FINDING}`, `{IF_PRESCREEN_HINTS_EXIST}` into each verifier prompt before spawn. Unsubstituted placeholders are a workflow violation.
- Step 5: Verifiers run PoCs in project test harness (Medium+ for Light / Core, all severities for Thorough).
- Step 5.1: Skeptic-Judge adversarial re-verify for HIGH / CRIT (Thorough only).
- Step 5.2: Final opus validation, one agent per surviving finding. Orchestrator enforces override protection: `[POC-PASS]` + INVALIDATED → CONTESTED.
- Step 5.5: Post-verification extraction of `[VER-NEW-*]` observations. Medium+ observations MUST re-enter Phase 5 PoC verification before flowing to 5.6 / 5.7. Low / Info get `[VER-NEW-UNVERIFIED]` and count as weak-evidence inputs for compound escalation.
- Step 5.6: Individual Low escalation (Wave 1 proposes, Wave 2 verifies).
- Step 5.7: Compound escalation of Low / Info into pairs and triples, then verify.

### Phase 6: Report Generation
- Step 6a: Index agent assigns finding IDs (Core, Thorough).
- Step 6b: Tier writer agents draft CRIT / HIGH, MEDIUM, LOW / INFO sections (Core, Thorough).
- Step 6b.5: Final Dedup Sweep (opus, unconditional, all modes). One agent reads all tier files (or the Light writer file), identifies duplicates by root cause, keeps the higher-severity survivor, merges loser locations and evidence into the survivor, and rewrites the tier files with losers removed. Writes `final_dedup.md` log.
- Step 6c: Assembler agent merges tier output with report template. Light uses 2-agent merged override plus the mandatory 6b.5 sweep between them.

---

## PART 2: PHASE 4a.NX COMBINATORIAL ANALYSIS (OVERVIEW)

Phase 4a.NX is the absorbed former skill pipeline. It runs inside the audit pipeline between Phase 3 (breadth) and Phase 4a (inventory). Its hypotheses flow into inventory as a third finding source, dedup by root cause, and enter the standard flow as `[NX-N]` findings.

### Step NX-1: EXTRACT
One sonnet agent reads `extraction/extract_agent.md` plus the language's taxonomy (`taxonomy/{LANGUAGE}.json`), pattern hints (`extraction/patterns/{hints_file}`), recon artifacts, and source files. Writes `{SCRATCHPAD}/nextup/pieces.json`.

### Step NX-2: COMBINE + ELIMINATE
Python combinator, zero LLM tokens. Runs `combinator/combine_{LANGUAGE}.py` with `pieces.json`, `k`, `--top {TOP_N}`. Writes `combos_ranked.json`. Per-language rules and weights in `combinator/rules/{LANGUAGE}.json` and `combinator/weights/{LANGUAGE}.json`. Shared BFS + scoring in `combinator/shared.py`.

### Step NX-3: HYPOTHESIZE
Skipped in Light mode. In Core (5-8 sonnet) and Thorough (8-15 sonnet), the orchestrator splits `combos_ranked.json` into batches of 10 to 15 and spawns hypothesis agents in a single parallel message. Each agent reads `hypothesis/hypothesis_agent.md`, its combo batch, and the referenced source. Priority guard: combinations that re-confirm existing breadth findings without stricter evidence are marked `INFEASIBLE-BREADTH-DUP`. Writes `hypotheses_batch_N.json`.

### Step NX-4: Investigation targets
Orchestrator-inline. Applies the routing table (Pass 1 category match, Pass 2 empty-bucket rebalance, Pass 3 imbalance redistribution) to assign each surviving combo to one of four depth domains. Writes `investigation_targets.md`.

### Step NX-5: Inject into depth
When Phase 4b spawns depth agents, each receives the relevant section of `investigation_targets.md` appended to its prompt. Empty sections skip injection.

### Downstream
- Phase 4a inventory reads `hypotheses_batch_*.json` alongside `analysis_*.md` and static-analysis promotions, dedups across sources per `prompts/{LANGUAGE}/phase4a-inventory-prompt.md` TASK 1.0, and writes `findings_inventory.md` with survivors indexed by `[XX-N]` (breadth), `[SLITHER-N]` / `[SD-N]` / `[SAN-N]` (static), or `[NX-N]` (NEXTUP) plus a `## Dedup Trail` appendix.
- Phase 4b depth agents receive investigation targets per NX-5.
- Phase 4c chain analysis, Phase 5 verification (PoC execution), Phase 5.6/5.7 escalation, and Phase 6 report treat NEXTUP-origin findings identically to breadth findings.

---

## PART 3: DETAILED LOOKUP

3 to 4 sentences per step, plus all files, tools, and datasets used.

### Audit Pipeline, Phase 0

#### Step 0a: Banner + toolchain + mode selection
Prints the NEXTUP banner, probes for required tools (`claude`, `python`, `npx`, `git`) and optional per-chain tools (`forge`, `slither`, `medusa`, `solana`, `anchor`, `trident`, `aptos`, `sui`), then asks `AskUserQuestion` for the audit mode. MODE determines the agent budget, model mix, and which later steps are skipped vs mandatory. If the user picks Compare, control jumps to Step 0e and the audit is not run.
Files: `commands/nextup.md` (wizard), `SKILL.md` (when Compare).
Tools: `AskUserQuestion`, `Bash` (toolchain probe).

#### Step 0a.2: NEXTUP combinatorial mode
Asks for the combinatorial depth of the NEXTUP seeder (k=2, k=3, k=4). This value drives Phase 4a.NX. If audit MODE is already set and NEXTUP mode is not, defaults follow MODE: Light to lightweight, Core to middleweight, Thorough to heavyw8t.
Files: `SKILL.md` (the table of k and Top-N).
Tools: `AskUserQuestion`.

#### Step 0b: Target project
Confirms the directory under audit. Never assumes the cwd silently. Sets `PROJECT_PATH` used by every downstream step.
Tools: `AskUserQuestion`.

#### Step 0c: Documentation
Asks the user for a whitepaper, spec, or URL that describes trust roles and actor permissions. Docs feed severity calibration during recon and depth. If the user declines, roles are inferred from code patterns (onlyOwner, role modifiers) and severity cannot treat admin as safe.
Tools: `AskUserQuestion`, `WebFetch` (if URL).

#### Step 0c.5: Scope
Collects either a scope file (one path per line) or free-form scope notes. Limits the set of files that breadth, depth, and inventory agents touch. Prevents wasted budget on out-of-scope code.
Tools: `AskUserQuestion`.

#### Step 0c.6: Proven-only
Optional toggle. When enabled, findings whose best evidence is `[CODE-TRACE]` (no executed PoC or fuzzer counterexample) are capped at Low in the report. Used for benchmark comparisons where only mechanically-proven issues count.
Tools: `AskUserQuestion`.

#### Step 0d: Cost estimate + confirmation
Calls `nextup.py --estimate` to compute expected agents, tokens, and API cost. Displays a formatted summary and plan-usage warnings. Forces `AskUserQuestion` confirmation before launching the pipeline. `wrapper-launch` in `$ARGUMENTS` bypasses this step (the terminal wrapper already confirmed).
Files: `nextup.py` (entry point `estimate_cost`).
Tools: `Bash`, `AskUserQuestion`.

#### Step 0e: Compare flow
Reads a past NEXTUP report and a ground truth report, diffs them, and runs the Post-Audit Improvement Protocol. Outputs alignment matrix, recall, precision, root-cause classification, and targeted methodology improvements. Does not run the audit pipeline.
Files: `rules/post-audit-improvement-protocol.md`.
Tools: `Read`.

#### Step 0.5: EVM network resolution
If `NETWORK` is set and `LANGUAGE == evm`, resolves to an RPC URL (public defaults or env vars like `$ETH_RPC_URL`). Used by Phase 1 production verification (TASK 11) and Phase 5 fork testing (`--fork-url`). If inference fails, production verification runs without fork testing.
Tools: `Bash` (env var read).

### Audit Pipeline, Phase 1

#### Step 1: Language detection
Scans the scope for `foundry.toml`, `Anchor.toml`, `Move.toml`, `Cargo.toml`, `CMakeLists.txt`, `Makefile`, `conanfile.py`, then greps for framework markers to resolve `LANGUAGE` to `evm`, `solana`, `aptos`, `sui`, or `c_cpp`. For Move, it disambiguates Aptos vs Sui by dependency strings. For Rust, it checks `#[program]` and `#[derive(Accounts)]` to set the `ANCHOR` flag. Language picks the prompts tree (`prompts/{LANGUAGE}/...`) and the skill trees for Phase 2.
Files: project manifests and source files.
Tools: `Glob`, `Grep`, `Read`.

#### Step 1b: Recon split (4 agents)
Reads `prompts/{LANGUAGE}/phase1-recon-prompt.md` (the ORCHESTRATOR SPLIT DIRECTIVE) and spawns 1A (RAG meta-buffer via `mcp__unified-vuln-db__*`), 1B (docs + external dep research), 2 (build + slither / static analysis + tests), and 3 (patterns + attack surface + template recommendations) in a single message. Writes `recon_summary.md`, `template_recommendations.md`, `attack_surface.md`, `state_variables.md`, `function_list.md`, `meta_buffer.md`. In Light mode this collapses to 2 sonnet agents and skips RAG and fork ancestry.
Files: `prompts/{LANGUAGE}/phase1-recon-prompt.md`, `prompts/{LANGUAGE}/mcp-tools-reference.md`, `prompts/{LANGUAGE}/generic-security-rules.md`, scratchpad directory.
Tools: `Agent` (general-purpose), `mcp__unified-vuln-db__*` (CSV-backed BM25 over `solodit_findings.dedup.csv`), `mcp__tavily-search__tavily_search`, `WebSearch`, `WebFetch`.
Datasets: `solodit_findings.dedup.csv` (19,370 MEDIUM + HIGH Solodit findings, 12 language shards).

#### Step 1c: Hard gate
Verifies `recon_summary.md`, `template_recommendations.md`, `attack_surface.md` exist before Phase 2 spawns. `meta_buffer.md` may be empty if the MCP is unavailable; Phase 4b.5 RAG sweep compensates via WebSearch later. Missing hard artifacts halt the pipeline and re-spawn the relevant recon agent.
Tools: `Bash` (`ls`).

### Audit Pipeline, Phase 2

#### Step 2a: Agent count sizing
Sizes the breadth spawn from complexity tiers (`<5 deps, <2000 lines` = 2 agents; `5-10 deps, 2000-5000 lines` = 4-5; `>10 deps or >5000 lines` = 5-7). Enforces minimum floor: 1 core-state, 1 access-control, 1 per major external dep. Computes a depth-budget floor from saved breadth slots: `depth_floor = 12 + (4 - actual_breadth_count)`.
Files: `recon_summary.md`, `template_recommendations.md`.

#### Step 2a.1: Merge hierarchy
If `template_recommendations.md` lists more required templates than the sized agent count, applies merges M1 to M5 (for example SEMI_TRUSTED_ROLES merges into access control). Never merges two heavy templates together. Never merges FLASH_LOAN_INTERACTION or ORACLE_ANALYSIS with anything else.
Files: `commands/nextup.md` (merge table).

#### Step 2b: Template instantiation
For each template in `template_recommendations.md`, reads `agents/skills/{LANGUAGE}/{template}/SKILL.md`, substitutes `{PLACEHOLDERS}`, and strips `<!-- LOAD_IF: FLAG -->...<!-- END_LOAD_IF: FLAG -->` blocks when the flag was not detected. Composes each agent prompt.
Files: `agents/skills/{LANGUAGE}/**/SKILL.md`.

#### Step 2b.1: Injectable skills
Reads injectable skills from `agents/skills/injectable/{skill-name}/SKILL.md`. Breadth agents get only a 1-line summary per section (under 200 tokens). Depth agents get dedicated Injectable Investigation Agents (sonnet, 1 per domain), spawned alongside the main depth agents.

Files: `agents/skills/injectable/**/SKILL.md`.

#### Step 2b.2: Real-world example backing

Many SKILL.md files (both language-tree and injectable) carry an inline `## Real-world examples` section, spliced immediately before the `## Step Execution Checklist`. Depth agents read this section as part of the skill. Each block follows a fixed template:

```
- Pattern: <one-line mechanism>
  Where it hit: <protocol / function / file>
  Severity: HIGH | MEDIUM | CRITICAL
  Source: Solodit (row_id N)  OR  <URL>
  Summary: <2-3 sentences>
  Map to: <labels from Section 0 marker seed list>
```

Coverage as of commit c5bce61 (post-wave 2 + bit-shift): ~73 skills carry the section. Sources come from two pipelines:
- Local Solodit-derived pool: per-skill regex + language filter against `solodit_findings.dedup.csv`, then a Sonnet selection agent picks 5-10 best-fitting rows and deduplicates HIGH/MEDIUM mechanism-twins. Output goes under `### From the local Solodit-derived corpus` with `row_id` citations.
- Web-sourced pool: for skills whose local pool was < 5, a WebSearch / tavily_search agent sources findings from Solodit, Cantina, Sherlock, Code4rena, OtterSec / Halborn / Neodyme / MoveBit / Zellic published audits, CVE/GHSA advisories, and protocol post-mortems. Output goes under `### From web-sourced audit reports` with verifiable URL citations.

The `## Real-world examples` section feeds two downstream consumers:
1. Phase 4b.4 precedent scout (below). The scout uses each example's `Pattern` and `Where it hit` lines as grep seeds across the scope to find other locations that may be vulnerable to the same class.
2. Phase 5 verification. The `security-verifier` agent's Step 0 consults the section first; a matched example produces the strongest precedent signal and lets the verifier skip redundant `get_similar_findings` calls.

Raw candidate pools are cached at `agents/skills/**/candidates.jsonl` but gitignored (regenerable from the CSV). The selection and web sidecars (`local_examples.md`, `web_examples.md`) are inlined into each SKILL.md and deleted after splicing.

#### Step 2c: Agent prompt structure
Assembles each agent prompt in the canonical form: role header, protocol context, task (instantiated template), targeted-sweep strategy, artifact list, output location, and the SCOPE CONTAINMENT closing directive (critical rule 5a).
Files: `rules/finding-output-format.md`, `prompts/{LANGUAGE}/generic-security-rules.md`.

#### Step 2d: Spawn manifest + verification gate
Builds `spawn_manifest.md` listing every template marked Required: YES, its assigned agent ID, and status. HALTs if any required template has no agent. After Phase 3 returns, re-checks the manifest to ensure each file was produced.
Files: `template_recommendations.md`, `spawn_manifest.md`.

### Audit Pipeline, Phase 3

#### Step 3: Parallel breadth analysis
Spawns ALL breadth agents in a single message (critical rule 5). After all return, verifies `analysis_*.md` files exist, contain findings, and applied the template methodology. Re-spawns any missing agent before Phase 4a. Orchestrator does NOT read these files (critical rule 6); the inventory agent reads them in Phase 4a.
Files: `{SCRATCHPAD}/analysis_*.md`, `spawn_manifest.md`.
Tools: `Agent`, `Bash` (`ls`).

#### Step 3b: Breadth re-scan (Thorough only)
After Phase 4a inventory produces an exclusion list, runs a sonnet re-scan loop (2-3 agents, max 2 iterations, exits on 0 new findings above Info). Targets areas that breadth may have missed because of template focus.
Files: `rules/phase3b-rescan-prompt.md`.

#### Step 3c: Per-contract analysis (Thorough only)
Runs a focused per-contract pass after re-scan. Feeds new findings back into the inventory before Phase 4a.5 starts.
Files: `rules/phase3b-rescan-prompt.md` (same prompt, later section).

### Audit Pipeline, Phase 4

#### Step 4a.NX: NEXTUP combinatorial analysis
Always runs, BEFORE inventory. Five sub-steps (see Part 2 for the compact overview and `SKILL.md` for the full reference):

- NX-1: one sonnet extraction agent reads `extraction/extract_agent.md` + taxonomy + pattern hints + recon artifacts and writes `pieces.json`.
- NX-2: Python combinator (`combinator/combine_{LANGUAGE}.py`, zero tokens) consumes `pieces.json`, emits `combos_ranked.json` with the top-N combinations of size `k`.
- NX-3 (Core: 5-8 sonnet, Thorough: 8-15 sonnet, SKIP in Light): parallel hypothesis agents read `hypothesis/hypothesis_agent.md`, their combo batch, and source. Priority guard marks combos that duplicate breadth findings as `INFEASIBLE-BREADTH-DUP`. Output: `hypotheses_batch_N.json`.
- NX-4: orchestrator-inline routing writes `investigation_targets.md`. Routing table is deterministic top-down (priority: contains D → depth-external; contains A07 → depth-edge-case; 2+ of {A,E,G} → depth-token-flow; 2+ of {C,F,H} → depth-state-trace; A+I or E+I → depth-edge-case; fallback → depth-state-trace). Pass 2 rebalances empty buckets; Pass 3 redistributes if max/min > 3.
- NX-5: when Phase 4b spawns depth agents, each receives the relevant section of `investigation_targets.md` appended to its prompt.

Failure never blocks the pipeline; extraction or combinator failure skips the rest and inventory runs on breadth + static only.

Files: `SKILL.md`, `extraction/extract_agent.md`, `hypothesis/hypothesis_agent.md`, `extraction/patterns/*.md`, `taxonomy/{LANGUAGE}.json`, `combinator/combine_{LANGUAGE}.py`, `combinator/rules/{LANGUAGE}.json`, `combinator/weights/{LANGUAGE}.json`, `combinator/shared.py`, `{SCRATCHPAD}/nextup/pieces.json`, `{SCRATCHPAD}/nextup/combos_ranked.json`, `{SCRATCHPAD}/nextup/hypotheses_batch_*.json`, `{SCRATCHPAD}/nextup/investigation_targets.md`.
Tools: `Agent`, `Bash` (Python combinator), `Read`, `Write`.

#### Step 4a: Inventory + side-effect trace + cross-source dedup
One opus agent (upgraded from sonnet on 2026-04-21 because this is the single dedup chokepoint across all finding sources). Reads all `analysis_*.md` files (breadth), `{SCRATCHPAD}/nextup/hypotheses_batch_*.json` (NEXTUP), and static-analysis promotions. Dedups across sources per TASK 1.0 priority: (1) breadth+PoC wins outright, (2) breadth-no-PoC loses only to a NEXTUP hypothesis with stricter source evidence, (3) NEXTUP-vs-NEXTUP goes by feasibility then severity then combo score, (4) static-detector survives only when alone. Losers are merged as `Related locations:` and `Puzzle-piece evidence:` footers on survivors; dropped items go into a `## Dedup Trail` appendix. Assigns IDs: breadth keeps `[XX-N]`, static uses `[SLITHER-N]` / `[SD-N]` / `[SAN-N]`, NEXTUP survivors without breadth match get `[NX-N]`. Writes `findings_inventory.md`, the side-effect trace, and `phase4_gates.md`. Gate 1 BLOCKED means missing breadth agents: must re-spawn before Step 4b.
Files: `prompts/{LANGUAGE}/phase4a-inventory-prompt.md`, `findings_inventory.md`, `phase4_gates.md`.

#### Step 4a.5: Semantic invariants (Pass 1 and Pass 2)
Pass 1 (Core, Thorough) enumerates write sites, defines semantic invariants, groups variables into clusters, flags conditional writes, mirror pairs, and time-weighted accumulation exposure. Pass 2 (Thorough only) reverses direction: for each function, which clusters does it write partially; then recursive stale-read consequence trace up to 3 levels. Output feeds depth agents so they do not re-derive invariants. Runs after Phase 4a inventory.
Files: `state_variables.md`, `function_list.md`, `semantic_invariants.md`.

#### Step 4b iter 1: Depth, scanners, niche
Spawns 4 depth agents (token-flow, state-trace, edge-case, external) with NEXTUP investigation targets injected per domain, plus 3 Blind Spot Scanners (A, B, C), 1 Validation Sweep Agent, and required niche agents from `template_recommendations.md`. Timeout split-and-retry: a timed-out agent splits into 2 lite agents (max 3 findings, no static analyzer, max 5 files). In Light mode this collapses to 4 merged sonnet agents and iteration 1 only.
Files: `prompts/{LANGUAGE}/phase4b-loop.md`, `prompts/{LANGUAGE}/phase4b-depth-templates.md`, `prompts/{LANGUAGE}/phase4b-scanner-templates.md`, `agents/depth-*.md`, `agents/skills/niche/**/SKILL.md`, `investigation_targets.md`.

#### Step 4b.4: Injectable example-precedent scout (Core, Thorough)
After each injectable investigation agent returns, spawns one sonnet precedent-scout per produced finding. The scout receives the parent finding and the parent skill's spliced `## Real-world examples` section, then sweeps the scope with Grep for OTHER locations matching the example patterns. Writes `{SCRATCHPAD}/precedent_{FINDING_ID}.md` listing HIGH-confidence candidates (new findings) and MEDIUM-confidence candidates (appended as `Related locations:` on the parent). Scout is capped at 30 Grep/Read calls per run. Skipped in Light mode since injectable investigation agents do not run there.
Files: `rules/phase4b-precedent-scout.md`, `agents/skills/injectable/**/SKILL.md` (for the examples section), `{SCRATCHPAD}/precedent_*.md`, `findings_inventory.md`.
Tools: `Agent` (general-purpose, model=sonnet), `Read`, `Grep`, `Glob`.

#### Step 4b scoring: Sonnet scoring agent
Spawns one sonnet agent that reads all depth outputs and writes `confidence_scores.md`. Core uses 2-axis (Evidence 0.5 + Analysis Quality 0.5). Thorough uses 4-axis (Evidence 0.25 + Consensus 0.25 + Analysis Quality 0.3 + RAG Match 0.2). Skipping this step to jump straight to chain analysis is a VIOLATION.
Files: `rules/phase4-confidence-scoring.md`, `confidence_scores.md`.

#### Step 4b iter 2 (Thorough only)
Mechanical gate: `iter2_required = exists uncertain f with severity in {Medium, High, Critical}`. If true, spawns Devil's Advocate depth agents for ALL uncertain Medium+ findings. Agents are structurally adversarial (DA role). Anti-dilution: evidence-only finding cards, max 5 per agent. Re-scores with new-evidence-only rule (AD-5). Classifies loop dynamics as CONTRACTIVE, OSCILLATORY, or EXPLORATORY; OSCILLATORY forces CONTESTED and exits. Skipping iter 2 when the gate is true is a workflow violation.
Files: `rules/phase4-confidence-scoring.md` (Convergence Criteria #3a).

#### Step 4b iter 3 (Thorough only)
Mechanical progress gate: `progress(iter_2) = at least one uncertain Medium+ finding's composite confidence increased by >= 0.10 with NEW evidence per AD-5`. Fires iff iter 2 ran AND progress was made AND budget is not exhausted. Forces any remaining `< 0.4` confidence findings to CONTESTED. Writes `adaptive_loop_log.md` with iteration count and exit reason.
Files: `rules/phase4-confidence-scoring.md` (Convergence Criteria #3, #3b), `adaptive_loop_log.md`.

#### Step 4b Design Stress Testing (Thorough only)
One UNCONDITIONAL reserved slot. The Design Stress Testing Agent runs regardless of budget. Tests whether the protocol's invariants hold under adversarial configuration at boundaries.
Files: `rules/phase4-confidence-scoring.md`.

#### Step 4b EVM fuzz checkpoint (Thorough, EVM only)
Two parallel agents: invariant fuzz campaign (5-min built-in timeout) and Medusa stateful fuzzer (15-min timeout). `MEDUSA_AVAILABLE` is read from `{SCRATCHPAD}/build_status.md`, where it was written by Step 0a's toolchain probe (`command -v medusa`). A missing flag is logged as `MEDUSA_UNAVAILABLE` to `violations.md`. Writes `invariant_fuzz_results.md` and `medusa_fuzz_findings.md`. Missing results without a failure reason counts as a workflow violation.
Files: `prompts/evm/phase4b-invariant-fuzz.md`, `prompts/evm/phase4b-loop.md` (Medusa section), `build_status.md`.
Tools: `forge test --match-contract Invariant`, `medusa fuzz`.

#### Step 4b.5: RAG validation sweep (Core, Thorough)
One sonnet agent. First reads `{SCRATCHPAD}/meta_buffer.md` (produced by recon Agent 1A) and reuses any matching common_vulnerabilities / attack_vectors entries — tagged `[RAG: SEED]` — to avoid redundant MCP calls. For findings not satisfied by seed reuse, runs `mcp__unified-vuln-db__*` against the local CSV-backed index. On MCP failure, falls back to WebSearch. On double failure, floors RAG scores at 0.3. Reads `{SCRATCHPAD}/rag_status.md`: if it contains `RAG_DISABLED_BY_MODE: light`, writes floor scores tagged `[RAG: LIGHT_MODE_SKIP]` without running WebSearch. Writing floor scores without attempting the sweep in Core / Thorough is a VIOLATION.
Files: `rules/phase4-confidence-scoring.md` (Phase 4b.5 section), `meta_buffer.md`, `rag_status.md`, `build_status.md`, `rag_validation.md`.
Tools: `mcp__unified-vuln-db__*` (CSV-backed), `WebSearch`, `Read`.
Datasets: `solodit_findings.dedup.csv`.

#### Step 4c: Chain analysis
2 opus agents (1 sonnet merged in Light). Step A enumerates enablers (shared state, caller-callee, capability exposure). Step B matches enablers to findings and constructs `chain_hypotheses.md`. Thorough mode runs an iteration 2 with variable-finding cross-reference.
Files: `rules/phase4c-chain-prompt.md`, `chain_hypotheses.md`.

### Audit Pipeline, Phase 5

#### Step 5 pre Step 0a: Early exit
Orchestrator inline check: for each finding, verify the referenced file and line still exist and contain the claimed code. Mark stale refs as FALSE_POSITIVE. Cap any finding whose entire attack depends on a trusted-actor action at Low. Writes `prescreen_early_exit.md`.
Files: `rules/phase5-prescreen.md`, `prescreen_early_exit.md`.
Tools: `Read`, `Grep`.

#### Step 5 pre Step 0a.filter: FALSE_POSITIVE removal (MANDATORY)
Orchestrator inline. Builds `{SCRATCHPAD}/verification_queue.md` = hypotheses.md MINUS every finding marked `EARLY_EXIT: BROKEN_REF` or `FALSE_POSITIVE`. Phase 5 spawner uses `verification_queue.md`, not hypotheses.md. FALSE_POSITIVE findings remain in hypotheses.md with their tag for the Phase 6 SUMMARY.md rejected appendix but do not consume verification budget.
Files: `verification_queue.md`, `hypotheses.md`, `prescreen_early_exit.md`.

#### Step 5 pre Step 0b: Invalidation selector
One sonnet agent, batched. Reads `rules/invalidation-library.md` and picks 2-3 most-applicable generic invalidation reasons per surviving finding. Writes `prescreen_invalidation_hints.md`.
Files: `rules/invalidation-library.md`, `rules/phase5-prescreen.md`, `prescreen_invalidation_hints.md`.

#### Step 5 pre Step 0c: External research (conditional)
0 or 1 sonnet agent. Triggered only when findings reference external protocols (Chainlink, Aave, Pendle, etc.). Verifies claims via WebSearch. Writes `prescreen_external_research.md`.
Files: `prescreen_external_research.md`.
Tools: `WebSearch`, `mcp__tavily-search__tavily_search`.

#### Step 5 pre Step 0d: Orchestrator substitution into verifier prompts (MANDATORY)
For each finding in `verification_queue.md`, orchestrator substitutes `{IF_PRESCREEN_HINTS_EXIST}`, `{INVALIDATION_HINTS_FOR_THIS_FINDING}`, and `{EXTERNAL_RESEARCH_FOR_THIS_FINDING}` into the verifier prompt before spawn. Spawning a verifier with any placeholder left unsubstituted is a workflow violation. Same substitution applies to Phase 5.2 Final Validation agents.
Files: `prompts/{LANGUAGE}/phase5-verification-prompt.md`, `prescreen_invalidation_hints.md`, `prescreen_external_research.md`, `verification_queue.md`.

#### Step 5: Verifiers
Spawns one verifier per finding in scope. Light and Core verify all Medium+. Thorough verifies ALL severities with fuzz variants. Verifier must run the PoC in the project test harness (`forge test`, `cargo test`, `pytest`, `jtx::Env`, etc.). No testnet or live submissions unless the project's own CLAUDE.md permits. Output: per-finding `verify_*.md` with verdict, evidence tag (`[POC-PASS]`, `[POC-FAIL]`, `[CODE-TRACE]`, `[CONTESTED]`), and run output.
Files: `prompts/{LANGUAGE}/phase5-verification-prompt.md`, `rules/phase5-poc-execution.md`.
Tools: native harness per language, `Bash`.

#### Step 5.1: Skeptic-Judge (Thorough only)
For every HIGH / CRITICAL finding, spawn an opus Skeptic agent with INVERSION MANDATE. If Skeptic AGREES, verdict stands. If Skeptic DISAGREES, spawn a sonnet Judge that applies "prove it or lose it": stronger mechanical evidence wins. Skipping with "all PoCs passed so skeptic is unnecessary" is invalid.
Files: `prompts/{LANGUAGE}/phase5-verification-prompt.md` (Skeptic-Judge section).

#### Step 5.2: Final opus validation
One opus agent per surviving finding (not FALSE_POSITIVE). Each renders an independent verdict: UPHELD, DOWNGRADED, INVALIDATED, CONTESTED. Override protection: `[POC-PASS]` + INVALIDATED is forced to CONTESTED. Mechanical evidence cannot be overridden by reasoning alone.
Files: `rules/phase5.2-final-validation.md`.

#### Step 5.5: Post-verification finding extraction
Orchestrator inline. Scans every `verify_*.md` for `[VER-NEW-*]` observations and assigns severity from the standard matrix. Routing: Medium+ observations MUST go through a targeted Phase 5 PoC verification pass before entering Phase 5.6 / 5.7 (the original verifier was focused on a different finding, so "trust the verifier" is not enough). Low / Info observations skip re-verification but are tagged `[VER-NEW-UNVERIFIED]` and are treated as weak-evidence inputs in Phase 5.7 compound escalation (a chain depending on them cannot be confirmed beyond Medium without Phase 5 PoC verification of the chain).
Files: `hypotheses.md`, `verify_*.md`, `prompts/{LANGUAGE}/phase5-verification-prompt.md`.

#### Step 5.6: Individual Low escalation
Wave 1: one opus agent per Low finding proposes an upgrade to Medium+ (or REJECT). Wave 2: one opus agent per proposed upgrade independently verifies. Applies CONFIRMED / PARTIAL / REJECTED. Findings upgraded to Medium+ leave the Low pool before Phase 5.7.
Files: `rules/phase5.6-individual-escalation.md`.

#### Step 5.7: Compound escalation
Builds an interaction graph of remaining Low / Info findings (shared state, same contract, caller-callee, same actor). Generates linked pairs (all modes) and triples (Core, Thorough), discards unlinked combinations. Spawns 2-5 opus agents (sonnet Light) to construct compound attack sequences where combined severity exceeds max individual severity. Survivors go through standard Phase 5 verification; Thorough HIGH / CRIT also re-runs Phase 5.1.
Files: `rules/phase5.7-compound-escalation.md`, `hypotheses.md`, `chain_hypotheses.md`.

### Audit Pipeline, Phase 6

#### Step 6a: Index agent (Core, Thorough)
One agent assigns final finding IDs (`F-01`, `F-02`, ...), orders by severity, and writes the TOC.

#### Step 6b: Tier writers (Core, Thorough)
3 agents, one per severity tier (CRIT / HIGH, MEDIUM, LOW / INFO). Each writes the tier section using `rules/report-template.md`.

#### Step 6b.5: Final Dedup Sweep (unconditional, all modes)
One opus agent reads the three tier files (or the Light single-writer file), `report_index.md`, `findings_inventory.md`, and `chain_hypotheses.md`, identifies duplicates by root cause + exploit mechanism + location overlap, and keeps the higher-severity survivor per the priority table (severity → evidence tag → location count → lowest report ID). Loser evidence (locations, attack variants) merges into the survivor. Tier files are rewritten in place with losers removed. Writes `final_dedup.md` as the audit trail. Runs between tier writers and assembler in all modes; in Light mode this is the one opus carve-out from the all-sonnet rule. If the sweep fails, the orchestrator logs to `violations.md` and proceeds to the assembler on un-deduplicated tier files (degraded mode).
Files: `rules/phase6-report-prompts.md` (Step 6b.5 section), `final_dedup.md`.

#### Step 6c: Assembler
Merges header, TOC, and tier sections (now deduplicated by Step 6b.5) into `AUDIT_REPORT.md`. Light mode replaces 6a + 6b + 6c with a sonnet writer plus sonnet assembler and the mandatory 6b.5 opus sweep between them, and includes the Light mode disclaimer. `AUDIT_REPORT.md` is the single combined report for the audit pipeline.
Files: `rules/phase6-report-prompts.md`, `rules/report-template.md`.

### Phase 4a.NX, detailed

Phase 4a.NX is the absorbed former skill pipeline. See the Phase 4 section above for the orchestrator-facing step description and `SKILL.md` for the full technical reference (schemas, routing rules, priority guard, failure handling).

The standalone filter agent (`filter/filter_agent.md`) and primer rewrite step (`primers/sherlock.md`) are retired. Their responsibilities moved into Phase 4a inventory TASK 1.0 (dedup) and Phase 6 tier writers (report style), respectively.

---

## PART 4: EXTERNAL TOOLS AND DATASETS (REFERENCE)

### MCP servers
- `mcp__unified-vuln-db__*`: local CSV-backed BM25 index over `solodit_findings.dedup.csv`. Tools include `get_similar_findings`, `get_common_vulnerabilities`, `get_attack_vectors`, `get_root_cause_analysis`, `validate_hypothesis`, `analyze_code_pattern`, `get_exploitation_requirements`, `get_reachability_evidence`, `get_controllability_evidence`, `get_impact_precedents`, `assess_hypothesis_strength`, `get_knowledge_stats`, `get_poc_template`. Two tools return `{error, fallback}`: `get_similar_exploit_code`, `get_fix_patterns`.
- `mcp__tavily-search__tavily_search`: web search fallback for recon and pre-screen.

### WebSearch / WebFetch
Generic fallbacks when the MCP is unavailable or when docs are provided as URLs.

### Language toolchains
- EVM: `forge`, `slither`, `medusa` (optional, Thorough stateful fuzz).
- Solana: `solana`, `anchor`, `trident` (optional fuzz).
- Aptos: `aptos`.
- Sui: `sui`.
- C / C++: `clang`, `cmake`, plus sanitizers when available.

### Datasets
- `solodit_findings.dedup.csv`: 19,370 MEDIUM + HIGH Solodit findings across 12 language shards. Read-only, no embeddings.

### Primers
Retired. Report style is owned by the audit pipeline's Phase 6 tier writers and `rules/report-template.md`. The `primers/sherlock.md` file is retained only for historical reference.

### Scratchpad layout
`{SCRATCHPAD}/` contains: `recon_summary.md`, `template_recommendations.md`, `attack_surface.md`, `state_variables.md`, `function_list.md`, `meta_buffer.md`, `analysis_*.md`, `spawn_manifest.md`, `findings_inventory.md`, `phase4_gates.md`, `semantic_invariants.md`, `confidence_scores.md`, `adaptive_loop_log.md`, `phase4b_manifest.md`, `invariant_fuzz_results.md`, `medusa_fuzz_findings.md`, `chain_hypotheses.md`, `hypotheses.md`, `verify_*.md`, `violations.md`, `checkpoint_postdepth.md`, `AUDIT_REPORT.md`, and the nested `nextup/` subdirectory with `pieces.json`, `combos_ranked.json`, `combo_batch_*.json`, `hypotheses_batch_*.json`, and `investigation_targets.md` for Phase 4a.NX.

---

## RULE: CHANGELOG AND PIPELINE SYNC (R8)

After writing an entry to `~/Desktop/NEXTUP SKILL/CHANGELOG.md` (R6), update this file too.

Workflow for any change under `nextup/`:
1. Append the dated CHANGELOG entry (R6, step 0 of R7).
2. For each pipeline step the change affected, update the corresponding overview line AND the detailed lookup entry in this file. This keeps `PIPELINE.md` the single authoritative map of the current pipeline.
3. If a step was added, removed, renamed, or resequenced, also re-number the surrounding overview list so the step ordering stays accurate.
4. If a file path, tool, or dataset referenced in a step changed, update the "Files:", "Tools:", or "Datasets:" lines for that step.
5. Commit `PIPELINE.md` together with the other `nextup/` paths in the same commit (R7 step 2).

A CHANGELOG entry that touches a pipeline step without a matching `PIPELINE.md` edit is an incomplete rework. Before running `git commit`, verify both files have been updated.
