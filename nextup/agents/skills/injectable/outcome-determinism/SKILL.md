---
name: "outcome-determinism"
description: "Protocol Type Trigger outcome_determinism - detected when EITHER of these code patterns are present - - Selection from finite depletable pool with fallback behavior (while(full)..."
---

# Injectable Skill: Outcome Determinism - Selection Fairness & Strategic Timing

> **Protocol Type Trigger**: `outcome_determinism` - detected when EITHER of these code patterns are present:
>   - Selection from finite depletable pool with fallback behavior (`while(full) next`, `modulo` with shrinking domain, category/slot/validator selection)
>   - Time-gated actions with observable default/fallback outcomes (`deadline`, `claimPeriod`, `defaultSelection`, `expiry` + fallback path that computes from predictable state)
> **Inject Into**: Breadth agents, depth-edge-case
> **Language**: All (rational actor patterns are chain-agnostic)
> **Finding prefix**: `[OD-N]`
> **Added in**: v1.1
>
> **NOTE**: Callback selective revert (Section 1a of the original skill) and RNG consumption enumeration (Section 1b) are now ALWAYS-ON checks in the depth agent template - they do not require this injectable to trigger.

## What This Injectable Adds (beyond always-on checks)

The always-on depth template already covers:
- **Callback selective revert**: Full taxonomy of external execution transfers (ERC-721/1155/777/1363, flash loans, hooks, low-level calls, ETH transfers) - see depth-templates.md "CALLBACK SELECTIVE REVERT ANALYSIS"
- **Tainted source consumption enumeration**: RNG/oracle consumed by multiple functions → rate severity by worst consumer - see depth-templates.md PART 1 item 6

This injectable adds analysis that only applies when SPECIFIC structural patterns exist:

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `randomness`, `VRF`, `chainlink_vrf`, `commit_reveal`, `block.number`, `block.timestamp`, `prevrandao`, `RANDAO`, `blockhash`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[OD-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Selection Fairness Under Constraint Changes

For every selection algorithm operating on a set that can shrink, grow, or be modified between selections:

### 1a. Probability Redistribution on Depletion

| Selection Function | Pool Size | Depletion Mechanism | Fallback Behavior | Redistribution Fair? |
|-------------------|-----------|--------------------|--------------------|---------------------|

**Fairness test**: When element X is removed from a pool of N:
- **Fair**: Each remaining element gets probability 1/(N-1) - uniform redistribution
- **Biased**: Sequential fallback (`index++`, `next slot`) - adjacent element gets doubled probability
- **Broken**: Infinite loop (no exit when all depleted) or unreachable elements

**Common biased patterns across protocol types**:
- `while (slot_full) { index++ }` - next-in-line gets 2/N probability (NFT categories, validator slots, LP positions)
- `if (depleted) skip` - skipped element's share goes entirely to next check, not distributed
- `modulo(N)` where N decreases - specific indices get boosted as N shrinks

**Quantify**: At each depletion level (1-of-N, N/2-of-N, N-1-of-N), what is the maximum probability deviation from uniform? Is it exploitable (can the actor influence which elements deplete first)?

Tag: `[VARIATION:pool N→N-K → element X probability 1/N→{new_prob} → bias={factor}x]`

### 1b. Admin Parameter Regression on Selection Algorithms

For bounded parameters (caps, limits, quotas) where the bound can be LOWERED below already-accumulated state and the bound is used by a selection/iteration algorithm:

| Parameter | Setter | Current Accumulated | Can Set Below Accumulated? | Selection Algorithm Affected | What Breaks? |
|-----------|--------|--------------------|--------------------------|-------|--------------|

**This extends Rule 14** (Setter Regression) specifically for selection/allocation algorithms: when a cap is lowered below the current count, does the selection algorithm's termination condition still hold? (e.g., `while (count == max)` becomes unreachable when count > max)

---

## 2. Strategic Timing - Delay, Front-Run, Sequence

**Core question**: For each user-facing action, is the TIMING of the action exploitable by a rational self-interested actor?

### 2a. Delay-vs-Act Rationality

For every time-gated action with a default or fallback:

| Action | Active Path | Default/Fallback Path | Default Predictable? | Default Sometimes Better? | Delay Cost |
|--------|-----------|----------------------|---------------------|--------------------------|-----------|

**A rational actor will delay when ALL THREE hold**:
1. The default outcome is **predictable** (computed from observable on-chain state, not future unknowns)
2. The default is **sometimes better** than the active choice (different formula, different prices, different parameters)
3. The **cost of waiting** (opportunity cost, gas, penalty) is lower than the expected value gain

**Cross-protocol examples**:
- DeFi: Defer unstaking claim when penalty decreases over time and rate may improve
- NFT: Defer coin/trait claiming when default allocation uses more favorable prices than current
- Governance: Defer vote to observe other votes and vote strategically
- Staking: Defer withdrawal when accrued rewards during delay exceed the withdrawal amount
- Auctions: Defer bid to last block to prevent counter-bidding (sniping)

**Methodology**:
1. Identify the active path (user calls function before deadline)
2. Identify the default path (what happens if user doesn't act - system assigns default, claim expires, fallback triggers)
3. Is the default outcome computable from CURRENT on-chain state? (If it depends on future block hash or unresolved oracle → not predictable → no strategic edge)
4. Compare: under what market/state conditions is default > active? How often do those conditions occur?
5. What does delay cost? (forfeiture, penalty, opportunity cost, gas savings)

Tag: `[TRACE:action={fn} deadline={T} → default={fallback_fn} → computed_from={state_vars} → predictable={YES/NO} → default_better_when={condition}]`

### 2b. Admin Action Information Asymmetry

For every admin-settable parameter that affects pending or future user operations:

| Parameter | Setter | Timelock? | Event Emitted? | Affects Pending Operations? | Asymmetry Window |
|-----------|--------|-----------|---------------|---------------------------|-----------------|

**Applies universally** - any `onlyOwner`/`onlyAdmin` setter that changes a parameter used in user-facing calculations creates a window where the admin knows the new value but users don't.

**Severity factors**:
- Instant setter (no timelock): 1-block asymmetry - exploitable via same-block front-running
- No event emission: window extends until users discover change via failed transaction or manual inspection
- Retroactive effect on pending state: admin changes rules for operations already in progress
- Combined (instant + no event + retroactive): maximum exploitation window

### 2c. Sequence-Dependent Outcomes

For actions where the ORDER of multiple actors matters:

| Action | Same-Block Ordering Matters? | Cross-Block Ordering Matters? | First-Mover Advantage? | Last-Mover Advantage? |
|--------|----------------------------|------------------------------|----------------------|---------------------|

**Check**: Can an actor observe others' pending actions (mempool) and position before/after them for profit?

---

## Key Questions (must answer all)
1. For each selection from a shrinking pool: does probability redistribute uniformly? Quantify the bias.
2. For each time-gated action: is the default/fallback predictable and sometimes better than active choice?
3. For each admin setter: what is the information asymmetry window? Does it affect pending operations?
4. For each multi-actor sequence: can ordering be exploited?

## Common False Positives
- **Truly unpredictable defaults**: If fallback depends on future block hash or external oracle not yet published, strategic delay has no edge
- **Equal-value outcomes in selection**: If all pool elements have identical economic value, selection bias has no incentive
- **Timelock-protected setters**: If admin changes require N-block delay with public announcement, asymmetry is mitigated (but verify ALL setters have the timelock, not just some)
- **Uniform delay cost**: If delaying always costs more than the potential gain, rational delay is not profitable

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Attacker reuses shared sequence number across lottery providers by reverting callback after observing provider change, forcing the same randomness slot to be re-consumed under the new provider and controlling the lottery outcome.
  Where it hit: Megapot ScaledEntropyProvider (Solidity)
  Severity: MEDIUM
  Source: Solodit (row_index 23)
  Summary: The contract tracks VRF requests by sequence number only, not by (sequence, provider) pair. An attacker front-runs a provider switch and causes the pending callback to revert, leaving the sequence number uncleared. The attacker then calls the new provider with the same sequence number, choosing the result that wins the jackpot.
  Map to: sequence_dependent, front_run

- Pattern: Rational actor observes on-chain collateral-settlement threshold (put options in-the-money condition), predicts when LP losses will be realized, and exits the LP vault before `settle()` is called, shifting the full loss to slower LPs.
  Where it hit: Dopex PerpetualAtlanticVaultLP (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 10535)
  Summary: The price threshold that triggers option settlement is publicly observable. Any LP who detects an upcoming in-the-money settlement can redeem before it executes, provided excess collateral exists. The default outcome (remaining in the vault through settlement) is strictly worse than the active choice (exit before settlement). Repeated LP exits drain available collateral, causing secondary DoS on RdpxV2Core bonding.
  Map to: strategic_timing, depletion

- Pattern: Accepted grant recipient front-runs the manager's `_allocate()` call by re-registering with a higher `proposalBid`, causing the subsequently-called `_distribute()` to pay out the inflated amount rather than the accepted one.
  Where it hit: Gitcoin RFPSimpleStrategy (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 10266)
  Summary: `_registerRecipient()` overwrites `proposalBid` without checking whether the recipient is already accepted. The pool manager's acceptance transaction is visible in the mempool; the registrant re-submits with a larger bid before allocation commits it. Because `_distribute()` reads the live `proposalBid`, the payout is the attacker's inflated value rather than the negotiated one.
  Map to: sequence_dependent, front_run

- Pattern: At auction close, any bidder who delays to the last block prevents counter-bids; the ordering guarantee of block finality provides a structural last-mover advantage.
  Where it hit: Clearpool Finance PermissionlessProtocol `bid()` (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 12572)
  Summary: Every bid transaction can be front-run or back-run. Because there is no time buffer after the final bid, a bidder who submits in the last block cannot be outbid before the auction closes. Waiting to bid is therefore a dominant strategy for any bidder who can monitor the mempool, making honest earlier bids economically irrational.
  Map to: strategic_timing, sequence_dependent

- Pattern: A relayer delays honest checkpoint submission, observes the signed checkpoint data of the first honest submitter in the mempool, and re-submits the same proof with a higher gas price to steal the reward.
  Where it hit: Filecoin SubnetActorManagerFacet `submitCheckpoint()` (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 8269)
  Summary: `submitCheckpoint()` pays a reward to whichever address submits a valid checkpoint first. Because checkpoint data is public once broadcast, a monitoring actor can copy a valid submission and front-run it. Honest relayers who do the computational work receive nothing; the reward allocation outcome is purely a function of gas-price ordering, not of who originated the work.
  Map to: strategic_timing, sequence_dependent

- Pattern: Admin setter for system parameters (oracle prices, collateral ratios) takes effect in the same block with no timelock and no event; users who observe the pending parameter-change transaction can act on state that has not yet updated, while the admin acts on the post-update value.
  Where it hit: TBTC/Keep TBTCSystem admin parameter setters (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 18837)
  Summary: Owner functions change system parameters (price feeds, collateral thresholds) immediately, with no mandatory delay. The admin observes the chain state and can sequence their own transactions before user operations that depend on the old parameters, or can front-run user transactions with a parameter change that makes the user's action unfavorable. The absence of timelocks means the asymmetry window is one block for a colluding miner and potentially many blocks for any user who relies on event logs.
  Map to: admin_parameter_regression, front_run

- Pattern: Two governance actors submit conflicting `removeValidators` transactions; the ordering of inclusion determines which validator set remains active, and either party can front-run the other to force a different selection outcome.
  Where it hit: Liquid Collective OperatorsRegistry `removeValidators()` (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 13752)
  Summary: `removeValidators()` takes a list of validator indices to remove from the active set. If entities A and B each submit a removal with different index lists, the order in which the transactions are mined produces a different final active validator set. Either party can observe the other's pending transaction and front-run it to ensure their preferred selection outcome. No snapshot or ordering guard exists.
  Map to: sequence_dependent, probability_redistribution

- Pattern: Calling `pokeTokens()` before other voters have cast their votes inflates the total voting-power denominator used for bribe calculation, reducing the per-token bribe payout for all honest voters who voted before the poke.
  Where it hit: Alchemix Voter.sol `pokeTokens()` (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 6840)
  Summary: `pokeTokens()` does not verify that the epoch has not already been voted in. Invoking it early adds weight to the total without waiting for all votes, then subsequent vote weight additions increase the denominator, diluting early voters' bribe share. The outcome distribution across voters is sequence-dependent: actors who vote after the poke receive a smaller share than those who voted before it, regardless of their absolute vote weight.
  Map to: sequence_dependent, probability_redistribution

- Pattern: User observes a pending oracle price update in the mempool and times a deposit or redemption to execute against the stale exchange rate, capturing risk-free profit from the price delta before the oracle commits.
  Where it hit: DYAD protocol `_eth2dyad()` / `_dyad2eth()` (Solidity)
  Severity: HIGH
  Source: Solodit (row_index 13207)
  Summary: The exchange rate used for deposits and redemptions is derived from an oracle that updates via observable on-chain transactions. A rational actor can watch for the oracle update transaction and front-run it: deposit at the pre-update rate when the new rate is higher (leveraged ETH exposure), or redeem before a rate decrease. Because the oracle price path is often predictable from off-chain ETH price feeds, strategic timing does not even require mempool access.
  Map to: strategic_timing, front_run


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Depletion Redistribution | IF selection from finite/depletable pool | | Quantify bias at each depletion level |
| 1b. Parameter Regression on Selection | IF admin can lower cap below accumulated AND cap used by selection algo | | Extends Rule 14 |
| 2a. Delay-vs-Act Rationality | IF time-gated action with default/fallback | | Check all three conditions |
| 2b. Admin Information Asymmetry | IF admin setter affects pending user operations | | Check timelock AND event emission |
| 2c. Sequence-Dependent Outcomes | IF multiple actors' ordering affects results | | Check same-block and cross-block |
