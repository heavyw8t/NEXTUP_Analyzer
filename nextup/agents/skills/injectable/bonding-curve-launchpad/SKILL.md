---
name: "bonding-curve-launchpad"
description: "Protocol Type Trigger bonding_curve_launchpad (detected when recon finds bonding_curve|virtual_sol_reserves|virtual_token_reserves|graduation|pump|moonshot|liquidity_migration - protocol IMPLEMENTS a bonding-curve launchpad)"
---

# Injectable Skill: Bonding Curve Launchpad Security

> Protocol Type Trigger: `bonding_curve_launchpad` (detected when recon finds: `bonding_curve`, `virtual_sol_reserves`, `virtual_token_reserves`, `graduation`, `pump`, `moonshot`, `liquidity_migration`)
> Inject Into: depth-token-flow, depth-edge-case, depth-state-trace
> Language: Solana only
> Finding prefix: `[BC-N]`
> Relationship to clmm-pool-integration: graduation routes funds into an external CLMM or AMM. Activate both for migration analysis.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-edge-case (curve math rounding)
- Section 2: depth-state-trace (virtual vs real reserves)
- Section 3: depth-edge-case (graduation threshold race)
- Section 4: depth-token-flow (creator-fee siphon)
- Section 5: depth-edge-case (partial buy accounting)
- Section 6: depth-state-trace (migration reentrancy)

## When This Skill Activates

Recon detects a launchpad program with bonding-curve pricing (pump.fun-style or Moonshot-style), including virtual reserves, graduation threshold, and liquidity migration into an external pool.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: bonding_curve, virtual_sol_reserves, virtual_token_reserves, graduation, pump
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[BC-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Curve Math Rounding

### 1a. Buy/Sell Rounding Direction
- Buy amount-out must round down, sell amount-in must round up. Does the program pick correctly?
- Real finding pattern (Solodit, pattern observed in multiple audits): Both paths use floor division, so sell returns slightly more SOL than the curve owes, draining pool over time.

### 1b. Constant-Product Formula Precision
- `x * y = k` math with u64 operands needs u128 intermediates. Missing cast causes overflow and truncation.
- Real finding pattern (pattern observed in multiple audits): Multiply as `u64 * u64` overflows; release build wraps silently, pricing is zero after overflow.

### 1c. Fee Deducted Before or After Curve
- Fee-before-curve and fee-after-curve give different prices. Is the choice documented and consistent across buy/sell?
- Real finding pattern (pattern observed in multiple audits): Buy deducts fee after curve, sell before; asymmetry drains pool per round-trip.

Tag: [TRACE:rounding_direction_per_side=correct/incorrect → u128_intermediate_used=YES/NO → fee_timing_symmetric=YES/NO]

---

## 2. Virtual vs Real Reserve Drift

### 2a. Virtual Reserves Update
- When a buy consumes from the pool, do both virtual and real reserves update consistently?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Program updates virtual reserves but forgets to subtract actual SOL moved, so virtual and real diverge; subsequent pricing is wrong.

### 2b. Initialization Invariant
- At init, `virtual_sol == INIT_VIRTUAL_SOL`, `virtual_token == INIT_VIRTUAL_TOKEN`. Is `virtual_token` equal to total supply the curve will sell?
- Real finding pattern (pattern observed in multiple audits): Misconfigured init permits additional mint after graduation, inflating supply beyond curve calc.

### 2c. Real Reserve Reconciliation
- Does the program read real token-account balances when needed, or trust the stored counter exclusively?
- Real finding pattern (pattern observed in multiple audits): Stored counter is trusted; attacker forces a transfer into the pool via direct SPL transfer; counter and reality diverge; accounting skewed.

Tag: [TRACE:virtual_real_updated_together=YES/NO → init_invariant_correct=YES/NO → reserves_reconciled=YES/NO]

---

## 3. Graduation Threshold Race

### 3a. Graduation Trigger Atomicity
- Is graduation triggered atomically in the last buy that crosses the threshold, or deferred?
- Real finding pattern (Solodit, pattern observed in multiple audits): Deferred graduation permits buys after threshold at curve price, then graduation locks the remainder; arb difference captured by last buyer.

### 3b. Threshold Front-Run
- Can a searcher observe the pending graduation buy and front-run?
- Real finding pattern (pattern observed in multiple audits): Searcher front-runs the graduation buy at curve price, back-runs after pool opens at AMM price.

### 3c. Partial Graduation Replay
- If graduation fails (e.g. CPI to DEX errors), does the program leave state consistent for retry?
- Real finding pattern (pattern observed in multiple audits): Partial graduation locks reserves but not flag; buys resume on curve until migrated manually.

Tag: [TRACE:graduation_atomic=YES/NO → frontrun_mitigation=YES/NO → partial_graduation_recovery=YES/NO]

---

## 4. Creator-Fee Siphon

### 4a. Creator Fee Account
- Creator fee account must be bound to the market, not user-supplied.
- Real finding pattern (Solodit, pattern observed in multiple audits): Program reads `creator_fee_account` from instruction accounts without PDA derivation; attacker supplies their own.

### 4b. Creator Permissions Post-Graduation
- After graduation, does the creator retain ability to adjust fees or mint? Mint should be frozen.
- Real finding pattern (pattern observed in multiple audits): Creator retains mint authority; post-graduation dumps inflate supply.

### 4c. Zero-Supply Token Edge Case
- Tokens with zero initial supply or all-creator allocations open rug vectors.
- Real finding pattern (pattern observed in multiple audits): Launch allows 100% creator allocation; pool is empty at launch; "buy" reverts; funds stuck.

Tag: [TRACE:creator_fee_pda_bound=YES/NO → mint_authority_burned_at_graduation=YES/NO → zero_supply_prevented=YES/NO]

---

## 5. Partial Buy Accounting

### 5a. Max-SOL Bound
- If the curve runs out of tokens during a buy, does the program refund the unspent SOL?
- Real finding pattern (Cantina, pattern observed in multiple audits): Remaining SOL silently kept; user pays more than curve requires near graduation.

### 5b. Min-Out Enforcement
- User-specified `min_tokens_out` must be enforced; otherwise sandwich attackers drain output.
- Real finding pattern (pattern observed in multiple audits): Enforcement only on happy path; partial-fill branch skips the check.

### 5c. Graduation Tail Allocation
- The last buy that crosses graduation should fill up to graduation cap. Does the program avoid overfilling into next-state reserves?
- Real finding pattern (pattern observed in multiple audits): Overfill passes through and is counted as real reserve, inflating post-graduation liquidity incorrectly.

Tag: [TRACE:partial_refund=YES/NO → min_out_enforced_on_partial=YES/NO → graduation_cap_honored=YES/NO]

---

## 6. Migration Reentrancy

### 6a. CPI During Migration
- Migration CPI into a DEX can re-enter the launchpad program via shared accounts. Does the program guard with a state flag?
- Real finding pattern (Solodit, pattern observed in multiple audits): Migration flow opens pool, re-enters launchpad via CPI, processes a buy mid-migration leaving pool double-counted.

### 6b. Authority Passthrough
- The migration CPI signs with the bonding-curve PDA. Is the PDA seed strict enough that only the migration instruction can sign?
- Real finding pattern (pattern observed in multiple audits): Seed allows any "migrator" role; attacker drains by triggering fake migration.

### 6c. LP Token Custody
- After migration, LP tokens should be burned or time-locked. Does the program do this atomically?
- Real finding pattern (pattern observed in multiple audits): LP tokens left in creator wallet; creator withdraws liquidity immediately after launch.

Tag: [TRACE:migration_state_flag=YES/NO → pda_seed_strict=YES/NO → lp_burned_or_locked=YES/NO]

---

## Common False Positives

- Program only implements the buy/sell math and defers migration to a separate reviewed contract. Section 6 partially delegated.
- Initial supply fully allocated to the curve, no creator tail. Section 4c does not apply.
- Linear-sum curve instead of constant product changes section 1 constants but same rounding concerns apply.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Migration config variable not persisted through admin update
  Where it hit: Pump Science — `Global::update_settings` omits write to `migration_token_allocation`
  Severity: HIGH
  Source: Solodit (row_id 2251)
  Summary: The `migration_token_allocation` field in the `Global` struct is read during migration but never written by the settings-update instruction. An admin calling `update_settings` leaves this value at its initialized default regardless of the intended change. Migration executes with stale allocation, misrouting tokens.
  Map to: liquidity_migration, bonding_curve

- Pattern: PDA-derived account pre-creation DoS on pool lock
  Where it hit: Pump Science — `lock_pool` / `create_lock_escrow` with predictable PDA seeds
  Severity: HIGH
  Source: Solodit (row_id 2252)
  Summary: The `lock_escrow` account is derived from `pool` and `owner` seeds, which any observer can compute. An attacker creates the account before the legitimate `create_lock_escrow` transaction, causing it to fail with an account-already-exists error. This permanently blocks `lock_pool` for that pool unless a recovery path exists.
  Map to: liquidity_migration

- Pattern: Real reserve drift from direct external SOL transfer
  Where it hit: Pump Science bonding curve — `bonding_curve_sol_escrow` vs `real_sol_reserves`
  Severity: HIGH
  Source: Solodit (row_id 2975)
  Summary: The protocol enforces `sol_escrow_lamports == real_sol_reserves` only inside swap instructions. A direct SOL transfer to the escrow account (outside any instruction) widens the gap without triggering a sync. Once the invariant is broken the protocol halts all swaps until a manual sync function is called.
  Map to: virtual_sol_reserves, bonding_curve

- Pattern: ATA existence check via lamport balance enables DoS on pool lock
  Where it hit: Pump Science — `lock_pool` ATA creation for LP tokens
  Severity: HIGH
  Source: Solodit (row_id 2976)
  Summary: The LP-token ATA creation step inside `lock_pool` checks whether the `escrow_vault` has lamports to decide if the ATA must be created. An attacker sends a dust SOL amount to the vault address before the transaction, making the check evaluate as "already funded" and skipping ATA creation. The subsequent token transfer then fails, denying pool lock to all users.
  Map to: liquidity_migration

- Pattern: Phase-boundary discontinuity in fee schedule causes sudden drop
  Where it hit: Pump Science fee calculation — phase transition boundary
  Severity: MEDIUM
  Source: Solodit (row_id 2248)
  Summary: The fee formula produces 8.76% on the last slot of one phase and 1% on the first slot of the next, with no interpolation at the boundary. A buyer who times the phase transition captures the fee delta as profit at the protocol's expense. The fix requires recalibrating formula coefficients so the two phase curves meet at the boundary.
  Map to: bonding_curve

- Pattern: Invariant check incorrectly includes rent in lamport balance comparison
  Where it hit: Pump Science — bonding curve invariant check comparing `sol_escrow_lamports` to `real_sol_reserves`
  Severity: MEDIUM
  Source: Solodit (row_id 2249)
  Summary: `sol_escrow_lamports` is the total lamport balance including rent-exemption deposit, while `real_sol_reserves` tracks only tradeable SOL. Comparing them directly makes the invariant always appear violated by the rent amount, causing false-positive halts or allowing the check to be bypassed depending on the error-handling path.
  Map to: virtual_sol_reserves, bonding_curve

- Pattern: Token account init fails if account pre-exists, enabling DoS on curve creation
  Where it hit: Pump Science — `CreateBondingCurve` instruction, `bonding_curve_token_account`
  Severity: MEDIUM
  Source: Solodit (row_id 2971)
  Summary: The `bonding_curve_token_account` constraint uses `init` with `associated_token::mint` and `associated_token::authority`, so the account address is fully predictable. Any attacker can create the token account first, causing every subsequent `CreateBondingCurve` call for that mint to fail. Changing the constraint to `init_if_needed` removes the attack surface.
  Map to: bonding_curve


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Rounding Per Side | YES | | buy down, sell up |
| 1b. u128 Intermediate | YES | | overflow guard |
| 1c. Fee Timing Symmetry | YES | | buy/sell symmetric |
| 2a. Virtual/Real Consistency | YES | | updated together |
| 2b. Init Invariant | YES | | supply binding |
| 2c. Reserves Reconciliation | YES | | direct transfer defense |
| 3a. Graduation Atomicity | YES | | last-buy triggers |
| 3b. Front-Run Mitigation | IF graduation search-surface | | commit-reveal or cap |
| 3c. Partial Graduation Recovery | YES | | retryable state |
| 4a. Creator Fee PDA | YES | | bound account |
| 4b. Post-Graduation Authority | YES | | mint frozen |
| 4c. Zero-Supply Prevented | YES | | init rejects degenerate |
| 5a. Partial Refund | YES | | excess SOL returned |
| 5b. Min-Out on Partial | YES | | enforced all branches |
| 5c. Graduation Cap | YES | | overfill blocked |
| 6a. Migration State Flag | YES | | reentrancy guard |
| 6b. PDA Seed Strict | YES | | unique migrator path |
| 6c. LP Burned/Locked | YES | | custody removed |
