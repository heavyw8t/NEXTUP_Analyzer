---
name: "cross-chain-timing"
description: "Type Thought-template (instantiate before use) - Research basis Multi-block arbitrage windows, bridge latency exploitation"
---

# Skill: Cross-Chain Timing Analysis

> **Type**: Thought-template (instantiate before use)
> **Research basis**: Multi-block arbitrage windows, bridge latency exploitation

## Trigger Patterns
```
bridge|L1|L2|tunnel|messenger|crossChain|sendMessage|receiveMessage|
_processMessageFrom|LayerZero|CCIP|Wormhole|Arbitrum|Optimism
```

## Reasoning Template

### Step 1: Identify Sync Mechanism
- Find all cross-chain messaging calls in {CONTRACTS}
- For each call, determine:
  - What state is being synced? (rates, balances, epochs, totals)
  - What triggers the sync? (every operation, periodic, manual)
  - What bridge/messenger is used?

### Step 2: Measure Timing Window
- Research {BRIDGE_PROTOCOL} documentation for realistic latency
- Typical ranges: optimistic rollups (10-30 min), zk-rollups (minutes), standard bridges (20-60 min)
- Document: submission -> finality -> execution timeline

### Step 3: Trace Stale State Usage
- From {SYNC_POINT}, identify all state that depends on synced values
- For each dependent operation at {DEPENDENT_FUNCTIONS}:
  - Is fresh state required or is stale acceptable?
  - What decisions are made with potentially stale data?

### Step 4: Model Arbitrage Sequence
```
1. Attacker monitors {SOURCE_CHAIN} for state changes at {MONITOR_POINT}
2. State change triggers sync message (latency window opens)
3. Attacker executes on {DEST_CHAIN} at {EXPLOIT_FUNCTION} using stale {STALE_STATE}
4. Sync message arrives, state updates
5. Attacker profits: {PROFIT_CALCULATION}
```

### Step 5: Quantify Viability
- Maximum {STALE_STATE} delta during sync window: {MAX_DELTA}
- Profit calculation: {PROFIT_FORMULA}
- Cost calculation: gas + bridge fees + capital lockup
- Viable if: profit > cost AND repeatable

## Key Questions (must answer all)
1. What is the realistic sync latency for {BRIDGE_PROTOCOL}? (cite documentation)
2. Can an attacker monitor {SOURCE_CHAIN} and front-run sync on {DEST_CHAIN}?
3. What is the maximum {STALE_STATE} change during normal operation?
4. Is this attack repeatable or one-time?

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Sourced from Sherlock, Code4rena, and Cyfrin audit reports (2023-2025).
> Tags map to SKILL.md instantiation parameters.

---

## Finding 1: LayerZero Ordered Delivery Failure Blocks Channel (DoS / stuck funds)

- Source: Sherlock — sherlock-audit/2025-05-lend-audit-contest-judging, Issue #695
- Severity: Medium
- Tags: cross_chain_timing, bridge_delay, L1_L2_sync

Summary: The CrossChainRouter._send() function configures LayerZero's ordered execution mode by overriding `_acceptNonce` and `nextNonce`, but omits the required `addExecutorOrderedExecutionOption` in the `_options` bytes passed to `_lzSend`. When two users send cross-chain messages whose nonces resolve to the same value, the second message's `_origin.nonce` fails the `require(_origin.nonce == inboundNonce + 1)` guard, permanently blocking the LayerZero channel. Subsequent messages queue behind a stuck nonce and cannot execute.

Attack sequence:
1. User A and User B submit cross-chain borrow transactions near-simultaneously.
2. `nextNonce()` returns the same value for both (nonce 1).
3. Message A executes; `inboundNonce` increments to 1.
4. Message B arrives with `_origin.nonce == 1`; the channel requires nonce 2 and reverts.
5. All future messages are blocked; user funds become unwithdrawable.

Root cause: `bridge_delay` + nonce mis-ordering under concurrent load.
Fix: Pass `addExecutorOrderedExecutionOption` in every `_lzSend` call when ordered delivery is configured.

---

## Finding 2: LayerZero Message Replay Without Nonce Tracking (unlimited borrow exploit)

- Source: Sherlock — sherlock-audit/2025-05-lend-audit-contest-judging, Issue #7
- Severity: High
- Tags: cross_chain_timing, bridge_delay

Summary: The CrossChainRouter processes incoming LayerZero `BorrowCrossChain` messages with no replay-protection map (no nonce, GUID, or `processedMessages` mapping). An attacker re-broadcasts a previously delivered payload; the destination chain mints and transfers new tokens on each replay, with no limit on how many times the message can be submitted.

Attack sequence:
1. Legitimate user sends a cross-chain borrow; message is delivered and executed.
2. Attacker captures the signed LayerZero packet from the source chain.
3. Attacker calls the LayerZero endpoint's `deliver` / relayer interface to re-submit the same payload.
4. Each delivery mints fresh tokens on the destination chain; attacker drains the lending pool.

Root cause: Missing replay guard on message receipt — timing window is perpetual rather than bounded.
Fix: Store a `processedGuids` mapping; revert if `guid` was already processed.

---

## Finding 3: Cross-Chain Liquidation Race (double-liquidation via state sync lag)

- Source: Sherlock — sherlock-audit/2025-07-malda-judging, Issue #18
- Severity: High
- Tags: cross_chain_timing, L1_L2_sync, finality

Summary: `mErc20Host._liquidateExternal` does not validate whether the borrower's cross-chain collateral state is in sync before executing a liquidation. Because cross-chain state messages have non-zero latency, an attacker can trigger liquidation on two chains simultaneously for the same undercollateralised position, seizing more collateral than the debt justifies.

Attack sequence:
1. Borrower becomes undercollateralised on Chain A (500 USDC shortfall).
2. Attacker calls liquidation on Chain A — 500 USDC collateral seized, message queued to Chain B.
3. Before the sync message arrives on Chain B, attacker calls liquidation on Chain B with stale state showing the position still undercollateralised.
4. Chain B seizes a further 500 USDC; borrower loses 1000 USDC for a 500 USDC debt.

Root cause: No in-flight liquidation lock or cross-chain state version check at `_liquidateExternal`.
Fix: Implement a global liquidation cooldown flag that persists until the cross-chain state sync confirms the updated position.

---

## Finding 4: Liquidation Helper Reads Stale Stored Balances (missed liquidation opportunities)

- Source: Sherlock — sherlock-audit/2025-07-malda-judging, Issue #8
- Severity: Medium
- Tags: cross_chain_timing, finality

Summary: The liquidation helper contract returns stored balance data without first calling `accrueInterest`. Liquidation bots query this helper to decide whether a position is eligible; because interest has not been accrued, the returned debt figure is lower than the true value, causing bots to skip liquidations that should execute, accumulating bad debt.

Root cause: Cross-chain balance snapshots are not refreshed before being served to external callers. Any latency between interest accrual on the source chain and the helper's cached read creates a window where insolvent positions appear solvent.
Fix: Call `accrueInterest` on all markets before computing the liquidation eligibility check, or explicitly document staleness and require callers to accrue first.

---

## Finding 5: Swap Deadline Calculated from Execution Time, Not Submission Time

- Source: Sherlock — sherlock-audit/2025-05-dodo-cross-chain-dex-judging, Issue #308
- Severity: Medium
- Tags: cross_chain_timing, bridge_delay, epoch_race

Summary: In DODO's cross-chain DEX (ZetaChain), the swap deadline is set inside the destination-chain execution handler using `block.timestamp + offset` rather than being supplied by the user at submission time on the source chain. Cross-chain bridge latency (10 to 60 minutes depending on the path) shifts the effective deadline window entirely into the future relative to when the user agreed to the price. An attacker or MEV searcher can delay relaying the message until market conditions diverge substantially from the user's original price expectation, then execute the swap with an unexpired deadline at an unfavourable rate.

Root cause: Deadline passed across the bridge reflects execution time, not user intent time. The bridge latency is the timing window.
Fix: Have the user specify an absolute `deadline` timestamp on the source chain, encode it in the cross-chain message payload, and enforce it verbatim on the destination chain.

---

## Finding 6: No L2 Sequencer Uptime Check Causes Stale Oracle Prices After Downtime

- Source: Sherlock — sherlock-audit/2024-04-interest-rate-model-judging, Issue #88; Code4rena — code-423n4/2024-07-benddao-findings, Issue #24
- Severity: Medium
- Tags: cross_chain_timing, L1_L2_sync, finality

Summary: Contracts deployed on Optimism and Arbitrum that consume Chainlink price feeds do not verify the L2 Sequencer Uptime Feed before accepting oracle data. When the sequencer goes down, Chainlink's L2 oracle stops updating. After the sequencer restarts, there is a grace period during which the cached (stale) price is still served. Protocols that execute borrows, liquidations, or redemptions during this grace period act on prices that may be hours old and significantly diverged from the true market price.

Root cause: The timing window between sequencer restart and the first fresh oracle round is not gated. Any call that reads `latestRoundData` during this window receives stale data without any indication of staleness.
Fix: Integrate Chainlink's `sequencerUptimeFeed`; revert or pause protocol actions if the sequencer has been down for fewer than `GRACE_PERIOD_TIME` seconds since recovery.

---

## Finding 7: Arbitrum Sequencer Downtime Spanning Epoch Boundary Prevents Depeg Trigger

- Source: Sherlock — sherlock-audit/2023-03-Y2K-judging, Issue #422
- Severity: Medium
- Tags: cross_chain_timing, epoch_race, finality

Summary: Y2K Finance's structured products trigger depeg payouts when a price falls below a peg threshold before epoch expiry. On Arbitrum, if the sequencer goes down and the downtime straddles the epoch expiry timestamp, the oracle price cannot be read during the critical window, and the depeg condition can never be triggered for that epoch even though the peg actually broke. Users who should receive insurance payouts lose them because the epoch expires with no recorded depeg.

Root cause: Epoch-based settlement assumes continuous L2 liveness. A sequencer outage whose duration overlaps the epoch boundary creates a timing gap that the contract cannot distinguish from "peg held."
Fix: Extend the depeg observation window by the duration of any sequencer downtime, or pause epoch finalization until sequencer liveness is confirmed for a minimum observation period.

---

## Finding 8: Light Client `force()` After DoS Creates Finality-Assumption Bypass

- Source: Cyfrin Audit — local CSV row 12774 (HIGH)
- Tags: finality, cross_chain_timing

Summary: Telepathy's `LightClient.sol` allows `LightClient.force()` to finalise a block header after an extended waiting period. Under normal conditions more than two-thirds of the sync committee must sign a header. However, if a DoS attack suppresses the active Telepathy provers during a sync committee period in which a malicious validator controls at least 10 keys (~5% stake), the validator can submit a forged beacon block with a synthetic sync committee composed only of their own keys. After the waiting period expires, `force()` accepts the forged header, giving the attacker control over all future light client state updates.

Root cause: `force()` relaxes the two-thirds quorum assumption based on elapsed time alone, not on observed honest participation. The timing window is the prover suppression + waiting period.
Fix: Remove `force()` or extend the waiting period to exceed any realistic DoS duration; alternatively require a privileged guardian role to mediate forced updates.

---

## Finding 9: CCTPv2 Fast Finality Disabled by Incorrect Fee Calculation

- Source: Cyfrin Audit — local CSV row 388 (MEDIUM)
- Tags: finality, cross_chain_timing, bridge_delay

Summary: Circle's CCTPv2 fee API does not include the minimum fee required to elect fast-finality routing. Integrators calling the API receive a fee quote sufficient for standard finality (minutes to hours) but below the fast-finality threshold. Transfers submitted with this fee fall back to standard finality silently, violating user expectations around settlement timing. If the threshold rises, all fast-finality attempts will fail. Protocols that assume CCTPv2 transfers settle within seconds for liquidation or time-sensitive arbitrage execution are exposed.

Root cause: Fee derivation does not model the fast-finality minimum, creating a gap between the quoted fee and the fee needed to trigger the short-latency path.
Fix: Expose the fast-finality minimum fee as a separate field in the API response; validate at submission that `fee >= fastFinalityMinimum` if fast finality is requested.

---

## Finding 10: Optimistic Finality Handle Array Index Conflict Causes msg.value Shortfall

- Source: Cyfrin Audit — local CSV row 4078 (MEDIUM)
- Tags: finality, cross_chain_timing, bridge_delay

Summary: In `SpokeOptimisticFinalityLogic.sol`, `handleInstantAction` reads `costs[0]` for both the `instantAction` fee and the `finalizeCredit` fee. The `costs` array is designed such that index 0 covers the instant action and index 1 covers finalize credit. Using index 0 for both means the `finalizeCredit` branch under-charges `msg.value`, causing the transaction to revert with insufficient ETH. The mismatch is triggered specifically under optimistic finality paths where both cost slots are non-zero, i.e. during time-sensitive cross-chain credit finalisation.

Root cause: Off-by-one index in a costs array that maps directly to cross-chain message fees; the error surfaces only on the optimistic-finality code path where both messages are sent in the same call.
Fix: Change the `finalizeCredit` cost reference from `costs[0]` to `costs[1]`.

---

## Tag Distribution

| Tag | Count |
|-----|-------|
| cross_chain_timing | 7 |
| bridge_delay | 5 |
| finality | 6 |
| L1_L2_sync | 4 |
| epoch_race | 2 |


## Common False Positives
- **Monotonic state**: If {STALE_STATE} only increases (never decreases), arbitrage may not be profitable in both directions -- verify directionality
- **Negligible delta**: If max delta during sync window is <0.1%, may not be economically viable after costs
- **Rate limiting**: If operations have cooldowns longer than sync latency, window may not be exploitable
- **Same-block dependency**: If dependent operation requires same-block freshness (checked via block number), stale state is rejected

## Instantiation Parameters
```
{CONTRACTS}           -- List of contracts to analyze
{BRIDGE_PROTOCOL}     -- Specific bridge (LayerZero, CCIP, Arbitrum Messenger, etc.)
{SYNC_POINT}          -- Function/event where sync occurs
{DEPENDENT_FUNCTIONS} -- Functions that read synced state
{SOURCE_CHAIN}        -- Chain where state originates
{DEST_CHAIN}          -- Chain where stale state is exploited
{MONITOR_POINT}       -- What attacker monitors on source chain
{EXPLOIT_FUNCTION}    -- Function attacker calls on dest chain
{STALE_STATE}         -- Specific state variable that becomes stale
{PROFIT_CALCULATION}  -- Formula for attacker profit
{MAX_DELTA}           -- Maximum observed state change
{PROFIT_FORMULA}      -- (new_value - old_value) * position_size
```

## Output Schema
| Field | Required | Description |
|-------|----------|-------------|
| sync_mechanism | yes | How state is synced (bridge, function, event) |
| latency_estimate | yes | Realistic sync latency with source |
| stale_operations | yes | List of operations using potentially stale state |
| arbitrage_sequence | yes | Step-by-step attack if viable |
| profit_viability | yes | VIABLE / NOT_VIABLE / NEEDS_VERIFICATION |
| finding | yes | CONFIRMED / REFUTED / NEEDS_DEPTH |
| evidence | yes | Code locations with line numbers |
