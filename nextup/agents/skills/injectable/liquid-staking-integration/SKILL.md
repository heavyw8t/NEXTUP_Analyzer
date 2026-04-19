---
name: "liquid-staking-integration"
description: "Protocol Type Trigger lst_integration (detected when recon finds stETH|wstETH|rETH|frxETH|sfrxETH|cbETH|mETH|swETH|ankrETH|osETH - protocol HOLDS or ACCEPTS liquid staking tokens as input)"
---

# Injectable Skill: Liquid Staking Token Integration Security

> **Protocol Type Trigger**: `lst_integration` (detected when recon finds: `stETH`, `wstETH`, `rETH`, `frxETH`, `sfrxETH`, `cbETH`, `mETH`, `swETH`, `ankrETH`, `osETH`, `ILido`, `IWstETH`, `IRocketTokenRETH`, `ISfrxEth` - AND the protocol ACCEPTS or HOLDS these tokens, not issues them)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case, depth-external
> **Language**: EVM only
> **Finding prefix**: `[LST-N]`
> **Relationship to STAKING_RECEIPT_TOKENS**: That skill covers generic receipt token donation attacks. This skill covers protocol-specific behaviors of major LSTs that affect integrating protocols. Both may be active.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-token-flow (rebasing, balance accounting, share conversion)
- Section 2: depth-edge-case (exchange rate staleness, boundary values, precision)
- Section 3: depth-external (oracle dependency, withdrawal queue, external state)
- Section 4: depth-token-flow + depth-state-trace (collateral valuation, liquidation)

## When This Skill Activates

Recon detects that the protocol integrates with liquid staking tokens — accepts them as deposits, collateral, or payment; or holds them in its own accounting. This is the "caller side" of liquid staking: the protocol consumes LSTs, it doesn't issue them.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `stETH`, `rETH`, `cbETH`, `mETH`, `frxETH`, `exchange_rate`, `rebase`, `withdrawal_queue`, `submit`, `getPooledEth`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[LST-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Rebasing and Balance Mutation

Different LSTs have fundamentally different balance models. The protocol MUST handle the correct model for each LST it integrates.

### 1a. LST Balance Model Classification

For each LST the protocol accepts, classify its model:

| LST | Model | Balance Behavior | Key Risk |
|-----|-------|-----------------|----------|
| stETH (Lido) | **Rebasing** | `balanceOf()` changes daily without transfers | Tracked balance drifts from actual |
| wstETH (Lido wrapped) | **Non-rebasing** | Balance fixed, value accrues in exchange rate | Exchange rate staleness |
| rETH (Rocket Pool) | **Non-rebasing** | Balance fixed, value accrues in exchange rate | Exchange rate can decrease on slashing |
| frxETH (Frax) | **Non-rebasing** (base) | 1:1 peg target, no yield | Depeg risk, not yield-bearing |
| sfrxETH (Frax staked) | **Non-rebasing vault** | ERC-4626 vault share, value accrues | Share price manipulation at low TVL |
| cbETH (Coinbase) | **Non-rebasing** | Balance fixed, value accrues in exchange rate | Centralized exchange rate oracle |
| mETH (Mantle) | **Non-rebasing** | Balance fixed, value accrues in exchange rate | Similar to wstETH model |

### 1b. Rebasing Token Accounting (stETH)

If the protocol holds stETH:
- Does the protocol use `balanceOf(address(this))` for stETH accounting? If yes: the balance will change between transactions without any transfer event. Internal tracking via state variables will drift.
- Does the protocol snapshot stETH balance and compare later? The balance at snapshot time differs from balance at comparison time due to rebases.
- Does the protocol's share/receipt token accounting handle the rebasing correctly? A user who deposits 100 stETH should not lose value when stETH rebases up (their share should represent more ETH, not the same amount of stETH).
- **Transfer precision**: stETH transfers can deliver 1-2 wei less than the specified amount due to internal share rounding. Does the protocol handle this (e.g., use `transferSharesFrom` instead of `transfer`)?
- **Real finding pattern (Solodit: multiple)**: Protocol uses `safeTransfer(stETH, recipient, amount)`. Due to stETH's internal shares→amount rounding, 1 wei less arrives. If protocol then checks `balanceOf(recipient) >= expected`, the check fails intermittently. Fix: use `transferShares()` or accept 1-2 wei tolerance.
- **Real finding pattern**: Protocol deposits stETH into a vault, tracks user balance via internal mapping. Over time, stETH rebases add value but the mapping stays fixed. Users withdraw their original deposit, and the rebase yield is permanently locked in the vault.

Tag: `[TRACE:stETH_accounting → balanceOf_used={YES/NO} → tracked_state_drifts={YES/NO} → transfer_precision_handled={YES/NO}]`

### 1c. Wrapped vs Unwrapped Confusion

- Does the protocol accept BOTH stETH and wstETH? If yes: does it normalize to a common unit before comparison or arithmetic?
- Can a user deposit stETH and withdraw wstETH (or vice versa) to exploit a conversion mismatch?
- Is the stETH↔wstETH conversion rate hardcoded or read from the wrapper contract?
- **Real finding pattern**: Protocol accepts stETH deposits and wstETH deposits, converts both to an internal unit using a snapshot rate. Users deposit stETH, wait for rebase, withdraw as wstETH at the stale rate — extracting value at the expense of other depositors.

Tag: `[TRACE:wrapped_unwrapped → both_accepted={YES/NO} → normalized={YES/NO} → conversion_source={contract/hardcoded}]`

---

## 2. Exchange Rate and Pricing

### 2a. Exchange Rate Source

For each non-rebasing LST (wstETH, rETH, sfrxETH, cbETH, mETH):
- Where does the protocol get the LST→ETH exchange rate?
  - Direct from LST contract (e.g., `rETH.getExchangeRate()`, `wstETH.stEthPerToken()`)
  - From a Chainlink price feed
  - From a DEX TWAP
  - Hardcoded
- Is the rate cached? If yes: how often is it refreshed? Can it go stale?
- Is there a staleness check on the rate? What's the maximum accepted age?

### 2b. Exchange Rate Manipulation

- For rates read directly from LST contracts: can the rate be manipulated within a single transaction (flash loan → large deposit → inflated rate → profit)?
  - **stETH/wstETH**: Rate is based on total pooled ETH / total shares. Large deposits don't immediately change the rate (buffered by Lido oracle).
  - **rETH**: Rate is `rocketTokenRETH.getExchangeRate()`. Based on total ETH / total rETH. NOT flash-loan-manipulable (rate updated by oracle, not by deposits).
  - **sfrxETH**: Rate is ERC-4626 `convertToAssets()`. CAN be manipulated if `totalAssets()` is directly linked to contract balance (classic ERC-4626 donation attack).
  - **cbETH**: Rate set by Coinbase oracle. NOT flash-loan-manipulable.
- For rates from Chainlink: apply standard ORACLE_ANALYSIS (staleness, decimals, sequencer).
- For rates from DEX TWAP: what's the TWAP window? Can it be manipulated with sustained trading pressure?

Tag: `[TRACE:rate_source={direct/chainlink/twap/hardcoded} → flash_manipulable={YES/NO} → staleness_check={YES/NO/N/A} → max_age={value}]`

### 2c. Exchange Rate Decrease (Slashing)

- **rETH**: The exchange rate CAN DECREASE if Rocket Pool validators are slashed. This is rare but documented.
- **cbETH**: Rate can decrease if Coinbase applies a penalty.
- **stETH/wstETH**: Rate cannot decrease under normal operation (Lido socializes losses). However, post-Shapella, large withdrawal queues can create temporary depeg on secondary markets.
- Does the protocol assume the LST exchange rate is monotonically increasing? If yes: a slashing event breaks this assumption.
- What happens to protocol accounting if the rate decreases? (Underwater positions, bad debt, incorrect liquidations)
- **Real finding pattern (Sherlock)**: Protocol uses rETH as collateral with LTV based on monotonically-increasing rate assumption. Rocket Pool validator slashing decreases rETH rate. Protocol's collateral valuation drops below debt, creating bad debt that is socialized across all suppliers.
- **Real finding pattern**: Protocol caches `wstETH.stEthPerToken()` and uses it for 24 hours. During a Lido negative rebase event (validator slashing socialization), the cached rate is higher than actual. Arbitrageurs deposit at the stale high rate.

Tag: `[TRACE:rate_decrease_possible={YES/NO per LST} → protocol_assumes_monotonic={YES/NO} → slashing_impact={description}]`

---

## 3. Withdrawal Queue and Liquidity

### 2d. Static 1:1 stETH/ETH Assumption

- Does the protocol assume 1 stETH == 1 ETH? This is the single most common real-world LST integration bug.
- **Real finding pattern (C4: Asymmetry Finance #588)**: `WstEth.ethPerDerivative()` correctly called `wstETH.stEthPerToken()` but then equated the stETH value to ETH 1:1. During the June 2022 depeg, stETH traded at ~0.93 ETH on Curve — function overestimated wstETH value by 7%.
- **Real finding pattern (Cork Protocol exploit, $12M loss May 2025)**: Cork treated wstETH as fixed value without calling `wstETH.stEthPerToken()` dynamically. Combined with missing access control on hook callbacks and lack of slippage protection, attackers drained 3,762 wstETH (~$12M).
- For any LST→ETH conversion: is the conversion rate queried from the LST contract at time of use, or cached/hardcoded?

Tag: `[TRACE:stETH_ETH_peg_assumption → hardcoded_1_to_1={YES/NO} → rate_queried_dynamically={YES/NO}]`

### 3a. Direct Unstaking Path

- Does the protocol rely on direct LST→ETH unstaking (vs. DEX swap)?
  - **Lido**: Withdrawal queue with variable wait time (hours to days). Request → finalization → claim.
  - **Rocket Pool**: Burn rETH for ETH via minipool exit. Can be delayed.
  - **Frax**: sfrxETH → frxETH is instant (ERC-4626 withdraw). frxETH → ETH via redemption queue.
  - **cbETH**: Unwrapping requires Coinbase, may be restricted.
- If the protocol has time-sensitive operations (liquidations, rebalancing): is the withdrawal delay acceptable?
- Can the withdrawal queue be full/paused? What happens to the protocol's pending withdrawal?

### 3a2. Withdrawal Queue Insolvency (stETH)

- If stETH is held in a withdrawal queue contract between request and claim: does the queue track nominal `amountToRedeem` or share-denominated amounts?
- **Real finding pattern (C4: Renzo #282, High)**: Users queued stETH withdrawals with fixed `amountToRedeem`. A negative rebase (Lido slashing) reduced the queue contract's actual stETH balance below the sum of pending amounts. First claimants drained the pool; late claimants' claims reverted permanently.
- **Real finding pattern (Sherlock: Mellow M-9)**: stETH rewards accrued while sitting in a withdrawal queue intermediate contract. The queue only tracked originally-requested amounts. The rebase delta (rewards earned during the queue period) had no accounting entry — permanently stuck, unreclaimable by anyone.
- Fix: Track withdrawals in stETH shares (via `getSharesByPooledEth()`), not in nominal stETH amounts. Convert back to stETH amounts at claim time.

### 3b. Secondary Market Liquidity

- If the protocol swaps LSTs on DEX instead of direct unstaking: what's the liquidity depth?
- Can a large protocol withdrawal move the LST price on secondary markets?
- Is slippage protection applied to LST→ETH swaps?
- In a mass-exit scenario (validator slashing, protocol crisis): can the LST depeg significantly, making DEX swaps produce less ETH than the oracle rate suggests?

### 3c. Depeg Scenarios

- Does the protocol have a circuit breaker if the LST depegs more than X% from ETH?
- For collateral protocols: is the LST valued at oracle rate or market rate? Using oracle rate during a depeg creates bad debt.
- For vaults: if the underlying LST depegs, can depositors front-run the depeg by withdrawing at the stale oracle rate?

Tag: `[TRACE:unstaking_path={direct/dex/both} → queue_delay={time} → depeg_circuit_breaker={YES/NO} → valuation_during_depeg={oracle/market}]`

---

## 4. Collateral and Composition Risks

### 4a. LST as Collateral

If the protocol accepts LSTs as collateral (lending, borrowing, margin):
- Is the collateral valued in ETH-terms using the exchange rate? Is this rate fresh?
- Can the exchange rate decrease (Section 2c) cause unexpected liquidations?
- For rebasing stETH: does the collateral value increase with rebases, or is it fixed at deposit time?
- Is the LTV ratio appropriate for the LST's volatility profile? (stETH/ETH is usually tightly pegged but CAN depeg 5-10% in extreme events)

### 4b. Reward Accrual While Deposited

- When an LST is deposited into the protocol: who receives the staking rewards?
  - For wstETH/rETH/sfrxETH (non-rebasing): rewards accrue in the exchange rate. The protocol benefits unless it passes through the rate change to depositors.
  - For stETH (rebasing): the protocol's balance increases on rebase. Does the protocol credit this to the depositor, keep it, or ignore it?
- Is there a clear policy on reward attribution? An implicit policy (rewards silently accrue to the protocol) may surprise users.

### 4c. Multi-LST Composition

If the protocol accepts multiple LSTs:
- Are they treated as fungible (1 stETH = 1 rETH = 1 ETH)?
- If yes: this ignores credit risk differences (Lido vs Rocket Pool vs Coinbase). A slashing event on one LST shouldn't affect positions collateralized by a different LST.
- Are there per-LST caps, concentration limits, or risk parameters?
- Can an attacker swap a high-quality LST for a lower-quality one within the protocol?

Tag: `[TRACE:collateral_valuation={exchange_rate/fixed/market} → reward_attribution={depositor/protocol/ignored} → multi_lst_fungible={YES/NO}]`

---

## Common False Positives

- **wstETH-only protocols**: If the protocol exclusively uses wstETH (not raw stETH), rebasing concerns don't apply — wstETH is non-rebasing by design
- **Hardcoded Chainlink feed with staleness check**: If the rate comes from a verified Chainlink feed with proper staleness/sequencer checks, exchange rate manipulation is not feasible
- **Protocol IS the LST issuer**: If the protocol is Lido/Rocket Pool/Frax itself, this skill doesn't apply — use protocol-type skills instead
- **Non-collateral use**: If LSTs are only used as swap intermediary (receive and immediately swap out), most accounting concerns don't apply

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. LST Balance Model Classification | YES | | Classify each LST |
| 1b. Rebasing Token Accounting | IF stETH held | | Balance drift, transfer precision |
| 1c. Wrapped vs Unwrapped | IF both accepted | | Normalization, conversion |
| 2a. Exchange Rate Source | YES | | Source, caching, staleness |
| 2b. Exchange Rate Manipulation | YES | | Flash loan, TWAP window |
| 2c. Exchange Rate Decrease | YES | | Slashing, monotonic assumption |
| 3a. Direct Unstaking Path | IF protocol unstakes | | Queue delay, pause risk |
| 3b. Secondary Market Liquidity | IF protocol swaps on DEX | | Depth, slippage, mass exit |
| 3c. Depeg Scenarios | YES | | Circuit breaker, valuation |
| 4a. LST as Collateral | IF collateral use | | LTV, rate freshness |
| 4b. Reward Accrual | YES | | Who gets rewards while deposited |
| 4c. Multi-LST Composition | IF 2+ LSTs accepted | | Fungibility, credit risk |
