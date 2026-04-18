# NEXTUP - Combinatorial Puzzle-Piece Security Auditor

A novel web3 security auditing tool that finds **interaction bugs** by extracting dangerous code patterns ("puzzle pieces"), combining them statically, and using LLM reasoning only on high-priority combinations to generate exploit hypotheses.

## Core Idea

Traditional auditing scans code linearly. NEXTUP works differently:

1. **Extract** interesting code patterns (rounding, missing guards, oracle deps, loops, etc.)
2. **Combine** them into pairs/triples/quads using a Python script (zero LLM tokens)
3. **Eliminate** impossible or uninteresting combinations via static rules + graph connectivity
4. **Hypothesize** exploits from surviving combinations using LLM agents

The key insight: many exploits emerge from the **interaction** of two individually-innocent patterns, not from a single obvious bug.

## Three Modes

| Mode | k | What it does |
|------|---|-------------|
| **Lightweight** | 2 | All pairs of puzzle pieces |
| **Middleweight** | 3 | All triples |
| **Heavyw8t** | 4 | All quads |

## Pipeline

```
Phase 0: Setup (detect language, create scratchpad)
    |
Phase 1: EXTRACT (1 LLM agent reads code, outputs pieces.json)
    |
Phase 2: COMBINE + ELIMINATE (Python script, 0 LLM tokens)
    |
Phase 3: HYPOTHESIZE (N parallel LLM agents, batched)
    |
Phase 4: FILTER + DEDUP (1 LLM agent)
    |
Phase 5: REPORT
```

**Phase 2 is the differentiator** -- static elimination via graph connectivity means only combinations where pieces actually interact (shared state, dependencies, same call path) survive. Typical elimination rates: 70-95%.

## Puzzle Piece Taxonomy

45 types across 9 categories:

| Category | Examples |
|----------|---------|
| **A** Arithmetic & Precision | Floor rounding, ceil rounding, precision truncation, checked arithmetic gaps, zero passthrough |
| **B** Access Control | Owner-only, self-callback, no access control, pause gates |
| **C** State & Storage | Loop storage mutation, unbounded iteration, delete in loop, counters |
| **D** External Dependencies | Oracle price dep, staleness windows, cross-contract calls, error swallowing |
| **E** Economic Logic | First depositor path, share calculation, fee computation, slippage protection |
| **F** Control Flow | Cron batch, cancel-before-create, multi-hop chains, reply-on-error |
| **G** Token Handling | Fund verification, refund calculation, mint/burn, dust accumulation |
| **H** Ordering & Timing | Block height discrimination, maker/taker split, ID manipulation |
| **I** Invariants | Invariant preservation, balance accounting |

Each piece carries: location, state variables touched, actor, economic direction (favors_protocol/favors_user/neutral), call context, and a code snippet.

## Elimination Rules

The combinator applies these static rules (zero tokens):

| Rule | What it eliminates |
|------|-------------------|
| **Graph connectivity** | Pieces that don't form a connected graph (shared state, deps, same call path, bridge types) |
| **Actor conflict** | owner + non-owner required simultaneously |
| **Same-function duplicate** | All pieces from the exact same location |
| **Redundant rounding** | All rounding pieces with the same direction |
| **Read-only irrelevance** | All pieces in query/view functions |
| **Pure defensive** | All pieces are protective (access control, validation, invariant checks) |
| **No state overlap** | Different call contexts + no shared state + no dependencies |
| **All neutral same context** | All neutral direction, same context, no economic/oracle pieces |

## Supported Languages

- Solidity / EVM
- Rust / CosmWasm
- Move (Aptos & Sui)

## File Structure

```
nextup/
  SKILL.md                              # Orchestrator instructions
  nextup-command.md                     # Slash command entry point
  taxonomy/
    puzzle_taxonomy.json                # 45 puzzle piece types
  extraction/
    extract_agent.md                    # Extraction agent prompt
    patterns/
      rust_cosmwasm.md                  # Rust/CosmWasm pattern markers
      solidity_evm.md                   # Solidity/EVM pattern markers
      move.md                           # Move (Aptos/Sui) pattern markers
  combinator/
    combine.py                          # Zero-token combination engine
    elimination_rules.json              # Configurable elimination rules
    scoring_weights.json                # Configurable scoring weights
  hypothesis/
    hypothesis_agent.md                 # Hypothesis generation agent prompt
  filter/
    filter_agent.md                     # Filter + dedup agent prompt
  report/
    report_template.md                  # Report format template
  nextup-integration.md                 # How NEXTUP orchestrator calls combinatorial seeder
```

## Seeder Mode

NEXTUP can run its combinatorial analysis as a **hypothesis seeder** within the full audit pipeline. In this mode:

1. NEXTUP orchestrator calls the combinatorial analysis after Phase 4a (Inventory), before Phase 4b (Depth Loop)
2. NEXTUP runs extraction + combination only (no hypothesis/filter/report phases)
3. Outputs `investigation_targets.md` — focused questions routed to NEXTUP's depth agents
4. Depth agents investigate NEXTUP targets **alongside** their standard methodology
5. Any NEXTUP-originated findings are tagged `[NX-{ID}]` and flow through the standard pipeline

**Key property**: NEXTUP combinatorial analysis is purely additive. It never replaces, overrides, or conflicts with standard findings. If it fails or produces nothing, the pipeline continues normally.

| NEXTUP Mode | Combinatorial Mode | Budget |
|-------------|-------------|--------|
| Light | lightweight (k=2) | 1 sonnet agent |
| Core | middleweight (k=3) | 1 sonnet agent |
| Thorough | heavyw8t (k=4) | 1 sonnet agent |

See `nextup-integration.md` for full orchestrator integration details.

## Current State

| Component | Status |
|-----------|--------|
| Taxonomy (45 types) | Done |
| Extraction agent prompt | Done |
| Language pattern hints (3 languages) | Done |
| Combinator (combine.py) | Done + tested |
| Elimination rules (10 rules) | Done + tested |
| Scoring & ranking | Done + tested |
| Hypothesis agent prompt | Written, not yet tested end-to-end |
| Filter agent prompt | Written, not yet tested end-to-end |
| SKILL.md orchestrator (dual-mode) | Done |
| Slash command (interactive mode picker) | Done |
| NEXTUP integration (seeder mode) | Done |

**Tested on**: 12 sample pieces from Dango DEX (CosmWasm). Results:
- k=2: 66 combos -> 20 survivors (69.7% eliminated)
- k=3: 220 combos -> 26 survivors (88.2% eliminated)
- k=4: 495 combos -> 25 survivors (94.9% eliminated)

## Installation on Another Machine (Claude Code)

### Prerequisites

- Claude Code CLI installed
- Python 3.6+ (for the combinator)

### Setup

1. Copy the skill files into Claude Code's agent directory:

```bash
# Create directories
mkdir -p ~/.claude/agents/skills/nextup
mkdir -p ~/.claude/commands

# Copy all skill files (from this repo)
cp -r nextup/* ~/.claude/agents/skills/nextup/

# Copy the slash command entry point
cp nextup/nextup-command.md ~/.claude/commands/nextup.md
```

2. Verify the combinator works:

```bash
python3 ~/.claude/agents/skills/nextup/combinator/combine.py --help
# Should print: Usage: python3 combine.py <pieces.json> <k=2|3|4> <output.json> [--top N]
```

3. Test with a sample:

```bash
# Create a minimal test pieces file
echo '[{"id":"P001","type":"A01","category":"A","file":"test.rs","function":"foo","line_start":1,"line_end":1,"description":"test","state_touched":["x"],"actor":"any_user","direction":"neutral","call_context":"execute::foo","contract":"test","depends_on":[],"snippet":"x"},{"id":"P002","type":"E03","category":"E","file":"test.rs","function":"foo","line_start":5,"line_end":5,"description":"test2","state_touched":["x"],"actor":"any_user","direction":"favors_protocol","call_context":"execute::foo","contract":"test","depends_on":[],"snippet":"y"}]' > /tmp/test_nextup.json

python3 ~/.claude/agents/skills/nextup/combinator/combine.py /tmp/test_nextup.json 2 /tmp/test_out.json
# Should show: 1 combination, 1 survivor
```

### Usage

In Claude Code:

```
/nextup lightweight /path/to/smart/contracts/src
/nextup middleweight /path/to/src
/nextup heavyw8t /path/to/src
```

Or just `/nextup` to use middleweight mode on the current directory.

### Customization

- **Add puzzle piece types**: Edit `taxonomy/puzzle_taxonomy.json`
- **Tune elimination**: Edit `combinator/elimination_rules.json`
- **Tune scoring**: Edit `combinator/scoring_weights.json`
- **Add language support**: Create a new file in `extraction/patterns/`
