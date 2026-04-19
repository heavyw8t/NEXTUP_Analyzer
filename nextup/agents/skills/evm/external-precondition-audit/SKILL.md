---
name: "external-precondition-audit"
description: "Trigger Pattern Any external contract interaction detected in attack_surface.md - Inject Into Breadth agents (merged via M7 hierarchy)"
---

# EXTERNAL_PRECONDITION_AUDIT Skill

> **Trigger Pattern**: Any external contract interaction detected in attack_surface.md
> **Inject Into**: Breadth agents (merged via M7 hierarchy)
> **Constraint**: Interface-level inference only -- no production fetch required

For every external contract the protocol interacts with:

## 1. Interface-Level Requirement Inference

From the interface/import used by the protocol, infer what the external contract requires:

| External Function Called | Parameters Passed | Likely Preconditions (from interface) | Our Protocol Validates? |
|-------------------------|-------------------|---------------------------------------|------------------------|

**Inference method**: Read the function signature, parameter names, NatSpec comments (if any),
and common patterns for that function type. Example: `IVault.swap(FundManagement memory funds)`
-> infer that `funds.sender` must be authorized, `funds.recipient` determines where output goes.

## 2. Return Value Consumption

| External Call | Return Type | How Protocol Uses Return | Failure Mode if Return Unexpected |
|--------------|-------------|-------------------------|----------------------------------|

For each return value: what happens if it returns 0? What happens if it returns MAX?
What happens if the external call reverts?

## 3. State Dependency Mapping

| Protocol State | Depends on External State | External State Can Change Without Our Knowledge? |
|---------------|--------------------------|--------------------------------------------------|

For each dependency: model what happens when the external state changes between
our protocol's read and use.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Source: candidates.jsonl (82 rows). Selected 8 findings covering all five distinct sub-categories.

---

## Category: external_call / return_value — unchecked external call return

### Example 1 (HIGH, row 903)
*ArbitrumGateway ERC677 ignored return value*

`inboundEscrowAndCall` calls `ERC677Receiver.onTokenTransfer` and discards the boolean return. ERC677 requires the callee to signal success via that return; ignoring it means a silent failure is treated as success and the token transfer proceeds regardless. The same pattern appears in `ERC677Token.transferAndCall`, which also ignores the return of both `transfer` and `onTokenTransfer`.

Precondition violated: the external contract's interface contract obligates callers to inspect the returned boolean and revert on `false`. The protocol does not satisfy this precondition.

Tags: `external_call`, `return_value`

---

### Example 2 (MEDIUM, row 11850)
*Notional GenericToken / TreasuryAction unverified money-market return data*

`GenericToken.executeLowLevelCall` and `TreasuryAction` call external money-market `deposit`/`mint` and `redeem`/`burn` without inspecting the return data. The contracts assume all money markets revert on error, but some return an error code instead. A non-reverting failure causes the protocol to credit a deposit or redemption that never completed, potentially sending assets to users despite the underlying action having failed.

Precondition violated: the assumption that every money-market reverts on failure is not guaranteed by any interface the protocol controls.

Tags: `external_call`, `return_value`

---

## Category: paused_dep — external dependency paused or halted

### Example 3 (MEDIUM, row 10222)
*Perennial oracle provider switch bricks market on previous provider failure*

When the oracle provider is switched, the contract continues using the old provider until the last pending request for it is committed. If the previous Pyth feed stops returning valid prices before that commit happens, `Oracle._latestStale` can never advance past the switch point. The market enters a state where all user requests revert and funds are locked, with no mechanism to override after a timeout.

Precondition violated: the protocol assumes the outgoing oracle provider remains functional through the transition window. If the external dependency is degraded or sunset exactly during a switch, the assumption breaks permanently.

Tags: `paused_dep`, `rate_limit`

---

### Example 4 (MEDIUM, row 6230)
*GammaSwapLiquidityWarehouse stale feed reverts with no fallback*

`_getAssetOraclePrice` detects a stale Chainlink feed and reverts, but provides no fallback path to a secondary oracle. If the primary feed goes stale (e.g. during the 6-hour Chainlink ETH/USD delay incident) every operation that reads the price reverts, halting the contract entirely rather than degrading gracefully.

Precondition violated: the external price feed is assumed to be live at call time; there is no contingency when it is not.

Tags: `paused_dep`, `rate_limit`

---

## Category: sunset — external dependency deprecated or removed

### Example 5 (MEDIUM, row 15958)
*Bunker Protocol uses deprecated Chainlink `latestAnswer`*

`PriceOracleImplementation` calls `latestAnswer()` which Chainlink has deprecated and may stop supporting without notice. If Chainlink removes the function or it starts returning stale sentinel values, the oracle silently provides bad data or reverts, with no fallback.

Precondition violated: `latestAnswer` provides no round-completeness or staleness data; continued reliance on a deprecated API is a latent sunset risk.

Tags: `sunset`, `return_value`

---

### Example 6 (MEDIUM, row 8753)
*ChainlinkOracle treats abandoned feeds as supported*

`ChainlinkOracle.isTokenSupported()` returns `true` even when the underlying Chainlink feed has been abandoned. Downstream callers rely on this flag to decide whether to proceed with a price query. An abandoned feed returns stale or zero data; the protocol has no mechanism to detect or reject feeds that Chainlink has discontinued.

Precondition violated: `isTokenSupported` is expected to reflect the live operational state of the external feed, not merely its historical existence.

Tags: `sunset`, `return_value`

---

## Category: cross_contract_invariant — assumption about external contract state or return semantics

### Example 7 (MEDIUM, row 2639)
*DIAOracleV2SinglePriceOracle bad-data flag overwritten by second call*

`getPriceUSD18` fetches the quote token price first and sets `_isBadData = true` when that price is stale. It then fetches the base token price; if that fetch succeeds, the code overwrites `_isBadData` with `false`. The final combined price is therefore returned as valid even though one of the two inputs was flagged as bad. The cross-contract invariant -- "both inputs must be fresh for the composite price to be trusted" -- is not enforced.

Tags: `cross_contract_invariant`, `return_value`

---

### Example 8 (HIGH, row 16009)
*NFTPairWithOracle ignores INFTOracle success boolean*

`INFTOracle.get()` returns `(bool success, uint256 price)`. `NFTPairWithOracle` calls this function but uses only `price`, ignoring `success`. When `success == false` the oracle contract signals stale or invalid data; the protocol treats the returned price as authoritative regardless. This can expose lenders to loans priced on stale NFT floor data.

Precondition violated: the interface explicitly communicates validity through the `success` return value; callers are required to check it.

Tags: `cross_contract_invariant`, `return_value`, `external_call`

---

## Coverage Summary

| Sub-category | Examples |
|---|---|
| `external_call` + `return_value` (unchecked) | 1, 2, 8 |
| `paused_dep` / `rate_limit` | 3, 4 |
| `sunset` | 5, 6 |
| `cross_contract_invariant` | 7, 8 |

Note: `return_value` appears across all categories because unchecked or misread return values are the primary failure mode for external precondition violations. No standalone `rate_limit` example was present in the candidate set as a distinct finding type separate from paused/stale dependencies.


## Step Execution Checklist
| Section | Required | Completed? |
|---------|----------|------------|
| 1. Interface-Level Requirement Inference | YES | Y/N/? |
| 2. Return Value Consumption | YES | Y/N/? |
| 3. State Dependency Mapping | YES | Y/N/? |
