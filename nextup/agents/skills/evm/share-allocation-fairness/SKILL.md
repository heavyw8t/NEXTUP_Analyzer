---
name: "share-allocation-fairness"
description: "Trigger SHARE_ALLOCATION flag detected in pattern scan - Used by Breadth agents, depth-edge-case"
---

# Skill: SHARE_ALLOCATION_FAIRNESS

> **Trigger**: SHARE_ALLOCATION flag detected in pattern scan
> **Used by**: Breadth agents, depth-edge-case

## Purpose
Analyze fairness of share/token allocation mechanisms where users receive shares proportional to deposits, contributions, or participation -- checking for late-entry advantages, queue-position gaming, and time-weighting omissions.

## Methodology

### STEP 1: Classify Allocation Mechanism
Identify which pattern the protocol uses:

| Type | Pattern | Key Risk |
|------|---------|----------|
| Pro-rata snapshot | Shares minted at fixed ratio at deposit time | Late depositors dilute early depositors' accrued value |
| Time-weighted | Shares accrue value based on duration held | Checkpoint manipulation, discrete vs continuous accrual |
| Queue-based | Deposits processed in batch/queue order | Queue position gaming, front-running batch processing |
| Epoch-based | Shares valued per epoch/period boundary | Cross-epoch timing arbitrage |

### STEP 2: Late Entry Attack Model
For each allocation entry point:

1. **Identify accrual source**: What generates value for existing share holders? (yield, fees, rewards, appreciation)
2. **Trace timing**: When does accrued value become claimable vs when can new shares enter?
3. **Check for time-weighting**: Does allocation account for HOW LONG shares were held, or only THAT shares are held?
4. **Model attack**: Can a depositor enter AFTER value accrues but BEFORE distribution, capturing value they did not earn?

| Entry Function | Accrual Source | Time-Weighted? | Late Entry Possible? | Impact |
|---------------|----------------|----------------|---------------------|--------|

#### STEP 2c: Cross-Address Deposit Model
For each entry function accepting an `address` beneficiary parameter (e.g., `stake(address to, uint256 amount)`):
Check: what is the DEFAULT state for a never-before-seen `to` address? Can depositing for `to` where `to` has zero-initialized accounting unlock historical rewards, bypass cooldowns, or inherit accrued value?

| Entry Function | Accepts Beneficiary? | Default State for New Address | Exploitable? | Impact |
|---------------|---------------------|------------------------------|-------------|--------|

If `to != msg.sender` enables reward capture the recipient did not earn -> FINDING (late-entry variant).

#### STEP 2d: Pre-Setter Timing Model
For each admin-settable reward/rate parameter: model the sequence user_stakes -> admin_sets_rate -> rewards_accrue.
Does the user receive retroactive rewards for the period BEFORE the rate was set? Does a staker after rate-setting receive the same, more, or less?

| Parameter Setter | Staked-Before-Set? | Retroactive Rewards? | Fair? |
|-----------------|-------------------|---------------------|-------|

If staking before rate-setting yields unearned rewards or causes reward loss for post-set stakers -> FINDING (timing fairness).

### 2e. Pre-Configuration State Analysis

For the allocation mechanism identified in Step 1:

| Configuration Step | Parameter Set | Functions Available Before Set | Exploitable Default? |
|--------------------|-------------|-------------------------------|---------------------|

1. What is the deployment/initialization sequence? List all configuration steps in order.
2. For each step: what functions are callable BEFORE this configuration completes?
3. Are there reward/share calculations that use unconfigured (zero/default) values?
4. Can a user deposit/stake before full configuration and receive outsized rewards/shares?
5. Is there a `pause` mechanism that prevents interaction before configuration completes?

If users can interact during partial configuration AND default values create unfair advantage → FINDING (minimum Medium, Rule 13: design gap).

### STEP 3: Queue Position and Batch Processing
For protocols with batch/queue processing:

1. **Ordering fairness**: Is queue order FIFO, arbitrary (operator-chosen), or manipulable?
2. **Partial processing**: Can operator process some deposits but not others within a batch?
3. **Cross-batch state**: Does processing order within a batch affect allocation ratios?
4. **Deposit splitting**: Can a user split one large deposit into many small ones for queue advantage?

### STEP 4: Share Redemption Symmetry
Check that entry and exit use consistent valuation:

1. **Mint vs burn ratio**: Are shares minted at the same exchange rate they can be burned?
2. **Pending claims**: Can unredeemed shares dilute active shares' value?
3. **Withdrawal queue**: Does withdrawal ordering create unfair priority?

#### STEP 4b: Aggregate Constraint Coherence (Rule 14)
For independently-settable allocation rates/shares (e.g., per-pool weights, fee splits, distribution %):
Is the sum constraint enforced ON-CHAIN in the setter? Can each rate be changed independently without validating the aggregate?

| Rate/Weight Setter | Aggregate Constraint | Enforced On-Chain? | What if Sum Exceeds/Falls Short? |
|-------------------|---------------------|-------------------|--------------------------------|

If aggregate constraint NOT enforced and rates independently settable -> FINDING (Rule 14).

## Output
For each finding, specify:
- Allocation mechanism type
- Whether time-weighting is present or missing
- Concrete attack sequence with numerical example
- Who benefits and who is harmed

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Source: candidates.jsonl (94 rows). Selected 8 findings covering all six distinct sub-buckets.

---

## Example 1

bucket: first_depositor
severity: HIGH
row_index: 2214
summary: SheepDog contract — attacker calls `protect` with 1 wei, then transfers a large token amount directly to the contract. Total balance inflates without touching totalShares. Subsequent depositors receive 0 shares due to rounding. Attacker waits the 2-day withdrawal delay and claims the entire pool.
why_selected: Cleanest canonical first-depositor + donate-inflate sequence with explicit rounding-to-zero outcome and concrete withdrawal path. Fix: dead-shares mint or minimum initial deposit.

---

## Example 2

bucket: share_inflation
severity: HIGH
row_index: 10301
summary: StakePet contract — creator deposits a small amount to obtain 1 share unit, then sends a large collateral amount directly to the contract. Each subsequent depositor receives 0 ownership shares because the single share now represents enormous collateral. Complete loss of deposited funds for victims. Fix: Uniswap V2 dead-shares pattern (burn minimal liquidity to null address).
why_selected: Explicitly tagged "Vault; Share Inflation; Initial Deposit; First Depositor Issue". Covers the creator-as-attacker variant and references the accepted mitigation pattern.

---

## Example 3

bucket: donation_attack
severity: HIGH
row_index: 3467
summary: ClaggAaveAdapter / ClaggBaseAdapter — `compound()` sets totalLiquidity to the current aToken balance. An attacker donates aTokens directly to the contract, inflating totalLiquidity and totalSupply independently, causing other users to lose shares. Fix: mint dead shares on first deposit (10 000 dead shares added post-fix).
why_selected: Demonstrates the donation vector via rebasing/receipt tokens rather than plain ERC20 transfer, and shows how `compound()` as the accounting reset point is the real root cause.

---

## Example 4

bucket: dead_shares
severity: HIGH
row_index: 2594
summary: AutoCompoundingPodLp — dead shares are minted to `msg.sender` instead of a dead address. The deployer retains those shares and can withdraw them, reversing the inflation-protection guarantee entirely. Attack path: frontrun deployment, inflate totalAssets, withdraw leaving 2 shares, then profit from victim's deposit rounding.
why_selected: Precisely isolates the dead-shares mitigation failure mode: correct intent, wrong recipient. Useful contrast against Example 2 to show that implementing dead shares to msg.sender provides no real protection.

---

## Example 5

bucket: rounding
severity: HIGH
row_index: 2647
summary: Fraxlend lending pairs — rounding direction when minting/burning shares is exploitable: attacker manipulates rounding to inflate the value of a single share and steals 100% of the first deposit. Exploitable only in newly created pairs. Fix: deployer makes an initial deposit into each new pair before opening to users.
why_selected: Tagged explicitly as a rounding-direction finding in a lending context. Shows that rounding-down-favors-protocol can be inverted to favor attacker when totalSupply is 0.

---

## Example 6

bucket: share_dilution
severity: HIGH
row_index: 1656
summary: Closure contract — `valueStaked` is updated before tax earnings are distributed. The new LP's deposit is counted in the denominator before they are entitled to the current round of taxes, diluting the share of earnings that existing LPs should receive. Happens on every single-sided liquidity add. Fix: distribute tax before updating valueStaked.
why_selected: Clean share-dilution-on-fee-accrual pattern caused by update ordering, not inflation. Distinct from donate attacks. Concrete on-chain trigger (every single-sided add) makes it high-likelihood.

---

## Example 7

bucket: share_rate_manipulation
severity: HIGH
row_index: 14112
summary: AutoPxGmx ERC4626 vault — Alice deposits 1 wei, then sends 10e18 - 1 pxGMX directly to the vault via ERC20 transfer, setting share price to 10 pxGMX per share. Bob deposits 19 pxGMX and gets only 1 share due to `convertToShares` rounding. Both redeem at 14.5 pxGMX each, so Bob loses ~4.5 pxGMX net (less withdrawal fee). Mitigations: high minimum first deposit, dead shares, or seed pools at deployment.
why_selected: Textbook share-rate-manipulation via direct ERC20 transfer with quantified victim loss and explicit per-share arithmetic. Good for agent pattern-matching against `convertToShares` / `totalAssets` based vaults.

---

## Example 8

bucket: share_dilution
severity: MEDIUM
row_index: 8824
summary: Covalent staking — reward distribution uses the total staked balance at the moment of distribution, including stakes placed after the relevant epoch began. An attacker front-runs the staking manager's distribution call, stakes, receives a full-epoch reward, then unstakes and repeats with the same capital. Existing stakers' share of each epoch's reward is diluted. Fix: checkpoint-based share accounting per epoch.
why_selected: Represents the late-entry / new-staking-dilutes-existing-stakers variant of share dilution in a staking (not ERC4626) context. Distinct root cause from Example 6: not an ordering bug but a missing time-weight checkpoint.


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Classify Allocation Mechanism | YES | ✓/✗/? | |
| 2. Late Entry Attack Model | YES | ✓/✗/? | |
| 2c. Cross-Address Deposit Model | YES | ✓/✗/? | Check beneficiary != msg.sender patterns |
| 2d. Pre-Setter Timing Model | YES | ✓/✗/? | Model deposit-before-rate-set sequence |
| 2e. Pre-Configuration State Analysis | YES | ✓/✗/? | Deployment window + unconfigured defaults |
| 3. Queue Position and Batch Processing | IF queue/batch detected | ✓/✗(N/A)/? | |
| 4. Share Redemption Symmetry | YES | ✓/✗/? | |
| 4b. Aggregate Constraint Coherence | IF multiple settable weights | ✓/✗(N/A)/? | Rule 14 enforcement check |

If any step skipped, document valid reason (N/A, no queue, single pool, no settable weights).
