# MCP Tools Reference

> **MCP tools (`mcp__slither-analyzer__*`, `mcp__unified-vuln-db__*`) are available directly.** The servers are configured globally in `~/.claude.json` and load automatically at session start. Call them directly - no ToolSearch or loading step needed.
>
> **If a tool call fails with "No such tool available"**, it means the MCP server failed to start. Check with `claude mcp list` and restart the session.

> **MCP tools are your PRIMARY interface to Slither and the vulnerability database.** Call `mcp__slither-analyzer__*` and `mcp__unified-vuln-db__*` tools DIRECTLY - never route through Bash or CLI unless the MCP call itself has failed. This is not a preference; it is a hard requirement. CLI is the fallback, not the default.
>
> **PROHIBITED SUBSTITUTIONS**: NEVER use `mcp__farofino__slither_audit` or any `mcp__farofino__*` tool for Slither operations. `farofino` is a separate MCP server - it is NOT a substitute for `mcp__slither-analyzer__*`. The ONLY approved namespaces are `mcp__slither-analyzer__*` (for Slither) and `mcp__unified-vuln-db__*` (for vulnerability DB). Calling `farofino` instead of `slither-analyzer` is a workflow violation identical to skipping MCP entirely.

> **Mental model**: You are good at understanding INTENT and tracing LOGIC. Tools are good at EXHAUSTIVE ENUMERATION. You miss things when scanning large files manually. Tools never skip anything but can't understand intent. **Use both.**

> **MCP TIMEOUT POLICY (MANDATORY)**: When an MCP tool call returns a timeout error or fails, do NOT retry the same call. Record `[MCP: TIMEOUT]` and skip ALL remaining calls to that provider - switch immediately to fallback (code analysis, grep, WebSearch). Claude Code's default tool timeout is 60s (configurable via `MCP_TOOL_TIMEOUT` env var). You cannot cancel a pending call, but you control what happens after the error returns.

## slither-analyzer - Your Systematic Safety Net (CALL VIA MCP, NOT CLI)

### Slither Failure Policy (GLOBAL)

> Slither can permanently fail on certain projects (namespace imports like `import X as Y`, mixed compiler versions, unusual AST). When it fails, it will **never** succeed on that project - retrying wastes time.

**Recon (Phase 1)**: The recon agent probes Slither with ONE `list_contracts` call. If it fails → `SLITHER_AVAILABLE = false` for the entire audit. All Slither tasks switch to grep fallback. See `phase1-recon-prompt.md` TASK 2 for details.

**Depth agents (Phase 4b)**: If recon set `SLITHER_AVAILABLE = false` (documented in `build_status.md`), depth agents MUST NOT call any `mcp__slither-analyzer__*` tools. Use `Read` tool to read source files directly instead of `get_function_source`. Use grep for caller/callee tracing instead of `get_function_callees/callers`.

**Verification (Phase 5)**: Verifiers check `build_status.md` for Slither status. If unavailable, use `Read` tool for all source extraction.

| Tool | What It Gives You | When to Use | What You'd Miss Without It |
|------|-------------------|-------------|---------------------------|
| `list_functions(path, include_internal)` | Complete function inventory | Step 1b - before reading | Functions you accidentally skip |
| `export_call_graph(path)` | Cross-contract interaction map | Step 1b - before reading | Indirect call paths, hidden dependencies |
| `analyze_state_variables(path, contract)` | Variable lifecycle overview | Step 1b - feed to lifecycle agent | State variables you don't trace fully |
| `analyze_modifiers(path)` | Modifier application map | Step 1b - feed to access-control agent | Unused/missing modifiers |
| `run_detectors(path, detectors)` | Pattern-based issue detection | Step 3 - after reading | CEI violations, public library functions, dead code |
| `get_function_source(path, contract, function)` | Targeted source extraction | During verification | Quick reads without loading full files |
| `list_contracts(path)` | Contract inventory | Step 1b | Contracts you didn't know existed |
| `get_function_callees/callers` | Call relationships per function | During reading | Who calls what, unexpected callers |
| `find_dead_code(path)` | Unused code detection | Step 3 | Unused variables, functions, imports |
| `analyze_events(path)` | Event definitions and emissions | Step 1b | Event audit input for Core Agent 8 |

## unified-vuln-db - Your Attack Pattern Library

### Local CSV-backed Index (19,370 findings, MEDIUM + HIGH only)

All queries hit an in-process BM25 index over a curated Solodit-derived CSV. No network calls, no ChromaDB. Per-language shards (Solidity 16,814, Rust 1,194, Solana 432, Go 402, Vyper 138, Move 128, TypeScript 102, JavaScript 58, Cairo 49, Python 25, C++ 22, C 6).

| Tool | What It Gives You | When to Use |
|------|-------------------|-------------|
| `get_root_cause_analysis(bug_class)` | Summary excerpts of past findings matching the bug class | Step 1c - prime your analysis |
| `get_attack_vectors(bug_class)` | Similar findings clustered by attack mechanism | Depth agents - understand exploit mechanics |
| `analyze_code_pattern(pattern, code_context, protocol_type)` | BM25 matches with reasoning material | Step 6 - validate hypotheses |
| `validate_hypothesis(hypothesis)` | Cross-reference against known bugs | Step 6 - before verification |
| `get_similar_findings(pattern)` | Top-k BM25 row dicts | Step 6 - calibrate severity |
| `get_common_vulnerabilities(protocol_type)` | Tag/severity aggregation for a protocol type or language | Pre-depth scoping |
| `get_exploitation_requirements(vulnerability_type)` | Keyword-extracted pre-conditions | Depth reasoning |
| `get_reachability_evidence(sink_type)` / `get_controllability_evidence(input_type)` | Summary-level evidence strings | Reasoning about control paths |
| `get_impact_precedents(impact_type)` | Severity + tag distribution over matches | Severity calibration |
| `assess_hypothesis_strength(hypothesis)` | Score + strength from validate_hypothesis + severity weighting | Verification confidence |
| `get_knowledge_stats()` | Index size, by-language and by-severity breakdowns | Agent 1A readiness probe |
| `get_poc_template(bug_class, framework)` | Static PoC skeleton; `historical_examples=0` under CSV | PoC drafting |

**Unavailable under CSV** (return explicit `{error, fallback}` — use `get_similar_findings` + WebSearch instead):
- `get_similar_exploit_code(...)` — CSV has no PoC source code
- `get_fix_patterns(...)` — CSV has no recommendations or diff patches

**Bug classes** (seed terms that yield results): reentrancy, access-control, arithmetic-precision, arithmetic-overflow, oracle-manipulation, flash-loan, dos, first-depositor, share-inflation, price-manipulation, signature, front-running, governance, bridge, cross-chain, initialization, upgrade.

**Filter semantics**:
- `filters.protocol_types`: language slug (`Solidity`/`Vyper`/`Rust`/`Solana`/`Move`/`Cairo`/`Go`/`C`/`C++`/`TypeScript`/`JavaScript`/`Python`) routes to language shard; other values substring-match `protocol_category`.
- `filters.severities`: accepts `high`, `medium`; `critical`, `low`, `info` are dropped silently.
- `filters.sources`: ignored (Solodit is the only source).
- `filters.has_poc` / `has_diff`: always return empty.

**Common tags available as `filters.tag` substring**: Reentrancy, Oracle, Access Control, Flash Loan, Front-running, Price Manipulation, Logic Error, DOS, Griefing, Signature, Upgrade, Initialization, Precision Loss, Rounding, First Depositor, Share Inflation, ERC4626, Liquidation, Governance, Cross-chain, Bridge, Slippage, Timestamp, Randomness, Delegatecall.

When local results are thin (< 5 hits), expand via `mcp__tavily-search__tavily_search` or WebSearch rather than a live Solodit call.

## Static Analysis Escalation Ladder

When Slither MCP fails, use this fallback chain:

| Priority | Tool | What It Provides | When to Use |
|----------|------|-----------------|-------------|
| 1 (Primary) | `mcp__slither-analyzer__*` | Full AST analysis, call graphs, detectors | Always attempt first via probe call |
| 2 (Fallback A) | `mcp__farofino__aderyn_audit` | Rust-based static analysis, common vulns | When Slither probe fails |
| 3 (Fallback B) | `mcp__farofino__pattern_analysis` | Pattern-based detection (reentrancy, tx.origin, etc.) | Alongside Aderyn when Slither fails |
| 4 (Fallback C) | `mcp__farofino__read_contract` | Contract source reading | When Slither `get_function_source` unavailable |
| 5 (Manual) | Grep + Read tools | Manual pattern search | When all MCP tools fail |

> **Note**: `mcp__farofino__slither_audit` is NOT a substitute for `mcp__slither-analyzer__*`. The farofino Slither wrapper uses a different configuration. Only use `mcp__farofino__aderyn_audit` and `mcp__farofino__pattern_analysis` as complements.

**Recon policy**: If Slither probe fails → immediately run Aderyn + Pattern Analysis. Do not wait. Document all tool availability in `build_status.md`.

**Depth agent policy**: If `build_status.md` shows SLITHER_AVAILABLE = false, use Read tool for source extraction and Grep for caller/callee tracing. Do NOT attempt Slither MCP calls.

## tavily-search - Web Research

| Tool | What It Gives You | When to Use |
|------|-------------------|-------------|
| `mcp__tavily-search__tavily_search` | Web search results | During recon for protocol documentation, known issues |
| `mcp__tavily-search__tavily_extract` | Extract content from URLs | When documentation URL is provided by user |
| `mcp__tavily-search__tavily_research` | Deep research on topic | Understanding protocol architecture from public sources |
| `mcp__tavily-search__tavily_crawl` | Crawl site for content | Gathering comprehensive documentation from protocol site |

**Fork Ancestry usage**: Use `tavily_search` during TASK 0 to research known vulnerabilities of detected parent codebases: `tavily_search(query="{parent_name} smart contract vulnerability exploit")`. See FORK_ANCESTRY skill for methodology.

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
| Critical+High tier writer (6b) | opus | opus (no change - quality critical) |
| Medium tier writer (6b) | sonnet | sonnet (if >15 agents used) |
| Low+Info tier writer (6b) | sonnet | sonnet (if >15 agents used) |
| Assembler (6c) | sonnet (≤25 findings), sonnet (>25) | sonnet if >25 (no change) |

**Optional skill skip**: If total agent count > 15, skip optional skills (EVENT_CORRECTNESS, CENTRALIZATION_RISK) to conserve budget.
