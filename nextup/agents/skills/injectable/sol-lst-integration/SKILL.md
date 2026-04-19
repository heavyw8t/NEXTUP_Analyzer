---
name: "sol-lst-integration"
description: "Protocol Type Trigger sol_lst_integration (detected when recon finds mSOL|jitoSOL|bSOL|JSOL|msol_mint|jitosol_mint|marinade_finance|stake_pool|sanctum|unstake_it|sol_value_calculator - protocol USES SOL liquid-staking tokens)"
---

# Injectable Skill: SOL Liquid Staking Token Integration Security

> Protocol Type Trigger: `sol_lst_integration` (detected when recon finds: `mSOL`, `jitoSOL`, `bSOL`, `JSOL`, `msol_mint`, `jitosol_mint`, `marinade_finance`, `stake_pool`, `sanctum`, `unstake_it`, `sol_value_calculator`)
> Inject Into: depth-token-flow, depth-external
> Language: Solana only
> Finding prefix: `[LST-N]`
> Relationship to spl-stake-pool-integration: many LSTs are SPL stake pools under the hood. Activate both when the LST uses the SPL program.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (exchange-rate refresh cadence)
- Section 2: depth-token-flow (delayed vs liquid unstake fee paths)
- Section 3: depth-external (slashing passthrough)
- Section 4: depth-token-flow (decimals assumption)
- Section 5: depth-external (exchange-rate staleness compounding)
- Section 6: depth-token-flow (mint supply invariant assumption)

## When This Skill Activates

Recon detects that the protocol holds or prices mSOL, jitoSOL, bSOL, JSOL, or any other SOL LST, or uses Sanctum's SOL value calculator.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: mSOL, jitoSOL, bSOL, marinade, stake_pool, sanctum, sol_value_calculator
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[LST-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Exchange-Rate Refresh Cadence / Epoch Boundary

### 1a. Epoch Boundary Crossing
- LST exchange rates typically update on epoch boundaries (~2 days). Does the protocol pin reads to post-update state?
- Real finding pattern (Solodit, pattern observed in multiple audits): Protocol reads rate in the slot after a new epoch but before the stake pool's `update` instruction runs; rate is one epoch stale.

### 1b. Required Update Instruction
- Some LSTs require calling `update_stake_pool_balance` / `update_validator_list` before reads. Does the protocol invoke?
- Real finding pattern (pattern observed in multiple audits): Protocol treats stake pool fields as trustworthy without the update CPI; mid-epoch reads are stale.

### 1c. Cross-Epoch Averaging
- Does the protocol smooth rate updates or treat each boundary as a step? A step causes discrete mispricing windows.
- Real finding pattern (pattern observed in multiple audits): Discrete update lets traders arbitrage the discrete jump against cached wrapper rate.

Tag: [TRACE:post_update_read=YES/NO → update_cpi_invoked=YES/NO → rate_smoothing=YES/NO]

---

## 2. Delayed vs Liquid Unstake Fee Paths

### 2a. Fee Schedule Per Path
- Liquid unstake incurs an immediate fee; delayed unstake requires waiting an epoch. Does the protocol charge correct fee for the chosen path?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Wrapper always routes through liquid unstake but bills delayed-unstake fee.

### 2b. Liquidity Pool Empty
- Liquid unstake fee depends on remaining pool liquidity; when pool is empty, liquid path reverts. Does the wrapper fallback to delayed path?
- Real finding pattern (pattern observed in multiple audits): Wrapper reverts user, no delayed fallback.

### 2c. Early Exit Penalty
- Some LST programs penalize unstake within an epoch of deposit. Does the wrapper refuse or account?
- Real finding pattern (pattern observed in multiple audits): Wrapper allows same-epoch roundtrip that loses deposit principal to penalty.

Tag: [TRACE:fee_path_matches_route=YES/NO → delayed_fallback=YES/NO → early_exit_penalty_tracked=YES/NO]

---

## 3. Slashing Passthrough / Exchange-Rate Decrease

### 3a. Non-Monotonic Rate Assumption
- Slashing events reduce LST exchange rate. Does the protocol assume monotonic increase?
- Real finding pattern (Cantina, pattern observed in multiple audits): Accounting stores "last known rate" and rejects updates that decrease it, freezing user operations after slashing.

### 3b. Loss Allocation
- Whose capital absorbs the slash: depositors pro rata, insurance reserve, or protocol treasury? Consistency matters.
- Real finding pattern (pattern observed in multiple audits): Wrapper claims insurance reserve but reserve is empty; losses silently socialized.

### 3c. Commission Change
- Stake pool commission changes affect future exchange rates. Does the protocol track?
- Real finding pattern (pattern observed in multiple audits): Commission raised to 100%; wrapper continues pricing at pre-change rate.

Tag: [TRACE:non_monotonic_allowed=YES/NO → loss_allocation_defined=YES/NO → commission_tracked=YES/NO]

---

## 4. Decimals Assumption

### 4a. 9-Decimal Mint
- SOL LSTs are 9-decimal. Does the wrapper assume 6 or 9?
- Real finding pattern (pattern observed in multiple audits): Wrapper converts to 6 decimals for USD display but persists 6-decimal amount as the operational value, losing 1000x.

### 4b. Mixed-Decimals Math
- Exchange rate math often mixes lamports (9-dec) and LST lamports (9-dec) with different scale. Does the wrapper preserve precision?
- Real finding pattern (pattern observed in multiple audits): Multiplication order truncates intermediate; 1 lamport error per conversion.

### 4c. Oracle Decimals
- SOL price oracles often return 8 decimals. Mixing with 9-decimal amounts requires careful scaling.
- Real finding pattern (pattern observed in multiple audits): Wrapper treats Pyth USD/SOL output as 9-decimals; prices inflated 10x.

Tag: [TRACE:lst_decimals_correct=YES/NO → mixed_precision_safe=YES/NO → oracle_decimals_correct=YES/NO]

---

## 5. Exchange-Rate Staleness Under Compounding

### 5a. Staleness Window
- Each read should be validated against a max age.
- Real finding pattern (pattern observed in multiple audits): Wrapper reads stake pool state that has not updated for 3 epochs; exchange rate stale by >1%.

### 5b. Per-LST Rate Cache
- If the wrapper caches rate between user calls, staleness can widen rapidly.
- Real finding pattern (pattern observed in multiple audits): Cache persists across epoch boundary; mispricing.

### 5c. Compounded Fee Impact
- Staleness plus fee plus slippage compound. Is the wrapper aware?
- Real finding pattern (pattern observed in multiple audits): Individual checks pass but total cost exceeds user-specified max-slippage.

Tag: [TRACE:staleness_enforced=YES/NO → rate_cache_refreshed=YES/NO → compound_slippage_enforced=YES/NO]

---

## 6. Mint Supply Invariant Assumption

### 6a. Hard-Coded Mint
- Does the wrapper pin the LST mint pubkey or accept user-supplied?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Wrapper accepts any mint that reports 9 decimals; attacker mints a fake jitoSOL.

### 6b. Mint Authority Locked
- LST mint should be controlled by the stake-pool PDA. Does the wrapper verify?
- Real finding pattern (pattern observed in multiple audits): Mint authority not pinned; malicious new stake pool takes over.

### 6c. Supply-Rate Consistency
- Total supply times rate should equal total SOL held. A mismatch indicates bug or exploit.
- Real finding pattern (pattern observed in multiple audits): Wrapper does not cross-check; stale accounting masked drain.

Tag: [TRACE:lst_mint_pinned=YES/NO → mint_authority_pinned=YES/NO → supply_rate_cross_checked=YES/NO]

---

## Common False Positives

- Wrapper only holds LST as pass-through with no internal rate math. Most math sections reduced.
- Wrapper exposes LST only to a sub-vault that handles redemptions. Section 2 delegated.
- Wrapper uses SolValueCalculator from Sanctum, which centralizes much of sections 1, 5, 6. Verify version pinning.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Post-Update Read | YES | | epoch boundary |
| 1b. Update CPI Invoked | YES | | update instruction |
| 1c. Rate Smoothing | IF step jumps are an issue | | smoothing approach |
| 2a. Fee Path Matches Route | YES | | liquid vs delayed |
| 2b. Delayed Fallback | YES | | empty pool recovery |
| 2c. Early Exit Penalty | IF short-dated deposits | | penalty tracked |
| 3a. Non-Monotonic Allowed | YES | | slashing tolerance |
| 3b. Loss Allocation | YES | | defined path |
| 3c. Commission Tracked | YES | | rate impact |
| 4a. LST Decimals | YES | | 9-dec constant |
| 4b. Mixed Precision | YES | | ordering |
| 4c. Oracle Decimals | YES | | unit match |
| 5a. Staleness Enforced | YES | | age bound |
| 5b. Rate Cache Refreshed | YES | | per tx |
| 5c. Compound Slippage | YES | | total bound |
| 6a. LST Mint Pinned | YES | | allow-list |
| 6b. Mint Authority | YES | | stake pool PDA |
| 6c. Supply-Rate Cross Check | YES | | invariant |
