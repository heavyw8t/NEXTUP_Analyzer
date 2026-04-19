---
name: "account-validation"
description: "Trigger Pattern Always required for Solana audits - Inject Into Breadth agents, depth agents"
---

# ACCOUNT_VALIDATION Skill

> **Trigger Pattern**: Always required for Solana audits
> **Inject Into**: Breadth agents, depth agents
> **Finding prefix**: `[AV-N]`
> **Rules referenced**: S1, S6, S7, S8, R4

For every instruction handler in the Solana program:

## 1. Account Type Inventory

For EACH instruction, list every account with expected constraints:

| # | Account Name | Expected Owner | Expected Type (Discriminator) | Mutable? | Signer? | Constraints (has_one, seeds, etc.) |
|---|-------------|----------------|-------------------------------|----------|---------|-----------------------------------|
| 1 | {name} | {program_id / system / token} | {Account<T> / UncheckedAccount / etc.} | YES/NO | YES/NO | {list all} |

**Anchor auto-checks**: Anchor's `Account<T>` validates owner + discriminator automatically. `UncheckedAccount` / `AccountInfo` do NOT - manual validation required.

## 2. Owner Check Audit

For each `AccountInfo` or `UncheckedAccount` usage:

| Account | Owner Validated? | Validation Location | Correct Owner? | Missing? |
|---------|-----------------|---------------------|---------------|----------|
| {name} | YES/NO | {line} | {expected vs actual} | FLAG if NO |

**Critical pattern**: Any `AccountInfo` deserialized without prior owner check → arbitrary data injection.
**Anchor pattern**: `#[account(owner = expected_program)]` or manual `require!(account.owner == &expected_id)`.

## 3. Discriminator Check

For all accounts deserialized from raw data:

| Account | Uses Account<T>? | Discriminator Checked? | Can Substitute Different Account Type? |
|---------|------------------|----------------------|---------------------------------------|
| {name} | YES/NO | YES/NO (Anchor auto) | {if NO: what types could be substituted} |

**Attack**: Pass an account of Type B where Type A is expected - different data layout, fields interpreted incorrectly.
**Safe**: Anchor's `Account<T>` checks the 8-byte discriminator. Manual programs must check explicitly.

## 4. Data Matching (Cross-Account References)

For each cross-account reference (has_one, constraint, seeds):

| Instruction | Account A | Account B | Relationship | Validated? | Bypass? |
|-------------|-----------|-----------|-------------|-----------|---------|
| {ix} | {a} | {b} | {a.field == b.key()} | YES/NO | {if NO: how to exploit} |

**Pattern**: Ensure that when Account A references Account B (e.g., `vault.mint == mint.key()`), the relationship is enforced on-chain.
**Attack**: Substitute a different mint account that the vault doesn't actually belong to.

## 5. Remaining Accounts Audit

For each use of `ctx.remaining_accounts`:

| Instruction | Remaining Account Usage | Owner Validated? | Type Validated? | Signer Checked? | Data Validated? |
|-------------|------------------------|-----------------|----------------|-----------------|-----------------|
| {ix} | {purpose} | YES/NO | YES/NO | YES/NO | YES/NO |

**Critical**: `remaining_accounts` bypass Anchor's automatic validation. Every field must be checked manually.
**Attack**: Inject attacker-controlled accounts via remaining_accounts to redirect funds or corrupt state.

## 6. Duplicate Account Detection

For each instruction with 2+ mutable accounts:

| Instruction | Mutable Account A | Mutable Account B | Key Uniqueness Enforced? | Self-Transfer Risk? |
|-------------|-------------------|-------------------|------------------------|-------------------|
| {ix} | {a} | {b} | YES/NO | {if NO: impact of a==b} |

**Attack (S7)**: Pass the same account as both `from` and `to` in a transfer → potential balance inflation.
**Defense**: `require!(account_a.key() != account_b.key())` or Anchor `constraint`.

## 7. Sysvar Validation

For each sysvar account passed as input:

| Sysvar | Passed As | Address Validated? | Could Be Spoofed? |
|--------|-----------|-------------------|-------------------|
| Clock | AccountInfo | YES/NO | {if NO: attacker controls time} |
| Rent | AccountInfo | YES/NO | {if NO: attacker controls rent} |
| Instructions | AccountInfo | YES/NO | {if NO: Wormhole-style attack} |

**Safe pattern**: Use `Sysvar::from_account_info()` or `_checked` variants.
**Unsafe pattern**: Raw deserialization of sysvar data from unchecked AccountInfo.

## 8. Trust Chain Analysis

For each account validation chain, trace to its root:

| Account | Validated Against | Root Trust Anchor | Chain Complete? |
|---------|------------------|-------------------|----------------|
| {account} | {what validates it} | PDA / Program ID / Hardcoded pubkey / NONE | YES/NO |

**Pattern**: Validation chain must root in a known-good value. If chain roots in user input → FINDING.
**Example**: `authority` validated against `vault.authority`, `vault` validated against PDA seeds → chain roots in PDA (good).

## Finding Template

```markdown
**ID**: [AV-N]
**Severity**: [based on what attacker can do with invalid account]
**Step Execution**: ✓1,2,3,4,5,6,7,8 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [S1:✓, S6:✓/✗, S7:✓/✗, S8:✓/✗, R4:✓/✗]
**Location**: program/src/instructions/{file}.rs:LineN
**Title**: Missing [validation type] for [account] in [instruction] enables [attack]
**Description**: [Specific missing validation with code reference]
**Impact**: [What attacker can achieve: fund theft, state corruption, DoS]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Skill: `account-validation`
Date collected: 2026-04-19
Local CSV baseline: 4 hits (rows 5122, 6252, 1064, 6922)

---

## Finding 1: Cashio Infinite Mint — Missing Cross-Account Mint Validation

- Pattern: account_validation, owner_check
- Where it hit: Cashio (CASH stablecoin), Solana mainnet, March 2022
- Severity: CRITICAL
- Source: https://www.halborn.com/blog/post/explained-the-cashio-hack-march-2022
- Summary: The `crate_collateral_tokens` instruction validated that a token type matched `saber_swap.arrow`, but never validated the `mint` field *inside* `saber_swap.arrow`. An attacker supplied a fake `saber_swap.arrow` account with a fabricated mint, which in turn allowed creation of a fake `crate_collateral_tokens` account. The program accepted worthless collateral and the attacker minted 2 billion CASH tokens, draining $52.8M. The root cause is a broken trust chain: account A was validated against account B, but account B itself was never owner- or data-validated.
- Map to: account_validation, owner_check

---

## Finding 2: Wormhole — Fake Sysvar Instructions Account (Unchecked AccountInfo)

- Pattern: account_validation, owner_check
- Where it hit: Wormhole bridge, Solana mainnet, February 2022
- Severity: CRITICAL
- Source: https://www.halborn.com/blog/post/explained-the-wormhole-hack-february-2022
- Summary: The `verify_signatures` function accepted the Solana `Instructions` sysvar as a raw `AccountInfo` and never asserted that the provided account was actually the canonical sysvar address. The deprecated `load_instruction_at` helper was used instead of `load_instruction_at_checked`. An attacker crafted a fake account populated with data mimicking the Instructions sysvar, bypassed guardian-set signature verification, and minted 120,000 wETH ($326M) without backing collateral.
- Map to: account_validation, owner_check

---

## Finding 3: Lido on Solana v2 — Account Type Confusion via Non-Leading Type Field (Discriminator)

- Pattern: discriminator, account_validation
- Where it hit: Lido on Solana v2, Neodyme audit, October 2022
- Severity: MEDIUM
- Source: https://neodyme.io/reports/Lido-2.pdf
- Summary: Lido's native (non-Anchor) deserialization used `try_from_slice_unchecked` and placed the account-type discriminator at byte offset 6 in list accounts and offset 2 in the main Lido struct rather than as the first byte. This layout allowed an attacker controlling a fake Lido manager instance to pass a list-type account where the main struct was expected (and vice versa), enabling arbitrary addition or removal of validators and maintainers. The fix reorders the `accountType` field to byte 0 in all account types.
- Map to: discriminator, account_validation

---

## Finding 4: Drift Protocol — Missing Oracle Account Owner Check

- Pattern: owner_check, account_validation
- Where it hit: Drift Protocol, Neodyme audit (report published; exploit unrelated — see note)
- Severity: HIGH (audit finding)
- Source: https://cdn.prod.website-files.com/6310e7dee49f0866da8eed4c/6686bbdfe7c6e5a997cc51bc_Neodyme%20-%20Drift%20Security%20Audit.pdf
- Summary: Neodyme's audit of Drift Protocol identified that admin instructions accepted oracle `AccountInfo` references without verifying the account owner. Both the account being read and an arbitrary oracle account that could be written to the market lacked an owner check. The recommended fix was to add `require!(oracle_account.owner == expected_oracle_program)` before reading price data from the account. Without this check an admin-level caller (or a compromised admin key) could inject a spoofed oracle.
- Map to: owner_check, account_validation

---

## Finding 5: Orderly Network Solana Vault — Missing Deposit Token Mint Validation

- Pattern: account_validation, has_one, constraint
- Where it hit: Orderly Network Solana contract, Sherlock audit, September 2024
- Severity: HIGH
- Source: https://github.com/sherlock-audit/2024-09-orderly-network-solana-contract-judging/issues/37
- Summary: The `solana_vault::deposit` instruction (Anchor) did not include a constraint linking `deposit_token.mint` to `allowed_token.mint_account`. An attacker passed a worthless dummy SPL mint as `deposit_token` while supplying the legitimate `allowed_token` USDC record, successfully transferring dummy tokens into the vault and triggering a USDC deposit message to the Orderly chain. The attacker could then withdraw real USDC. The fix is a `constraint = deposit_token.mint == allowed_token.mint_account` in the `Deposit` struct.
- Map to: has_one, constraint, account_validation

---

## Finding 6: Orderly Network — Missing Access Control on `oapp_lz_receive::apply` (UncheckedAccount CPI Entry)

- Pattern: account_validation, owner_check
- Where it hit: Orderly Network Solana contract, Sherlock audit, September 2024
- Severity: HIGH
- Source: https://github.com/sherlock-audit/2024-09-orderly-network-solana-contract-judging/issues/142
- Summary: The `oapp_lz_receive::apply` instruction is the LayerZero entry point into the Orderly Solana programs. No constraint or signer check validated that the caller was the expected LayerZero endpoint program. Any external account could invoke the instruction, causing arbitrary cross-chain messages to be parsed and executed, including unauthorized withdrawals.
- Map to: account_validation, owner_check

---

## Finding 7: Neodyme Security Workshop Level 3 — Account Confusion (Discriminator Bypass in Native Program)

- Pattern: discriminator, account_validation
- Where it hit: Neodyme public security workshop (canonical reproduce of real exploit class), documented 2022
- Severity: HIGH (exercise replicates real $50M+ bug class)
- Source: https://workshop.neodyme.io/level3-solution.html
- Summary: In a native Solana program (no Anchor), the program deserializes accounts with `try_from_slice_unchecked` and does not verify a discriminator before reading fields. An attacker passes an account of type B in place of type A; because the struct layouts overlap in the first N bytes, the program reads attacker-controlled values as legitimate fields. This pattern underlies the Cashio exploit and is catalogued by Neodyme as the dominant $50M+ bug class on Solana. The fix is always reading a typed discriminator first, which `Account<T>` in Anchor handles automatically.
- Map to: discriminator, account_validation

---

## Finding 8: Authorize-Invoke Source Account Not Validated (CSV row 6922)

- Pattern: account_validation, owner_check
- Where it hit: Unnamed wallet/session program, local CSV row 6922, MEDIUM
- Severity: MEDIUM
- Source: local CSV row 6922 (solodit_findings.dedup.csv); no external URL available
- Summary: The `authorize_invoke` instruction accepted any signer-flagged account as the source for transfer instructions. The intended invariant was that withdrawals must originate from `wallet_authority`, but the missing source-account check allowed callers to redirect transfers from `session_authority` instead, enabling fund misuse. Fixed by adding an explicit `require!(source.key() == wallet_authority.key())` check.
- Map to: account_validation, has_one

---

## Finding 9: Bank Account Not Validated Against Whitelisted Tokens (CSV row 5122)

- Pattern: account_validation, has_one
- Where it hit: Unnamed lending/yield program, local CSV row 5122, HIGH
- Severity: HIGH
- Source: local CSV row 5122 (solodit_findings.dedup.csv); no external URL available
- Summary: The `deposit`, `withdraw`, and `collectRewards` instructions accepted a `bank` account without verifying it was in `common_state.whitelisted_tokens`. Any caller could substitute an unintended bank account, bypassing token whitelist controls and collecting rewards or deposits into arbitrary vaults. Fixed by adding a `has_one` or `constraint` check against the whitelisted token list.
- Map to: account_validation, has_one


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Account Type Inventory | YES | ✓/✗/? | For every instruction |
| 2. Owner Check Audit | YES | ✓/✗/? | For every AccountInfo/UncheckedAccount |
| 3. Discriminator Check | YES | ✓/✗/? | For all deserialized accounts |
| 4. Data Matching | YES | ✓/✗/? | For all cross-account references |
| 5. Remaining Accounts Audit | IF remaining_accounts used | ✓/✗(N/A)/? | Manual validation check |
| 6. Duplicate Account Detection | YES | ✓/✗/? | For all mutable account pairs |
| 7. Sysvar Validation | IF sysvars passed as AccountInfo | ✓/✗(N/A)/? | Address validation |
| 8. Trust Chain Analysis | YES | ✓/✗/? | Chain to root trust anchor |
