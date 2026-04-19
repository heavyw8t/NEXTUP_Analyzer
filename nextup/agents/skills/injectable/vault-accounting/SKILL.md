---
name: "vault-accounting"
description: "Protocol Type Trigger vault (detected in recon TASK 0 Step 1) - Inject Into Core state agent OR economic design agent (merge via M4 hierarchy)"
---

# Injectable Skill: Vault Accounting Correctness

> **Protocol Type Trigger**: `vault` (detected in recon TASK 0 Step 1)
> **Inject Into**: Core state agent OR economic design agent (merge via M4 hierarchy)
> **Language**: Both EVM and Solana (language-agnostic methodology, language-specific examples omitted)
> **Finding prefix**: `[VA-N]`

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Sections 1, 4: depth-edge-case (share price boundaries, first depositor)
- Sections 2, 2b: depth-state-trace (time-decay state consistency, anchor timestamps)
- Sections 3, 5, 5b: depth-token-flow (fee flows, cross-fee ratios, fee solvency)
- Section 6: depth-edge-case OR depth-state-trace (withdrawal fairness)

## When This Skill Activates

Recon classifies protocol as `vault` type based on indicators: deposit/withdraw/shares/strategy/vault.
This skill adds vault-specific accounting checks that the general ECONOMIC_DESIGN_AUDIT does not cover.

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `ERC4626`, `convertToShares`, `previewDeposit`, `totalAssets`, `totalSupply`, `share_inflation`, `virtualShares`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[VA-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Share Price Consistency Under Adversity

For vault protocols with share-based accounting (LP tokens, vault shares):

Compute share price = total_assets / total_shares at these states:
| State | total_assets | total_shares | Share Price | Expected | Issue? |
|-------|-------------|-------------|-------------|----------|--------|
| After deposit | {val} | {val} | {computed} | {expected} | |
| After withdrawal | {val} | {val} | {computed} | {expected} | |
| After profit report | {val} | {val} | {computed} | {expected} | |
| After loss report | {val} | {val} | {computed} | {expected} | |
| After fee harvest | {val} | {val} | {computed} | {expected} | |
| After time-decay expiry | {val} | {val} | {computed} | {expected} | |

Tag: `[TRACE:state={event} -> share_price={value} -> {expected_or_unexpected}]`

## 2. Time-Decay State Consistency (if applicable)

For vaults with time-decay mechanisms (locked profit, vesting schedules, streaming distributions):
- Identify the BASE variable the decay operates on and the DECAY variable that diminishes over time
- Enumerate ALL state transitions that modify the BASE (profit, loss, deposit, withdrawal, fee harvest)
- For EACH transition: does the DECAY variable adjust accordingly? If BASE decreases but DECAY doesn't → DECAY can exceed BASE
- Does adding new value to the decay (e.g., reporting new profit) reset the timer for ALL remaining decay, or only for the new portion?
- At decay duration = 0: does everything release immediately? At MAX duration?
- After full decay completion: is the decay variable exactly 0, or can dust remain?

Tag: `[TRACE:{transition} -> {base_var} changed -> {decay_var} unchanged -> {decay_var} > {base_var} -> {consumer} computes {wrong_result}]`

### 2b. Time-Weighted Anchor Timestamp Validation

For time-weighted calculations (fees, vesting, rewards) that use a `(value × timeDelta)` formula:
1. Identify the ANCHOR timestamp (e.g., `lastDistributionTime` (vesting vaults), `periodFinish`/`lastUpdateTime` (Synthetix-style staking), `lastFeeCollection` (management fee), `lastStreamUpdate` (streaming))
2. Trace ALL functions that START a new time-weighted period (e.g., `distributeYield`/`updateSharePrice` (vesting vaults), `notifyRewardAmount` (Synthetix), `reportProfit`/`report` (Yearn-style), `startNewEpoch` (epoch-based))
3. For each: does it update the anchor timestamp to `block.timestamp` (or `now`) UNCONDITIONALLY, or only inside a conditional block?
4. If the anchor is NOT updated when a new period starts: `timeDelta` in the next calculation will include time from BEFORE the new period, causing accelerated vesting/fee accrual
5. Test: what happens if the anchor timestamp is 7 days stale when a new period of 7 days starts? fraction = 7d/(7d+7d) = 50% vests immediately instead of 0%

Tag: `[TRACE:new_period_start → anchor_timestamp NOT updated → timeDelta includes {stale_duration} → {acceleration_factor}x acceleration]`

## 3. Cross-Fee Ratio Dependency (if applicable)

For vaults where one fee type changes a ratio that another fee type reads:
- For each fee type, trace whether applying it changes the canonical assets/shares ratio
- Map fee→ratio→fee chains: if fee A changes the ratio and fee B uses that ratio as input, compute the combined effective rate
- For ratio-threshold mechanisms (e.g., high water marks, performance benchmarks): does any fee or state change shift the ratio without representing actual protocol performance?
- For ratio snapshots: after a negative event (loss, slashing), does the snapshot become permanently stale? Is there a reset or recalibration path?

## 4. First Depositor / Dead Weight / Re-entry

- Is there first-depositor protection (minimum deposit, virtual shares, burned initial shares)?
- After all users exit (return to zero): does the protection re-activate?
- Can residual dust/fees create an exploitable state for the next depositor?

## 5. Fee Source Analysis

For each fee accumulator (platform fees, performance fees, management fees, yield fees):
1. Trace the fee claim path: does `claimFees()` transfer vault assets out, or mint new tokens to the fee recipient?
2. If vault assets are transferred out: are corresponding shares burned to maintain the assets-per-share ratio? If NO → fees dilute existing shareholders (share-backed liability). Flag as finding.
3. If new shares are minted to the fee recipient: does the mint inflate total supply without adding assets? If YES → same dilution effect. Flag as finding.
4. Assess whether the dilution is documented/intended (management fee model) vs undocumented/surprising to depositors.

### 5b. Fee Solvency Under Stress

For each fee accumulator identified in section 5:
1. Trace total accrued fees (feeAccumulator or equivalent) across a sequence: deposit → yield → loss → yield → fee claim
2. Verify: can accrued fees exceed the vault's actual available assets? If fees are computed on a snapshot (e.g., `lastRecordedSupply × sharePrice × timeDelta`) and the snapshot is NOT reduced by loss events, fees accumulate on phantom assets
3. Check: does the fee calculation use `min(currentSupply, lastUpdateSupply)` or equivalent conservative bounding? If YES, verify the `lastUpdateSupply` is updated on ALL paths (deposit, withdrawal, loss, yield)
4. If fees can exceed vault solvency → FINDING: fee solvency gap under stress
5. **Fee base amplification**: Trace whether the fee calculation base (e.g., `totalAssets`, `sharePrice`, `exchangeRate`) can be INFLATED by a preceding operation in the same transaction or administrative sequence. Pattern: admin resets a high-water mark or benchmark → fee base recalculates from a lower reference → next yield event charges fees on phantom gains that were previously below the benchmark. Check: does the fee base track CUMULATIVE gain or INCREMENTAL gain since last collection? If cumulative: can any reset/recalibration cause double-counting?

### 5c. Fee Extraction vs Exchange Rate Consistency

For each fee claim path identified in section 5:
1. Are accrued fees subtracted from the exchange rate / share price BEFORE the fee claim transfers assets out? If fees inflate the exchange rate but are then extracted without deflating it → last redeemer insolvency
2. If vault assets are deployed externally (strategies, lending, bridges): does the fee claim path verify sufficient liquid reserves? If fees are claimable against the full balance but assets are illiquid → fee claim can drain liquid reserves below withdrawal needs

Tag: `[TRACE:loss_event → fee_base_unchanged → feesOwed > available_assets → {impact}]`

## 6. Withdrawal Fairness Under Stress

- If withdrawal is multi-step (request -> wait -> execute): can vault conditions change between steps?
- Are withdrawal amounts computed at request time or execution time?
- Can a large withdrawal request starve subsequent requestors?

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Direct token transfer inflates totalAssets before share calculation, causing zero shares for legitimate depositors
  Where it hit: StakedUSH vault (2025 audit)
  Severity: HIGH
  Source: Solodit (row_id 721)
  Summary: The vault calculates shares using totalSupply and totalAssets, but an attacker can send tokens directly to the contract to inflate totalAssets before a deposit executes. A legitimate depositor receives 0 shares and loses their funds. The root cause is reading balanceOf(address(this)) inside convertToShares without accounting for direct transfers.
  Map to: ERC4626, totalAssets, totalShares, convertToShares

- Pattern: Donation attack inflates share price to zero out victim LP contributions (first-depositor / share-inflation)
  Where it hit: AaveHyperdrive and DsrHyperdrive (Hyperdrive audit)
  Severity: HIGH
  Source: Solodit (row_id 7896)
  Summary: An attacker front-runs an LP by donating assets to artificially inflate the assets-per-share ratio so the victim mints 0 yield shares. The attacker then redeems their own shares to claim the victim's contributed assets. No virtual shares or burned initial shares are present to prevent the reset of share price when total supply reaches zero.
  Map to: ERC4626, totalAssets, totalShares, convertToShares, convertToAssets

- Pattern: Shares not excluded from effectiveSupply during withdrawal request, allowing convertToAssets inflation via yield donation
  Where it hit: Morpho-based vault with initiateWithdraw flow (2025 audit)
  Severity: HIGH
  Source: Solodit (row_id 985)
  Summary: When a user calls initiateWithdraw(), their collateral shares are not burned. Those shares continue to count in effectiveSupply(), so an attacker can donate yield tokens to inflate the collateral price reported by convertToAssets(). This lets the attacker borrow a disproportionate amount, draining the lending market.
  Map to: ERC4626, totalAssets, totalShares, convertToAssets

- Pattern: totalAssets inconsistency between cached and actual values enables deposit/redeem arbitrage
  Where it hit: LMPVault (Tokemak, 2023 Sherlock audit)
  Severity: HIGH
  Source: Solodit (row_id 10467)
  Summary: previewDeposit, previewMint, previewWithdraw, and previewRedeem all use a cached totalAssets (totalIdle + totalDebt), while _withdraw and _calcUserWithdrawSharesToBurn use the actual on-chain debtValue sum. An attacker deposits when totalAssets_cached < totalAssets_actual, receives more shares than fair value, then redeems after the cache is updated for a risk-free profit at the expense of other shareholders.
  Map to: ERC4626, totalAssets, totalShares, convertToShares, convertToAssets, previewDeposit, previewRedeem

- Pattern: State-mutating function called after previewDeposit inside deposit(), making previewDeposit stale relative to execution
  Where it hit: PerpetualAtlanticVaultLP (Dopex, 2023 Sherlock audit)
  Severity: HIGH
  Source: Solodit (row_id 10533)
  Summary: Inside deposit(), previewDeposit is evaluated first, then perpetualAtlanticVault.updateFunding() is called, which increases _totalCollateral. When the user immediately redeems in the same block, convertToAssets uses the newly increased collateral, so the depositor extracts immediate profit. Moving updateFunding() before previewDeposit eliminates the sandwich window.
  Map to: ERC4626, totalAssets, convertToAssets, previewDeposit, previewRedeem

- Pattern: Rounding direction wrong in previewWithdraw / convertToShares causes zero shares burned on withdrawal
  Where it hit: AutoPxGmx and AutoPxGlp vaults (Pirex, 2023 C4 audit)
  Severity: HIGH
  Source: Solodit (row_id 14114)
  Summary: PirexERC4626.convertToShares uses mulDivDown, so for small withdrawals the shares-to-burn calculation rounds to zero. The withdraw function then transfers assets to the user while burning no shares, allowing repeated free asset extraction until the vault is drained.
  Map to: ERC4626, totalAssets, totalShares, convertToShares, previewRedeem

- Pattern: Time-decay vesting boundary: _vestingInterest() returns 0 at vesting start, exposing full accrued interest to flash-loan harvest
  Where it hit: ERC4626 vault with locked-profit vesting mechanism (Sherlock 2023)
  Severity: HIGH
  Source: Solodit (row_id 1143)
  Summary: The _vestingInterest() function returns 0 when the vesting period resets, then grows linearly. At the moment of reset, totalAssets() includes the entire newly reported interest as immediately available. A flash-loan depositor can capture the entire epoch's yield in one block before any time-decay accrues.
  Map to: ERC4626, totalAssets, convertToShares, convertToAssets

- Pattern: Wrong rounding direction across deposit/mint/withdraw/redeem paths allows systematic value extraction
  Where it hit: Vault contract (Popcorn/RedVeil, 2023 Sherlock audit)
  Severity: MEDIUM
  Source: Solodit (row_id 13357)
  Summary: The vault uses Math.Rounding.Down in convertToShares for both deposit and withdraw paths. EIP-4626 requires withdraw to round up shares burned (favoring the vault) and deposit to round down. With the wrong direction a user calling withdraw burns 0 shares when the asset amount is small relative to total supply, extracting assets for free.
  Map to: ERC4626, totalAssets, totalShares, convertToShares, convertToAssets, previewDeposit, previewRedeem


## Step Execution Checklist

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Share Price Under Adversity | YES | | |
| 2. Time-Decay State Consistency | IF time-decay mechanism detected | | |
| 2b. Time-Weighted Anchor Validation | IF time-weighted mechanism detected | | |
| 3. Cross-Fee Ratio Dependency | IF multiple fee types detected | | |
| 4. First Depositor / Re-entry | YES | | |
| 5. Fee Source Analysis | IF fee mechanism detected | | |
| 5b. Fee Solvency Under Stress | IF fee mechanism detected | | |
| 6. Withdrawal Fairness | IF multi-step withdrawal | | |
