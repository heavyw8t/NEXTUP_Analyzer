---
name: "vault-security"
description: "Protocol Type Trigger vault_builder (detected when recon finds ERC4626|deposit|withdraw|totalAssets|totalShares|convertToShares|convertToAssets|previewDeposit|previewRedeem AND the protocol IS the vault implementation, not a caller)"
---

# Injectable Skill: Vault Builder Security

> **Protocol Type Trigger**: `vault_builder` (detected when recon finds: `ERC4626`, `deposit`, `withdraw`, `totalAssets`, `totalShares`, `convertToShares`, `convertToAssets`, `previewDeposit`, `previewRedeem`, `mint`, `redeem`, `maxDeposit`, `maxWithdraw`, share-based accounting logic - AND the protocol IS the vault implementation)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case, depth-state-trace
> **Language**: Primarily EVM; applicable to any share-based vault on any chain
> **Finding prefix**: `[VB-N]`
> **Relationship to VAULT_ACCOUNTING**: That skill covers accounting correctness (share price consistency, time-decay, fee flows). This skill covers vault construction vulnerabilities: first depositor variants, dust insolvency, lock-up gaming, bad debt socialization, reward distribution gaps. Both may be active simultaneously.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Sections 1, 1b, 1c, 1d: depth-edge-case (first depositor variants, share inflation, offset bypass)
- Section 2: depth-state-trace (reward distribution timing, zero-share periods)
- Section 3: depth-external + depth-edge-case (bad debt front-running, MEV on socialized losses)
- Section 4: depth-state-trace (lock-up/vesting bypass via 1-wei seeding)
- Sections 5, 5b: depth-token-flow (rounding direction, dust accumulation, insolvency)
- Section 6: depth-token-flow + depth-state-trace (reward token handling, claim paths)

## When This Skill Activates

Recon detects that the protocol IS a vault implementation (not just a caller). The protocol manages deposits, withdrawals, shares, and total asset tracking. It may also distribute rewards, enforce lock-ups, or socialize bad debt.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `first_depositor`, `donation`, `inflate_share`, `virtualShares`, `rewards_claim`, `totalAssets`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[VB-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. First Depositor Attack — Classic and Variants

The classic first depositor / share inflation attack exploits Solidity's floor rounding in share calculation: `shares = assets * totalShares / totalAssets`. If `totalShares` is very small (e.g., 1 wei) and `totalAssets` is inflated via direct transfer, victim deposits round to 0 shares.

### 1a. Classic Pattern

1. Identify the share minting formula. Does it use `assets * totalShares / totalAssets` or equivalent?
2. Is there a virtual shares/offset mechanism? Check for `_decimalsOffset()`, `+1` offset, `VIRTUAL_SHARES`, or OpenZeppelin's ERC4626 offset.
3. If NO offset: trace the attack path:
   - Attacker deposits 1 wei asset → receives 1 share
   - Attacker sends (donates) large amount of assets directly to the vault (e.g., `token.transfer(vault, 1000e18)`)
   - Vault ratio becomes 1 share = 1000e18 + 1 assets
   - Victim deposits 1000e18 assets → `shares = 1000e18 * 1 / (1000e18 + 1)` → rounds to 0
   - Attacker redeems 1 share for all assets
4. Check: is minting 0 shares explicitly blocked? (`require(shares > 0)` or equivalent)
5. Even WITH a zero-share check: attacker can donate 51% of the victim's deposit amount. Victim gets 1 share, but the attacker steals ~25% of the victim's assets (2 total shares, 1500e18 total assets, each share = 750e18).

Tag: `[TRACE:share_formula={formula} → offset={YES(type)/NO} → zero_share_blocked={YES/NO} → donation_vector={direct_transfer/other}]`

### 1b. Non-Direct Donation Variants

The classic attack uses `token.transfer(vault)` to inflate `totalAssets`. But if the vault tracks assets via a state variable (not `balanceOf`), look for other ways to increase that variable without minting shares:

1. **Rounding ladder**: Can a user deposit and immediately withdraw, where rounding gives them fewer assets back? Repeat N times to slowly inflate `totalAssets` relative to `totalShares`. Trace: does `withdraw(deposit(X))` return exactly X, or X - dust?
2. **Liquidation residual**: If the vault has liquidation functionality, does liquidating a position leave surplus assets in the vault without corresponding shares? Trace the liquidation path — where does the liquidated collateral go?
3. **Fee accumulation without shares**: Do management/performance fees increase `totalAssets` recorded by the vault without minting corresponding fee shares? (Cross-reference with VAULT_ACCOUNTING section 5.)
4. **Rebasing token interaction**: If the vault holds a rebasing token (stETH, aTokens), does the rebase increase `totalAssets`/`balanceOf(vault)` without minting shares?
5. **Interest accrual without checkpoint**: If the vault earns interest from an external source, does accruing interest increase `totalAssets` without a share checkpoint?

For each variant found: is the inflation rate sufficient to make the attack profitable after gas costs?

Tag: `[TRACE:totalAssets_source={balanceOf/state_variable} → inflation_vector={donation/rounding_ladder/liquidation/fee/rebase/interest} → profitable={YES/NO/MARGINAL}]`

### 1c. Offset Bypass

If the vault uses an offset mechanism (e.g., `shares = assets * (totalShares + 1) / (totalAssets + 1)`):
1. **Offset = 1**: The attack is no longer profitable, BUT the share ratio can still be inflated to grief the vault (preventing deposits that would round to 0 shares). This may be a DoS vector.
2. **Larger offset** (e.g., `+1e6`): Neither profitable nor ratio-distorting. Generally safe. Verify the offset is applied consistently in BOTH `convertToShares` AND `convertToAssets`.
3. **Virtual shares mismatch**: Are virtual shares applied to `convertToShares` but NOT to `convertToAssets` (or vice versa)? Asymmetric application creates an exploitable window.
4. **Return-to-zero reactivation**: After ALL users exit the vault (totalShares returns to 0), does the offset protection re-activate for the next depositor? Or does stale `totalAssets` (from dust, fees, or donations) persist, creating a manipulated starting ratio?

Tag: `[TRACE:offset={value} → applied_to_both={YES/NO} → return_to_zero={safe/stale_assets_remain}]`

### 1d. Share Price Oracle Manipulation

If the vault's share price (`totalAssets / totalShares`) is used as a price feed by other protocols:
1. Can an attacker inflate the share price via donation, making external protocols value vault shares incorrectly?
2. Is the share price read in a flash-loan-resistant way (e.g., TWAP, or multi-block average)?
3. Does the vault expose `convertToAssets(1e18)` as a price feed? This is manipulable in the same block.

Tag: `[TRACE:share_price_external_use={YES/NO} → flash_loan_resistant={YES/NO}]`

---

## 2. Reward Distribution Timing — Being First Pays Too Well

Vaults that distribute rewards time-based (epochs, dripping, streaming) often fail to handle periods with zero depositors.

### 2a. Zero-Depositor Reward Accumulation

1. Identify the reward distribution mechanism. Is it time-based (Synthetix-style `rewardRate * timeDelta / totalShares`)?
2. Trace: what happens if `totalShares == 0` during a reward period? Do rewards:
   - Accumulate and get assigned to the first depositor? (BUG: first depositor gets a windfall)
   - Get lost/stuck forever? (BUG: protocol leak)
   - Get paused until a depositor arrives? (CORRECT)
3. Test the sequence: vault created → reward distribution starts → N hours pass with 0 depositors → first user deposits → does user receive all accumulated rewards?

Tag: `[TRACE:reward_mechanism={type} → zero_depositor_handling={accumulates_to_first/stuck/paused} → windfall_amount={estimate}]`

### 2b. Post-Exit Reward Gap

Even if the vault handles the initial zero-depositor case:
1. What if ALL depositors withdraw, leaving `totalShares == 0` for some time, then a new depositor enters?
2. Are rewards from the empty period:
   - Assigned to the new depositor? (Same bug as 2a)
   - Stuck forever? (Leak)
   - Rolled into the next period? (Best behavior)
3. Check: does the reward start/end time update only once at initialization, or does it reset when `totalShares` transitions from 0 → >0?

Tag: `[TRACE:all_exit_scenario → reward_period_active={YES/NO} → re-entry_reward_handling={windfall/stuck/rolled_over}]`

### 2c. Reward Rate Manipulation

If the reward rate depends on `totalShares` or depositor count:
1. Can a user deposit just before a reward distribution and withdraw immediately after to claim a disproportionate share?
2. Is there a minimum stake duration before rewards are claimable?
3. Can flash loans be used to inflate share count during a reward snapshot?

Tag: `[TRACE:reward_rate_depends_on={totalShares/time/both} → flash_loan_exploitable={YES/NO} → minimum_stake_duration={value/NONE}]`

---

## 3. Front-Running Bad Debt Socialization

If the vault socializes losses (bad debt from liquidations, strategy losses, slashing events), users can front-run the loss event to avoid taking their share.

### 3a. Observable Loss Events

1. Identify all events that decrease the vault's `totalAssets` without decreasing `totalShares` (bad debt, strategy loss, slashing).
2. Can these events be predicted or observed before they land on-chain? (e.g., oracle price movement indicating upcoming liquidation, mempool observation of a liquidation TX)
3. Trace the MEV attack path:
   - User sees upcoming loss event (liquidation TX in mempool, or oracle indicates position is underwater)
   - User front-runs with `withdraw()`, avoiding the loss
   - Loss event executes, reducing share price for remaining depositors
   - User back-runs with `deposit()` at the reduced share price
   - User avoided loss socialization and may profit from the recovery

### 3b. Withdrawal Delay as Defense

1. Does the vault use a withdrawal delay / request-based withdrawal? (request → wait → execute)
2. If YES: is the delay long enough to prevent front-running observable events?
3. If NO delay: flag as potential vulnerability for any vault that socializes losses.
4. Check: can the withdrawal request be cancelled and re-submitted to reset the timer?

### 3c. Loss Event Accounting

1. When bad debt occurs: is it immediately reflected in `totalAssets` / share price?
2. Or is there a reporting lag where an admin/keeper must call a function to update the loss?
3. If reporting lag: the window between actual loss and on-chain update is an MEV window. Any withdrawals during this window get the pre-loss share price.

Tag: `[TRACE:loss_socialization={YES/NO} → loss_events={list} → observable_before_onchain={YES/NO} → withdrawal_delay={value/NONE} → reporting_lag={YES/NO}]`

---

## 4. Lock-Up / Vesting Gaming with 1 Wei

If the vault enforces deposit/withdrawal lock-ups or vesting periods, check if the timing can be seeded with a dust transaction.

### 4a. Single-Set Vesting Timer

1. Identify: is the lock-up timer set on the FIRST deposit/withdrawal and never reset by subsequent actions?
2. Trace the gaming path:
   - User deposits 1 wei (or minimum amount) → lock-up timer starts for T duration
   - User waits T duration → lock-up expires
   - User deposits the real amount (e.g., 100,000 tokens) → no new lock-up triggered
   - User can immediately withdraw the full amount
3. Check: does each deposit/withdrawal reset the lock-up timer?

Tag: `[TRACE:lockup_timer_set={first_action_only/each_action} → 1wei_seedable={YES/NO} → timer_reset_on_new_action={YES/NO}]`

### 4b. Per-Action vs Per-User Vesting

1. Does the vault track one vesting position per user, or one per deposit/withdrawal action?
2. If per-user (single position): the 1-wei seeding attack from 4a applies.
3. If per-action (multiple positions): verify the accounting handles multiple overlapping vesting positions correctly. Check:
   - Total user balance across all positions is tracked correctly
   - Withdrawal from a vested position doesn't affect unvested positions
   - No off-by-one in position indexing

### 4c. Vesting Reset Griefing

1. If each action resets the vesting timer: can another user deposit on behalf of (or transfer shares to) a victim to reset their timer?
2. Does `deposit(amount, receiver)` with `receiver != msg.sender` reset the receiver's vesting?
3. Can shares be transferred (ERC20 transfer) to reset the recipient's vesting?

Tag: `[TRACE:vesting_model={per_user/per_action} → deposit_for_others={YES/NO} → transfer_resets_vesting={YES/NO}]`

---

## 5. Dust Rounding and Insolvency

Solidity division rounds down. If the vault rounds DOWN when computing shares to burn on withdrawal, the user receives slightly more assets than their shares are worth, creating a slow leak.

### 5a. Rounding Direction Audit

1. For EVERY share-to-asset and asset-to-share conversion in the vault, verify rounding direction:
   - **Deposits** (assets → shares): should round DOWN (user gets fewer shares = protocol favored)
   - **Withdrawals** (shares → assets): should round DOWN (user gets fewer assets = protocol favored)
   - **Share burning** (computing shares to burn for a given asset withdrawal): should round UP (burn more shares = protocol favored)
2. Rule: **always round in favor of the vault**, never in favor of the user.
3. Check: does the vault use OpenZeppelin's `Math.mulDiv` with explicit rounding direction, or plain Solidity division (always rounds down)?
4. If plain division: verify that the division is in the correct direction for each use case.

Tag: `[TRACE:conversion={function} → direction={deposit/withdraw/redeem/mint} → rounding={favors_vault/favors_user} → math_lib={OZ_Math/plain_division}]`

### 5b. Dust Accumulation → Insolvency Path

1. Even if each rounding error is 1 wei: can a user exploit this by withdrawing many times?
   - Deposit once with a large amount
   - Withdraw 1 wei of shares repeatedly, each time gaining 1 extra wei of assets
   - After N withdrawals: user has extracted N wei more than they deposited
2. This is usually Low/Info severity. ESCALATE to Medium+ if:
   - Assets are tracked via a state variable (not `balanceOf(vault)`), meaning the variable can underflow
   - The vault has a fixed asset pool that doesn't replenish
   - The accumulated dust exceeds meaningful amounts at scale (e.g., 1000 users × 1000 withdrawals each × 1 wei = 1e6 wei = still dust for 18-decimal tokens, but significant for 6-decimal tokens like USDC)
3. Check: does `totalAssets` tracked by state variable ever go below the sum of all depositor claims? If yes → last withdrawer gets less than expected (insolvency).

Tag: `[TRACE:rounding_leak_per_withdraw={amount} → asset_tracking={balanceOf/state_variable} → decimal_count={N} → insolvency_risk={YES(path)/NO}]`

### 5c. Deposit-Withdraw Rounding Asymmetry

1. Trace: `deposit(X)` → receive S shares → `withdraw(S shares)` → receive Y assets. Is Y == X?
2. If Y < X: user loses dust on round-trip (vault favored, correct behavior).
3. If Y > X: user gains dust on round-trip (user favored, potential insolvency).
4. If Y == X exactly: verify this holds for ALL amounts, not just round numbers. Test with prime numbers, odd amounts, amounts near rounding boundaries.

Tag: `[TRACE:round_trip → deposit({X}) → shares={S} → withdraw({S}) → assets={Y} → delta={Y-X} → favors={vault/user}]`

---

## 6. Reward Token Handling

If the vault distributes incentive tokens beyond yield (not just share price appreciation):

### 6a. Reward Claim Completeness

1. List ALL external protocols the vault interacts with (strategies, lending protocols, DEXes).
2. For EACH: does the external protocol emit reward tokens? (e.g., Morpho rewards, Aave incentives, Compound COMP, Curve CRV)
3. Does the vault claim these rewards? Check for `claim()`, `getReward()`, `claimRewards()`, or equivalent calls.
4. If NOT claimed: rewards accumulate in the external protocol, stuck forever. Flag as finding.

### 6b. Reward Token Flexibility

1. External protocols can add or rotate incentive tokens at any time.
2. Does the vault hardcode reward token addresses?
3. If hardcoded: new reward tokens from the external protocol will be unclaimable. Recommend a configurable mapping.

### 6c. Permissionless Reward Claims

1. Can anyone call the external protocol's claim function for the vault's address?
2. If YES: reward tokens can be sent to the vault contract without the vault expecting it.
3. Does the vault handle unexpected incoming token transfers? If not: tokens are stuck in the contract.
4. If the vault uses `balanceOf` for its own accounting: an unexpected reward token transfer could corrupt accounting if the reward token is the same as the deposit token.

### 6d. Reward Distribution Fairness

1. When rewards are claimed: are they distributed proportionally to current share holders, or to shares at the time rewards were earned?
2. Can a user deposit just before reward distribution, claim rewards, and withdraw? (Same issue as section 2c.)
3. Are reward tokens valued correctly when computing vault NAV or share price?

Tag: `[TRACE:external_protocols={list} → reward_tokens={list} → claimed={YES/NO} → hardcoded={YES/NO} → permissionless_claim={YES/NO}]`

---

## Common False Positives

- **Virtual offset ≥ 1e6 with consistent application**: First depositor attack is effectively mitigated. Only flag if offset is asymmetric or <1e3.
- **Dust rounding in 18-decimal tokens**: 1 wei of 18-decimal token is economically negligible. Only escalate if asset decimals ≤ 8 or the vault tracks assets via state variable.
- **Reward tokens from inactive/deprecated protocols**: If the external protocol has stopped emitting rewards, unclaimed reward findings are informational.
- **Lock-up gaming with minimum deposit enforced**: If the vault requires minimum deposit > dust threshold, 1-wei seeding is blocked.
- **Bad debt front-running with withdrawal delay ≥ 24h**: Delay makes front-running impractical for most observable loss events.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: First depositor / share inflation via direct donation (no offset)
  Where it hit: StakedUSH vault (row 721), LendingVault (row 6800), GMVault (row 5627), Burve NoopVault (row 1653)
  Severity: HIGH
  Source: Solodit (row_index 721)
  Summary: When USH tokens are sent directly to the StakedUSH vault contract, `totalAssets` is inflated without a corresponding increase in `totalShares`. A first depositor sends 1 wei to obtain 1 share, then donates a large amount, causing subsequent depositors to receive 0 shares due to floor division. No virtual-share offset or zero-share guard was present. The team confirmed and fixed the bug.
  Map to: ERC4626, first_depositor, share_inflation, totalAssets, totalShares

- Pattern: Share inflation via dead-shares minted to `msg.sender` instead of the zero address
  Where it hit: AutoCompoundingPodLp (row 2594)
  Severity: HIGH
  Source: Solodit (row_index 2594)
  Summary: The vault minted "dead shares" to `msg.sender` on first deposit rather than to address(0). This means the attacker retains ownership of those shares and can redeem them after inflating `totalAssets` via a front-run donation. The attacker deposits a tiny amount, inflates the price, then withdraws all assets including the victim's deposit. Fix: mint dead shares to address(0) so they are permanently locked.
  Map to: ERC4626, first_depositor, share_inflation, totalAssets, totalShares

- Pattern: Yield front-running (sandwich attack on `totalAssets` update)
  Where it hit: MultipliVault `onUnderlyingBalanceUpdate` (row 1056), CurvedVault `totalAssets` stale liquidityIndex (row 4587)
  Severity: HIGH
  Source: Solodit (row_index 1056)
  Summary: When an external keeper updates the vault's underlying balance (increasing `totalAssets`), an attacker observes the pending transaction, deposits a large amount beforehand, and withdraws immediately after. The attacker captures yield they did not earn, diluting returns for long-term depositors. The root cause is that share price is determined by `totalAssets` at the moment of deposit/withdrawal with no minimum holding period. Fix: require a minimum deposit lock-up or use a time-weighted share price.
  Map to: ERC4626, totalAssets, totalShares, share_inflation

- Pattern: Bad debt front-running (withdrawal before loss socialization, no delay)
  Where it hit: FraxPair lending vault (row 15142), LendingVault vault (row 11607)
  Severity: HIGH
  Source: Solodit (row_index 15142)
  Summary: When a borrower accrues bad debt and the liquidation leaves residual shortfall, the vault's `totalAssets` remains overstated until the shortfall is explicitly written down. Depositors who observe the impending loss event (e.g., oracle price movement, pending liquidation in the mempool) can front-run with `withdraw()`, exiting at the pre-loss share price. Remaining depositors absorb the full loss. No withdrawal delay existed to prevent this. Fix: implement a withdrawal request queue with a delay, or mark bad debt immediately at the point of liquidation.
  Map to: ERC4626, totalAssets, withdrawal_queue

- Pattern: Withdrawal griefing via deposit-on-behalf (resets `idToBlockOfLastDeposit`)
  Where it hit: LendingAssetVault MetaVault (row 2648), VaultManagerV2 (row 7348)
  Severity: HIGH
  Source: Solodit (row_index 2648)
  Summary: A vault enforces a same-block withdrawal lock by recording `idToBlockOfLastDeposit` on every deposit. The `deposit(amount, receiver)` function accepts an arbitrary `receiver`, so an attacker can deposit 1 wei on behalf of any victim to reset their withdrawal lock to the current block, permanently blocking the victim from withdrawing in the same transaction. The attacker repeats this on every block to freeze the victim's assets indefinitely. Fix: restrict `deposit` so that only the `receiver` themselves can trigger a new deposit on their account.
  Map to: ERC4626, withdrawal_queue, first_depositor

- Pattern: Rounding direction wrong — `withdraw` rounds down shares burned (user favored)
  Where it hit: FundContract (row 1519), TurboSafe ERC4626 mint bug (row 16483)
  Severity: HIGH
  Source: Solodit (row_index 1519)
  Summary: The `withdraw()` function used Solidity floor division when computing shares to burn, instead of ceiling division. This meant users received slightly more assets than their shares were worth on each withdrawal, creating a slow drain from the vault. With enough withdrawals or a low-decimal asset, the vault's tracked `totalAssets` diverges from its real balance, eventually making the last redeemer unable to exit. ERC4626 spec requires that `withdraw` rounds up shares burned (in favor of the vault). Fix: use `Math.mulDiv(..., Math.Rounding.Up)` when computing shares to burn.
  Map to: ERC4626, totalAssets, totalShares, vault_accounting

- Pattern: Reward windfall for first depositor after zero-depositor period
  Where it hit: Fair Funding vault `amount_claimable_per_share` (row 13143), RedVeil Popcorn `highWaterMark` (row 13373)
  Severity: HIGH
  Source: Solodit (row_index 13143)
  Summary: The Fair Funding vault accumulates `amount_claimable_per_share` over time. When a new depositor arrives, their position is immediately eligible to claim all previously accrued WETH (the counter since contract creation), not just rewards earned after their entry. Because the vault over-commits payouts, it becomes insolvent: the first few claimants drain the contract while later depositors find nothing to claim. Fix: initialize `position.amountClaimed` to the current `amount_claimable_per_share` snapshot at deposit time so new depositors only accrue future rewards.
  Map to: ERC4626, totalShares, totalAssets

- Pattern: Fee accounting corruption — deposit fee not reflected in `totalAssets` before share mint
  Where it hit: GovernanceHYBR.sol (row 177)
  Severity: HIGH
  Source: Solodit (row_index 177)
  Summary: In `GovernanceHYBR.deposit`, the contract first deposits HYBR tokens into `votingEscrow`, which causes `totalAssets()` to increase before shares are minted. The share calculation uses the *post-deposit* `totalAssets`, which already includes the tokens just provided by the depositor. This results in the depositor receiving fewer shares than they are entitled to. The standard pattern requires capturing the share price *before* the asset transfer and computing shares on the pre-transfer ratio. Fix: snapshot `totalAssets` prior to the deposit call and use that value for the share calculation.
  Map to: ERC4626, totalAssets, totalShares, vault_accounting


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Classic First Depositor | YES | | Share formula, offset, zero-share check |
| 1b. Non-Direct Donation Variants | YES | | totalAssets inflation vectors |
| 1c. Offset Bypass | IF offset mechanism present | | Asymmetry, return-to-zero |
| 1d. Share Price Oracle Manipulation | IF share price used externally | | Flash loan resistance |
| 2a. Zero-Depositor Reward Accumulation | IF time-based rewards | | First depositor windfall |
| 2b. Post-Exit Reward Gap | IF time-based rewards | | All-exit scenario |
| 2c. Reward Rate Manipulation | IF reward rate depends on shares | | Flash loan, minimum stake |
| 3a. Observable Loss Events | IF vault socializes losses | | MEV front-running path |
| 3b. Withdrawal Delay Defense | IF vault socializes losses | | Delay adequacy |
| 3c. Loss Event Accounting | IF vault socializes losses | | Reporting lag window |
| 4a. Single-Set Vesting Timer | IF lock-up/vesting exists | | 1-wei seeding |
| 4b. Per-Action vs Per-User Vesting | IF lock-up/vesting exists | | Position accounting |
| 4c. Vesting Reset Griefing | IF timer resets on action | | Deposit-for-others |
| 5a. Rounding Direction Audit | YES | | Every conversion, every direction |
| 5b. Dust Accumulation → Insolvency | YES | | State variable tracking, decimals |
| 5c. Deposit-Withdraw Asymmetry | YES | | Round-trip test |
| 6a. Reward Claim Completeness | IF external protocols emit rewards | | All protocols checked |
| 6b. Reward Token Flexibility | IF reward tokens exist | | Hardcoded vs configurable |
| 6c. Permissionless Claims | IF external claim is open | | Unexpected token handling |
| 6d. Reward Distribution Fairness | IF rewards distributed | | Timing, flash loan |
