---
name: "marginfi-lending-integration"
description: "Protocol Type Trigger marginfi_lending_integration (detected when recon finds marginfi|MarginfiAccount|MarginfiGroup|Bank|lending_account_deposit|lending_account_withdraw|lending_account_borrow|lending_account_liquidate - protocol USES MarginFi v2)"
---

# Injectable Skill: MarginFi Lending Integration Security

> Protocol Type Trigger: `marginfi_lending_integration` (detected when recon finds: `marginfi`, `MarginfiAccount`, `MarginfiGroup`, `Bank`, `lending_account_deposit`, `lending_account_withdraw`, `lending_account_borrow`, `lending_account_liquidate`)
> Inject Into: depth-token-flow, depth-external, depth-edge-case
> Language: Solana only
> Finding prefix: `[MFI-N]`
> Relationship to pyth-oracle-integration and switchboard-oracle-integration: MarginFi bank configs reference external oracles; activate those skills together.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-edge-case (account health computation path)
- Section 2: depth-external (bank config staleness)
- Section 3: depth-edge-case (asset tag discipline)
- Section 4: depth-token-flow (liquidation invariants, bad debt)
- Section 5: depth-state-trace (emission schedule claims)
- Section 6: depth-external (oracle feed binding per bank)

## When This Skill Activates

Recon detects that the protocol deposits, borrows, or liquidates through MarginFi banks, typically via CPI into `marginfi::cpi::lending_account_*` instructions.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: marginfi, MarginfiAccount, Bank, lending_account_deposit, lending_account_liquidate
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[MFI-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Account Health Computation Path

### 1a. Full Account Balances Passed
- `lending_account_withdraw` and `lending_account_borrow` require all active balances as remaining_accounts. Does the protocol always pass the full set?
- Real finding pattern (Solodit, pattern observed in multiple audits): Protocol truncates remaining_accounts to a fixed count; an additional position is ignored; health check passes despite debt.

### 1b. Order of Oracle Accounts
- Each balance requires its oracle account adjacent. Does the program preserve pairing order?
- Real finding pattern (pattern observed in multiple audits): Oracle accounts reordered; wrong oracle paired with bank; health wildly incorrect.

### 1c. Initial Health vs Maintenance Health
- Operations must not reduce account below initial-health threshold. Does the protocol distinguish `RiskRequirementType::Initial` vs `Maintenance`?
- Real finding pattern (pattern observed in multiple audits): Wrapper uses maintenance threshold for borrow checks; account can borrow into immediate liquidatable state.

Tag: [TRACE:full_balances_forwarded=YES/NO → oracle_pairing_preserved=YES/NO → initial_vs_maintenance=correct/confused]

---

## 2. Bank Config Staleness

### 2a. Cached Bank Parameters
- Bank config (LTV, liq threshold, caps) is governance-mutable. Does the protocol re-read per transaction?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Protocol caches LTV at bank onboarding; governance tightens LTV; wrapper uses cached value, users unexpectedly liquidated.

### 2b. Bank Paused State
- Banks can be paused. Does the protocol handle the revert gracefully or freeze user funds?
- Real finding pattern (pattern observed in multiple audits): Wrapper reverts user withdraw when bank paused, with no recovery path for the user's non-paused assets.

### 2c. Bank Close or Removal
- Banks can be decommissioned. Does the protocol detect and migrate?
- Real finding pattern (pattern observed in multiple audits): Bank removed from group; protocol still holds share tokens; no redemption path in wrapper.

Tag: [TRACE:bank_config_per_tx=YES/NO → paused_state_handled=YES/NO → bank_removal_handled=YES/NO]

---

## 3. Asset Tag Discipline

### 3a. Default vs Isolated vs Collateral
- MarginFi banks have asset tags: `Default`, `IsolatedRiskTier`, `SolRiskTier`, etc. Does the protocol enforce its banks-in-use against an allow-list?
- Real finding pattern (pattern observed in multiple audits): Protocol adds an isolated-tier bank thinking it will be collateral; position fails to borrow because isolated tag restricts usage.

### 3b. Multiple Isolated Banks
- A single marginfi account cannot simultaneously hold multiple isolated-tier positions. Does the protocol enforce?
- Real finding pattern (pattern observed in multiple audits): Wrapper permits two isolated deposits; second CPI reverts, leaving partial state.

### 3c. SOL Risk Tier Interaction
- SOL-tier banks have specific collateral treatment (e.g. native stake). Does the program handle correctly?
- Real finding pattern (pattern observed in multiple audits): Program treats SOL tier the same as default, miscomputing weights.

Tag: [TRACE:bank_tag_allowlist=YES/NO → isolated_exclusivity_enforced=YES/NO → sol_tier_handled=YES/NO]

---

## 4. Liquidation Invariants and Bad Debt

### 4a. Liquidation Path Exposed
- If the protocol exposes its positions to liquidation, does it expose the liquidator-bonus so third parties can liquidate before bad debt?
- Real finding pattern (Solodit, pattern observed in multiple audits): Wrapper owns all positions via PDA; third parties cannot supply the correct PDA signer to liquidate; bad debt persists.

### 4b. Socialized Loss Handling
- If a MarginFi bank socializes loss, shares drop in value. Does the wrapper propagate loss to depositors or absorb via treasury?
- Real finding pattern (pattern observed in multiple audits): Wrapper accounting assumes share value is monotonically non-decreasing; loss event breaks internal invariant, freezing withdrawals.

### 4c. Liquidation Fee Leakage
- Liquidation rewards should flow to the insurance fund or designated account. Does the program capture the reward or leave it to caller?
- Real finding pattern (pattern observed in multiple audits): Liquidation reward credited to caller (user); protocol does not capture.

Tag: [TRACE:third_party_liquidation_possible=YES/NO → loss_propagated_correctly=YES/NO → liquidation_reward_routed=YES/NO]

---

## 5. Emission Schedule Double-Claim

### 5a. Emission Index Snapshot
- Reward emission uses a per-bank index. Double calling claim without updating index can double-pay.
- Real finding pattern (pattern observed in multiple audits): Wrapper's claim instruction does not invoke `collect_bank_fees` first; stale index double-pays on second claim in same slot.

### 5b. Emission Mint Change
- If emission mint rotates, old reward vault balance is orphaned. Does the program detect?
- Real finding pattern (pattern observed in multiple audits): Protocol indexes by mint symbol; mint rotation breaks claim path.

### 5c. Share Timestamp Attack
- Depositing just before a large emission distribution and withdrawing after should not capture disproportionate rewards. Does the program use time-weighted shares?
- Real finding pattern (pattern observed in multiple audits): Share-weighted emission allows JIT deposits to capture large share.

Tag: [TRACE:claim_updates_index=YES/NO → emission_mint_rotation_handled=YES/NO → jit_deposit_protected=YES/NO]

---

## 6. Oracle Feed Binding Per Bank

### 6a. Bank-Oracle Binding Verification
- Each bank has a configured oracle (Pyth / Switchboard / Pyth pull). Does the protocol verify the passed oracle matches `bank.config.oracle_keys`?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Protocol passes a Pyth account that matches the bank's symbol but not the configured key, causing MarginFi to reject; user operations revert unexpectedly.

### 6b. Oracle Setup Enum Handling
- `OracleSetup` enum includes `PythEma`, `SwitchboardV2`, `PythPushOracle`. Does the wrapper select the correct account structure per variant?
- Real finding pattern (pattern observed in multiple audits): Wrapper always builds Pyth account set; switchboard-configured bank fails.

### 6c. Oracle Change Mid-Flight
- Governance can change a bank's oracle. Does the protocol pin an expected oracle or trust whatever bank points to?
- Real finding pattern (pattern observed in multiple audits): Oracle changed to different asset due to config error; protocol trusts silently; positions mispriced.

Tag: [TRACE:bank_oracle_matched=YES/NO → oracle_setup_variant_handled=YES/NO → oracle_change_detected=YES/NO]

---

## Common False Positives

- Protocol is read-only (reads MarginFi positions for analytics), no deposits or borrows. Most sections do not apply.
- Protocol uses MarginFi only for a single well-known bank on SOL. Sections 3, 2c, 6c reduced.
- Claims are done through MarginFi UI directly, not wrapper. Section 5 delegated.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Full Balances Forwarded | YES | | remaining_accounts set |
| 1b. Oracle Pairing Preserved | YES | | order integrity |
| 1c. Initial vs Maintenance | YES | | correct threshold |
| 2a. Bank Config Per Tx | YES | | no stale cache |
| 2b. Paused State Handled | YES | | graceful revert |
| 2c. Bank Removal | IF long-lived deposits | | migration path |
| 3a. Bank Tag Allowlist | YES | | tag filter |
| 3b. Isolated Exclusivity | YES | | single isolated bank |
| 3c. SOL Tier | IF SOL tier banks | | weight handling |
| 4a. Third-Party Liquidation | IF positions are liquidatable | | PDA signer access |
| 4b. Loss Propagation | YES | | share value drop handled |
| 4c. Liquidation Reward Route | IF wrapper liquidates | | correct recipient |
| 5a. Claim Updates Index | IF rewards claimed | | collect first |
| 5b. Mint Rotation | IF emission mint changes | | rotation handling |
| 5c. JIT Deposit Protection | IF rewards are share-based | | time-weighted |
| 6a. Bank Oracle Matched | YES | | binding check |
| 6b. Oracle Setup Variant | YES | | enum per setup |
| 6c. Oracle Change Detected | YES | | drift check |
