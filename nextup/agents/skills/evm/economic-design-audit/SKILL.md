---
name: "economic-design-audit"
description: "Trigger Pattern MONETARY_PARAMETER flag (required) - Inject Into Breadth agents (merged via M6 hierarchy)"
---

# ECONOMIC_DESIGN_AUDIT Skill

> **Trigger Pattern**: MONETARY_PARAMETER flag (required)
> **Inject Into**: Breadth agents (merged via M6 hierarchy)

For every monetary parameter setter (rate, rebase, supply, mint, burn, emission, inflation,
peg, price cap/floor, fee, reward rate) in the protocol:

## 1. Parameter Boundary Analysis

| Parameter | Setter | Min Value | Max Value | Enforced? | Impact at Min | Impact at Max |
|-----------|--------|-----------|-----------|-----------|---------------|---------------|

For each parameter: substitute min and max into ALL consuming functions.
Tag: [BOUNDARY:param=val -> outcome]

## 2. Economic Invariant Identification

List all economic invariants the protocol must maintain:
| Invariant | Parameters Involved | Can Admin Break It? | Functions That Assume It |

For each setter: can changing this parameter break an invariant that user-facing
functions depend on? If yes -> finding.

## 3. Rate/Supply Interaction Matrix

For protocols with multiple monetary parameters that interact:
| Parameter A | Parameter B | Interaction | Can A*B Produce Extreme Output? |

Check: can two independently-valid parameter settings combine to create an
extreme or invalid economic state? (Rule 14 constraint coherence)

## 4. Fee Formula Verification at Normal Values

For every fee-related computation (fee calculation, fee deduction, fee distribution):

### 4a. Concrete Example Computation
Pick 3 representative fee rates (e.g., 1% = 100 BPS, 5% = 500 BPS, 10% = 1000 BPS) and trace through the actual code formula:

| Fee Param | Value | Formula | Input Amount | Expected Output | Actual Output | Match? |
|-----------|-------|---------|-------------|----------------|---------------|--------|
| {fee_bps} | 100 | {code formula} | 1e18 | {expected} | {computed} | YES/NO |
| {fee_bps} | 500 | {code formula} | 1e18 | {expected} | {computed} | YES/NO |
| {fee_bps} | 1000 | {code formula} | 1e18 | {expected} | {computed} | YES/NO |

Tag: `[BOUNDARY:fee_bps={val} → effective_rate={computed_rate}]`

**Red flags**:
- Gross-up formulas: `amount * MAX / (MAX - fee)` charges effective rate of `fee/(MAX-fee)`, not `fee/MAX`. At 5% this is 5.26%, not 5%. Document whether this is intentional.
- Fee-on-fee: Does fee A's output feed into fee B's input? If so, the combined effective rate is not simply A + B.
- Rounding direction: Does rounding favor the protocol or the user? For fee deductions, rounding UP (ceiling via `mulDivUp` or equivalent) favors the protocol.
- Precision loss: With `uint256` math at `1e18` scale, do intermediate products overflow or lose precision? Check `mulDiv` ordering.

### 4d. Fee-Base Consistency
For every fee computation, trace the base amount (the value the fee is computed on) through ALL subsequent code paths:

| Fee Site | Base Amount Variable | Modified After Fee? | Modified How | Fee Recomputed? | Overcharge? |
|----------|---------------------|--------------------:|-------------|-----------------|-------------|

**Methodology**:
- Identify the variable used as fee base (e.g., `amount`, `depositAmount`)
- Trace that variable FORWARD from the fee computation to the end of the function
- If the variable is reduced (capped, downscaled, adjusted to remaining capacity, slippage-adjusted) AFTER the fee was computed → the fee was charged on a larger base than what was actually used
- **Concrete test**: If `fee = amount * feeRate / MAX`, then `amount` is reduced to `leftover` (e.g., remaining allocation), the user paid `fee` on `amount` but only `leftover` was processed - overcharge of `fee * (1 - leftover/amount)`

### 4b. Fee Interaction Matrix
For protocols with multiple fee types:

| Fee A | Fee B | A Output Feeds B Input? | Combined Effective Rate | Independent Rate Sum | Discrepancy? |
|-------|-------|------------------------|------------------------|---------------------|-------------|

### 4c. Fee Impact on Share Price
If the protocol uses share-based accounting (ERC4626 vaults, LP tokens):
- After fee deduction: does the share price change?
- Does the fee mechanism create a spread between deposit and immediate withdrawal?
- Is the spread documented and within reasonable bounds?

## 5. Emission/Inflation Sustainability

For protocols with emission/inflation/rebase mechanics:
- What is the maximum emission rate over 1 day / 1 week / 1 year?
- Can emissions exceed the protocol's capacity to back them?
- Is there a supply cap? Can it be bypassed by parameter changes?

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> Source: candidates.jsonl (21 rows). 8 examples selected across 6 pattern categories.
> Pattern tags: incentive, bank_run, griefing, sybil, first_mover, MEV_design

---

## incentive — Inflation Rate Decay Not Applied at Boundary

- Pattern: `incentive`
- Severity: HIGH
- Source: Solodit (row_index 15697)
- Protocol category: Dexes; CDP; Yield; Cross Chain; Staking Pool
- Summary: If `_executeInflationRateUpdate` is not called exactly at the decay boundary, the old (higher) rate is used to compute `totalAvailableToNow` for the period that should have used the decayed rate. The result is that `totalAvailableToNow` accumulates more tokens than the protocol allows, and the total token supply can exceed the predetermined cap. The fix requires splitting the period at the decay boundary and applying each rate to its respective window.
- Map to: emission_sustainability, inflation_rate, supply_cap_bypass

---

## bank_run — Unstable Liquidation Design Allows Collateral Drain

- Pattern: `bank_run`
- Severity: HIGH
- Source: Solodit (row_index 13205)
- Protocol category: Oracle
- Summary: The DyadStablecoin liquidation mechanism lets a liquidator inject ETH and claim the entire dNFT plus all of its shares when shares fall below a threshold. Because liquidators also control `totalDeposits`, they can manipulate the threshold trigger. There is no game-theoretically stable outcome: the mechanism consistently over-rewards liquidators relative to the shortfall, and does not keep the system overcollateralized. Once one dNFT is liquidated at favorable odds, rational actors race to be first, creating a bank-run dynamic where liquidators cascade through all marginal positions.
- Map to: bank_run, incentive_misalignment, liquidation_design

---

## sybil — Liquid Lock Bypass via Tokenized Contract Ownership

- Pattern: `sybil`
- Severity: HIGH
- Source: Solodit (row_index 16208)
- Protocol category: Liquid Staking; Dexes; CDP; Yield; Services
- Summary: The HolyPaladinToken locking design assumes locked tokens are illiquid. An attacker deposits hPAL into a purpose-built contract, locks it, and delegates voting power to themselves. The ownership of the contract (i.e., the right to unlock and withdraw) can then be sold or tokenized, making the locked position liquid. This mirrors the veToken wrapper pattern (veCRV, veANGLE) and breaks the protocol's assumption that locking reduces circulating supply and concentrates voting power in long-term holders. Fix: whitelist only approved contract types for locking, matching the veCRV approach.
- Map to: sybil_incentive, governance_bypass, lock_circumvention

---

## MEV_design — Slash Front-Run via Unstake Before Flag

- Pattern: `MEV_design`
- Severity: MEDIUM
- Source: Solodit (row_index 9751)
- Protocol category: Staking
- Summary: A target staker in the Streamr VoteKickPolicy can monitor the mempool and call `unstake()` or `forceUnstake()` before the flagger's `flag()` transaction lands. The target exits with full funds before the slash condition is evaluated, defeating the slashing mechanism entirely. Because slashing depends on the target still being staked at the time `flag()` executes, any target with access to a flashbot searcher (or even a simple mempool watcher) can make themselves immune to governance-enforced penalties. Fix: introduce delayed unstaking so a fraction of funds remains at risk for the duration of the penalty window.
- Map to: MEV_extractable_design, front_run_slash, staking_exit

---

## first_mover — NFT Collateral Liquidated at Minimum Price via Stale Auction

- Pattern: `first_mover`
- Severity: MEDIUM
- Source: Solodit (row_index 14070)
- Protocol category: Dexes; CDP; Services; Cross Chain; Indexes
- Summary: In Paraspace, a user whose health factor recovers after a price drop does not automatically invalidate prior auctions unless they explicitly call `setAuctionValidityTime()`. An attacker opens auctions on all of a user's NFT collateral when the health factor first drops. The user supplies additional collateral to recover, but omits the validity reset. The attacker waits until auction prices decay to the minimum and liquidates all NFTs at that floor. The first actor to open auctions gains a persistent economic advantage regardless of the user's subsequent recovery actions.
- Map to: first_mover_economic_advantage, auction_staleness, liquidation_MEV

---

## griefing — Staking Incentives Permanently Lost When Epoch Weight Is Zero

- Pattern: `griefing`
- Severity: MEDIUM
- Source: Solodit (row_index 6604)
- Protocol category: Staking
- Summary: In `claimStakingIncentives`, when `totalWeight` for an epoch is zero (no votes allocated), `calculateStakingIncentives` returns a `totalReturnAmount` of zero rather than the expected unused allocation. The unused staking incentives are neither refunded to the inflation cap nor redistributed to future epochs — they are silently discarded. An attacker or negligent governance participant who ensures a nominee has zero votes in a given epoch can cause the entire epoch allocation to be lost, permanently reducing the protocol's reward budget.
- Map to: griefing_incentive, epoch_zero_weight, reward_loss

---

## bank_run — Cooldown Dilution via Token Transfer Enables Early Unstake

- Pattern: `bank_run`
- Severity: MEDIUM
- Source: Solodit (row_index 16205)
- Protocol category: Liquid Staking; Dexes; CDP; Yield; Services
- Summary: `_getNewReceiverCooldown` in HolyPaladinToken computes a weighted-average cooldown when a receiver already holds tokens. A user with a recently started cooldown (Day 0) can receive a transfer from a user whose cooldown started earlier (Day 15), pulling their effective cooldown forward. Concretely: Alice (200 tokens, Day 0 cooldown) receives 100 tokens from Bob (Day 15 cooldown), yielding a blended cooldown of Day 5. Alice can now unstake before the full `UNSTAKE_PERIOD` expires. This creates an economic incentive for coordinated transfers to mutually accelerate unstaking, mimicking a bank-run coordination game where rational actors exploit the averaging formula.
- Map to: bank_run_dynamics, cooldown_dilution, early_unstake

---

## sybil — Credit Cap Bypassed by Repeated Function Calls

- Pattern: `sybil`
- Severity: MEDIUM
- Source: Solodit (row_index 14763)
- Protocol category: NFT
- Summary: The NFTR protocol intends to cap assigner credits at `MAX_ASSIGNER_CREDITS` and user naming credits at `MAX_CREDITS_ASSIGNED`. Both `addAssignerCredits` and `assignNamingCredits` check the cap at the moment of a single call but do not track cumulative totals across calls. Calling either function multiple times in sequence bypasses the cap, allowing unlimited credit creation or accumulation. A sybil attacker can either self-assign naming credits far beyond the intended limit or, if they control an assigner address, mint unbounded credits and distribute them, distorting the protocol's naming tokenomics.
- Map to: sybil_incentive, cap_bypass, credit_inflation


## Step Execution Checklist
| Section | Required | Completed? |
|---------|----------|------------|
| 1. Parameter Boundary Analysis | YES | Y/N/? |
| 2. Economic Invariant Identification | YES | Y/N/? |
| 3. Rate/Supply Interaction Matrix | IF >1 monetary param | Y/N(N/A)/? |
| 4. Fee Formula Verification at Normal Values | IF fee parameters detected | Y/N(N/A)/? |
| 5. Emission/Inflation Sustainability | IF emission/rebase detected | Y/N(N/A)/? |
