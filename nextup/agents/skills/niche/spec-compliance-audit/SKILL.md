---
name: "spec-compliance-audit"
description: "Trigger HAS_DOCS flag in template_recommendations.md (recon detects non-empty DOCS_PATH - whitepaper, spec, or design doc provided) - Agent Type general-purpose (standalone nich..."
---

# Niche Agent: Spec-to-Code Compliance

> **Trigger**: `HAS_DOCS` flag in `template_recommendations.md` (recon detects non-empty DOCS_PATH - whitepaper, spec, or design doc provided)
> **Agent Type**: `general-purpose` (standalone niche agent, NOT injected into another agent)
> **Budget**: 1 depth budget slot in Phase 4b iteration 1
> **Finding prefix**: `[SPEC-N]`
> **Added in**: v9.9.5

## When This Agent Spawns

Recon Agent 1B processes DOCS_PATH (whitepaper, spec, or design doc). If docs are non-empty and contain protocol behavior claims (fee structures, token distribution, thresholds, permissions, state transitions), recon sets `HAS_DOCS` flag in the BINDING MANIFEST under `## Niche Agents`.

The orchestrator spawns this agent in Phase 4b iteration 1 alongside standard agents (1 budget slot). The agent gets a CLEAN context window with ONLY the docs and code - zero attention dilution with other findings.

## Why a Dedicated Agent

Spec compliance requires reading two large artifacts (documentation + code) and systematically comparing them. Injecting this into a breadth agent would cause severe attention dilution - the agent would either skim the docs or skip compliance checks in favor of vulnerability hunting. A dedicated agent ensures every spec claim is verified.

## Agent Prompt Template

```
Task(subagent_type="general-purpose", prompt="
You are the Spec Compliance Agent. You compare documentation claims against actual code behavior.

## Your Inputs
Read:
- The documentation file(s) at {DOCS_PATH}
- {SCRATCHPAD}/design_context.md (extracted trust assumptions)
- {SCRATCHPAD}/function_list.md (all functions)
- {SCRATCHPAD}/state_variables.md (all state variables)
- Source files in scope

## STEP 1: Extract Spec Claims

Read the documentation thoroughly. Extract every CONCRETE, TESTABLE claim into a structured list:

| # | Claim | Source Section | Claim Type | Testable? |
|---|-------|---------------|------------|-----------|

**Claim Types**:
- PARAMETER: Specific numeric value (fee = 0.3%, max supply = 1M, cooldown = 7 days)
- FLOW: Token/value flow description (fees go to treasury, rewards distributed proportionally)
- PERMISSION: Access control claim (only admin can pause, anyone can liquidate)
- INVARIANT: Protocol-wide guarantee (total shares == total assets, no negative balances)
- SEQUENCE: Operational ordering (must stake before claiming, lock before unlock)
- THRESHOLD: Boundary condition (liquidation at 80% LTV, quorum at 50%+1)

Skip vague/marketing claims ('secure', 'efficient', 'battle-tested'). Only extract claims that can be verified against code.

**Target**: 10-30 claims depending on doc depth. If docs are thin (<10 claims), note coverage gap and proceed.

## STEP 2: Verify Each Claim Against Code

For EACH extracted claim, find the corresponding code and verify:

| # | Claim | Code Location | Match? | Details |
|---|-------|-------------- |--------|---------|

**Match types**:
- MATCH: Code implements exactly what spec says
- MISMATCH: Code contradicts spec (wrong value, wrong logic, wrong recipient)
- PARTIAL: Code partially implements (some cases match, some don't)
- MISSING: Spec describes feature that code does not implement
- STRONGER: Code has stricter constraints than spec requires (usually safe)
- WEAKER: Code has looser constraints than spec states (usually a finding)

For each non-MATCH result, read the actual code and quote the specific lines.

## STEP 3: Classify Divergences

For each MISMATCH, MISSING, or WEAKER result:

1. **Impact**: What goes wrong if users trust the spec but code behaves differently?
2. **Severity**: Use standard matrix (Impact x Likelihood). Likelihood is HIGH if users/integrators would reasonably rely on the spec claim.
3. **Root cause**: Is this a doc bug (code is correct, doc is wrong) or code bug (doc is correct, code is wrong)? Report BOTH - the audit team decides.

## STEP 4: Check Inverse - Code Without Spec

Scan function_list.md for significant functions that the documentation does NOT mention:
- State-changing functions with no doc coverage
- Fee/reward mechanisms not described in docs
- Emergency/admin functions not in the trust model

These are not vulnerabilities per se, but document them as INFO findings - undocumented behavior is a trust risk.

## Output Requirements
Write to {SCRATCHPAD}/niche_spec_compliance_findings.md
Use finding IDs: [SPEC-1], [SPEC-2]...
Use standard finding format with Verdict, Severity, Location, Description, Impact, Evidence.

For each finding, include:
- **Spec Claim**: Exact quote from documentation
- **Code Reality**: Exact code behavior with file:line reference
- **Divergence Type**: MISMATCH / MISSING / WEAKER

Maximum 10 findings - prioritize by severity.

## Quality Gate
Every finding MUST cite both the spec source (section/page) AND the code location (file:line).
Findings without both references will be discarded.

Return: 'DONE: {N} spec divergences - {M} MISMATCH, {P} MISSING, {W} WEAKER, {I} undocumented behaviors'
")
```

## Integration Point

This agent's output (`niche_spec_compliance_findings.md`) is read by:
- Phase 4a inventory merge (after Phase 4b iteration 1)
- Phase 4c chain analysis (enabler enumeration - spec mismatches can enable other attacks)
- Phase 6 report writers (findings appear in the report like any other finding)
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: ERC-4626 `withdraw()` rounds shares down instead of up, violating the standard's rounding requirement for withdraw/redeem
  Where it hit: FundContract / `withdraw()`
  Severity: HIGH
  Source: Solodit (row_id 1519)
  Summary: The `withdraw()` function rounds the requested asset amount down when computing shares to burn. EIP-4626 §7 requires that `withdraw` and `redeem` round shares *up* (in the vault's favor) so that users cannot extract more assets than their shares represent. Rounding down lets callers receive slightly more assets per call than they are entitled to, draining the vault at the expense of other depositors. The fix is to substitute round-down division with round-up (ceiling) division when converting assets to shares in the withdrawal path.
  Map to: EIP_compliance, ERC4626, rounding, withdraw, previewWithdraw

- Pattern: ERC-721 `onERC721Received` callback never invoked because the contract calls `transferFrom` instead of `safeTransferFrom`
  Where it hit: OmoAgent / `depositPosition()` and `onERC721Received()`
  Severity: HIGH
  Source: Solodit (row_id 1964)
  Summary: The contract implements `onERC721Received` to execute deposit logic when an NFT arrives, but `depositPosition()` moves the token via plain `transferFrom`. EIP-721 only triggers the `onERC721Received` callback when `safeTransferFrom` is used. The result is that legitimate deposits never execute the handler, causing permanent denial-of-service for deposit functionality and any subsequent protocol actions gated on it. The fix is to replace `transferFrom` with `safeTransferFrom` at every deposit call site.
  Map to: EIP_compliance, ERC721, onERC721Received, safeTransferFrom, callback

- Pattern: EIP-712 `STRATEGY_TYPEHASH` uses `uint256` for a field typed `uint32` in the struct, plus a struct-name collision with another on-chain struct
  Where it hit: VaultImplementation.sol / IVaultImplementation.sol / `STRATEGY_TYPEHASH`
  Severity: HIGH
  Source: Solodit (row_id 13268)
  Summary: The `STRATEGY_TYPEHASH` encodes `strategistNonce` as `uint256` but the Solidity struct declares it as `uint32`. EIP-712 §11 requires the type string to match the exact Solidity type of every field; a mismatch produces a different digest than off-chain signers compute, so signatures always fail or, worse, accept incorrectly padded data. Additionally, the type string reuses the name `StrategyDetails` for a different struct already present in the ABI, violating the uniqueness requirement in EIP-712 §14. Both issues must be corrected: update the type string to `uint32` and rename one of the colliding structs.
  Map to: EIP_compliance, EIP712, typehash, domainSeparator, signature

- Pattern: ERC-20 `transfer()` return value not checked, allowing silent transfer failures to be treated as successes
  Where it hit: MerkleVesting / `withdraw()`
  Severity: HIGH
  Source: Solodit (row_id 15940)
  Summary: The `withdraw()` function calls `token.transfer(user, amount)` without inspecting the boolean return value. EIP-20 §6 specifies that compliant tokens MUST return a boolean indicating success or failure. Non-reverting ERC-20 implementations (e.g., tokens that return `false` on failure) allow the transfer to silently fail while the function records the allocation as distributed, permanently locking the user's vested tokens. The fix is to use OpenZeppelin's `SafeERC20.safeTransfer`, which checks the return value and reverts on failure.
  Map to: EIP_compliance, ERC20, return_value, safeTransfer, transfer

- Pattern: EIP-2612 domain separator cached at deployment with a fixed chain ID, enabling cross-fork signature replay
  Where it hit: ERC20Permit / `permit()`
  Severity: HIGH
  Source: Solodit (row_id 16294)
  Summary: The contract stores the `DOMAIN_SEPARATOR` as an immutable computed once at construction time using the chain ID at that moment. EIP-2612 §3 and EIP-712 §2.9 require implementations to detect chain ID changes (hard forks) and recompute the separator dynamically so signatures cannot be replayed on the fork chain. With a fixed separator, a valid permit signed on the original chain is also valid on any fork that shares the same chain ID, allowing replay attacks that drain allowances without the owner's knowledge. The fix is to check `block.chainid` on every `permit()` call and recompute the separator if it differs from the cached value, following OpenZeppelin's `EIP712._domainSeparatorV4()` pattern.
  Map to: EIP_compliance, EIP712, ERC20, EIP2612, permit, domainSeparator, replay

- Pattern: ERC-1155 calldata array offset mishandling in inline assembly corrupts `safeBatchTransferFrom` token and amount arrays
  Where it hit: ERC1155.sol / LibTransient.sol / Lifebuoy.sol
  Severity: HIGH
  Source: Solodit (row_id 2934)
  Summary: The assembly code accesses calldata array elements by adding a fixed offset to the calldata pointer. EVM ABI encoding for dynamic arrays places a length-prefixed data region at a location pointed to by an offset word, not directly at the pointer. When the pointer does not happen to coincide with the array start (e.g., arrays following other dynamic arguments), the assembly reads the wrong memory region, producing corrupted or attacker-controlled token IDs and amounts in `safeBatchTransferFrom`. The issue was fixed in Solady PR 1237 by correctly dereferencing the ABI-encoded offset before reading array elements.
  Map to: EIP_compliance, ERC1155, safeBatchTransferFrom, calldata, assembly

- Pattern: ERC-20 `approve()` called directly on non-standard tokens (e.g., USDT) that do not return a boolean, causing unconditional revert
  Where it hit: BrightPoolLenger / UniswapExchange / token approval logic
  Severity: HIGH
  Source: Solodit (row_id 8614)
  Summary: The contracts call `IERC20(token).approve(spender, amount)` and expect a `bool` return value. Mainnet USDT and several other widely used tokens omit the return value entirely, violating the EIP-20 interface the contracts assume. The ABI decoder reverts when it attempts to decode a missing return value as `bool`, making approval permanently unavailable for these tokens and blocking all downstream operations that require an allowance. The fix is to replace raw `approve` calls with OpenZeppelin's `SafeERC20.safeApprove` (or `forceApprove`), which handles non-returning tokens via low-level call inspection.
  Map to: EIP_compliance, ERC20, return_value, approve, safeApprove, USDT


