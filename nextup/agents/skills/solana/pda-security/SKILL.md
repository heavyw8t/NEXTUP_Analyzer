---
name: "pda-security"
description: "Trigger Pattern PDA flag detected (seeds/bump/find_program_address usage) - Inject Into Breadth agents, depth agents"
---

# PDA_SECURITY Skill

> **Trigger Pattern**: PDA flag detected (seeds/bump/find_program_address usage)
> **Inject Into**: Breadth agents, depth agents
> **Finding prefix**: `[PDA-N]`
> **Rules referenced**: S2, S1

For every PDA in the Solana program:

## 1. PDA Seed Inventory

List all PDA seed declarations:

| # | PDA Name | Seeds | Purpose | Anchor Constraint | Location |
|---|----------|-------|---------|------------------|----------|
| 1 | {name} | `[b"prefix", user.key().as_ref(), &[bump]]` | {what it stores} | `seeds = [...], bump` | {file:line} |

## 2. Canonical Bump Enforcement

For each PDA:

| PDA | Bump Source | Canonical? | Risk if Non-Canonical |
|-----|-----------|-----------|---------------------|
| {name} | Anchor auto (`bump`) / `find_program_address` / USER INPUT | YES/NO | {if NO: multiple valid addresses} |

**Attack (S2)**: If bump is user-supplied, attacker can use a non-canonical bump to derive a DIFFERENT address that still passes `create_program_address`. This creates a separate PDA from the intended one.
**Defense**: Always use `find_program_address` (returns canonical bump) or Anchor's `bump` constraint.

## 3. Seed Collision Analysis

For each PAIR of PDA seed schemas:

| PDA A Seeds | PDA B Seeds | Can Byte Sequences Overlap? | Collision Risk? |
|-------------|-------------|---------------------------|----------------|
| `[b"vault", mint.as_ref()]` | `[b"vaultm", ...]` | CHECK: "vault" + mint_bytes could equal "vaultm" + other_bytes? | YES/NO |

**Attack**: Two different PDA types with seeds that can produce identical byte sequences → one PDA masquerades as another.
**Defense**: Use unique fixed-length prefixes (e.g., `b"vault\x00"`) or ensure seed structures cannot collide.

## 4. Seed Uniqueness

For each PDA type, verify seeds include sufficient uniqueness:

| PDA | Unique Per | Seeds Include User/Entity Key? | Could Two Users Share PDA? |
|-----|-----------|-------------------------------|--------------------------|
| {name} | User / Mint / Pool / Global | YES/NO | {if YES: shared state corruption} |

**Pattern**: User-specific PDAs MUST include the user's pubkey in seeds. Omitting it means all users share the same PDA.

## 5. PDA Isolation

For each PDA used as an authority or signer:

| PDA | Signs For | Isolated to Scope? | Can Different Instruction Misuse? |
|-----|-----------|-------------------|----------------------------------|
| {name} | {what operations} | YES/NO | {if NO: cross-instruction authority sharing} |

**Attack**: A PDA authority used across multiple instructions where one instruction has weaker validation → attacker uses the weak path.

## 6. PDA Sharing Detection

Check if multiple account types share the same PDA seed schema:

| Seed Schema | Account Types Using It | Type Confusion Risk? |
|-------------|----------------------|---------------------|
| `[b"data", key.as_ref()]` | {list all account types} | {if >1: type confusion possible} |

## 7. Initialization Front-Running

For each PDA created with `init`:

| PDA | Created By | Front-Runnable? | Impact if Front-Run |
|-----|-----------|----------------|---------------------|
| {name} | {instruction} | YES/NO | {attacker initializes with malicious data} |

**Attack (S2)**: Attacker front-runs PDA initialization, creating the account with attacker-controlled data before the legitimate initialization transaction.
**Defense**: `init` (not `init_if_needed`) + seeds that include the authorized initializer's pubkey.
**Warning**: `init_if_needed` is explicitly dangerous - it silently succeeds if account already exists with potentially malicious data.

## Finding Template

```markdown
**ID**: [PDA-N]
**Severity**: [based on impact: seed collision = Critical, non-canonical bump = High]
**Step Execution**: ✓1,2,3,4,5,6,7 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [S2:✓, S1:✓]
**Location**: program/src/{file}.rs:LineN
**Title**: [PDA issue type] in [context] enables [attack]
**Description**: [Specific PDA vulnerability with seed analysis]
**Impact**: [Fund theft via PDA confusion / state corruption / front-running]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> Source: candidates.jsonl (17 rows). Selected: 10 findings.
> Tags: `PDA, find_program_address, seeds, bump, canonical_bump, seed_collision`
> Coverage: seed collision, non-canonical bump, seeds lack user input, PDA front-run init, missing bump_seed check, has_one vs seeds, PDA isolation

---

## Example 1 — Missing Seed Validation Lets Attacker Substitute Arbitrary Account

**Severity**: HIGH
**Row**: 920
**Distilled Pattern**: `vault_gkhan_account` accepted any SPL token account whose `owner` field matched a specific PDA without verifying the account was derived from the expected seeds via the ATA program. An attacker could craft a token account with the right owner field set and pass it as the legitimate vault PDA, then drain the real vault balance.
**PDA Concept**: missing bump_seed / seed derivation check
**Key Terms**: `seeds`, `bump`, `find_program_address`, ATA derivation

---

## Example 2 — Cross-Authority PDA Write via Unvalidated Account Argument

**Severity**: HIGH
**Row**: 1066
**Distilled Pattern**: `AppendDataSandwichValidatorsBitmap` accepted the `sandwich_validators` PDA account as a passed argument rather than deriving it inside the context. Authority A could supply Authority B's PDA address, writing data into B's state. The fix is to derive the PDA inside the Anchor account constraint using `seeds` and `bump` so only the signer's own PDA can be targeted.
**PDA Concept**: seeds include user input without sanitization; missing seeds constraint
**Key Terms**: `seeds`, `bump`, `find_program_address`, PDA derivation inside context

---

## Example 3 — Unvalidated token_pool_pda Enables Token Theft

**Severity**: HIGH
**Row**: 5322
**Distilled Pattern**: `MintToInstruction` and `TransferInstruction` marked `token_pool_pda` as mutable but applied no seed or bump validation. An attacker supplies their own token account in place of the legitimate pool PDA, routes compress/decompress flows through it, and steals tokens from the real pool on decompression.
**PDA Concept**: missing bump_seed check; no seed validation
**Key Terms**: `seeds`, `bump`, `find_program_address`, `canonical_bump`, seed validation

---

## Example 4 — PDA Front-Running via create_account Blocks Legitimate Initialization

**Severity**: MEDIUM
**Row**: 89
**Distilled Pattern**: The program used `create_account` to initialize PDAs. An attacker can pre-fund the PDA address with a small SOL amount before the legitimate transaction, causing `create_account` to fail (account already exists). The correct mitigation avoids `create_account` for PDAs; instead fund, allocate, and assign separately, or use Anchor `init` with seeds so the PDA is owned by the program from the start.
**PDA Concept**: PDA pre-created by attacker (front-run init)
**Key Terms**: `find_program_address`, `seeds`, `bump`, PDA initialization front-run

---

## Example 5 — Unguarded GlobalConfig PDA Allows Anyone to Initialize OffRampState

**Severity**: MEDIUM
**Row**: 681
**Distilled Pattern**: The `initialize` instruction created a new `OffRampState` for any signer. The global `OffRampCounter` PDA had no `authorized_initializer` constraint, so an attacker could deploy a counterfeit off-ramp state under the same program ID and present it as official. The fix adds a `GlobalConfig` PDA seeded with an allowlist of authorized admins, enforced via `has_one` or `seeds` constraint.
**PDA Concept**: PDA front-run init; has_one vs seeds
**Key Terms**: `seeds`, `bump`, `find_program_address`, `has_one`, authorized initializer

---

## Example 6 — Sale PDA Seeds Omit Creator Key, Enabling Spam and ID Exhaustion

**Severity**: MEDIUM
**Row**: 1296
**Distilled Pattern**: `initialize_sale` imposed no fee or permission check and omitted the creator's pubkey from the Sale PDA seeds. Any user could create sales without cost, exhaust global IDs, and create sales with malicious properties. Adding the creator's key to the seed set scopes each PDA to its creator and prevents ID collision across users.
**PDA Concept**: seeds include user input without sanitization; seed uniqueness failure
**Key Terms**: `seeds`, `bump`, `find_program_address`, seed uniqueness, user pubkey in seeds

---

## Example 7 — transfer_authority PDA Derived Without refund_token Field

**Severity**: MEDIUM
**Row**: 6361
**Distilled Pattern**: `prepare_market_order` computed the `transfer_authority` PDA hash without including the `refund_token` field. An attacker sets an arbitrary address as `refund_token`. Subsequent transactions referencing the `prepared_order` fail because messages were already produced against a different PDA; the only recovery path is `close_prepare_order`, which transfers funds to the attacker's `refund_token`. The fix includes `refund_token` in the seed calculation.
**PDA Concept**: seeds do not cover all relevant fields; seed collision / incomplete binding
**Key Terms**: `seeds`, `find_program_address`, seed_collision, incomplete seed binding

---

## Example 8 — User-Supplied Bump Accepted Instead of Canonical Bump

**Severity**: MEDIUM
**Row**: 11011
**Distilled Pattern**: Several functions (`withdraw_v2`, `deposit`, `SyncSpace`) accepted a bump value from user input and passed it directly to `create_program_address`. A non-canonical bump produces a different but valid program address, so the attacker can derive a distinct PDA that passes the check while pointing to attacker-controlled state. All call sites must use the canonical bump stored at account creation or derive it via `find_program_address`.
**PDA Concept**: non-canonical bump; user-supplied bump accepted
**Key Terms**: `bump`, `canonical_bump`, `find_program_address`, `create_program_address`, non-canonical bump

---

## Example 9 — Authority Check Uses Account Owner Field Instead of PDA

**Severity**: MEDIUM
**Row**: 3857
**Distilled Pattern**: `finalize_locked_stake` and `finalize_lock_campaign` verified the caller's account `owner` field equals `sablier_sdk::ID`. An attacker creates a new account and transfers ownership to `sablier_sdk::ID`, spoofing the Sablier worker program identity. The fix replaces the owner check with a PDA derived from `sablier_sdk::ID` seeds so only the true program can produce the signer.
**PDA Concept**: PDA isolation; authority should be PDA, not owner-field check
**Key Terms**: `seeds`, `bump`, `find_program_address`, PDA as authority, PDA isolation

---

## Example 10 — Vault Accounts Not Using PDA Authority, Allowing Malicious Admin Override

**Severity**: MEDIUM
**Row**: 10286
**Distilled Pattern**: `create_market` did not verify that `market_base_vault` and `market_quote_vault` used a PDA as their Solana token account authority, nor that `close_market_admin` was set as an authority on those vaults. A malicious actor who controls the vaults' authority field can drain them. The fix enforces PDA-derived vault authorities so only the program can sign for vault transfers.
**PDA Concept**: PDA isolation; vault authority must be program-controlled PDA
**Key Terms**: `seeds`, `bump`, `find_program_address`, PDA as vault authority, PDA isolation


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. PDA Seed Inventory | YES | ✓/✗/? | For every PDA |
| 2. Canonical Bump Enforcement | YES | ✓/✗/? | For every PDA |
| 3. Seed Collision Analysis | YES | ✓/✗/? | For every PDA pair |
| 4. Seed Uniqueness | YES | ✓/✗/? | User-specific PDAs |
| 5. PDA Isolation | IF PDA used as authority | ✓/✗(N/A)/? | Cross-instruction misuse |
| 6. PDA Sharing Detection | YES | ✓/✗/? | Type confusion |
| 7. Initialization Front-Running | IF init used | ✓/✗(N/A)/? | init_if_needed is dangerous |
