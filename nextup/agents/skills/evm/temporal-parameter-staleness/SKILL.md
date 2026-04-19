---
name: "temporal-parameter-staleness"
description: "Type Thought-template (instantiate before use) - Research basis Cached parameters in multi-step operations become stale when governance changes them mid-operation"
---

# Skill: Temporal Parameter Staleness Analysis

> **Type**: Thought-template (instantiate before use)
> **Research basis**: Cached parameters in multi-step operations become stale when governance changes them mid-operation

## Trigger Patterns
```
interval|epoch|period|duration|delay|cooldown|lockPeriod|timelock|
unbondingPeriod|claimDelay|withdrawDelay|maturityTime
```

## Reasoning Template

### Step 1: Enumerate Multi-Step Operations

Find all operations that span multiple transactions:

| Operation | Step 1 (Initiate) | Wait Condition | Step N (Complete) |
|-----------|-------------------|----------------|-------------------|
| {op_name} | {initiate_fn}() | {wait_condition} | {complete_fn}() |

For each multi-step operation:
- What parameters are read/cached at Step 1?
- What parameters are re-read at Step N?
- What parameters are used but NOT re-read at Step N?

### Step 2: Identify Cached Parameters

For each parameter used across steps:

| Parameter | Read At Step | Cached? | Governance-Changeable? | Re-Validated At Completion? |
|-----------|-------------|---------|------------------------|----------------------------|
| {param} | initiate() L{N} | YES/NO | YES/NO | YES/NO |

**Red flags**: Parameter is cached at Step 1 AND governance-changeable AND NOT re-validated at Step N.

### Step 3: Model Staleness Impact

For each cached parameter that can become stale:

```
Scenario A: Parameter INCREASES between steps
1. User initiates at Step 1 with param = X
2. Governance changes param to X + delta
3. User completes at Step N
4. Impact: {what happens with stale value X when current is X + delta}

Scenario B: Parameter DECREASES between steps
1. User initiates at Step 1 with param = X
2. Governance changes param to X - delta
3. User completes at Step N
4. Impact: {what happens with stale value X when current is X - delta}
```

**BOTH directions are mandatory** -- increase and decrease often have different impacts.

### Step 3b: Update Source Audit
For each parameter updated from an external source:
- Is the source (e.g., balanceOf, oracle, timestamp) the correct
  representation of what this parameter tracks?
- Should this parameter be fixed for a period (e.g., per epoch, per
  cycle) rather than continuously refreshed?
- Which functions update it? Which functions SHOULD update it?
  Any mismatch?

### Step 4: Retroactive Application Analysis

For fee/rate parameters that apply to existing state:

| Parameter | Applies To | Retroactive? | Impact |
|-----------|-----------|--------------|--------|
| {fee_param} | {what it affects} | YES/NO | {if retroactive: who is harmed} |

**Pattern**: Fee changes that affect already-accrued rewards or already-initiated operations are retroactive.

### Step 5: Assess Severity

For each staleness issue:
- **Who is affected?** (single user, all users with pending operations, protocol)
- **Is the impact bounded?** (capped by fee range, max delay, etc.)
- **Can it be exploited intentionally?** (governance front-running)
- **Is there a recovery path?** (re-initiate, admin override)

## Key Questions (must answer all)

1. What multi-step operations exist? (request/claim, deposit/lock/withdraw, propose/vote/execute)
2. For each cached parameter: can governance change it between steps?
3. What happens if a delay DECREASES after initiation? (users locked longer than necessary)
4. What happens if a delay INCREASES after initiation? (users can claim too early)
5. Are fees applied retroactively to existing positions or only to new ones?
6. Is there a maximum parameter range that bounds the staleness impact?

## Common False Positives

- **Immutable parameters**: If the parameter cannot be changed after deployment, no staleness
- **Bounded ranges**: If min/max bounds limit the change magnitude, impact may be Low
- **User can re-initiate**: If users can cancel and restart with new parameters, reduced severity
- **Timelock protection**: If parameter changes require timelock, users have time to react

## Instantiation Parameters
```
{CONTRACTS}           - Contracts to analyze
{MULTI_STEP_OPS}      - Identified multi-step operations
{CACHED_PARAMS}       - Parameters cached at initiation
{GOVERNANCE_PARAMS}   - Governance-changeable parameters
{DELAY_PARAMS}        - Delay/cooldown parameters
{FEE_PARAMS}          - Fee/rate parameters that may apply retroactively
```

## Output Schema
| Field | Required | Description |
|-------|----------|-------------|
| multi_step_ops | yes | List of multi-step operations found |
| cached_params | yes | Parameters cached across steps |
| staleness_vectors | yes | How cached params can become stale |
| retroactive_fees | yes | Fees applied retroactively |
| finding | yes | CONFIRMED / REFUTED / CONTESTED |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | Status for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> 10 selected from candidates.jsonl (45 rows). Covers all 5 distinct categories.
> Tags: staleness | stale_cache | totalAssets_drift | exchange_rate_lag | epoch_boundary

---

## Example 1 — Stale Oracle Price (HIGH)

**Category**: `staleness`
**Severity**: HIGH
**row_index**: 4444

**Pattern**: Lending market integrates a third-party price oracle without checking the freshness of the price feed. No `publishTime` or `updatedAt` comparison is performed before the price is consumed. Stale prices allow users to exploit outdated valuations.

**Root cause**: Missing staleness check on oracle price consumption. The fix added a comparison of `publishTime` against a configurable staleness factor before using the returned price.

**Skill steps triggered**: Step 3b (update source audit — is the source the correct representation?), Step 5 (governance-front-running / exploit intentionality).

---

## Example 2 — Stale Oracle Price, No Freshness Check (MEDIUM)

**Category**: `staleness`
**Severity**: MEDIUM
**row_index**: 674

**Pattern**: `ChainlinkFeedLibrary.getPrice()` calls `latestRoundData()` but ignores the returned `updatedAt` timestamp. Any price feed that has not updated within the oracle's heartbeat window returns a stale price without any revert or fallback.

**Root cause**: `updatedAt` field from `latestRoundData` is present but never compared to a staleness threshold. Fix: check `block.timestamp - updatedAt <= MAX_STALENESS` before consuming the price.

**Skill steps triggered**: Step 2 (cached parameter re-validation at consumption site), Step 3 (parameter decrease scenario: oracle goes stale after a market event, protocol uses last known high/low price).

---

## Example 3 — Stale Chainlink Price Enables Mint/Redeem Arbitrage (MEDIUM)

**Category**: `staleness`
**Severity**: MEDIUM
**row_index**: 854

**Pattern**: Redeemer and Minter contracts use Chainlink oracles for stablecoin prices without verifying `updatedAt` freshness. An attacker observes a stale price, mints VUSD at the lower stale price, then redeems for a different stablecoin priced at market rate, draining protocol assets.

**Root cause**: No maximum staleness threshold check in the price consumption path. Recommended fix: `require(block.timestamp - updatedAt <= STALENESS_THRESHOLD)` in both Redeemer and Minter.

**Skill steps triggered**: Step 3 (Scenario A: price of borrowed asset appears artificially low due to stale feed), Step 5 (can it be exploited intentionally — yes, attacker times the call during a stale window).

---

## Example 4 — Pyth getPriceUnsafe No Staleness, Forced Liquidations (MEDIUM)

**Category**: `staleness`
**Severity**: MEDIUM
**row_index**: 3287

**Pattern**: Pyth integration uses `getPriceUnsafe()` which returns the last stored price with its timestamp regardless of how old it is. The protocol does not check whether the returned price is fresh. During periods where Pyth data is not pushed, significantly outdated prices may be used for collateral valuation, enabling forced liquidations or undercollateralised borrows.

**Root cause**: `getPriceUnsafe()` is documented to return stale data; the caller must validate `publishTime`. The fix implemented a staleness check plus a fallback oracle, and deployed an off-chain bot to push fresh Pyth data on-chain.

**Skill steps triggered**: Step 3b (is `getPriceUnsafe()` the correct update source for this parameter?), Step 5 (who is affected: all borrowers with pending positions when the feed goes stale).

---

## Example 5 — Two-Oracle Chain, Staleness Checked on Only One Feed (MEDIUM)

**Category**: `exchange_rate_lag`
**Severity**: MEDIUM
**row_index**: 2920
**protocol_category**: Lending

**Pattern**: `EETHPriceAdapter.latestRoundData()` composes two Chainlink oracles to price eETH in USD. The consuming function `PriceOracle::getAssetPriceFromChainlink` checks staleness on only one of the two feeds, leaving the second feed's timestamp unchecked. A stale second feed produces an invalid composite price without triggering a revert.

**Root cause**: Staleness validation is applied to the first oracle in the chain but not propagated to the second. Fix: add an independent `updatedAt` staleness check for each oracle in the composition path.

**Skill steps triggered**: Step 2 (multi-step parameter cache: first feed validated, second feed cached without re-validation), Step 3b (is the composition of two feeds the correct representation of eETH/USD?).

---

## Example 6 — Mismatched Heartbeat for Two-Feed Adaptor (MEDIUM)

**Category**: `exchange_rate_lag`
**Severity**: MEDIUM
**row_index**: 11930
**protocol_category**: Lending
**tag**: Oracle; Chainlink

**Pattern**: `chainlinkAdaptor` uses a single `heartbeat` constant to validate freshness for both a USDC/USD feed (24-hour heartbeat) and an asset/USD feed (1-hour heartbeat). Using the slower heartbeat for the faster feed allows up to 23 hours of stale data from the asset feed; using the faster heartbeat for the slower feed causes near-constant revert/downtime for the USDC feed.

**Root cause**: Shared staleness threshold does not accommodate feeds with different update cadences. Fix: assign a per-feed heartbeat and check each independently.

**Skill steps triggered**: Step 2 (two governance-changeable parameters — per-feed heartbeat — absent from the contract), Step 3 (Scenario A: fast feed stale for 22 hours, slow feed threshold applied — no revert, stale price consumed).

---

## Example 7 — Redstone Pull-Oracle Cache Staleness Prevents Timely Update (MEDIUM)

**Category**: `stale_cache`
**Severity**: MEDIUM
**row_index**: 6744

**Pattern**: `RedstoneCoreOracle` caches a price locally. The `updatePrice` function can only be called when `block.timestamp > cacheUpdatedAt + maxCacheStaleness`. A logic bug means the combined staleness check (`cacheStaleness AND priceStaleness`) is evaluated incorrectly, blocking `updatePrice` from being called even when the cache is genuinely stale. This causes the adapter to serve an outdated price until the compound condition clears.

**Root cause**: The gate condition for `updatePrice` should allow invocation whenever `block.timestamp > cacheUpdatedAt`, but the implementation ORs/ANDs the two staleness conditions incorrectly. Fix: allow `updatePrice` whenever either staleness window is exceeded, or remove local caching in favour of direct pull-oracle reads.

**Skill steps triggered**: Step 3b (which functions update the cached parameter? which functions SHOULD update it? any mismatch?), Step 4 (does the stale cache apply retroactively to all borrows/collateral valuations outstanding at query time?).

---

## Example 8 — Swap Fee Computed from Outdated Price (MEDIUM)

**Category**: `stale_cache`
**Severity**: MEDIUM
**row_index**: 1998

**Pattern**: `SwapOperations.swapExactTokensForTokens` and `swapTokensForExactTokens` accept `_priceUpdateData` but only push the updated price at the inner `_swap` call. Fee calculation in `getSwapFee()` runs before the price is updated, so it consumes the price that was current at the previous transaction, not the one supplied by the caller.

**Root cause**: The price update call is ordered after (not before) the fee calculation. Fix: force price update in all external entry points before any fee or slippage calculation, or add a staleness check inside `getSwapFee()`.

**Skill steps triggered**: Step 1 (multi-step: price supplied → fee computed → swap executed; price is only applied at step 3), Step 2 (fee parameter is cached from prior state, not re-read from the freshly supplied data).

---

## Example 9 — TWAP Oracle Unaware of Elapsed Time, Post-Downtime Stale Price (MEDIUM)

**Category**: `epoch_boundary`
**Severity**: MEDIUM
**row_index**: 14915
**protocol_category**: Dexes; CDP; Services; Cross Chain; RWA

**Pattern**: `reserves()`, `sampleReserves()`, and `sampleSupply()` functions that back the TWAP oracle for `$CANTO` do not use `block.timestamp` and have no awareness of how much time has elapsed since the last observation. During a network outage or sequencer pause, the last observation window can be arbitrarily long. On restart, an attacker queues a borrow transaction that uses the stale TWAP price, which may be far above market, to borrow stablecoins at an inflated collateral value.

**Root cause**: TWAP implementation lacks a maximum observation age check. Fix: track average observation duration; if any sample observation is significantly longer than the average, refuse to return a price or flag the sample as unreliable.

**Skill steps triggered**: Step 3 (Scenario A: price stays high during downtime, attacker borrows against inflated collateral), Step 5 (intentional exploit: attacker times the borrow for the first available block after an outage).

---

## Example 10 — Epoch Boundary Staleness: poolUpkeep Skips Intervals on Backlog (MEDIUM)

**Category**: `epoch_boundary`
**Severity**: MEDIUM
**row_index**: 16055
**protocol_category**: Dexes; CDP; Yield; Services; Derivatives

**Pattern**: `LeveragedPool.poolUpkeep()` is the function that advances the pool through update intervals and executes queued commitments. When the pool has fallen behind by multiple intervals (e.g., keeper was offline), the first call sets `lastPriceTimestamp = block.timestamp`. The second call immediately hits `require(intervalPassed())` which fails because `block.timestamp` has not advanced. All commitments queued during the missed intervals remain unprocessed, and `updateIntervalId` lags indefinitely.

**Root cause**: `lastPriceTimestamp` is set to `block.timestamp` before all backlogged intervals are drained. The fix redesigns the logic so that `lastPriceTimestamp` advances by one interval per upkeep call and `executePriceChange()` is called only once per series of backlogged commitments.

**Skill steps triggered**: Step 1 (multi-step: queue commitment → wait interval → execute; the "wait interval" check uses `lastPriceTimestamp` which becomes stale mid-drain), Step 3 (Scenario B: effective interval grows unboundedly when upkeep is behind, users locked longer than the protocol's stated interval).


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Enumerate Multi-Step Operations | YES | | |
| 2. Identify Cached Parameters | YES | | |
| 3. Model Staleness Impact (both directions) | YES | | |
| 3b. Update Source Audit | YES | | |
| 4. Retroactive Application Analysis | YES | | |
| 5. Assess Severity | YES | | |

### Cross-Reference Markers

**After Step 2**: If cached parameters are governance-changeable -> MUST complete Step 3 with BOTH increase and decrease scenarios.

**After Step 4**: Cross-reference with SEMI_TRUSTED_ROLES.md for admin functions that change these parameters.
