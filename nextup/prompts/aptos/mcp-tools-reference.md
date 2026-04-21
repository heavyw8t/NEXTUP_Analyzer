# MCP Tools Reference -- Aptos/Move

> **No Move-specific MCP servers are available.** Unlike EVM (which has Slither MCP and Farofino), the Aptos/Move ecosystem does not have dedicated MCP static analysis servers. Use CLI tools via Bash for compilation, testing, and formal verification.
>
> **MCP tools (`mcp__unified-vuln-db__*`, `mcp__tavily-search__*`) are available directly.** The servers are configured globally in `~/.claude.json` and load automatically at session start. Call them directly -- no ToolSearch or loading step needed.
>
> **If a tool call fails with "No such tool available"**, it means the MCP server failed to start. Check with `claude mcp list` and restart the session.

> **Mental model**: You are good at understanding INTENT and tracing LOGIC. Tools are good at EXHAUSTIVE ENUMERATION. You miss things when scanning large files manually. Tools never skip anything but can't understand intent. **Use both.**

> **MCP TIMEOUT POLICY (MANDATORY)**: When an MCP tool call returns a timeout error or fails, do NOT retry the same call. Record `[MCP: TIMEOUT]` and skip ALL remaining calls to that provider - switch immediately to fallback (code analysis, grep, WebSearch). Claude Code's default tool timeout is 60s (configurable via `MCP_TOOL_TIMEOUT` env var). You cannot cancel a pending call, but you control what happens after the error returns.

---

## Static Analysis Escalation Ladder for Aptos/Move

When analyzing Move code, use this tool chain in priority order:

| Priority | Tool | What It Provides | When to Use |
|----------|------|-----------------|-------------|
| 1 (Primary) | `aptos move prove` | Formal verification against spec annotations | Always attempt first if `spec` blocks exist in source |
| 2 (Fallback A) | `aptos move compile --check` | Type checking, ability verification, dependency resolution | When Move Prover fails or no spec annotations present |
| 3 (Fallback B) | Grep + Read tools | Manual pattern search, call graph tracing, ability auditing | When all CLI tools fail or for targeted analysis |

### Move Prover (`aptos move prove`)

**What it catches**: Formal property violations, arithmetic overflow/underflow (with specs), resource invariant violations, abort condition verification, loop bound violations.

**How to use**:
```bash
# Run prover on entire package
aptos move prove --package-dir {PROJECT_DIR}

# Run prover on specific module
aptos move prove --package-dir {PROJECT_DIR} --filter {module_name}
```

**Evidence level**: Move Prover violations are [CODE] evidence at highest quality. A Prover-confirmed violation is strong evidence for CONFIRMED verdict. Prover success for a relevant `spec` property is strong evidence for FALSE_POSITIVE.

**Failure modes**: The Move Prover may fail on:
- Modules without `spec` annotations (nothing to verify)
- Complex data structures (Tables, SmartVectors with nested generics)
- External module dependencies not available locally
- Timeout on complex verification conditions

**Recon policy**: Probe Move Prover with one `aptos move prove` call during TASK 2. If it fails, set `PROVER_AVAILABLE = false` in `build_status.md`. Do not retry.

### Compilation Check (`aptos move compile --check`)

**What it catches**: Type errors, ability constraint violations, missing dependencies, visibility violations, unused variables/imports.

**How to use**:
```bash
# Check compilation of entire package
aptos move compile --check --package-dir {PROJECT_DIR}

# Full compilation (generates bytecode)
aptos move compile --package-dir {PROJECT_DIR}
```

**Recon policy**: Always run `aptos move compile --check` during TASK 2, regardless of Prover availability. Compilation warnings and errors are promoted as static analysis findings.

### Build Status Documentation

The recon agent documents tool availability in `{SCRATCHPAD}/build_status.md`:

```markdown
# Build Status
- COMPILE_AVAILABLE = true/false  (aptos move compile succeeded)
- PROVER_AVAILABLE = true/false   (aptos move prove succeeded on at least one module)
- TEST_AVAILABLE = true/false     (aptos move test succeeded)
- PROVER_FAILURE_REASON = {reason if false}
- COMPILE_FAILURE_REASON = {reason if false}
```

### Manual Analysis (Grep + Read)

When CLI tools fail or for targeted analysis beyond what the compiler checks:

| Pattern | Grep Command | What It Finds |
|---------|-------------|---------------|
| Ability annotations | `has key`, `has store`, `has drop`, `has copy` | All struct ability declarations |
| Public functions | `public fun`, `public entry fun`, `public(friend) fun` | Full visibility surface |
| Friend declarations | `friend ` | Cross-module trust boundaries |
| External calls | `use 0x1::`, `use {addr}::` | Framework and third-party dependencies |
| Resource operations | `move_to`, `move_from`, `borrow_global`, `borrow_global_mut`, `exists` | Global storage access patterns |
| Object operations | `object::create_object`, `ConstructorRef`, `TransferRef`, `MintRef`, `BurnRef`, `ExtendRef`, `DeleteRef` | Object lifecycle and capability management |
| Bit shifts | `<<`, `>>` | Potential abort vectors (MR2) |
| Assertions | `assert!`, `abort` | Error handling and precondition checks |
| Randomness | `randomness::`, `#[randomness]` | Randomness API usage (AR4) |
| Dispatchable hooks | `dispatchable_fungible_asset`, `deposit_dispatch`, `withdraw_dispatch` | FA hook registration (AR2) |
| Event emissions | `event::emit` | Event correctness audit inputs |

**Depth agent policy**: Since no MCP static analyzer exists for Move, depth agents use Read tool for source extraction and Grep for caller/callee tracing. This is the standard path, not a fallback.

---

## unified-vuln-db -- Your Attack Pattern Library

### Local CSV-backed Index (19,370 findings, MEDIUM + HIGH only)

All queries hit an in-process BM25 index over a curated Solodit-derived CSV. No network, no ChromaDB. Per-language shards; for Aptos queries use `filters={"protocol_types": ["Move"]}` (128 Move rows).

| Tool | What It Gives You | When to Use |
|------|-------------------|-------------|
| `get_root_cause_analysis(bug_class)` | Summary excerpts of past findings matching the bug class | Step 1c -- prime your analysis |
| `get_attack_vectors(bug_class)` | Similar findings clustered by attack mechanism | Depth agents -- understand exploit mechanics |
| `analyze_code_pattern(pattern, code_context, protocol_type)` | BM25 matches with reasoning material | Step 6 -- validate hypotheses |
| `validate_hypothesis(hypothesis)` | Cross-reference against indexed findings | Step 6 -- before verification |
| `get_similar_findings(pattern)` | Top-k BM25 row dicts | Step 6 -- calibrate severity |
| `get_common_vulnerabilities(protocol_type)` | Tag/severity aggregation | Pre-depth scoping |
| `get_knowledge_stats()` | Index readiness probe | Agent 1A startup probe |

**Unavailable under CSV** (return explicit `{error, fallback}`):
- `get_similar_exploit_code` -- CSV has no PoC source code.
- `get_fix_patterns` -- CSV has no recommendations or diff patches.

When local results are thin (< 5 hits), expand via `mcp__tavily-search__tavily_search` or `WebSearch` rather than a live Solodit call.

**Bug classes** (seed terms): reentrancy, access-control, arithmetic-precision, oracle-manipulation, flash-loan, dos, ability-misuse, bit-shift-overflow.

**Aptos-specific query tips**: The index is EVM-heavy (16,814 Solidity rows) but patterns transfer. Frame queries by underlying pattern:
- Ability misuse -> `get_root_cause_analysis(bug_class='access-control')` + search for "copy"/"drop".
- Bit-shift overflow -> `get_attack_vectors(bug_class='arithmetic-precision')`.
- Type confusion -> `get_root_cause_analysis(bug_class='access-control')` + "type" keywords.
- Ref lifecycle -> `get_attack_vectors(bug_class='access-control')` + "capability"/"permission".
- "resource access control" -> access-control.
- "oracle price manipulation" -> oracle-manipulation.
- "donation attack threshold manipulation" -> dos.

**Common tags available via `filters.tag` substring**: Reentrancy, Oracle, Access Control, Flash Loan, Front-running, Price Manipulation, Logic Error, DOS, Griefing, Signature, Upgrade, Initialization, Precision Loss, Rounding, First Depositor, Share Inflation, ERC4626, Liquidation, Governance, Cross-chain, Bridge, Slippage, Timestamp, Randomness, Delegatecall.

**Aptos/Move-relevant tags**: Move, Aptos, Ability, Bit Shift, FungibleAsset, Object, Resource, Type Safety, Module Upgrade, Capability.

> **Note**: The index is Solidity-heavy. For Move/Aptos-specific patterns, supplement `get_similar_findings` with `tavily_search` for Aptos vulnerability disclosures, Move security blog posts, and Aptos framework changelog entries.

---

## tavily-search -- Web Research

| Tool | What It Gives You | When to Use |
|------|-------------------|-------------|
| `mcp__tavily-search__tavily_search` | Web search results | During recon for protocol documentation, known issues, Aptos-specific vulnerabilities |
| `mcp__tavily-search__tavily_extract` | Extract content from URLs | When documentation URL is provided by user |
| `mcp__tavily-search__tavily_research` | Deep research on topic | Understanding protocol architecture from public sources |
| `mcp__tavily-search__tavily_crawl` | Crawl site for content | Gathering comprehensive documentation from protocol site |

**Fork Ancestry usage**: Use `tavily_search` during TASK 0 to research known vulnerabilities of detected parent codebases: `tavily_search(query="{parent_name} Move smart contract vulnerability exploit")`. See FORK_ANCESTRY skill for methodology.

**Aptos-specific research queries**:
- `"Aptos Move security vulnerability {pattern}"` -- for Move-specific vuln patterns
- `"aptos-framework changelog breaking changes"` -- for framework dependency risks
- `"Move Prover formal verification {module_pattern}"` -- for verification approaches
- `"Aptos object model security"` -- for Object/resource model risks
- `"dispatchable fungible asset hook security"` -- for FA dispatch hook patterns

---

## Cascaded Model Selection Reference

| Task Type | Default Model | Budget Degradation (>15 agents) |
|-----------|--------------|--------------------------------|
| Scoring agent | sonnet | sonnet (no change) |
| Index agent (6a) | sonnet | sonnet (no change) |
| Breadth agents | sonnet | sonnet (no change) |
| Depth agents | specialized (depth-*) | specialized (no change) |
| Blind spot scanners | sonnet (general-purpose) | sonnet (no change) |
| Validation sweep | sonnet (general-purpose) | sonnet (no change) |
| Critical+High tier writer (6b) | opus | opus (no change -- quality critical) |
| Medium tier writer (6b) | sonnet | sonnet (if >15 agents used) |
| Low+Info tier writer (6b) | sonnet | sonnet (if >15 agents used) |
| Assembler (6c) | sonnet (<=25 findings), sonnet (>25) | sonnet if >25 (no change) |

**Optional skill skip**: If total agent count > 15, skip optional skills (EVENT_CORRECTNESS, CENTRALIZATION_RISK) to conserve budget.

---

## MCP Failure Policy -- Aptos Summary

| Scenario | Action |
|----------|--------|
| Move Prover fails (no specs, prover error) | Set `PROVER_AVAILABLE = false`, all analysis via Read + Grep |
| `aptos move compile` fails | Set `COMPILE_AVAILABLE = false`, analyze source directly via Read |
| `aptos move test` fails | Set `TEST_AVAILABLE = false`, verifiers write PoC tests but note compilation failure |
| unified-vuln-db MCP fails | Document failure, proceed without RAG (RAG_Match axis = 0.3 floor) |
| tavily-search MCP fails | Document failure, proceed without web research |
| All MCP tools fail | Full audit proceeds via Read + Grep tools only -- document in build_status.md |

**Key difference from EVM**: There is no Slither equivalent for Move. The entire static analysis pipeline relies on Move Prover (formal verification) and compile-time checks. When these fail, manual pattern search via Grep is the ONLY fallback. This makes thorough manual source review even more critical for Move audits.
