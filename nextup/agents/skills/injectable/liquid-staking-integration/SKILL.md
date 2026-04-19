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

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: stETH withdrawal queue stores nominal amounts instead of shares; negative rebase causes insolvency where late claimants receive nothing
  Where it hit: Renzo Protocol WithdrawQueue (ezETH/stETH cross-chain restaking)
  Severity: HIGH
  Source: Solodit (row_id 12)
  Summary: The WithdrawQueue stores `amountToRedeem` as a fixed stETH amount at request time. If stETH rebases negatively between request and claim, the queue contract's actual stETH balance falls below the sum of pending amounts. First claimants drain the pool; late claimants revert permanently. Fix is to store and redeem in stETH shares via `getSharesByPooledEth()`.
  Map to: stETH, withdrawal_queue, rebase, slashing

- Pattern: 1 stETH == 1 ETH hardcoded assumption; `ethPerDerivative` queries wstETH→stETH rate then equates stETH to ETH at 1:1
  Where it hit: Asymmetry Finance SafETH WstEth derivative (multi-LST staking aggregator)
  Severity: HIGH
  Source: Solodit (row_id 42)
  Summary: `WstEth.ethPerDerivative()` calls `wstETH.stEthPerToken()` to get stETH per wstETH, but then treats that stETH amount as 1:1 with ETH. During the June 2022 depeg (stETH at ~0.93 ETH on Curve), the function overestimated wstETH value by ~7%. The `withdraw` function set `minOut` as a 1% slippage on stETH balance, causing all unstake calls to revert during depeg conditions.
  Map to: wstETH, stETH, exchange_rate

- Pattern: Protocol fee tracked in nominal stETH amounts; not scaled to current shares ratio after rebase, causing over-withdrawal and insolvency
  Where it hit: LidoVault (fixed/variable yield vault using Lido staking)
  Severity: HIGH
  Source: Solodit (row_id 3)
  Summary: `totalProtocolFee` is accumulated in raw stETH amounts but `totalEarnings` is computed using the current stETH/ETH shares ratio. The fee is not scaled, so `totalEarnings` is overestimated. Users can withdraw more stETH than the vault holds, pushing the protocol into insolvency. Fix is to track `totalProtocolFee` as shares.
  Map to: stETH, rebase, exchange_rate

- Pattern: mETH exchange rate manipulable via unsanctioned oracle record updates; no sanity bounds on `currentTotalValidatorBalance` allows mint/burn at artificial rate
  Where it hit: Mantle mETH staking protocol (mETH oracle record management)
  Severity: HIGH
  Source: Solodit (row_id 26)
  Summary: The mETH contract's record update function lacks sanity checks on `currentTotalValidatorBalance`. An attacker who can submit a record (or exploit a window in which the admin can post an incorrect record) can set an arbitrary exchange rate in one transaction, then mint mETH at the deflated rate or burn at the inflated rate before the admin corrects it. After an incorrect update, only the admin can recover, making this a high-severity DOS with theft vector.
  Map to: exchange_rate, slashing

- Pattern: stETH 1-2 wei transfer shortfall from share rounding causes downstream balance checks to fail or DoS
  Where it hit: Protocol holding stETH (exact amount cited: 1-2 fewer shares than requested)
  Severity: HIGH
  Source: Solodit (row_id 10)
  Summary: stETH's internal share-based accounting delivers 1-2 wei fewer tokens than the requested `amount` on `transfer`/`transferFrom`. Protocols that call `safeTransfer(stETH, recipient, amount)` and then check `balanceOf(recipient) >= amount` fail intermittently. The report confirms denial-of-service across the contract's core functionality. Fix is to use `transferShares()` or accept a 1-2 wei tolerance in balance checks.
  Map to: stETH, rebase

- Pattern: stETH rewards accrue in queue intermediate contract but only requested amounts are tracked; rebase delta is permanently unclaimable
  Where it hit: Mellow Flexible Vaults (yield vault with stETH queue)
  Severity: MEDIUM
  Source: Solodit (row_id 83)
  Summary: When stETH sits in a withdrawal queue contract between request and claim, rebases increase the contract's stETH balance. The queue only tracks the originally-requested nominal amounts. The delta earned during the queue period has no accounting entry and is permanently stuck. This is the Mellow M-9 finding pattern: incompatibility with rebasing tokens means rewards lock in queue contracts with no recovery path.
  Map to: stETH, rebase, withdrawal_queue

- Pattern: rETH oracle calls non-existent function `getExchangeRatio()` instead of the correct `getExchangeRate()`; entire asset pricing subsystem halts
  Where it hit: LybraRETHVault (CDP/stablecoin protocol accepting rETH collateral)
  Severity: MEDIUM
  Source: Solodit (row_id 134)
  Summary: `LybraRETHVault.getAssetPrice()` calls `rETH.getExchangeRatio()` which does not exist on the Rocket Pool rETH contract. The correct function is `getExchangeRate()`. Every operation dependent on asset pricing (minting, redemptions, liquidations) reverts, fully halting the vault. Confirmed by LybraFinance.
  Map to: rETH, exchange_rate

- Pattern: Share price not reduced after stETH slashing event; inflated price allows depositors to withdraw more than available balance
  Where it hit: DepositETH contract (Lido stETH yield-bearing deposit system)
  Severity: MEDIUM
  Source: Solodit (row_id 93)
  Summary: The `DepositETH` function's share price calculation does not handle reductions in the Lido stETH balance caused by slashing events. After a slash, the protocol's stETH balance drops but the share price remains stale, allowing users to redeem shares at a price that implies more stETH than is held. The report recommends updating the share price calculation to account for balance decreases.
  Map to: stETH, slashing, exchange_rate, rebase

- Pattern: LidoVault slashing after vault end fails to account for prior variable-user income withdrawals, causing fund lock and incorrect earnings calculation
  Where it hit: LidoVault variable/fixed yield vault
  Severity: MEDIUM
  Source: Solodit (row_id 99)
  Summary: `LidoVault.vaultEndedWithdraw` does not factor in income already withdrawn by variable users before a slashing event. When slashing occurs post-vault-end, the total-earnings calculation is wrong: it subtracts the slashing loss from a base that excludes prior withdrawals, producing an undercount or underflow that permanently locks remaining funds. A PoC was provided and the team issued a fix.
  Map to: stETH, slashing, withdrawal_queue

- Pattern: wstETH oracle price derived from `getStETHByWstETH()` only (wstETH→stETH), ignoring stETH→ETH conversion step; protocol misprices wstETH in ETH terms
  Where it hit: Lido adapter in a yield/RWA cross-chain protocol
  Severity: MEDIUM
  Source: Solodit (row_id 173)
  Summary: The adapter's `price()` function calls `IWstETH(token).getStETHByWstETH()` and returns the result as the ETH price of wstETH. This gives the wstETH/stETH rate, not wstETH/ETH. When stETH is not at a 1:1 peg (depeg or slashing socialization), the protocol misprices collateral. The harvestable-amount calculation and all downstream valuation logic are incorrect, enabling over-borrowing or unfair liquidations.
  Map to: wstETH, stETH, exchange_rate


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
