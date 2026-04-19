---
name: "spl-stake-pool-integration"
description: "Protocol Type Trigger spl_stake_pool_integration (detected when recon finds spl_stake_pool|StakePool|validator_list|update_stake_pool_balance|transient_stake|stake_pool_withdraw_sol|stake_pool_deposit_sol - protocol USES SPL stake pool program)"
---

# Injectable Skill: SPL Stake Pool Integration Security

> Protocol Type Trigger: `spl_stake_pool_integration` (detected when recon finds: `spl_stake_pool`, `StakePool`, `validator_list`, `update_stake_pool_balance`, `transient_stake`, `stake_pool_withdraw_sol`, `stake_pool_deposit_sol`)
> Inject Into: depth-external, depth-state-trace
> Language: Solana only
> Finding prefix: `[SPL-SP-N]`
> Relationship to sol-lst-integration: LST wrappers that run on SPL stake-pool should activate both skills.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-state-trace (update cadence, stale-rate arbitrage)
- Section 2: depth-state-trace (validator list mutation)
- Section 3: depth-state-trace (transient stake edge cases)
- Section 4: depth-external (fee recipient rotation)
- Section 5: depth-external (sole-depositor concentration)
- Section 6: depth-external (preferred validator routing)

## When This Skill Activates

Recon detects direct interaction with the SPL stake pool program, including deposit/withdraw SOL or stake, rebalancing via transient stake accounts, or validator list management.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: stake_pool, StakePool, validator_list, update_stake_pool_balance, transient_stake
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[SPL-SP-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. update_stake_pool_balance Cadence / Stale-Rate Arbitrage

### 1a. Update Before Deposit or Withdraw
- Deposits and withdrawals use `total_lamports / pool_mint.supply` as exchange rate. Stale `total_lamports` lets first-mover arb.
- Real finding pattern (Solodit, pattern observed in multiple audits): Wrapper deposits without calling `update_validator_list_balance` + `update_stake_pool_balance` first; attacker sandwiches and captures epoch gains.

### 1b. Epoch Boundary Race
- At epoch boundary, new stake rewards are materialized. Does the wrapper update before users transact?
- Real finding pattern (pattern observed in multiple audits): First deposit of the epoch benefits from rate advance at the expense of existing holders.

### 1c. Rate Cached in Wrapper
- Does the wrapper cache exchange rate across instructions in the same tx? Cached values can diverge from pool state after an update CPI in between.
- Real finding pattern (pattern observed in multiple audits): Wrapper reads rate at top of instruction and reuses after CPI mutation.

Tag: [TRACE:update_before_txn=YES/NO → epoch_boundary_handled=YES/NO → rate_cache_avoided=YES/NO]

---

## 2. Validator List Mutation During Iteration

### 2a. In-Place Mutation
- Instructions that iterate the validator list while modifying it (e.g. remove-validator during update) can corrupt state. Does the wrapper call safe sequences?
- Real finding pattern (pattern observed in multiple audits): Wrapper's keeper removes a validator mid-update; iteration index invalidated, subsequent computations read zeroed entry.

### 2b. Validator List Size Cap
- The list has a max size; wrapper should refuse to add beyond cap.
- Real finding pattern (pattern observed in multiple audits): Wrapper's add_validator ignores cap; CPI reverts with opaque error.

### 2c. Active Stake in Removed Validator
- Removing a validator with active stake is forbidden. Wrapper must deactivate first.
- Real finding pattern (pattern observed in multiple audits): Wrapper attempts remove with active stake, bricks rebalancer path.

Tag: [TRACE:safe_iteration_order=YES/NO → list_cap_respected=YES/NO → active_stake_drained_before_remove=YES/NO]

---

## 3. Transient Stake Edge Cases

### 3a. Transient Activating vs Deactivating
- Transient accounts have distinct states; wrapping both in one call causes failures.
- Real finding pattern (pattern observed in multiple audits): Wrapper decrements activating transient while it should be deactivating, so CPI fails mid-rebalance.

### 3b. Cross-Epoch Transient
- Transient accounts must settle within one epoch; if not, they block subsequent rebalance.
- Real finding pattern (pattern observed in multiple audits): Wrapper ignores leftover transient; next rebalance reverts.

### 3c. Minimum Delegation
- Transient stake must meet minimum delegation; under-min causes CPI revert.
- Real finding pattern (pattern observed in multiple audits): Wrapper splits stake into many small transients; network minimum rejects them.

Tag: [TRACE:transient_state_selected=correct/wrong → transient_cleared_per_epoch=YES/NO → min_delegation_enforced=YES/NO]

---

## 4. Fee Recipient Rotation

### 4a. Manager vs Depositor Fee
- Manager fee and depositor fee have distinct recipients. Does the wrapper bind each?
- Real finding pattern (pattern observed in multiple audits): Wrapper uses same PDA for both; one fee stream overwrites the other.

### 4b. SOL vs Stake Deposit Fee Split
- Separate fees for SOL deposit, stake deposit, and SOL withdraw. Does the wrapper route each?
- Real finding pattern (pattern observed in multiple audits): Wrapper treats all fees as one account; accounting mismatch.

### 4c. Fee Recipient Verification
- Recipient token account must be owned by the configured authority and mint == pool mint.
- Real finding pattern (pattern observed in multiple audits): Recipient mint mismatch; deposit reverts.

Tag: [TRACE:manager_depositor_bound=YES/NO → per_op_fee_routed=YES/NO → recipient_mint_verified=YES/NO]

---

## 5. Sole-Depositor Concentration

### 5a. First Depositor Inflation
- First deposit to a stake pool picks the share ratio. Without a seed deposit, the first user can round everyone else to 0.
- Real finding pattern (pattern observed in multiple audits): Wrapper permits first deposit of 1 lamport followed by large airdrop; second user receives 0 shares.

### 5b. Concentration-Triggered Withdraw Restriction
- Some stake pools restrict withdraw above a threshold. Wrapper should detect.
- Real finding pattern (pattern observed in multiple audits): Wrapper cannot withdraw beyond threshold; user funds stuck.

### 5c. Single-Validator Pool
- A pool with a single validator concentrates slashing risk. Does the wrapper warn or refuse?
- Real finding pattern (pattern observed in multiple audits): Wrapper treats single-validator pool as safe; validator slashed, depositors lose disproportionately.

Tag: [TRACE:seed_deposit_required=YES/NO → withdraw_threshold_monitored=YES/NO → validator_count_minimum=YES/NO]

---

## 6. Preferred Validator Routing

### 6a. Preferred Deposit / Withdraw
- Stake pools can set preferred validators for deposit and withdraw. Does the wrapper route correctly?
- Real finding pattern (pattern observed in multiple audits): Wrapper ignores preferred; deposits go to any validator, creating rebalance churn.

### 6b. Preferred Validator Changes
- Preferred validator can change; wrapper must re-read.
- Real finding pattern (pattern observed in multiple audits): Wrapper caches preferred; change breaks routing invariant.

### 6c. Removed Preferred Validator
- Preferred validator removal can make the preferred path invalid.
- Real finding pattern (pattern observed in multiple audits): Removed validator still listed as preferred; deposit reverts.

Tag: [TRACE:preferred_routing_followed=YES/NO → preferred_change_detected=YES/NO → removed_preferred_handled=YES/NO]

---

## Common False Positives

- Wrapper uses a single fixed stake pool and only user-level deposit/withdraw; sections 2 and 6 reduced.
- Wrapper only reads exchange rate (view only) with no deposits; section 5a not applicable.
- Wrapper uses LST token (pool mint) purely as collateral elsewhere; section 4 reduced if fees not customized.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Search performed: 2026-04-19. Target: 5-10 verifiable findings.
Total found: 6

---

## Finding 1

- Pattern: Reserve stake account lamports not minted as pool tokens during initialization; first depositor captures excess reserve funds at inflated share ratio
- Where it hit: Official SPL stake-pool program (`solana-program-library`), discovered by Soteria (now sec3) via automated semantic inconsistency analysis
- Severity: CRITICAL
- Source: https://www.sec3.dev/blog/solana-stake-pool-a-semantic-inconsistency-vulnerability-discovered-by-x-ray and https://medium.com/coinmonks/solana-stake-pool-a-semantic-inconsistency-vulnerability-discovered-by-soteria-b92abcbaf909
- Summary: The `initialize` instruction placed lamports into the reserve stake account but did not issue pool tokens for them. The first depositor received pool tokens priced against the empty-token supply, claiming the full reserve balance. PoC: deposit 1 SOL, claim 990,000,000 pool tokens, withdraw 97.99 SOL profit. The bug was silently live in all forks of the SPL stake-pool at time of disclosure.
- Map to: `spl_stake_pool`, `StakePool`, `stake_pool_deposit_sol`, `stake_pool_withdraw`

---

## Finding 2

- Pattern: Stake accounts passed into `UpdateValidatorListBalance` are not verified against pool-owned PDAs; a caller can substitute forged stake accounts with fewer lamports to underreport total stake
- Where it hit: SPL stake-pool program — GitHub Issue #1567 (`solana-labs/solana-program-library`)
- Severity: HIGH
- Source: https://github.com/solana-labs/solana-program-library/issues/1567
- Summary: The `UpdateValidatorListBalance` instruction accepted arbitrary stake account addresses without verifying they were PDA-derived accounts owned by the pool. An attacker could supply forged accounts reporting lower balances than the pool actually held, causing `stake_total` to be computed incorrectly. The fix required passing the stake pool account into the instruction so `get_validator_checked()` could validate ownership before summing balances.
- Map to: `spl_stake_pool`, `StakePool`, `validator_list`, `update_stake_pool_balance`

---

## Finding 3

- Pattern: Preferred deposit/withdraw validator can be set to a validator already queued for removal (`ReadyForRemoval` state), making all subsequent deposits or withdrawals to that path revert
- Where it hit: SPL stake-pool program — GitHub Issue #2262 (`solana-labs/solana-program-library`)
- Severity: MEDIUM
- Source: https://github.com/solana-labs/solana-program-library/issues/2262
- Summary: The `SetPreferredValidator` instruction did not check whether the named validator entry was in `ReadyForRemoval` state. An operator (or a wrapper with auto-routing logic) could set a preferred validator, then trigger its removal; any deposit or withdrawal routed to that preferred path would revert. The fix was to reject `SetPreferredValidator` when the target entry is `ReadyForRemoval`.
- Map to: `spl_stake_pool`, `StakePool`, `validator_list`

---

## Finding 4

- Pattern: Depositing a stake account with extra non-staked lamports (beyond rent-exempt minimum plus delegation) allows the depositor to receive pool tokens for those excess lamports and immediately redeem them as fully-activated stake
- Where it hit: SPL stake-pool program — GitHub Issue #2260 (`solana-labs/solana-program-library`)
- Severity: HIGH
- Source: https://github.com/solana-labs/solana-program-library/issues/2260
- Summary: `DepositStake` calculated pool tokens using the total lamports of the provided stake account, including any excess non-staked lamports. The attacker deposited a stake account padded with extra lamports, received tokens for the full amount, then redeemed tokens for a normally-activated stake account — effectively converting inactive lamports into active stake instantly, bypassing the one-epoch activation delay and diluting existing holders.
- Map to: `spl_stake_pool`, `StakePool`, `stake_pool_deposit_sol`, `transient_stake`

---

## Finding 5

- Pattern: Validator reuse attack via PDA seed collision — a removed validator's stake account PDA can be re-added with a different vote account, allowing a keeper to drain one epoch of rewards by manipulating the delegation target
- Where it hit: Lido on Solana v2 — Neodyme security audit, October 2022
- Severity: HIGH
- Source: https://neodyme.io/reports/Lido-2.pdf
- Summary: After a validator was removed, its on-chain stake account PDA remained derivable from the same seeds. An attacker who controlled the manager key could add a new validator whose PDA collided with the removed one, then redirect stake delegations to a high-commission validator and capture that epoch's rewards. The fix introduced a `validator_generation` counter into all PDA seeds so removed accounts are forever distinct from newly-added ones.
- Map to: `spl_stake_pool`, `StakePool`, `validator_list`, `update_stake_pool_balance`

---

## Finding 6

- Pattern: Precision truncation in LST wrapper — `recordStake()` operates on the pre-truncation user input rather than the actual amount sent to the L1 staking layer, causing pool token minting to exceed real deposited value
- Where it hit: Kinetiq LST (Hyperliquid liquid staking) — Spearbit security review
- Severity: HIGH
- Source: https://solodit.cyfrin.io/issues/precision-truncation-on-stake-may-lead-to-improper-accounting-and-protocol-insolvency-spearbit-none-kinetiq-lst-pdf
- Summary: HyperCore requires deposit amounts aligned to 8 decimals (multiples of 1e10 wei). The wrapper's `recordStake()` used the original user-supplied amount to mint pool tokens, not the truncated amount actually forwarded to L1. The residual difference was silently lost, so more LST shares were minted than backed by real stake — a latent insolvency that compounds over many deposits. The pattern is directly analogous to any SPL stake pool wrapper that reads `total_lamports` before calling `update_stake_pool_balance`, minting shares against a stale numerator.
- Map to: `spl_stake_pool`, `StakePool`, `update_stake_pool_balance`, `stake_pool_deposit_sol`

---

## Coverage notes

- Findings 1-4 are directly in the SPL stake-pool program itself; they apply to any wrapper that forks or integrates it.
- Finding 5 is a Lido-specific integration layer vulnerability that exercises the validator-list mutation path.
- Finding 6 is a wrapper-level precision bug whose root cause (deposit without update / stale rate) maps to Section 1 of the skill.
- Sections 3 (transient stake edge cases) and 4 (fee recipient rotation) did not yield additional verifiable public findings beyond the existing `candidates.jsonl` entry; the patterns remain documented in the skill for code-level analysis.


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Update Before Txn | YES | | update CPI |
| 1b. Epoch Boundary | YES | | boundary race |
| 1c. Rate Cache Avoided | YES | | per-tx read |
| 2a. Safe Iteration Order | IF list mutation used | | order safe |
| 2b. List Cap | IF add_validator used | | cap respected |
| 2c. Active Stake Drain | IF remove used | | drain first |
| 3a. Transient State | IF transient used | | correct state |
| 3b. Transient Cleared | IF transient used | | per epoch |
| 3c. Min Delegation | IF transient used | | min respected |
| 4a. Manager vs Depositor | YES | | distinct accounts |
| 4b. Per-Op Fee Routed | YES | | per-op recipient |
| 4c. Recipient Mint | YES | | mint match |
| 5a. Seed Deposit | IF first deposit path | | anti-inflation |
| 5b. Withdraw Threshold | IF large users | | monitor |
| 5c. Validator Count | IF config controls | | minimum count |
| 6a. Preferred Routing | IF preferred set | | follow routing |
| 6b. Preferred Change | YES | | re-read each tx |
| 6c. Removed Preferred | YES | | handle stale |
