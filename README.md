# NEXTUP

Combinatorial puzzle-piece security auditor for web3 codebases. NEXTUP finds interaction bugs by extracting dangerous code patterns ("puzzle pieces"), combining them statically, and applying LLM reasoning only to high-priority combinations that survive elimination.

Current version: 1.2.0 (CSV-backed vuln DB; retires ChromaDB + live Solodit API). See `CHANGELOG.md` for the full history.

## Core Idea

Traditional auditors scan code linearly. NEXTUP does not.

1. Extract interesting code patterns (rounding, missing guards, oracle deps, PDA seeds, Move abilities, memory aliasing, etc.).
2. Combine them into pairs, triples, or quads using a Python script (zero LLM tokens).
3. Eliminate impossible or uninteresting combinations via static rules and graph connectivity.
4. Hypothesize exploits from the surviving combinations using LLM agents.

Many exploits emerge from the interaction of two individually-innocent patterns, not a single obvious bug. Phase 2 (static elimination via graph connectivity) keeps only combinations where the pieces actually interact through shared state, dependencies, or the same call path. Typical elimination rates are 70 to 95 percent.

## Modes

| Mode | k | Description |
|------|---|-------------|
| Lightweight | 2 | All pairs |
| Middleweight | 3 | All triples |
| Heavyw8t | 4 | All quads |

## Supported Languages (v1.1.0)

The puzzle-piece taxonomy is forked per language. Piece type ids are language-prefixed (`EVM-D03`, `SOL-K07`, `APT-J02`, `SUI-O04`, `CXX-M11`).

| Language | Taxonomy file | Piece types |
|----------|--------------|-------------|
| Solidity / EVM | `nextup/taxonomy/evm.json` | 63 |
| Solana | `nextup/taxonomy/solana.json` | 87 |
| Move / Aptos | `nextup/taxonomy/aptos.json` | 70 |
| Move / Sui | `nextup/taxonomy/sui.json` | 63 |
| C / C++ | `nextup/taxonomy/c_cpp.json` | 48 |

Total: 331 types. Each language taxonomy inherits the relevant subset of the shared A-I categories (arithmetic, access, state, deps, economics, control, tokens, ordering, invariants) and adds native J+ categories.

- EVM: proxy, assembly, reentrancy variants.
- Solana: account model, PDA, CPI, rent, sysvar, Token-2022.
- Aptos: abilities, resources, FungibleAsset, entry/access, back-call reentry.
- Sui: object model, PTB, package versioning, dynamic fields, capabilities.
- C/C++: memory safety, aliasing, concurrency, input validation, UB, resource management.

Piece `direction` enum: `{favors_protocol, favors_user, neutral}` for DeFi-style languages, plus `{exploitable, latent}` for C/C++.

Canonical per-language contract: `nextup/taxonomy/_schema.md`. Design rationale per language: `nextup/taxonomy/_design/{language}_design.md`.

## Pipeline (Standalone Combinator)

```
Phase 0: Setup (detect language, create scratchpad)
Phase 1: EXTRACT    (1 LLM agent reads code, outputs pieces.json)
Phase 2: COMBINE + ELIMINATE  (combine_{language}.py, 0 LLM tokens)
Phase 3: HYPOTHESIZE (N parallel LLM agents, batched)
Phase 4: FILTER + DEDUP (1 LLM agent)
Phase 5: REPORT
```

Phase 2 is the differentiator. Static elimination via graph connectivity keeps only combinations where pieces actually interact.

## Elimination Rules (per language)

The combinator applies these static rules with zero tokens:

| Rule | What it eliminates |
|------|-------------------|
| Graph connectivity | Pieces that do not form a connected graph over shared state, deps, same call path, or bridge types |
| Actor conflict | owner and non-owner required simultaneously |
| Same-function duplicate | All pieces from the exact same location |
| Redundant rounding | All rounding pieces with the same direction |
| Read-only irrelevance | All pieces in query or view functions |
| Pure defensive | All pieces are protective (access control, validation, invariant checks) |
| No state overlap | Different call contexts and no shared state and no dependencies |
| All neutral same context | All neutral direction, same context, no economic or oracle pieces |

Language-specific custom rules live in `combinator/rules/{language}.json` and their implementations in `combinator/combine_{language}.py`. See `CHANGELOG.md` for the current set; some heuristics were removed in the 2026-04-18 rework because they dropped real combos based on metadata the extractor rarely emits.

## Seeder Mode (Integrated with Full Audit)

NEXTUP can also run its combinatorial analysis as a hypothesis seeder inside the full audit pipeline. The orchestrator calls the combinator between Phase 4a (Inventory) and Phase 4b (Depth Loop). Surviving combinations become `investigation_targets.md` questions routed to depth agents by domain (NX-TF-* token flow, NX-ST-* state trace, NX-EC-* edge case, NX-EX-* external).

| NEXTUP audit mode | Combinator mode | Budget |
|-------------------|-----------------|--------|
| Light | lightweight (k=2) | 1 sonnet agent |
| Core | middleweight (k=3) | 1 sonnet agent |
| Thorough | heavyw8t (k=4) | 1 sonnet agent |

Seeder mode is purely additive. If it fails or produces nothing, the pipeline continues. See `nextup/SKILL.md` for the full orchestrator contract and `nextup/nextup-integration.md` for integration details.

## Injectable Skills

Protocol-specific skills under `nextup/agents/skills/injectable/` are injected into depth agents when recon detects matching triggers (e.g. `aave-integration` activates on `IPool`, `scaledBalanceOf`, `flashLoan`). Each skill declares its protocol-type trigger keywords, injection targets (which depth agents it augments), finding prefix, language, sibling-skill relationships, and an Orchestrator Decomposition Guide mapping sections to depth domains.

Every injectable skill starts with a mandatory "0. Taxonomy Pre-Search" step. The depth agent reads the matching `taxonomy/{language}.json`, greps `types[].markers` for domain keywords, tags any finding with both the skill prefix and the taxonomy id (e.g. `[AAV-N] (taxonomy: EVM-D03 ...)`), and affirmatively dismisses every in-scope marker that produced no finding.

Coverage as of v1.1.0:

- EVM (17 skills): Aave, account abstraction, DEX integration, EigenLayer, governance attack vectors, LayerZero, lending protocols, liquid staking, Morpho, NFT protocol, outcome determinism, Permit2, Uniswap V4 hooks, vault accounting, vault integration, vault security.
- Solana (14 skills): bonding-curve launchpad, CLMM pool, compressed NFT, Drift perps, Jito MEV bundles, Jupiter aggregator, Kamino, Marginfi, Metaplex NFT, Pyth oracle, Solana LST, SPL stake pool, Squads multisig, Switchboard oracle.
- Cross-chain (1 skill): Wormhole bridge.

## Trace Mode (Optional)

Post-hoc finding lifecycle tracer. When enabled (`/nextup ... trace: true` or selected in the wizard), one haiku agent runs after Phase 6 and reconstructs each finding's full lifecycle from scratchpad files into `{PROJECT_ROOT}/AUDIT_TRACE.md` (origin, evolution, keep or drop reason). When disabled (default), zero extra tokens are spent and `rules/trace-mode.md` is never read.

## File Structure

```
NEXTUP SKILL/
  README.md                               (this file)
  CHANGELOG.md                            (gitignored, per-machine local log)
  nextup/
    CLAUDE.md                             NEXTUP policy block to append to ~/.claude/CLAUDE.md
    SKILL.md                              Orchestrator instructions + non-negotiable rules (R1-R7)
    nextup-command.md                     Slash command entry point
    nextup-integration.md                 Seeder mode contract
    nextup.py                             CLI launcher (terminal wrapper)
    VERSION                               1.1.0
    taxonomy/
      _schema.md                          Canonical per-language contract
      _design/{language}_design.md        Authoring record per language
      evm.json, solana.json, aptos.json, sui.json, c_cpp.json
    combinator/
      shared.py                           BFS connectivity, scoring scaffold, CLI harness
      combine_{language}.py               Per-language combinator
      rules/{language}.json               Declarative elimination rules
      weights/{language}.json             Scoring weights
    extraction/
      extract_agent.md
      patterns/{language}.md              Pattern hints per language
    hypothesis/, filter/, report/         Standalone-mode agents
    rules/                                Shared pipeline rules (phases 3b through 6)
    prompts/{language}/                   Language-specific phase prompts
    agents/
      depth-*.md                          Depth agent definitions
      skills/injectable/{skill}/SKILL.md  Protocol-specific skills (EVM + Solana + cross-chain)
    primers/                              Report primers (Sherlock, etc.)
```

## Installation on a New Machine

NEXTUP lives in a single repo. The Claude Code global directory (`~/.claude/`) only needs thin wrappers pointing at the repo clone. No `cp -r`, no duplicated state, no drift.

### Prerequisites

- Claude Code CLI.
- Python 3.8 or later.
- Python deps for the CLI wrapper: `pip install -r nextup/requirements.txt` (just `rich` and `InquirerPy`).
- For Thorough mode on EVM projects: Foundry (`forge`) and optionally Medusa. Other chains need their own toolchains.

### Steps

1. Clone the repo. The default `NEXTUP_HOME` is `~/Desktop/NEXTUP SKILL/nextup`. If you clone somewhere else, substitute your path in every step below and in the `NEXTUP_HOME` line you will add to `~/.claude/CLAUDE.md`.

```
git clone <repo-url> ~/Desktop/NEXTUP\ SKILL
cd ~/Desktop/NEXTUP\ SKILL
pip install -r nextup/requirements.txt
```

2. Symlink the wrapper. The slash command and the CLI launcher should read directly from the repo, not be copied.

```
REPO="$HOME/Desktop/NEXTUP SKILL"
mkdir -p ~/.claude/commands
ln -sf "$REPO/nextup/nextup-command.md" ~/.claude/commands/nextup.md
ln -sf "$REPO/nextup/nextup.py"         ~/.claude/nextup.py
```

After this, any change you pull in the repo is live immediately. There is nothing else to sync.

3. Append the NEXTUP policy block to `~/.claude/CLAUDE.md`. This block declares `NEXTUP_HOME`, the audit modes table, the critical rules, and the reference-file paths that the orchestrator reads.

```
# at the top of the appended block, add:
# > NEXTUP_HOME: ~/Desktop/NEXTUP SKILL/nextup - all paths below are relative to this root unless fully qualified.
# > Path convention: {NEXTUP_HOME} = ~/Desktop/NEXTUP SKILL/nextup. Resolve before passing to agents.

cat "$REPO/nextup/CLAUDE.md" >> ~/.claude/CLAUDE.md
```

Then open `~/.claude/CLAUDE.md` and:

- Insert the `NEXTUP_HOME` line just under the `# NEXTUP` heading, with your actual path if it differs from the default.
- In the CRITICAL RULES list, set rule 10 to your platform: `LINUX PLATFORM - Use forward slashes for paths` or the Windows equivalent (the repo ships the Windows variant by default in `nextup/CLAUDE.md`).

4. Verify.

```
python3 ~/.claude/nextup.py --help
python3 "$REPO/nextup/combinator/combine_evm.py" --help
```

Both should print usage without error. In Claude Code, run `/nextup` and confirm the wizard loads the current mode and path prompts.

### Uninstall

```
rm ~/.claude/commands/nextup.md ~/.claude/nextup.py
```

Then remove the NEXTUP block from `~/.claude/CLAUDE.md`. The repo is untouched.

### Multi-machine sync

The wrapper is just symlinks, so `git pull` in the repo updates every machine pointed at it. Note that `CHANGELOG.md` is gitignored by design (R6 policy, personal local log), so each machine keeps its own changelog and the repo tree stays clean.

## Usage

```
/nextup                                            full interactive wizard
/nextup light                                      Light mode, pick path in wizard
/nextup core /path/to/src                          Core mode, path set
/nextup thorough /path/to/src                      Thorough mode
/nextup thorough /path/to/src trace: true proven-only: true
```

Shortcuts and arg parsing are documented in `nextup/nextup-command.md` under "Step 0: Interactive Setup Wizard" and "Step 0a.3: Trace Mode".

## Customisation

- Add puzzle piece types: edit the relevant `nextup/taxonomy/{language}.json`.
- Tune elimination: edit `nextup/combinator/rules/{language}.json` for declarative rules, or edit the `extra_eliminate` function in `nextup/combinator/combine_{language}.py` for custom heuristics.
- Tune scoring: edit `nextup/combinator/weights/{language}.json`.
- Add a new injectable skill: create `nextup/agents/skills/injectable/{skill-name}/SKILL.md` using any existing skill as a template. Declare the protocol-type trigger, injection targets, finding prefix, and Orchestrator Decomposition Guide, and include the mandatory "0. Taxonomy Pre-Search" section that reads the matching `taxonomy/{language}.json`.
- Add a new language: add `taxonomy/{language}.json` (following `_schema.md`), `combinator/combine_{language}.py` (following an existing script), `combinator/rules/{language}.json`, `combinator/weights/{language}.json`, `extraction/patterns/{language}.md`, and a `prompts/{language}/` tree. Then wire the language name into `SKILL.md` Step 0b and `nextup-command.md`.

## Current State and Policy

- Working rules live in `nextup/SKILL.md` as R1 through R7. Notably, R6 and R7 together require that every commit touching `nextup/` is preceded by an appended `CHANGELOG.md` entry and followed by `git pull --rebase` + selective `git add` + `git commit` + `git push`.
- `CHANGELOG.md` is the source of truth for what changed, when, and why. It is gitignored by design.
- Detailed component status and rework history live in `CHANGELOG.md`. See the latest dated entry for active work.
