---
name: "cpi-security"
description: "Trigger Pattern CPI flag detected (invoke/invoke_signed/CpiContext usage) - Inject Into Breadth agents, depth agents"
---

# CPI_SECURITY Skill

> **Trigger Pattern**: CPI flag detected (invoke/invoke_signed/CpiContext usage)
> **Inject Into**: Breadth agents, depth agents
> **Finding prefix**: `[CPI-N]`
> **Rules referenced**: S3, S5, R1, R4

For every Cross-Program Invocation (CPI) in the Solana program:

## 1. CPI Target Inventory

Enumerate ALL CPI calls:

| # | Location | CPI Type | Target Program | Target Instruction | Accounts Forwarded | Signers Forwarded |
|---|----------|----------|----------------|-------------------|--------------------|-------------------|
| 1 | {file:line} | invoke/invoke_signed/CpiContext | {program_id} | {instruction} | {list} | {list} |

## 2. Target Program Validation

For each CPI call, verify the target program ID:

| CPI | Program ID Source | Hardcoded/Validated? | Spoofable? |
|-----|------------------|---------------------|-----------|
| {cpi} | {where program_id comes from} | Hardcoded constant / Validated against known / FROM USER INPUT | {if from input: CRITICAL finding} |

**Attack (S3)**: If program ID comes from user input without validation, attacker substitutes a malicious program that mimics the expected interface but steals funds.
**Defense**: Always validate program ID against a hardcoded constant or well-known program address.

## 3. Signer Privilege Tracing

For each CPI that forwards signers:

| CPI | Signer Source | Privilege Level | Should Forward? | Over-Privileged? |
|-----|--------------|----------------|-----------------|------------------|
| {cpi} | {PDA / user wallet / authority} | {what the signer can do in target} | YES/NO | {if forwarding more privilege than needed} |

**Attack**: Forwarding user's wallet as signer to a CPI target that uses it for unintended operations.
**Pattern**: PDA signers via `invoke_signed` are safe (program-controlled). User wallet forwarding needs careful scoping.

## 4. Account Reload Audit (S5 - CRITICAL)

For each CPI call, check what accounts are read AFTER the CPI returns:

| CPI | Accounts Modified by Target | Read After CPI? | reload() Called? | Owner Re-checked? |
|-----|---------------------------|----------------|-----------------|-------------------|
| {cpi} | {list accounts CPI can modify} | YES/NO | YES/NO | YES/NO |

**Attack (S5)**: CPI target modifies account data. Caller reads stale cached data without `reload()`.
**CRITICAL**: Anchor's `reload()` refreshes data but does NOT re-verify the account owner. A CPI target could `assign` the account to a different program. After `reload()`, the data is fresh but the owner may have changed.
**Full defense**: After CPI, both `reload()` AND re-check `account.owner`.

## 5. Lamport Balance Conservation

For each CPI that transfers SOL:

| CPI | Expected Lamport Change | Actual Change Verified? | Drain Risk? |
|-----|------------------------|------------------------|------------|
| {cpi} | {expected delta} | YES/NO | {if NO: CPI could drain more than expected} |

**Attack**: CPI target drains more lamports than expected from accounts owned by the caller's program.
**Defense**: Check lamport balances before and after CPI; verify delta matches expected amount.

## 6. Account Owner Check Post-CPI

For each CPI that could modify account ownership:

| CPI | Can Target Call system_program::assign? | Owner Checked After CPI? | Risk |
|-----|----------------------------------------|------------------------|------|
| {cpi} | YES/NO | YES/NO | {if YES and NO: account hijacking} |

**Attack**: CPI target uses `system_program::assign` to change account owner to attacker-controlled program. Caller continues using the account assuming it's still owned by its program.

## 7. CPI Depth Analysis

For each code path with nested CPIs:

| Entry Point | CPI Chain | Max Depth | CU Cost Estimate | Risk |
|-------------|-----------|-----------|-----------------|------|
| {instruction} | {A → B → C} | {depth} | {estimate} | {CU exhaustion?} |

**Solana limit**: CPI depth capped at 4 levels. Check if deep chains approach this limit.

## Finding Template

```markdown
**ID**: [CPI-N]
**Severity**: [based on impact: fund theft via program spoofing = Critical, stale data = High]
**Step Execution**: ✓1,2,3,4,5,6,7 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [S3:✓, S5:✓, R1:✓, R4:✓/✗]
**Location**: program/src/{file}.rs:LineN
**Title**: [CPI issue type] in [instruction] enables [attack]
**Description**: [Specific CPI vulnerability with call chain trace]
**Impact**: [Fund theft / state corruption / privilege escalation]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Sourced from `candidates.jsonl` (19 rows). 8 examples selected across 5 distinct vulnerability classes.

---

## Category: `signer_seeds` — Signer Seeds Mismatch / Missing Bump

### Example 1 (row 4401) — HIGH
*Pattern tag*: `signer_seeds`

**Summary**: The `rebate_info` and `rebate_manager` functions cannot sign their CPI call because the `seeds` helper omits the bump byte. `invoke_signed` requires the full seed set including the canonical bump; without it, the derived PDA does not match the account address and the runtime rejects the signature. Result: `claim_rebate_fee` and `withdraw` are permanently uncallable, locking tokens in the contract.

**Key detail**: The `seeds` function returned `[prefix, key]` instead of `[prefix, key, bump]`. Every `invoke_signed` call that uses a PDA signer must pass the bump that was stored at account initialization.

**Fix reference**: WOOFi_Solana PR #32.

---

### Example 2 (row 13575) — HIGH
*Pattern tag*: `invoke_signed`

**Summary**: `mayan_invoke` is a single function that always calls `sol_invoke_signed`, meaning it forwards PDA authority on every CPI regardless of whether the callee actually needs it. An attacker calls `mayan_flash_swap_start` then `mayan_flash_swap_finish` to route a token transfer through the same account as both source and destination, receiving tokens for free because the PDA's signature authority is applied unconditionally.

**Key detail**: `invoke` vs `invoke_signed` is a privilege decision. Using `invoke_signed` when `invoke` suffices over-delegates PDA authority to the callee, enabling replay-style attacks on flash paths.

**Fix reference**: Patch efae9ee — split into two separate functions, one with seeds and one without.

---

## Category: `program_id_check` — Program ID Not Pinned / Wrong Authority

### Example 3 (row 1307) — HIGH
*Pattern tag*: `program_id_check`

**Summary**: In `early_purchase::redeem_receipt::handler()`, the `token::transfer` CPI is constructed with the *buyer* as the transfer authority rather than the sale PDA. The program does not validate which account is acting as authority before issuing the CPI, so any caller who controls a buyer account can authorize transfers they should not be able to authorize.

**Key detail**: CPI authority fields must be checked against a program-controlled PDA or a verified signer, not a caller-supplied account. Using an unvalidated user account as the CPI authority is equivalent to not having an authority check at all.

**Fix reference**: Commit c3a83a5.

---

### Example 4 (row 15279) — HIGH
*Pattern tag*: `program_id_check`

**Summary**: An attacker can manipulate settings and invoke a function that the program assumes is reached only through a trusted path. The report recommends using a `ControlAuthority` PDA to verify that inbound calls arrived via CPI from a known program rather than from an arbitrary external caller. Without a program-ID check on the CPI source, the function's access control is bypassable.

**Key detail**: When a function must only be callable via CPI from a specific program, the callee must verify `ctx.accounts.some_authority` derives from that program's known address, or check the invoking program ID explicitly.

---

## Category: `cpi_accounts` — CPI Account Reordering / Wrong Accounts Passed

### Example 5 (row 4255) — MEDIUM
*Pattern tag*: `cpi_accounts`

**Summary**: The `AddMarketEmission` instruction reallocates `MarketTwo` but passes the wrong set of CPI accounts to the reallocation call. The size calculation inside the CPI relies on the account list it receives; passing mismatched accounts causes the computed size to be incorrect, leaving insufficient space for new data and corrupting subsequent writes.

**Key detail**: CPI account slices must exactly match what the callee's instruction handler expects in order and identity. Passing a structurally similar but distinct account set produces silent size or state errors.

**Fix reference**: PR #529.

---

### Example 6 (row 4884) — MEDIUM
*Pattern tag*: `cpi_accounts`

**Summary**: In `bond::process_redeem_bond`, the CPI to `NftIssuanceVault::close_user_token_account` omits the specific token account to close from the account list. The callee cannot determine which account to act on, so the close either no-ops or acts on an unintended account. Additionally, the balance check reads the wrong account (payment token account instead of bond token account), so the guard condition is never effective.

**Key detail**: Every account the CPI callee needs to identify and mutate must be explicitly included in the `AccountMeta` list. Omitting an account causes the callee to receive a different account at that position or panic.

**Fix reference**: Patch #104.

---

### Example 7 (row 4847) — MEDIUM
*Pattern tag*: `cpi_accounts`

**Summary**: The `vaultkausdc` program marks `token_program` and `usdc_mint` as mutable in the `AccountsMeta` passed to a CPI, but those accounts are read-only. The Solana runtime rejects CPIs where the caller elevates an account's mutability beyond its original declaration, producing an `InvalidArgument` error and making those instructions permanently uncallable.

**Key detail**: Each account's `is_writable` flag in an `AccountMeta` must match the flag under which the account was originally passed to the outer transaction. Erroneously setting `is_writable = true` on a read-only account causes a runtime CPI error.

---

## Category: `inner_instruction` — Inner-Instruction Introspection Bypass

### Example 8 (row 6699) — HIGH
*Pattern tag*: `inner_instruction`

**Summary**: `swap_introspection_checks` is intended to enforce that `PreSwap` and `PostSwap` appear together in a single transaction. An attacker crafts a transaction with specific instruction ordering that satisfies the introspection check without actually pairing the two operations, allowing unilateral fund withdrawal. The fix is to verify that the instruction was reached through CPI (not called directly) so the pair-enforcement logic cannot be bypassed via direct invocation.

**Key detail**: Instruction sysvar introspection can be bypassed if the program does not also confirm whether it is being called directly vs. via CPI. Checking `is_called_via_cpi()` (using the instructions sysvar and call depth) closes the bypass.

**Fix reference**: Version 978d1d3.

---

### Example 9 (row 8966) — HIGH
*Pattern tag*: `inner_instruction`

**Summary**: The `deposit` and `set_service` instructions use the instructions sysvar for introspection but do not validate that the sysvar account provided is the canonical `SysvarInstructions1111...` address. An attacker substitutes a crafted account, feeding the introspection check with controlled data and injecting unauthorized instructions into CPI calls. The fix adds explicit key checks for the sysvar account in both `validate_remaining_accounts` and `solana_ibc::cpi::set_stake`.

**Key detail**: The instructions sysvar must be validated by address (`solana_program::sysvar::instructions::ID`) before reading from it. Accepting any account at the sysvar position lets an attacker supply forged instruction data.

**Fix reference**: Patch b221448.


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. CPI Target Inventory | YES | ✓/✗/? | For every CPI |
| 2. Target Program Validation | YES | ✓/✗/? | For every CPI |
| 3. Signer Privilege Tracing | YES | ✓/✗/? | For every CPI with signers |
| 4. Account Reload Audit | YES | ✓/✗/? | **CRITICAL** - most common CPI bug |
| 5. Lamport Balance Conservation | IF SOL transfers | ✓/✗(N/A)/? | |
| 6. Account Owner Check Post-CPI | YES | ✓/✗/? | assign attack prevention |
| 7. CPI Depth Analysis | IF nested CPIs | ✓/✗(N/A)/? | CU exhaustion risk |
