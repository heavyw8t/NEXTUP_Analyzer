---
name: "jupiter-aggregator-integration"
description: "Protocol Type Trigger jupiter_aggregator_integration (detected when recon finds jupiter_swap|Jupiter|shared_accounts_route|sharedAccountsRoute|route_plan|platform_fee|JUP4|JUP6|jupiterProgram - protocol USES Jupiter for swap routing)"
---

# Injectable Skill: Jupiter Aggregator Integration Security

> Protocol Type Trigger: `jupiter_aggregator_integration` (detected when recon finds: `jupiter_swap`, `Jupiter`, `shared_accounts_route`, `sharedAccountsRoute`, `route_plan`, `platform_fee`, `JUP4`, `JUP6`, `jupiterProgram`)
> Inject Into: depth-token-flow, depth-external
> Language: Solana only
> Finding prefix: `[JUP-N]`
> Relationship to clmm-pool-integration: Jupiter routes through CLMM and legacy AMM pools. Both skills apply when the program composes direct CLMM calls with aggregator calls.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (CPI assembly, remaining_accounts ordering)
- Section 2: depth-token-flow (slippage bps, min-out)
- Section 3: depth-external (quote freshness)
- Section 4: depth-token-flow (platform-fee account collision)
- Section 5: depth-external (program ID allowlist)
- Section 6: depth-token-flow (token program mismatch across legs)

## When This Skill Activates

Recon detects that the program CPI-calls Jupiter (V4, V6, or shared accounts variant) to swap tokens inside an instruction, commonly used by vaults, LSTs, intent protocols, or liquidation engines.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: jupiter, shared_accounts_route, route_plan, platform_fee, slippage_bps
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[JUP-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Route CPI Assembly

### 1a. remaining_accounts Length and Order
- Jupiter's router walks `remaining_accounts` in the exact order specified by the off-chain quote. Does the program forward accounts in the original order, or does it reorder / filter?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program concatenates additional custody accounts before the Jupiter accounts, shifting the offset so the router reads a vault pubkey as a pool account.

### 1b. Inner Instruction Data Integrity
- Is the instruction data passed to Jupiter the same buffer produced off-chain? Any mutation changes the route plan.
- Real finding pattern (pattern observed in multiple audits): Program decodes the `route_plan` to validate it, then re-serializes, losing compact-u16 length bytes and causing router to misparse.

### 1c. Source and Destination Mint Binding
- The program should bind the mints used in its accounting to the Jupiter `input_mint` / `output_mint` it signs for.
- Real finding pattern (Sherlock, pattern observed in multiple audits): User-supplied `input_mint` differs from the token the vault actually spent; caller gets desired asset paid by vault's unrelated asset.

Tag: [TRACE:remaining_accounts_order=preserved/mutated → instruction_data_passthrough=YES/NO → input_output_mint_bound=YES/NO]

---

## 2. Slippage bps and Min-Out

### 2a. Slippage bps Clamp
- Is the user-supplied `slippage_bps` clamped by protocol policy? Zero or max slippage allows sandwiching.
- Real finding pattern (Code4rena, pattern observed in multiple audits): Program forwards user `slippage_bps = 10_000` (100%), so a sandwicher can drain output to 0.

### 2b. Min-Out Recomputed On-Chain
- Does the program recompute minimum output from the oracle at execution time, or does it trust the off-chain quote?
- Real finding pattern (Solodit, pattern observed in multiple audits): Quote is 10 minutes old; on-chain price moved 3%; protocol accepts far-off-market fill.

### 2c. Rounding on Min-Out
- For collateral-in-swap, min-out should round down; for debt-out-swap, it should round up. Does the direction match the protocol's economic role?
- Real finding pattern (pattern observed in multiple audits): Program rounds to nearest, sometimes up, leaking 1 lamport per swap across many transactions.

Tag: [TRACE:slippage_bps_clamped=YES/NO → min_out_oracle_checked=YES/NO → rounding_direction=correct/incorrect]

---

## 3. Quote Freshness

### 3a. Off-Chain Quote Age
- Is the quote timestamp (or slot) supplied by the caller, and verified against `Clock`?
- Real finding pattern (Cantina, pattern observed in multiple audits): Caller supplies a stale quote; price moved; program still fills.

### 3b. Signed Quote vs Unsigned
- Does the program require a signed quote from a trusted quoter, or accept any quote bytes?
- Real finding pattern (pattern observed in multiple audits): Unsigned quote allows the caller to hand-craft route bytes that pass basic sanity but steer output through a rug pool.

### 3c. Quote Exclusion List
- Has the program configured pool exclusions (e.g. disallowed markets)? Route plan must be inspected for forbidden pools.
- Real finding pattern (pattern observed in multiple audits): Program allows any AMM; route passes through a non-canonical pool with manipulated reserves.

Tag: [TRACE:quote_age_checked=YES/NO → signed_quote_required=YES/NO → pool_allowlist=YES/NO]

---

## 4. Platform-Fee Account Collision

### 4a. Platform Fee Account Owner
- `platform_fee_account` must be a token account owned by the protocol. Is it checked?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program accepts attacker's token account as `platform_fee_account`; fees routed away.

### 4b. Platform Fee Mint Matches Output
- The fee account mint must equal the swap's output mint. Is the mint validated?
- Real finding pattern (pattern observed in multiple audits): Mint mismatch causes CPI failure or, worse, sends fee to a low-value token.

### 4c. Platform Fee bps Policy
- Is `platform_fee_bps` bounded by protocol config?
- Real finding pattern (pattern observed in multiple audits): User controls platform_fee_bps and sets 0, effectively disabling revenue.

Tag: [TRACE:platform_fee_owner_checked=YES/NO → platform_fee_mint_checked=YES/NO → platform_fee_bps_bounded=YES/NO]

---

## 5. Program ID Allowlist

### 5a. Jupiter Program ID Pinned
- Is the program ID pinned to the exact Jupiter program (V4 or V6), not `AccountInfo` supplied by caller?
- Real finding pattern (Sherlock, pattern observed in multiple audits): CPI target is a user-supplied program; attacker supplies their own "router" that steals input.

### 5b. Version Discipline
- V4 and V6 have different instruction layouts. Is the program hard-coded to one version?
- Real finding pattern (pattern observed in multiple audits): Program accepts either version but only validates V6 fields; V4 call runs with partial validation.

### 5c. Shared-Accounts Variant Locking
- `shared_accounts_route` uses a program-owned intermediate account. Is the intermediate account PDA derived correctly?
- Real finding pattern (pattern observed in multiple audits): Wrong seed derivation; intermediate is attacker-controlled; trailing funds swept.

Tag: [TRACE:jupiter_program_id_pinned=YES/NO → version_locked=<v4|v6|both> → shared_accounts_pda_correct=YES/NO]

---

## 6. Token Program Mismatch Across Legs

### 6a. Token-2022 Leg in Classic Route
- Routes can traverse Token-2022 and classic SPL token pools. Does the program pass the correct `token_program` for each leg?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program always passes `spl_token::ID`; a Token-2022 leg fails or transfers without hook execution.

### 6b. Transfer Fee Extension
- A Token-2022 mint with transfer fee reduces delivered amount. Does the program treat the fee as expected slippage?
- Real finding pattern (pattern observed in multiple audits): Min-out ignores transfer fee; swap reverts even when price is fine.

### 6c. Decimals Assumption
- Decimals can differ between legs. Does the program normalize amounts to quote units?
- Real finding pattern (pattern observed in multiple audits): Program hard-codes 6 decimals; route includes a 9-decimal LST leg; amount values off by 1000x.

Tag: [TRACE:token_program_per_leg=YES/NO → token_2022_fee_accounted=YES/NO → decimals_normalized=YES/NO]

---

## Common False Positives

- Program uses a trusted signed quote service that re-validates on-chain. Sections 2 and 3 partially delegated.
- Program uses shared_accounts_route in a dedicated PDA with no user inputs beyond amount. Section 1 reorder risk low.
- Swap is purely internal (no user-initiated routes). Platform-fee and slippage griefing paths reduced.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. remaining_accounts Order | YES | | offset integrity |
| 1b. Instruction Data Passthrough | YES | | no re-encode drift |
| 1c. Input/Output Mint Bound | YES | | mint binding |
| 2a. Slippage bps Clamp | YES | | user-supplied bound |
| 2b. Min-Out Oracle Check | YES | | on-chain price gate |
| 2c. Rounding Direction | YES | | correct direction |
| 3a. Quote Age | YES | | staleness gate |
| 3b. Signed Quote | IF untrusted callers | | signature required |
| 3c. Pool Allowlist | IF policy restricts | | disallowed pools |
| 4a. Platform Fee Owner | IF fee enabled | | account owned by protocol |
| 4b. Platform Fee Mint | IF fee enabled | | mint matches output |
| 4c. Platform Fee bps Bound | IF fee enabled | | bps bound |
| 5a. Program ID Pinned | YES | | jupiter program id |
| 5b. Version Discipline | YES | | v4 vs v6 layout |
| 5c. Shared Accounts PDA | IF variant used | | seed correctness |
| 6a. Token Program per Leg | YES | | classic vs 2022 |
| 6b. Token-2022 Fee Accounted | IF 2022 legs present | | fee-as-slippage |
| 6c. Decimals Normalized | YES | | unit normalization |
