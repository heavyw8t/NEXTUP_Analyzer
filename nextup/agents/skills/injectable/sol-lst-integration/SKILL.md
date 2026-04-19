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

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Collected: 2026-04-19
> Target: 5-10 verifiable findings for skill sections 1-6

---

## Finding 1

- Pattern: mSOL exchange-rate rounding allows depositor to extract one extra mSOL-lamport by splitting a deposit that crosses the swap/mint boundary
- Where it hit: Marinade Finance (mSOL) — deposit instruction
- Severity: LOW
- Source: https://app.marinade.finance/docs/Neodyme_2023.pdf (Neodyme audit ND-MAR01-LO-01, October 2023)
- Summary: When a deposit spans both the liquidity-pool swap and the fresh-mint path, integer arithmetic implicitly rounds up instead of down. In the worst case the attacker gains at most S/T mSOL-lamports per transaction (≤1 lamport under normal conditions, but more if a slashing event causes S > T). Fixed in Marinade PR #69 by computing the mSOL buy amount once and subtracting the swap portion from it.
- Map to: mSOL, marinade_finance

---

## Finding 2

- Pattern: Validator commission raised to 100% at epoch end extracts one full epoch of staking rewards from a liquid staking pool before the pool can react; exchange rate drops for all remaining holders after the off-chain bot detects and blacklists the validator
- Where it hit: Marinade Finance (mSOL) — off-chain cranker + on-chain state
- Severity: MEDIUM (economic / governance; discussed as known risk in the audit)
- Source: https://app.marinade.finance/docs/Neodyme_2023.pdf (Neodyme 2023 audit, section "Validator Commission Attack")
- Summary: Solana validators can set commission to 100% at any point; the change takes effect immediately for that epoch. A validator controlling ~10% of Marinade's delegated stake can skim up to 10-100 epochs' worth of rewards in a single epoch. Marinade mitigates by monitoring and blacklisting, limiting exposure to one epoch. Any protocol that reads mSOL's exchange rate without accounting for this one-epoch lag will observe a stale, inflated rate.
- Map to: mSOL, marinade_finance, stake_pool

---

## Finding 3

- Pattern: Slashing event not reflected in exchange rate until the Update instruction runs; users who withdraw between the slashing event and the next update receive the pre-slash rate, leaving remaining depositors with a proportionally larger loss
- Where it hit: Marinade Finance (mSOL) — Withdraw instruction
- Severity: MEDIUM (economic; discussed in the Neodyme audit as "Arbitraging Imminent Slashing")
- Source: https://app.marinade.finance/docs/Neodyme_2023.pdf (Neodyme 2023 audit, section "Attacks Related to Slashing")
- Summary: A slashing event on a delegated validator is not visible to Marinade's on-chain state until the next call to the Update instruction. Between the event and the update, users can withdraw at the pre-slash rate. In extreme cases this produces a small bank run; users who exit first are made whole at the expense of those who remain. Integrators that cache the mSOL rate across Update calls inherit this window.
- Map to: mSOL, marinade_finance, stake_pool

---

## Finding 4

- Pattern: SPL stake pool initialization omits minting pool tokens for lamports already in the reserve account; first depositor receives far more pool tokens than the contributed SOL warrants, then redeems them to drain the reserve
- Where it hit: Solana Program Library stake-pool program (affects all LSTs built on it: jitoSOL, bSOL, JSOL, and any SPL-based pool)
- Severity: HIGH
- Source: https://www.sec3.dev/blog/solana-stake-pool-a-semantic-inconsistency-vulnerability-discovered-by-x-ray (Sec3/Soteria, patched in solana-program-library PR #2636)
- Summary: The process_initialize instruction reads from reserve_stake_info.data but performs no corresponding spl_token::mint_to. This violates the invariant "every use of reserve_stake is paired with a token operation." An attacker who deposits 1 SOL as the first depositor claims 990,000,000 pool tokens and withdraws approximately 97.99 SOL. Any protocol that forked or reused the stake-pool program before the patch may carry the same bug. Fixed: "Mint extra reserve lamports as pool tokens on init."
- Map to: jitoSOL, bSOL, stake_pool

---

## Finding 5

- Pattern: Token extension (ConfidentialTransferFeeConfig or other blocking extension) on the pool token mint can allow the pool manager to block Withdraw instructions, holding user funds hostage, because Withdraw transfers pool tokens to the manager fee account
- Where it hit: SPL stake pool program — Withdraw instruction (reviewed in Neodyme SPL change review 2023-11-14)
- Severity: HIGH (design-level; mitigated by extension whitelist in the reviewed PR)
- Source: https://neodyme.io/reports/SPL-Stake-Pool-2023.pdf (Neodyme change review 2023-11-14, section "Allow mints with confidential transfer fee extension")
- Summary: Token extensions can fundamentally alter transfer behavior, including blocking all transfers. If a blocking extension were applied to the pool token mint, the manager could prevent any user from withdrawing. The SPL program maintains a whitelist of safe extensions; the PR that added ConfidentialTransferFeeConfig was verified safe because that specific extension does not alter normal transfer or burn behavior. Protocols that accept arbitrary LST mints without checking extension whitelist status are exposed to the same manager-censorship risk.
- Map to: jitoSOL, bSOL, stake_pool

---

## Finding 6

- Pattern: Stake pool share-price manipulation via conversion-rate variable that any user can change through a permissionless instruction; allows theft of other users' staked tokens or minting of unlimited vote tokens
- Where it hit: Jet Governance (Solana staking program using a stake pool pattern)
- Severity: HIGH
- Source: local candidates.jsonl (row 16220; Jet Governance Audit, Solana)
- Summary: The conversion rate between tokens and shares uses self.shares_bonded, which is modified directly by the unbond method callable by any user. An attacker calls unbond to deflate shares_bonded, inflating the conversion rate, then deposits at the manipulated rate to steal staked tokens or mint unbounded vote tokens. Fix: use shares_bonded + shares_unbonded in conversion calculations, or store the rate as an immutable field.
- Map to: stake_pool

---

## Finding 7

- Pattern: Sanctum Infinity's S Controller reads LST intrinsic SOL value from external liquid-staking program state via SOL Value Calculator; if the external program's state has not been updated (epoch boundary not crossed or update instruction not called), the controller prices LSTs at a stale rate, enabling arbitrage between the stale internal price and the live AMM price
- Where it hit: Sanctum Infinity (multi-LST pool using sol_value_calculator)
- Severity: MEDIUM
- Source: https://raw.githubusercontent.com/igneous-labs/sanctum-static/master/audits/infinity/Neodyme-INV-24-01.pdf (Neodyme audit of Sanctum Infinity, February 2024); architecture confirmed at https://learn.sanctum.so/docs/technical-documentation/infinity
- Summary: Infinity allows swaps between any LSTs at prices derived from each LST's intrinsic SOL valuation. These valuations are read from external on-chain state (e.g., the SPL stake pool's total_lamports and pool_token_supply). If the external program's update has not run for the current epoch, the computed SOL value is up to one epoch stale. Traders can front-run the epoch-boundary update by swapping at the pre-update price, profiting from the discrete step change. Protocols that integrate sol_value_calculator without gating on a freshness check inherit this window.
- Map to: sanctum, sol_value_calculator, stake_pool

---

## Coverage Notes

- Findings 1-3 and finding 7 map directly to SKILL sections 1, 3, and 5 (exchange-rate staleness, slashing passthrough, commission tracking).
- Finding 4 maps to section 6 (mint supply invariant / initialization accounting).
- Finding 5 maps to section 6b (mint authority validation).
- Finding 6 maps to section 6c (supply-rate consistency / share-price manipulation).
- No verifiable public finding was located for section 4 (decimals assumption) or section 2b (empty-pool delayed-unstake fallback) despite targeted searches. These sections remain pattern-derived.

## Search Queries That Yielded Results

- `site:solodit.cyfrin.io marinade` — no direct hits; navigated to PDF audits via Marinade docs
- `Marinade Finance mSOL audit security vulnerability exchange rate stale epoch` — found Neodyme 2023 PDF
- `Sec3 Soteria Solana stake pool semantic inconsistency vulnerability CVE details` — found sec3.dev article
- `Neodyme Marinade mSOL audit 2023 findings vulnerabilities PDF` — found Neodyme 2023 PDF and Sanctum Infinity PDF
- `Sanctum Infinity audit Neodyme findings LST exchange rate sol value calculator vulnerability 2024` — confirmed Neodyme INV-24-01 exists
- `Solana SPL stake pool OtterSec Halborn Neodyme audit 2023 specific findings` — found Neodyme SPL change review PDF


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
