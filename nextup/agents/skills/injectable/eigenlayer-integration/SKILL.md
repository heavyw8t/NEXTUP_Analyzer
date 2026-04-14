---
name: "eigenlayer-integration"
description: "Protocol Type Trigger eigenlayer_integration (detected when recon finds IStrategy|IDelegationManager|ISlasher|IEigenPod|restake|eigenLayer|AVS|operator.*register - protocol integrates with EigenLayer restaking)"
---

# Injectable Skill: EigenLayer Integration Security

> **Protocol Type Trigger**: `eigenlayer_integration` (detected when recon finds: `IStrategy`, `IDelegationManager`, `ISlasher`, `IEigenPod`, `IStrategyManager`, `IRewardsCoordinator`, `restake`, `eigenLayer`, `AVS`, `operator.*register`, `queueWithdrawal`, `completeQueuedWithdrawal` - AND the protocol integrates with EigenLayer, not implements core EigenLayer contracts)
> **Inject Into**: Breadth agents, depth-external, depth-state-trace, depth-edge-case
> **Language**: EVM only
> **Finding prefix**: `[EL-N]`

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (operator trust, delegation, registration)
- Section 2: depth-state-trace (withdrawal queue, state transitions, timing)
- Section 3: depth-token-flow + depth-edge-case (slashing, share accounting, loss propagation)
- Section 4: depth-external (AVS validation, middleware trust)
- Section 5: depth-state-trace + depth-edge-case (reward accounting, claim ordering)

## When This Skill Activates

Recon detects that the protocol integrates with EigenLayer's restaking infrastructure — either as an AVS (Actively Validated Service), an operator management layer, a restaking vault/wrapper, or a protocol that accepts EigenLayer shares/strategy tokens as collateral. This skill covers the security of the integration, not EigenLayer core contracts.

---

## 1. Operator and Delegation Trust Model

EigenLayer's delegation model creates a multi-layer trust chain: Staker → Operator → AVS. Protocols integrating at any layer must understand the trust boundaries.

### 1a. Operator Registration and Validation

If the protocol manages or selects operators:
- What validation is performed when an operator registers? (Minimum stake, reputation, KYC, whitelist)
- Can a malicious operator register, attract delegation, then act against the protocol's interest?
- Is operator registration permissionless or gated? If gated: by whom? Is the gate enforced on-chain?
- Does the protocol verify operator registration status with EigenLayer's `DelegationManager` before accepting them?

### 1b. Delegation Flow

- Who controls delegation decisions? (Individual stakers, protocol governance, automated strategy)
- Can delegation be changed after initial setup? What's the re-delegation flow?
- If the protocol delegates on behalf of users: can the protocol redirect delegation without user consent?
- Is there a minimum delegation period? Can flash-delegation (delegate → use → undelegate in one tx) be exploited?

### 1c. Operator Deregistration and Ejection

- What happens to staked assets when an operator deregisters from the AVS?
- Does the protocol handle operator ejection (forced removal by AVS governance)?
- After deregistration: are pending rewards still claimable? Are pending withdrawals still processable?
- Can an operator deregister to avoid an incoming slashing event?
- **Real finding pattern (Sherlock)**: Operator monitors for incoming slashing transaction in mempool. Operator front-runs by deregistering from the AVS. Slashing transaction fails because operator is no longer registered. Operator re-registers after slashing window passes, avoiding all penalties.
- **Real finding pattern**: Protocol doesn't handle operator deregistration event. Stakers' shares still show as "delegated to operator X" in the protocol's UI, but EigenLayer no longer counts them. Users think they're earning rewards but are not.

Tag: `[TRACE:operator_validation={whitelist/permissionless/stake_threshold} → delegation_control={user/protocol/governance} → deregistration_handled={YES/NO}]`

---

## 2. Withdrawal Queue and Timing

EigenLayer enforces a withdrawal delay (currently 7 days on mainnet). This delay creates a window where state changes can affect pending withdrawals.

### 2a. Queue → Complete Flow

The withdrawal flow is: `queueWithdrawal()` → wait delay → `completeQueuedWithdrawal()`.

- Does the protocol correctly sequence queue and complete operations?
- Between queue and complete: can the staker's position change (additional deposits, delegation changes, slashing)?
- Does the protocol store the withdrawal root/nonce and validate it on completion?
- Can a withdrawal be completed by someone other than the original queuer? (EigenLayer allows a `withdrawer` address)

### 2b. Delay Period Exploitation

- Can an attacker use the withdrawal delay window to:
  - Queue withdrawal → get slashed → complete withdrawal at pre-slash value?
  - Queue withdrawal → prices move → complete at stale valuation?
  - Queue multiple overlapping withdrawals that collectively exceed their entitlement?
- Does the protocol check that the withdrawal amount is still valid (shares haven't been slashed) at completion time?
- **Real finding pattern (C4)**: User queues withdrawal for 100 shares at T=0. At T=3 days, operator is slashed 20%. At T=7 days, user completes withdrawal. EigenLayer returns 80 shares worth of tokens, but the protocol's internal accounting still shows 100 shares queued. The 20-share difference becomes unaccounted deficit.

### 2c. Queued Withdrawal State Consistency

- While a withdrawal is queued: does the protocol correctly account for the "in-flight" shares?
  - Are queued shares excluded from active stake calculations?
  - Are queued shares still eligible for rewards during the delay?
  - Can queued shares be re-delegated, re-staked, or used as collateral?
- Does the protocol's internal accounting match EigenLayer's share tracking for the user?

### 2d. Withdrawal Failure Modes

- What if `completeQueuedWithdrawal()` reverts? (Insufficient shares, slashing reduced shares below withdrawal amount, strategy paused)
- Does the protocol have a recovery path for stuck withdrawals?
- Can an admin or governance force-complete or cancel a queued withdrawal?
- **Real finding pattern (Immunefi: Puffer Finance #28788, Critical)**: Protocol tracks `eigenLayerPendingWithdrawalSharesAmount` in state. If `slashQueuedWithdrawal()` is called during the delay, shares are destroyed. `completeQueuedWithdrawal()` permanently reverts. But `pendingWithdrawalSharesAmount` is NEVER decremented — `totalAssets()` permanently overstates actual holdings. New pufETH minted against phantom backing.
- **Real finding pattern (C4: EigenLayer #24, High)**: `completeQueuedWithdrawal()` iterates ALL strategies atomically. If ANY single strategy reverts (hacked, paused, self-destructed), the ENTIRE withdrawal reverts — including funds from healthy strategies. No partial-withdrawal fallback exists. A single malicious strategy permanently locks all pending multi-strategy withdrawals.
- Does the protocol use single-strategy withdrawals or multi-strategy bundles? Single-strategy is safer against atomic-failure DoS.

Tag: `[TRACE:queue_complete_validated={YES/NO} → delay_exploitation={possible/prevented} → queued_excluded_from_active={YES/NO} → failure_recovery={YES/NO}]`

---

## 3. Slashing and Loss Propagation

EigenLayer operators can be slashed by AVSes for misbehavior. Slashing reduces the operator's (and delegators') shares.

### 3a. Slashing Detection

- Does the protocol detect when slashing has occurred? (Monitor events, check share balances, poll ISlasher)
- If the protocol wraps EigenLayer shares (e.g., a liquid restaking token): does the wrapper's exchange rate update after slashing?
- Is there a delay between slashing execution and the protocol detecting it? What can happen in that window?

### 3b. Loss Socialization

- How does the protocol distribute slashing losses?
  - Pro-rata across all depositors (fair but complex)?
  - To specific depositors based on operator delegation (precise but requires tracking)?
  - Absorbed by a reserve/insurance fund?
  - Ignored (the protocol's share price silently drops)?
- If pro-rata: does the protocol correctly compute each depositor's share of the loss? Integer division rounding can create dust imbalances.
- If operator-specific: what happens to depositors who delegated to a slashed operator but have pending withdrawals queued before the slash?

### 3c. Slashing + Withdrawal Interaction

- If a user queues a withdrawal and then slashing occurs during the delay:
  - Does `completeQueuedWithdrawal()` return the pre-slash or post-slash amount?
  - EigenLayer itself reduces shares on slash — so completion returns post-slash value. Does the protocol's internal accounting reflect this?
  - Can a user front-run a slashing event by queueing a withdrawal?

### 3d. Maximum Slashing Exposure

- What percentage of an operator's stake can be slashed? (EigenLayer allows configurable slashing percentages per AVS)
- Does the protocol have a maximum slashing exposure parameter? Is it enforced?
- If multiple AVSes can slash the same operator: can cumulative slashing exceed 100%? (EigenLayer's unique slashing model allows this)
- Does the protocol account for "overcommitted" operators (staked with multiple AVSes, total slashing exposure > 100%)?
- **Real finding pattern**: Protocol's LRT (liquid restaking token) delegates to operators serving 5 AVSes, each with 30% max slash. Total exposure: 150%. A coordinated slashing event across 2 AVSes slashes 60% of the operator's stake. The LRT's exchange rate drops below 1:1 but the protocol assumes it can't go below (1 - max_single_avs_slash).

Tag: `[TRACE:slashing_detected={event/poll/none} → loss_distribution={pro_rata/operator_specific/reserve/ignored} → withdrawal_slash_interaction={pre/post_slash} → max_exposure_enforced={YES/NO}]`

---

## 4. AVS Middleware and Validation

If the protocol IS an AVS or integrates with AVS middleware:

### 4a. Task and Attestation Validation

- How does the AVS validate operator task responses? (On-chain computation, optimistic with challenge, committee consensus)
- Can a malicious operator submit invalid task responses that are accepted?
- Is there a challenge/dispute period? Can challenges be griefed (costly to submit, easy to ignore)?

### 4b. Quorum and Threshold

- What quorum of operators must agree for a task response to be accepted?
- Can a coalition of operators (below the slash threshold) manipulate task outcomes?
- If the quorum is based on stake weight: can an attacker accumulate enough delegation to control the quorum?
- Are there minimum operator count requirements? Can the AVS function with a single operator?

### 4c. Middleware Contract Trust

- Does the protocol use EigenLayer's middleware contracts (RegistryCoordinator, StakeRegistry, BLSApkRegistry)?
- Are these middleware contracts upgradeable? By whom?
- If upgradeable: can a governance attack on the middleware compromise the AVS security guarantees?
- Does the protocol verify middleware contract addresses are canonical EigenLayer deployments?

### 4d. Service Manager Permissions

- What permissions does the ServiceManager have over the protocol's state?
- Can the ServiceManager (or its owner) freeze operators, modify quorum thresholds, or change slashing parameters unilaterally?
- Is the ServiceManager a proxy? Who controls the proxy admin?

Tag: `[TRACE:validation_method={on_chain/optimistic/committee} → quorum_threshold={value} → middleware_upgradeable={YES/NO} → service_manager_permissions={list}]`

---

## 5. Reward Accounting

EigenLayer's RewardsCoordinator distributes rewards to operators and delegators.

### 5a. Reward Claim Flow

- Does the protocol claim rewards on behalf of users or do users claim directly?
- If the protocol claims: how are rewards attributed to individual users? Is the split computation correct?
- Can rewards be claimed multiple times? (RewardsCoordinator uses Merkle roots — each root can only be claimed once, but the protocol must track this)
- Is there a delay between reward accrual and claimability? What happens to rewards during this delay?

### 5b. Reward Token Handling

- What tokens are rewards paid in? (Can vary by AVS — ETH, EIGEN, custom tokens)
- Does the protocol handle all possible reward tokens, or does it only expect specific tokens?
- If unexpected reward tokens arrive: are they stuck, redistributable, or exploitable?

### 5c. Reward + Slashing Ordering

- If slashing and rewards occur in the same period: which is processed first?
- Can an operator accumulate rewards, get slashed, and then the protocol distributes the pre-slash rewards to users who should have received less?
- Does the protocol snapshot reward entitlement before or after slashing?

Tag: `[TRACE:claim_flow={protocol/user_direct} → multi_claim_prevented={YES/NO} → reward_tokens={list} → slash_reward_ordering={slash_first/reward_first/undefined}]`

---

## Common False Positives

- **Read-only EigenLayer queries**: If the protocol only reads EigenLayer state (e.g., checks if an operator is registered) without staking, delegating, or claiming, most of this skill's concerns don't apply
- **Single operator, protocol-controlled**: If the protocol uses a single operator controlled by the same team, operator trust concerns are reduced (but centralization risk increases — see CENTRALIZATION_RISK skill)
- **No slashing enabled**: If the protocol's AVS has not activated slashing (slashing is opt-in per AVS and was launched later), slashing sections don't apply yet — but should be flagged as a future risk
- **Testnet only**: If EigenLayer integration is testnet-only (Holesky), mainnet-specific timing and economic concerns don't apply

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Operator Registration | IF protocol manages operators | | Validation, permissionless |
| 1b. Delegation Flow | YES | | Control, consent, flash-delegation |
| 1c. Operator Deregistration | IF protocol manages operators | | Asset handling, slashing dodge |
| 2a. Queue → Complete | IF protocol handles withdrawals | | Sequencing, validation |
| 2b. Delay Exploitation | IF protocol handles withdrawals | | Front-run slashing, stale valuation |
| 2c. Queued State Consistency | IF protocol handles withdrawals | | In-flight accounting |
| 2d. Withdrawal Failure | IF protocol handles withdrawals | | Recovery, stuck funds |
| 3a. Slashing Detection | YES | | Events, polling, delay window |
| 3b. Loss Socialization | YES | | Distribution method, fairness |
| 3c. Slashing + Withdrawal | IF both applicable | | Pre/post-slash amounts |
| 3d. Maximum Exposure | YES | | Multi-AVS overcommitment |
| 4a. Task Validation | IF protocol is AVS | | Response validation |
| 4b. Quorum | IF protocol is AVS | | Threshold, stake manipulation |
| 4c. Middleware Trust | IF uses EigenLayer middleware | | Upgradeability, canonical |
| 4d. Service Manager | IF protocol is AVS | | Permissions, proxy |
| 5a. Reward Claim | IF protocol handles rewards | | Attribution, double-claim |
| 5b. Reward Tokens | IF protocol handles rewards | | Multi-token, unexpected |
| 5c. Reward + Slashing Order | IF both applicable | | Snapshot timing |
