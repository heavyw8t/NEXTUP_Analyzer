---
name: "clmm-pool-integration"
description: "Protocol Type Trigger clmm_pool_integration (detected when recon finds whirlpool|whirlpool_program|tick_array|sqrt_price_x64|clmm_pool|raydium_clmm|tick_spacing|position_nft - protocol USES Orca/Raydium CLMM pools)"
---

# Injectable Skill: CLMM Pool Integration Security

> Protocol Type Trigger: `clmm_pool_integration` (detected when recon finds: `whirlpool`, `whirlpool_program`, `tick_array`, `sqrt_price_x64`, `clmm_pool`, `raydium_clmm`, `tick_spacing`, `position_nft`)
> Inject Into: depth-token-flow, depth-edge-case, depth-state-trace
> Language: Solana only
> Finding prefix: `[CLMM-N]`
> Relationship to jupiter-aggregator-integration: aggregator routes often land on CLMMs. Activate both when the program composes routes and direct CLMM calls.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-edge-case (tick / sqrt_price rounding direction)
- Section 2: depth-state-trace (tick array staleness)
- Section 3: depth-edge-case (position NFT authority)
- Section 4: depth-token-flow (fee growth / reward accounting on close)
- Section 5: depth-token-flow (thin-liquidity manipulation)
- Section 6: depth-state-trace (observation ring buffer)

## When This Skill Activates

Recon detects direct CPI calls or account layouts for Orca Whirlpools or Raydium CLMM, for example vaults that LP into a concentrated pool, perps using CLMM as price reference, or launchpads opening initial positions.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: whirlpool, tick_array, sqrt_price_x64, tick_spacing, position_nft, raydium_clmm
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[CLMM-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Tick and sqrt_price_x64 Rounding Direction

### 1a. Sqrt Price Rounding
- Does the program pick the correct rounding direction when converting amounts to sqrt_price_x64? Wrong direction leaks value per swap.
- Real finding pattern (Solodit, pattern observed in multiple audits): `compute_swap_step` rounds down on `amount_in`, then rounds up on `sqrt_price_next`, accumulating dust leakage on the pool operator.

### 1b. Tick Math Saturation
- Converting price to tick uses logarithm tables; boundary ticks (MIN_TICK, MAX_TICK) must saturate, not wrap.
- Real finding pattern (pattern observed in multiple audits): Program casts tick to `u32` before negation, turning MIN_TICK into a huge positive.

### 1c. Position Range Consistency
- Does the program enforce `tick_lower < tick_upper` and `tick_upper % tick_spacing == 0`?
- Real finding pattern (pattern observed in multiple audits): Position created with `tick_lower == tick_upper`; pool math divides by zero liquidity.

Tag: [TRACE:sqrt_price_rounding=correct/incorrect → tick_saturation_handled=YES/NO → position_range_validated=YES/NO]

---

## 2. Tick Array Discovery and Staleness

### 2a. Correct Tick Array Sequencing
- Swap crosses several tick arrays; the caller must provide three adjacent arrays in correct order. Does the program compute them deterministically?
- Real finding pattern (Solodit, pattern observed in multiple audits): Tick arrays supplied in wrong order; router fails mid-swap after partial state mutation.

### 2b. Tick Array Staleness
- If the program caches tick arrays, state may shift between read and write. Does it re-fetch inside the CPI context?
- Real finding pattern (pattern observed in multiple audits): Cached tick arrays from a prior tx are used; pool moved; liquidity computed against wrong ticks.

### 2c. Edge Arrays on Open Position
- Opening a position at MIN_TICK or MAX_TICK requires special-case tick arrays. Does the program permit this?
- Real finding pattern (pattern observed in multiple audits): Edge-case position blocked by `index_of_tick_array` underflow.

Tag: [TRACE:tick_array_order=deterministic/caller_supplied → tick_array_freshness=per_tx/cached → edge_ticks_supported=YES/NO]

---

## 3. Position NFT Authority

### 3a. NFT Mint Authority Burned
- Position NFT mints must have no further mint authority. Does the program verify? A mintable NFT lets the pool operator forge positions.
- Real finding pattern (Cantina, pattern observed in multiple audits): Program accepts a position NFT whose mint authority is still set to an attacker; attacker mints a second "copy" of the position.

### 3b. NFT Account Ownership
- Does the program check the NFT token account owner, freeze authority absent, and amount == 1?
- Real finding pattern (pattern observed in multiple audits): Amount check missing; zero-balance token account passes.

### 3c. Position Metadata Discriminator
- Does the program load position metadata through the CLMM loader (checking discriminator) rather than raw bytes?
- Real finding pattern (pattern observed in multiple audits): Raw byte read; attacker supplies a fake position metadata account.

Tag: [TRACE:nft_mint_authority_burned=YES/NO → nft_account_owner_checked=YES/NO → position_metadata_loader_used=YES/NO]

---

## 4. Fee Growth and Reward Emission on Close

### 4a. Collect Fees Before Close
- Closing a position without first collecting fees and rewards loses those to the pool. Does the program order correctly?
- Real finding pattern (Solodit, pattern observed in multiple audits): Close-position flow skips `collect_fees` when `liquidity == 0`; accrued fees forfeited.

### 4b. Reward Growth Snapshot
- Reward indices are checkpointed per position. A stale snapshot under-pays the position.
- Real finding pattern (pattern observed in multiple audits): Program fails to call `update_fees_and_rewards` before distribution, using stale snapshot.

### 4c. Reward Vault Drain on Reward Change
- If a pool operator changes a reward token mid-flight, does the program handle vacated rewards?
- Real finding pattern (pattern observed in multiple audits): Reward vault swapped; program's reward mint check not re-verified; wrong token transferred.

Tag: [TRACE:fees_collected_before_close=YES/NO → reward_snapshot_updated=YES/NO → reward_mint_rechecked=YES/NO]

---

## 5. Thin-Liquidity Price Manipulation

### 5a. Price Read From CLMM
- If the program reads `sqrt_price_x64` as an oracle, a small swap can move the price. Does the program use TWAP or observation averages?
- Real finding pattern (Code4rena, pattern observed in multiple audits): Mint-to-value rate computed from live sqrt_price; flashloan swap moves price 30% and drains vault.

### 5b. Minimum Liquidity Threshold
- Does the program refuse to quote when pool liquidity is below a threshold?
- Real finding pattern (pattern observed in multiple audits): Attacker creates a new pool with minimal liquidity and registers it; program reads price and accepts absurd values.

### 5c. JIT Liquidity Front-Run
- When the protocol LPs, a JIT attacker can add liquidity in the same slot to capture the fee.
- Real finding pattern (pattern observed in multiple audits): Keeper compound transaction is sandwiched by JIT adds, harvesting the pool fee share.

Tag: [TRACE:price_source=live/twap → min_liquidity_enforced=YES/NO → jit_protection=YES/NO]

---

## 6. Observation Ring Buffer

### 6a. Observation Required Before Read
- Raydium CLMM and Whirlpool observations write lazily. Reading without an update yields stale data.
- Real finding pattern (pattern observed in multiple audits): Program reads observation index without invoking update instruction; TWAP frozen at last-interacted tick.

### 6b. Buffer Wrap Edge Case
- Ring buffer wraps; observation at index `(current + N) % LEN` can be from a previous epoch. Does the program reject if age > max?
- Real finding pattern (pattern observed in multiple audits): Buffer wrap returns very old observation read as fresh; TWAP computes across stale-and-new split, producing huge delta.

### 6c. Time-Weighted Average Weighting
- Does the code compute TWAP across correct interval, including extrapolation for the open segment?
- Real finding pattern (pattern observed in multiple audits): TWAP divides by N-1 instead of N, biasing by 1 slot.

Tag: [TRACE:observation_updated_before_read=YES/NO → buffer_wrap_handled=YES/NO → twap_weighting_correct=YES/NO]

---

## Common False Positives

- Program only references CLMM through a delegated vault contract that already handles tick arrays and fee collection. Sections 1, 2, 4 delegated.
- Program reads price only from Pyth or Switchboard; CLMM sqrt_price is not used as oracle. Section 5 reduced.
- Program opens full-range position only; tick array discovery simplified. Section 2c still required.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Contract storage exhaustion via unbounded deposit array growth
  Where it hit: liquidity_lockbox::deposit() in lockbox-solana (Orca Whirlpool lockbox)
  Severity: HIGH
  Source: Solodit (row_id 9225)
  Summary: The lockbox contract stores one record per deposit in a fixed-size on-chain account capped at 10 KB. After 625 deposits the account is full and every subsequent deposit reverts, permanently DoS-ing the contract. An attacker can reach this cap cheaply with minimal-liquidity deposits.
  Map to: liquidity_lockbox, whirlpool

- Pattern: ATA pre-initialization griefing on NFT deposit
  Where it hit: liquidity_lockbox::deposit() in lockbox-solana (Orca Whirlpool lockbox)
  Severity: MEDIUM
  Source: Solodit (row_id 8774)
  Summary: The deposit instruction uses Anchor's `init` constraint to create the position NFT's associated token account. Because `init` reverts if the account already exists, an attacker who pre-creates that ATA causes every deposit for that specific NFT to fail permanently. No assets can be stolen, but the position is rendered undepositable.
  Map to: liquidity_lockbox, position_nft, whirlpool

- Pattern: Missing collect_rewards call before position close causes unexpected revert
  Where it hit: liquidity_lockbox::withdraw() in lockbox-solana (Orca Whirlpool lockbox)
  Severity: MEDIUM
  Source: Solodit (row_id 8775)
  Summary: The withdraw flow closes the Whirlpool position without first calling whirlpool::collect_rewards. When rewards are enabled on the pool, the close instruction reverts because uncollected rewards remain. This silently DoS-es withdrawals for any position with pending rewards, fitting the Section 4a pattern of ordering fees/rewards before close.
  Map to: liquidity_lockbox, whirlpool

- Pattern: No minimum deposit threshold enables cheap griefing via dust positions
  Where it hit: liquidity_lockbox::deposit() in lockbox-solana (Orca Whirlpool lockbox)
  Severity: MEDIUM
  Source: Solodit (row_id 9218)
  Summary: The lockbox imposes no lower bound on deposited liquidity. A malicious actor opens many dust positions at minimal cost, filling the on-chain position list. Legitimate users then bear the per-position transaction cost when withdrawing through a linear scan, creating a griefing vector that amplifies the storage-exhaustion risk in row_id 9225.
  Map to: liquidity_lockbox, whirlpool, tick_array

- Pattern: Flashloan-assisted reward manipulation via instant deposit-withdraw cycle
  Where it hit: liquidity_lockbox reward distribution in lockbox-solana (Orca Whirlpool lockbox)
  Severity: MEDIUM
  Source: Solodit (row_id 9219)
  Summary: A user can deposit a large amount of liquidity, immediately withdraw in the same transaction (or across two transactions using a flash loan), and claim a disproportionate share of OLAS rewards without bearing sustained liquidity risk. The attack is repeatable as long as the flashloan cost is less than the captured reward. This maps to the Section 5a thin-liquidity / price manipulation class applied to reward accounting.
  Map to: liquidity_lockbox, whirlpool, sqrt_price_x64

---

*Coverage note: All 5 candidates originate from a single audit of the Orca `liquidity_lockbox` contract in the `lockbox-solana` repository. Coverage of other CLMM integration domains (Raydium CLMM, tick array ordering, sqrt_price rounding, NFT authority checks, observation ring buffer) is absent from this candidate set. When this skill activates on a non-lockbox protocol, treat these examples as supplementary precedent only and rely on the skill's static patterns for full coverage.*


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Sqrt Price Rounding | YES | | per-direction rounding |
| 1b. Tick Math Saturation | YES | | MIN/MAX tick |
| 1c. Position Range | YES | | spacing and ordering |
| 2a. Tick Array Order | YES | | deterministic |
| 2b. Tick Array Freshness | YES | | per-tx fetch |
| 2c. Edge Ticks | IF boundary positions allowed | | special case |
| 3a. NFT Mint Authority Burned | YES | | authority null |
| 3b. NFT Account Ownership | YES | | amount=1, no freeze |
| 3c. Position Loader | YES | | discriminator check |
| 4a. Fees Collected Before Close | YES | | order correct |
| 4b. Reward Snapshot | YES | | update first |
| 4c. Reward Mint Recheck | IF reward can change | | mint binding |
| 5a. Price Source | IF price used as oracle | | twap vs live |
| 5b. Min Liquidity | IF quote path | | threshold |
| 5c. JIT Protection | IF keeper compounds | | anti-JIT |
| 6a. Observation Updated | IF observation used | | update call |
| 6b. Buffer Wrap | IF observation used | | age check |
| 6c. TWAP Weighting | IF TWAP consumed | | correct denominator |
