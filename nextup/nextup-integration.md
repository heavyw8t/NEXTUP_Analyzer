# NEXTUP Integration Guide

> **For the NEXTUP orchestrator**: How to call NEXTUP combinatorial analysis as a hypothesis seeder between Phase 4a and Phase 4b.
> **Principle**: NEXTUP findings are **purely additive**. They inject investigation questions into depth agents — they never replace, override, or conflict with standard NEXTUP findings.

---

## When to Call NEXTUP

NEXTUP combinatorial analysis runs **after Phase 4a (Inventory)** completes and **before Phase 4b (Depth Loop)** begins.

```
Phase 4a: Inventory Agent → findings_inventory.md
    ↓
Phase 4a.5: Semantic Invariants (runs in parallel with NEXTUP)
    ↓
NEXTUP Seeder: Extract → Combine → investigation_targets.md
    ↓
Phase 4b: Depth Loop (depth agents receive NEXTUP targets as additive context)
```

NEXTUP and Phase 4a.5 (Semantic Invariants) can run **in parallel** — they have no dependencies on each other.

---

## How to Call NEXTUP

The NEXTUP orchestrator spawns the combinatorial analysis as a single agent call:

```
Agent(subagent_type="general-purpose", model="sonnet", prompt="
Read the skill definition at {NEXTUP_HOME}/SKILL.md and follow its instructions exactly.

Arguments: nextup-seeder {NEXTUP_MODE} {SCOPE_PATH}

Environment:
- NEXTUP_SCRATCHPAD = {SCRATCHPAD}
- The following recon artifacts are available:
  - {SCRATCHPAD}/state_variables.md
  - {SCRATCHPAD}/function_list.md
  - {SCRATCHPAD}/attack_surface.md
  - {SCRATCHPAD}/build_status.md
")
```

### Mode Selection for NEXTUP

The NEXTUP orchestrator selects combinatorial mode based on audit mode:

| NEXTUP Mode | Combinatorial Mode | Rationale |
|-------------|-------------|-----------|
| Light | `lightweight` (k=2) | Minimal budget, pairs only |
| Core | `middleweight` (k=3) | Balanced — triples catch most interaction bugs |
| Thorough | `heavyw8t` (k=4) | Maximum depth — quads find complex multi-step interactions |

No interactive mode picker in seeder mode — the NEXTUP orchestrator decides.

---

## What NEXTUP Produces

In seeder mode, NEXTUP writes one file:

```
{SCRATCHPAD}/nextup/investigation_targets.md
```

This file contains investigation questions organized by depth domain:

| Section | Target Depth Agent |
|---------|-------------------|
| `## For depth-token-flow` | depth-token-flow |
| `## For depth-state-trace` | depth-state-trace |
| `## For depth-edge-case` | depth-edge-case |
| `## For depth-external` | depth-external |

Each target has:
- **NX-{DOMAIN}-{N}** ID (e.g., NX-TF-1, NX-ST-3)
- **Pieces**: Which puzzle pieces interact
- **Shared state**: The state variables connecting them
- **Investigate**: A focused question — WHAT to investigate, not WHAT to find
- **Code refs**: Exact file:line references

---

## How to Inject Targets into Depth Agents

After NEXTUP completes, the orchestrator reads `{SCRATCHPAD}/nextup/investigation_targets.md` and appends the relevant section to each depth agent's prompt.

### Injection Template

For each depth agent prompt in Phase 4b, append:

```markdown
## Additional Investigation Targets (from NEXTUP Combinatorial Analysis)

The following interaction patterns were identified by static combination of code patterns.
These are ADDITIONAL investigation questions — investigate them alongside your standard methodology.
Do NOT skip your standard analysis to focus on these. Treat them as bonus leads.

{PASTE RELEVANT SECTION FROM investigation_targets.md}

When you investigate a NEXTUP target:
- Tag findings originating from NEXTUP targets with [NX-{ID}] in the finding title
- Use standard finding format (same as all other findings)
- Apply the same severity matrix and evidence standards
- If a NEXTUP target overlaps with something you already found via standard analysis,
  note the overlap but do NOT create a duplicate finding
```

### Domain Routing

| Depth Agent | Gets Section |
|-------------|-------------|
| depth-token-flow | `## For depth-token-flow` |
| depth-state-trace | `## For depth-state-trace` |
| depth-edge-case | `## For depth-edge-case` |
| depth-external | `## For depth-external` |

If a depth agent's section is empty (no targets for that domain), skip the injection for that agent.

---

## Additive Guarantee

NEXTUP targets are **investigation questions**, not findings. They flow through the standard NEXTUP pipeline:

1. **Depth agents** investigate NEXTUP targets alongside their standard methodology
2. **Findings** from NEXTUP targets use standard finding format with `[NX-{ID}]` tag
3. **Chain analysis** processes NEXTUP-originated findings the same as any other
4. **Verification** treats NEXTUP-originated findings identically
5. **Report** includes NEXTUP-originated findings in the standard severity tiers

### What "Additive" Means

- NEXTUP targets **never replace** standard depth agent methodology
- NEXTUP targets **never override** existing findings
- If NEXTUP suggests investigating something already covered → depth agent notes the overlap, no duplicate
- If NEXTUP suggests something the standard methodology missed → depth agent investigates it as a bonus lead
- The depth agent's standard output is never reduced or redirected by NEXTUP targets

### Deduplication

NEXTUP-originated findings may overlap with standard findings. Dedup happens naturally:

1. **Same root cause found via both paths**: Keep the one with stronger evidence. Note `[NX-{ID}]` contributed to discovery.
2. **NEXTUP target leads to genuinely new finding**: Tag as `[NX-{ID}]` in finding title. It flows through chain analysis, verification, and report normally.
3. **NEXTUP target is infeasible**: Depth agent skips it (just like any other dead-end investigation).

---

## Budget Impact

| Component | Cost | Model |
|-----------|------|-------|
| NEXTUP extraction agent | 1 agent | sonnet |
| NEXTUP combinator | 0 (Python script) | - |
| Target generation | 0 (orchestrator inline) | - |
| Depth agent injection | 0 (appended to existing prompts) | - |
| **Total additional** | **1 sonnet agent** | |

NEXTUP adds exactly 1 sonnet agent to the pipeline. All other work piggybacks on existing depth agents.

---

## Failure Handling

| Failure | Action |
|---------|--------|
| NEXTUP extraction returns 0 pieces | Log warning, skip injection, proceed with standard Phase 4b |
| NEXTUP combinator returns 0 survivors | Log warning, skip injection, proceed with standard Phase 4b |
| NEXTUP agent crashes/times out | Log warning, skip injection, proceed with standard Phase 4b |
| investigation_targets.md is empty | Skip injection, proceed with standard Phase 4b |

NEXTUP failure never blocks the pipeline. It is a best-effort enhancement.

---

## Example Orchestrator Code

```python
# After Phase 4a completes, before Phase 4b:

# Spawn NEXTUP in parallel with Phase 4a.5 (semantic invariants)
nextup_agent = Agent(
    subagent_type="general-purpose",
    model="sonnet",
    run_in_background=True,
    prompt=f"""
    Read {NEXTUP_HOME}/SKILL.md and follow its instructions.
    Arguments: nextup-seeder {nextup_mode} {scope_path}
    NEXTUP_SCRATCHPAD = {scratchpad}
    """
)

# ... spawn semantic invariant agents ...

# Before Phase 4b, check if NEXTUP completed
# If investigation_targets.md exists, read it and inject into depth prompts
# If not, proceed without NEXTUP targets
```
