---
name: "oracle-analysis"
description: "Trigger Pattern ORACLE flag (required) - Inject Into Breadth agents, depth-external, depth-edge-case"
---

# ORACLE_ANALYSIS Skill (Sui)

> **Trigger Pattern**: ORACLE flag (required)
> **Inject Into**: Breadth agents, depth-external, depth-edge-case
> **Purpose**: Analyze oracle integrations in Sui Move protocols for staleness, decimal handling, failure modes, and manipulation vectors

For every oracle the protocol consumes:

**STEP PRIORITY**: Steps 6 (Failure Modes) and 5c (Deviation Reference) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections (4a-4d, 5a) before skipping 5c or 6.

## 1. Oracle Inventory

Enumerate ALL oracle data sources the protocol reads:

| Oracle | Type | Module / Object | Functions Called | Consumers (protocol functions) | Update Frequency | Heartbeat |
|--------|------|-----------------|-----------------|-------------------------------|-----------------|-----------|
| {name} | Pyth / Switchboard V2 / Supra / Custom / On-chain TWAP | {module::function or shared object ID} | {get_price / get_price_no_older_than / etc.} | {list all} | {expected} | {documented or UNKNOWN} |

**For each oracle**: What decision does the protocol make based on this data? (pricing, liquidation threshold, reward rate, share price, swap amount, etc.)

**Sui-specific inventory checks**:
- Is the oracle data passed as a shared object parameter (`&PriceInfoObject`) or read from on-chain state?
- Does the protocol use `pyth::price_info::get_price_info_from_price_info_object()` or a wrapper?
- Are oracle objects passed by reference (`&`) or by mutable reference (`&mut`)?
- **Shared object contention**: Oracle objects like Pyth's `PriceInfoObject` are shared objects. During high-volatility periods, multiple transactions compete to read/update the same oracle object, causing transaction ordering dependencies and potential stale reads due to sequencing delays.

## 2. Staleness Analysis

For each oracle identified in Step 1:

### 2a. Staleness Checks Present?

| Oracle | Timestamp Checked? | Max Staleness Enforced? | Staleness Threshold | Clock Source | Appropriate? |
|--------|-------------------|------------------------|--------------------:|-------------|-------------|
| {name} | YES/NO | YES/NO | {seconds or NONE} | {clock::timestamp_ms / custom} | {analysis} |

**CRITICAL -- Sui uses MILLISECONDS**: `clock::timestamp_ms(clock)` returns milliseconds, not seconds. Pyth's `price.timestamp` returns seconds. If the protocol compares these without unit conversion, the staleness check is 1000x too lenient or too strict. Check for:
- `publish_time` (seconds from Pyth) vs `clock::timestamp_ms()` (milliseconds) -- MUST convert one to match the other
- Direct subtraction without unit normalization
- Constants like `MAX_STALENESS` -- is the value in seconds or milliseconds?

**Correct Sui staleness pattern**:
```move
// Pyth on Sui -- check price freshness
let price = pyth::price_info::get_price_info_from_price_info_object(price_info_object);
let price_data = price_info::get_price_feed(&price);
let current_price = price_feed::get_price(price_data);
let timestamp = price::get_timestamp(&current_price); // SECONDS
let now_ms = clock::timestamp_ms(clock); // MILLISECONDS -- Clock is shared object at 0x6
let now_s = now_ms / 1000; // Convert to seconds to match Pyth
assert!(now_s - timestamp <= MAX_STALENESS_SECONDS, E_STALE_PRICE);
```

**If NO staleness check**: What happens when the oracle returns stale data?
- [ ] Protocol uses stale price for liquidations -- unfair liquidations
- [ ] Protocol uses stale price for minting/deposits -- mispriced assets
- [ ] Protocol uses stale price for swaps -- arbitrage opportunity
- [ ] Protocol uses stale price for rewards -- incorrect distribution

### 2b. Stale Data Impact Trace

For each consumer function, trace the impact of receiving data that is {heartbeat x 2} old:

| Consumer Function | Data Used | If Stale By {X}: Impact | Severity |
|-------------------|-----------|------------------------|----------|
| {function} | {price/rate} | {specific impact} | {H/M/L} |

### 2c. Pyth-Specific Checks

| Check | Code Reference | Status |
|-------|---------------|--------|
| `get_price()` return values checked? | {location} | YES/NO |
| `price.price` validated > 0? | {location} | YES/NO |
| `price.conf` (confidence interval) checked? | {location} | YES/NO |
| `price.expo` (exponent) handled correctly? | {location} | YES/NO |
| `price.timestamp` staleness validated? | {location} | YES/NO |
| `get_price_no_older_than()` used vs manual check? | {location} | YES/NO |
| Pyth price update fee paid via `Coin<SUI>`? | {location} | YES/NO |

### 2d. Switchboard V2-Specific Checks

| Check | Code Reference | Status |
|-------|---------------|--------|
| `aggregator::latest_value()` return validated? | {location} | YES/NO |
| Result timestamp checked for staleness? | {location} | YES/NO |
| Decimal scaling applied correctly? (Switchboard custom decimals per feed) | {location} | YES/NO |
| Min response count checked? | {location} | YES/NO |
| Aggregator authority validated? | {location} | YES/NO |

### 2e. Supra-Specific Checks

| Check | Code Reference | Status |
|-------|---------------|--------|
| Price feed ID validated? | {location} | YES/NO |
| Decimal precision from feed metadata used? | {location} | YES/NO |
| Timestamp freshness checked? | {location} | YES/NO |
| Round completeness verified? | {location} | YES/NO |

## 3. Decimal Normalization Audit

For each oracle data flow:

| Oracle | Oracle Decimals / Exponent | Consumer Expects | Normalization Applied? | Correct? |
|--------|---------------------------|-----------------|----------------------|----------|
| {name} | {e.g., expo = -8 for Pyth} | {expected by math} | YES/NO | {analysis} |

**Pyth exponent handling**: Pyth returns `Price { price: i64, conf: u64, expo: i32, timestamp: u64 }`. The `expo` field is typically negative (e.g., -8 means price has 8 decimal places). Verify:
- Is `expo` read dynamically or assumed to be a fixed value?
- Is the sign of `expo` handled correctly (negative exponent = division, positive = multiplication)?
- Does `10^|expo|` computation overflow for large exponents?

**MANDATORY GREP**: Search all oracle consumer modules for hardcoded decimal constants: `1_000_000_000`, `100_000_000`, `1_000_000`, `10_000`, `1e8`, `1e6`, `1e9`, `DECIMAL`, `PRECISION`. For each hit: (1) Is this a decimal normalization constant? (2) Does it match the ACTUAL oracle's exponent? (3) If the oracle feed changes exponent, does this constant break?

**Decimal chain trace**: For each arithmetic operation using oracle data, trace the full decimal chain: `oracle_output_decimals` -> `normalization_step` -> `consumer_expected_decimals`. If any step uses a hardcoded constant rather than reading the exponent dynamically -> FINDING.

**Common Sui decimal mismatches**:
- Pyth price expo = -8, but protocol assumes -18 (or vice versa)
- SUI has 9 decimals (`MIST_PER_SUI = 1_000_000_000`)
- USDC on Sui has 6 decimals
- Cross-multiplication without normalization: `price * amount` where price and amount have different decimal bases

### 3d. Decimal Grep Sweep (MECHANICAL -- MANDATORY)
Grep ALL oracle consumer modules for `10_|decimals|PRECISION|SCALE|expo|pow`. For each match, fill:

| File:Line | Pattern | Hardcoded Value | Oracle's Actual Decimals/Expo | Match? |
|-----------|---------|-----------------|------------------------------|--------|

If ANY row shows Match=NO or oracle decimals UNKNOWN with hardcoded constant -> FINDING (R16).
Skipping this step is a Step Execution violation (x3d).

<!-- LOAD_IF: TWAP -->
## 4. TWAP-Specific Analysis

If protocol uses any TWAP oracle (on-chain pool observation, custom TWAP accumulator, etc.):

### 4a. TWAP Window Analysis

| TWAP Oracle | Window Length | Pool Liquidity | Manipulation Cost (est.) | Sufficient? |
|-------------|-------------|----------------|-------------------------|-------------|
| {oracle} | {seconds} | {USD value} | {estimated} | YES/NO |

**Rule of thumb**: TWAP window < 30 min AND pool TVL < $10M -> potentially manipulable.
**Sui-specific**: On Sui, TWAP typically relies on CLOB or AMM observation points. Check if the TWAP source is a CLOB (orderbook DEX) or AMM. CLOB TWAPs can be manipulated with limit orders that are never filled.

### 4b. TWAP Arithmetic

| Check | Status | Impact if Wrong |
|-------|--------|-----------------|
| Overflow protection on cumulative price difference? | YES/NO | {impact} |
| Geometric vs arithmetic mean -- correct for use case? | {which used} | {impact if wrong} |
| Time-weighted vs observation-count-weighted? | {which} | {manipulation vector} |
| Empty observation slots handled? | YES/NO | {impact} |

### 4c. TWAP Lagging Behavior

During rapid price movements, TWAP lags spot price. Trace:
- What happens when TWAP price is significantly lower than spot? (discounted minting/borrowing)
- What happens when TWAP price is significantly higher than spot? (premium liquidations)
- Is this lag exploitable by attackers who can predict the direction?

### 4d. TWAP Cold-Start Analysis

Check oracle behavior when history is insufficient: (1) zero snapshots, (2) single snapshot, (3) window period not yet elapsed.

| Cold-Start State | Oracle Return Value | Protocol Behavior | Exploitable? |
|------------------|--------------------:|-------------------|-------------|

For each exploitable state: can attacker act during cold-start window at manipulated price? Tag: [BOUNDARY:snapshots=0], [BOUNDARY:snapshots=1].
If TWAP returns 0 or aborts during cold-start with no fallback -> FINDING (R16, minimum Medium).
<!-- END_LOAD_IF: TWAP -->

## 5. Oracle Weight / Threshold Boundaries

For multi-oracle systems or oracle-based thresholds:

<!-- LOAD_IF: MULTI_ORACLE -->
### 5a. Multi-Oracle Systems

| Oracle System | Aggregation Method | Oracle Count | Agreement Required | What if Disagreement? |
|---------------|-------------------|-------------|-------------------|----------------------|
| {system} | Median / Mean / Weighted / First-valid | {N} | {M of N} | {fallback behavior} |

**Check**: What happens at exact threshold boundaries?
- If median of [100, 100, 101]: result = 100. Is that correct?
- If weighted average with equal weights rounds down: impact?
- If one oracle aborts: does fallback handle it gracefully?
<!-- END_LOAD_IF: MULTI_ORACLE -->

### 5b. Oracle-Based Thresholds

| Threshold | Oracle Data Used | Threshold Value | At Exact Boundary | Off-by-One? |
|-----------|-----------------|----------------|-------------------|-------------|
| {name} | {oracle field} | {value} | {behavior at exact value} | YES/NO |

**Check `>` vs `>=`**: At the exact threshold value, does the protocol behave as intended?

### 5c. Deviation Reference Point Audit

For each deviation check in the protocol (max_deviation, price_deviation, deviation_threshold, etc.):

| Parameter | Measured Against | Reference Source | Reference Manipulable? | Reference Staleable? |
|-----------|-----------------|-----------------|----------------------|---------------------|

Checks:
1. What is the deviation MEASURED AGAINST? (previous on-chain price, TWAP, external oracle, hardcoded value)
2. Is the reference point itself manipulable? (e.g., if deviation checks current vs last-recorded, and last-recorded is admin-settable -> admin can set a stale reference that makes all future prices "within deviation")
3. Can the reference become stale? (e.g., if reference is updated only on specific actions, and those actions stop occurring)
4. Is the first recorded price special? (no prior reference -> deviation check may be bypassed on first update)
Tag: `[TRACE:deviation check: current vs {reference} -> reference source: {X} -> manipulable: {Y/N}]`

## 6. Oracle Failure Modes

For each oracle, model failure scenarios:

| Failure Mode | Oracle Behavior | Protocol Response | Impact | Mitigation Present? |
|-------------|-----------------|-------------------|--------|-------------------|
| Zero return | Returns price = 0 | {what happens} | {impact} | YES/NO |
| Abort | Function call aborts | {what happens} | {impact} | YES/NO -- caught? |
| Stale (heartbeat exceeded) | Returns old data | {what happens} | {impact} | YES/NO -- staleness check? |
| Extreme value | Returns outlier | {what happens} | {impact} | YES/NO -- bounds check? |
| Negative price (Pyth i64) | Returns < 0 | {what happens} | {impact} | YES/NO -- sign check? |
| High confidence interval | conf > threshold | {what happens} | {impact} | YES/NO -- conf check? |
| Price update not called | PriceInfoObject never refreshed | {what happens} | {impact} | YES/NO -- update enforced? |

**Sui-specific failure**: Pyth on Sui requires explicit price update transactions (`pyth::update_price_feeds`). If the protocol does not enforce fresh updates before reading, prices can be arbitrarily stale. Check:
- Does the protocol call `update_price_feeds` in the same PTB before reading?
- Or does it rely on external keepers to update? If so, what if keepers stop?
- Does the protocol use `get_price_no_older_than()` which enforces freshness?

**For each unmitigated failure mode**: What is the worst-case impact? Can it lead to fund loss?

**Circuit breaker check**: Does the protocol have a mechanism to pause oracle-dependent operations if the oracle enters a failure state?

## Finding Template

```markdown
**ID**: [OR-N]
**Severity**: [based on fund impact and likelihood of oracle failure/manipulation]
**Step Execution**: check1,2,3,4,5,6 | x(reasons) | ?(uncertain)
**Rules Applied**: [R1:check, R4:check, R10:check, R16:check]
**Location**: module::function:LineN
**Title**: Oracle [issue type] in [function] enables [attack/failure]
**Description**: [Specific oracle issue with data flow trace]
**Impact**: [Quantified impact under worst-case oracle scenario]
```

## Instantiation Parameters
```
{CONTRACTS}           -- Move modules to analyze
{ORACLE_MODULES}      -- Oracle integration modules (pyth, supra, custom)
{PRICE_OBJECTS}       -- Shared oracle objects (PriceInfoObject, etc.)
{CONSUMER_FUNCTIONS}  -- Functions that read oracle data
{ORACLE_TYPE}         -- Pyth / Supra / Switchboard / Custom
{HEARTBEAT}           -- Expected update frequency
```

## Output Schema
| Field | Required | Description |
|-------|----------|-------------|
| oracle_inventory | yes | All oracle sources and consumers |
| staleness_analysis | yes | Staleness checks and impact |
| decimal_audit | yes | Decimal normalization correctness |
| failure_modes | yes | Each oracle's failure scenarios |
| finding | yes | CONFIRMED / REFUTED / CONTESTED |
| evidence | yes | Code locations with line numbers |
| step_execution | yes | Status for each step |

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sourced via WebSearch (April 2026). Maps to SKILL.md tags: oracle, pyth, switchboard, staleness, price_update_cap, multi-source, decimal, failure_modes.

---

## WEB-OR-01: Pyth `get_price_unsafe` used instead of `get_price_no_older_than`

- Severity: HIGH
- Protocol: Bluefin (Sui perpetual DEX)
- Source: MoveBit audit blog, Hackenproof audit contest (Feb 2024)
- Tags: oracle, pyth, staleness

### Description

Bluefin's `perpetual.update_oracle_price` called `pyth::get_price_unsafe` to fetch prices used in `trade`, `liquidate`, and `deleverage`. Pyth's documentation explicitly marks this function as returning a price that is not guaranteed to be current. Any delay between the last price-update transaction and the call to `get_price_unsafe` causes the protocol to act on an outdated price.

### Impact

Stale prices used in liquidation and position sizing. During volatile markets the lag between keeper updates and protocol reads can be minutes; positions may be liquidated at incorrect marks or new positions opened at stale collateral values.

### Correct Pattern

```move
// use get_price_no_older_than instead
let price = pyth::get_price_no_older_than(
    price_info_object,
    clock,
    MAX_STALENESS_SECONDS
);
```

### Reference

https://www.movebit.xyz/blog/post/Bluefin-vulnerabilities-explanation-1.html

---

## WEB-OR-02: Zero-price not rejected from Pyth feed

- Severity: HIGH
- Protocol: Bluefin (Sui perpetual DEX)
- Source: MoveBit audit blog (Feb 2024)
- Tags: oracle, pyth, failure_modes

### Description

After calling `pyth::get_price_unsafe`, Bluefin validated the sign of the price with `get_magnitude_if_positive` but did not check whether the returned price was zero. Pyth can return `price = 0` during certain feed outage conditions. A zero price would pass the non-negative check and propagate into PnL, margin, and liquidation calculations.

### Impact

Protocol-wide mispricing at zero. Any position evaluated against a zero oracle price produces infinite or zero margin ratios depending on the direction of the division, enabling unlimited borrows or blocking all liquidations.

### Correct Pattern

```move
let price = pyth::get_price_no_older_than(price_info_object, clock, MAX_STALENESS_SECONDS);
let price_val = price::get_price(&price);
assert!(price_val > 0, E_ZERO_PRICE);
```

### Reference

https://www.movebit.xyz/blog/post/Bluefin-vulnerabilities-explanation-1.html

---

## WEB-OR-03: `clock::timestamp_ms` vs Pyth `publish_time` unit mismatch causes 1000x staleness tolerance

- Severity: HIGH
- Protocol: Generic Sui Move pattern (documented in Monethic security workshop)
- Source: Monethic.io Sui Move Security Workshop writeup; Sui Move security community
- Tags: oracle, pyth, staleness

### Description

`clock::timestamp_ms(clock)` on Sui returns milliseconds. Pyth's `price::get_timestamp` returns seconds. Protocols that compare these values directly without unit conversion produce a staleness check that is 1000x too lenient: a `MAX_STALENESS = 60` constant intended to mean 60 seconds is effectively treated as 60,000 seconds (16.7 hours).

Variant: a protocol that stores `clock::timestamp_ms` in a field named `seconds`, then later divides by 1000 before comparing to a `MAX_STALENESS_SECONDS` constant that is actually in milliseconds, produces the inverse 1000x error (checks fail immediately or allow zero elapsed time).

### Impact

Intended freshness window is negated. Prices that are hours old are accepted as fresh. In lending protocols this enables borrowing against stale collateral prices; in perpetuals it enables trading at stale marks.

### Correct Pattern

```move
let publish_time_s = price::get_timestamp(&current_price); // seconds (Pyth)
let now_s = clock::timestamp_ms(clock) / 1000;             // convert ms -> s
assert!(now_s - publish_time_s <= MAX_STALENESS_SECONDS, E_STALE_PRICE);
```

### Reference

https://medium.com/@monethic/sui-move-security-workshop-writeup-material-480c5e7d1da3

---

## WEB-OR-04: Pyth confidence interval not validated, allowing high-uncertainty prices

- Severity: MEDIUM
- Protocol: Generic (confirmed in multiple Sherlock contests for EVM; directly applicable to Sui Move Pyth integrations)
- Source: Sherlock 2024-10 Debita judging (issues #548, #825); Pyth best-practices documentation
- Tags: oracle, pyth, failure_modes

### Description

Protocols that call `pyth::get_price` (or `get_price_no_older_than`) but never read `price::get_conf` accept prices regardless of Pyth's stated confidence interval. During low-liquidity or high-volatility events Pyth reports a wide `conf` value indicating the price is uncertain. Using such prices for liquidation thresholds or LTV calculations without a confidence check can cause premature or blocked liquidations.

Pyth's own best-practices documentation recommends clamping the usable price to `price +/- conf` or rejecting prices where `conf / price > threshold`.

### Impact

Premature liquidations in lending protocols (if confidence-wide price is treated as mid), or inability to liquidate undercollateralised positions (if price appears high but confidence is enormous).

### Correct Pattern

```move
let conf = price::get_conf(&current_price);
let price_val = price::get_price(&current_price) as u64;
// Reject if confidence > 1% of price
assert!(conf * 100 <= price_val, E_PRICE_UNCERTAIN);
```

### References

- https://github.com/sherlock-audit/2024-10-debita-judging/issues/548
- https://github.com/sherlock-audit/2024-10-debita-judging/issues/825
- https://docs.pyth.network/price-feeds/core/best-practices

---

## WEB-OR-05: Centralized oracle fallback with insufficient key security and no circuit breaker

- Severity: MEDIUM
- Protocol: Navi Protocol (Sui lending)
- Source: Veridise formal audit VAR_Navi-240607-Decentralized_Oracle_Integration (June 2024)
- Tags: oracle, multi-source, price_update_cap

### Description

Navi's decentralized oracle aggregates Pyth and Supra as primary sources. When both decentralized sources are unavailable it falls back to a centralized oracle controlled by an admin key. Veridise's audit identified that (1) the key-storage mechanism's security was not formally verified, (2) no minimum number of key custodians was enforced, and (3) there was no on-chain circuit breaker that would prevent the centralized fallback from being used indefinitely if the primary sources recovered but the fallback was never reverted.

An operator or compromised key holder could feed arbitrary prices through the fallback path without the on-chain protocol detecting the abuse.

### Impact

Full price oracle control by a single key. In a lending context this means arbitrary liquidations or under-collateralised borrows against any asset priced through the fallback feed.

### Reference

https://veridise.com/wp-content/uploads/2024/11/VAR_Navi-240607-Decentralized_Oracle_Integration.pdf

---

## WEB-OR-06: Single low-TVL AMM pool used as price reference, manipulable via flash swap

- Severity: HIGH
- Protocol: f(x) Protocol (Move-based; analogous pattern confirmed in Initia Move username pricing)
- Source: Solodit/Sherlock local CSV row_index 846 (f(x)) and row_index 1804 (Initia Move)
- Tags: oracle, staleness, multi-source

### Description

The f(x) Protocol oracle system compares spot prices from multiple on-chain pools against an anchor price. A pool with low TVL was included in the aggregation set. An attacker could manipulate the low-TVL pool's spot price in a single transaction to skew the aggregate, causing the system to use the manipulated price instead of the anchor.

The Initia Move variant showed the same root cause: the `usernames` module read a spot price directly from the Dex module, which was manipulable with a flash loan or large deposit. The fix in both cases was to use a TWAP or external oracle for pricing decisions.

### Impact

Collateral mispriced relative to anchor. In f(x): potential losses for depositors when manipulated collateral price inflates available borrows. In Initia: domain registrations purchasable below market rate by the attacker, with other users forced to pay inflated prices.

### Reference

Solodit local CSV rows 846 and 1804 (Move language, HIGH severity).

---

## WEB-OR-07: CLMM pool price used as oracle; arithmetic overflow in liquidity math corrupts price accounting

- Severity: CRITICAL
- Protocol: Cetus Protocol (Sui CLMM DEX, $223M exploit May 2025)
- Source: Cyfrin, Dedaub, Halborn, QuillAudits post-mortems
- Tags: oracle, switchboard (CLMM internal), price_update_cap, failure_modes

### Description

Cetus Protocol computed token deltas for add-liquidity using `checked_shlw` in `clmm_math.move`. The overflow guard compared the input `n` against `0xFFFFFFFFFFFFFFFF << 192` (a value well above the actual overflow threshold) rather than `0x1 << 192`. This allowed values that would overflow on a left-shift-by-64 to pass the check. The result was that an attacker could add minimal real tokens while the protocol recorded a very large liquidity credit. Withdrawing against that inflated credit drained real reserves.

The CLMM pool's internal price feed, derived from this corrupted liquidity math, then became the oracle price used by downstream protocols (including Scallop and other Sui lending protocols that paused post-exploit).

### Correct Fix

```move
// Vulnerable
let mask = 0xffffffffffffffff << 192;
if (n > mask) { abort }
// Fixed
let mask = 1 << 192;
if (n >= mask) { abort }
```

### Impact

$223M drained. Corrupted internal price propagated to ~15 dependent Sui DeFi protocols that paused operations.

### References

- https://www.cyfrin.io/blog/inside-the-223m-cetus-exploit-root-cause-and-impact-analysis
- https://dedaub.com/blog/the-cetus-amm-200m-hack-how-a-flawed-overflow-check-led-to-catastrophic-loss/
- https://www.halborn.com/blog/post/explained-the-cetus-hack-may-2025

---

## WEB-OR-08: Pyth `PriceInfoObject` not updated in same PTB; protocol relies on keeper freshness with no enforcement

- Severity: MEDIUM
- Protocol: Generic Sui Move pattern; documented in academic study of Sui shared objects (2406.15002)
- Source: arxiv 2406.15002 (Shared Objects in Sui); Pyth Sui integration docs
- Tags: oracle, pyth, price_update_cap, staleness

### Description

Pyth on Sui requires an explicit `pyth::update_price_feeds` call in each PTB before downstream price reads. Protocols that read `PriceInfoObject` without calling the update in the same PTB rely on external keepers to have run the update in a prior transaction. The study of shared objects on Sui found 83 `PriceInfoObject` instances accounting for 38.9% of all shared-object transactions, with most being mutable (indicating update contention). During periods of keeper lag or network congestion, the `PriceInfoObject` is not updated and `get_price_no_older_than` aborts, or `get_price_unsafe` returns a stale value.

If the protocol does not use `get_price_no_older_than` and also does not call the update itself, the stale-price window is bounded only by keeper liveness, which is not an on-chain guarantee.

### Impact

Protocol reads prices that are arbitrarily old when keepers lag. Impact is identical to WEB-OR-01 but the root cause is architectural (no PTB update) rather than a function-selection error.

### Correct Pattern

```move
// In the same PTB: call update_price_feeds first, then read
pyth::update_price_feeds(pyth_state, price_info_objects, vaas, clock);
let price = pyth::get_price_no_older_than(price_info_object, clock, MAX_STALENESS_SECONDS);
```

### References

- https://arxiv.org/html/2406.15002v1
- https://docs.pyth.network/price-feeds/core/use-real-time-data/pull-integration/sui


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Oracle Inventory | YES | check/x/? | |
| 2. Staleness Analysis | YES | check/x/? | For each oracle |
| 3. Decimal Normalization Audit | YES | check/x/? | |
| 3d. Decimal Grep Sweep | YES | check/x/? | MANDATORY mechanical step |
| 4. TWAP-Specific Analysis | IF TWAP used | check/x(N/A)/? | |
| 4d. TWAP Cold-Start Analysis | IF TWAP used | check/x(N/A)/? | Zero/single snapshot states |
| 5. Oracle Weight / Threshold Boundaries | IF multi-oracle or thresholds | check/x(N/A)/? | |
| 5c. Deviation Reference Point Audit | IF deviation checks exist | check/x(N/A)/? | Reference manipulability |
| 6. Oracle Failure Modes | YES | check/x/? | For each oracle |
