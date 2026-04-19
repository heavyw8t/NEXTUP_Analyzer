---
name: "instruction-introspection"
description: "Trigger Pattern INSTRUCTION_INTROSPECTION flag detected (load_instruction_at/Sysvar1nstructions) - Inject Into Breadth agents, depth agents"
---

# INSTRUCTION_INTROSPECTION Skill

> **Trigger Pattern**: INSTRUCTION_INTROSPECTION flag detected (load_instruction_at/Sysvar1nstructions)
> **Inject Into**: Breadth agents, depth agents
> **Finding prefix**: `[II-N]`
> **Rules referenced**: S10, S8, R15

For every use of instruction introspection in the Solana program:

## 1. Introspection Usage Inventory

List all instruction introspection usage:

| # | Location | Function Used | Purpose | Instructions Sysvar Source |
|---|----------|--------------|---------|---------------------------|
| 1 | {file:line} | `load_instruction_at_checked` / `load_instruction_at` / `get_instruction_relative` | {what it checks} | {account source} |

## 2. Sysvar Address Validation (Wormhole Pattern - CRITICAL)

For each Instructions sysvar account:

| Usage | Sysvar Source | Address Validated? | Validation Method |
|-------|-------------|-------------------|-------------------|
| {usage} | {account param name} | YES/NO | {hardcoded check / Anchor constraint / NONE} |

**Attack pattern (sysvar address spoofing)**: If Instructions sysvar address is NOT validated, attacker passes a fake account containing crafted "instruction" data. The introspection reads attacker-controlled data instead of real transaction instructions.
**Defense**: `require!(sysvar_account.key() == sysvar::instructions::ID)` or use Anchor `#[account(address = sysvar::instructions::ID)]`.

## 3. Checked Function Usage

For each `load_instruction_at*` call:

| Call | Uses `_checked` Variant? | Risk if Unchecked |
|------|------------------------|-------------------|
| {call} | YES/NO | {if NO: deprecated function, potential ABI issues} |

**Rule**: Always use `load_instruction_at_checked` (validates the sysvar account) over the deprecated `load_instruction_at` (does not validate).

## 4. Instruction Sequence Validation

For flash loan and atomic operation patterns:

| Pattern | Borrow Instruction Checked? | Repay Instruction Checked? | Gap Between Checks? |
|---------|---------------------------|---------------------------|---------------------|
| Flash loan repay check | YES/NO | YES/NO | {can attacker insert instructions between borrow and repay?} |

**Attack (marginfi pattern)**: Protocol checks that a repay instruction exists in the transaction but doesn't verify that no state-modifying instructions execute BETWEEN the borrow and repay. Attacker inserts exploit instructions in the gap.
**Defense**: Verify the COMPLETE instruction sequence, not just the presence of specific instructions.

## 5. State Change Coverage

For each introspection-based check:

| Check | State Changes Between Checked Instructions | All Changes Accounted? | Gap? |
|-------|------------------------------------------|----------------------|------|
| {check} | {list possible state changes} | YES/NO | {if NO: what's unaccounted} |

**Pattern**: Introspection checks often verify instruction A and instruction B exist, but ignore what happens in between. Any state changes between A and B can be exploited.

## 6. Program ID Verification

For each instruction inspected via introspection:

| Inspected Instruction | Program ID Checked? | Expected Program | Spoofable? |
|----------------------|---------------------|-----------------|-----------|
| {instruction} | YES/NO | {expected} | {if NO: attacker deploys mimicking program} |

**Attack**: Introspection check verifies an instruction with matching function signature exists, but doesn't verify it belongs to the expected program. Attacker deploys a program with the same instruction signature that does nothing.

## Finding Template

```markdown
**ID**: [II-N]
**Severity**: [sysvar spoofing = Critical, sequence gap = High, missing program check = Medium]
**Step Execution**: ✓1,2,3,4,5,6 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [S10:✓, S8:✓/✗, R15:✓/✗]
**Location**: program/src/{file}.rs:LineN
**Title**: [Introspection issue] in [instruction] enables [attack]
**Description**: [Specific introspection vulnerability with sequence analysis]
**Impact**: [Flash loan bypass / fake instruction acceptance / state manipulation]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

# solana/instruction-introspection
# Generated: 2026-04-19
# Sources: Halborn, CertiK, Ackee, Kudelski, Asymmetric Research, ChainSecurity, Trail of Bits (Crytic), Cantina

---

## [II-W1] CRITICAL – Sysvar Account Not Validated Allows Fake Instructions Sysvar (Wormhole, Feb 2022, $326M)

***Protocol***: Wormhole Token Bridge (Solana side)
***Severity***: Critical
***Vulnerability Class***: instruction_sysvar / Sysvar1nstructions address spoofing

***Description***:
Wormhole's `verify_signatures` instruction used `load_instruction_at` (the deprecated, unchecked variant) to read the Secp256k1 precompile instruction from the Instructions sysvar account. Because the deprecated function does not validate that the passed account key equals `Sysvar1nstructions1111111111111111111111111`, the attacker substituted a program-owned account whose data was crafted to look like a prior Secp256k1 call. The signature verification passed against attacker-controlled data, producing a valid `SignatureSet` PDA. That PDA was then used to mint 120,000 wETH (~$326M) without any real guardian signatures.

***Root cause***: `load_instruction_at` trusts whatever account is passed in the accounts array. `load_instruction_at_checked` rejects any account whose key does not equal the canonical sysvar ID.

***Attack steps***:
1. Attacker creates an account whose data mimics a completed Secp256k1 precompile instruction.
2. Attacker calls `verify_signatures`, passing the fake account in the position expected for the Instructions sysvar.
3. `load_instruction_at` reads from the fake account; check passes.
4. Resulting `SignatureSet` PDA used to call `complete_wrapped`, minting unbacked wETH.

***Affected code pattern***:
```rust
// VULNERABLE – no address check
let ix = load_instruction_at(index, &instructions_sysvar_account)?;

// SAFE
let ix = load_instruction_at_checked(index, &instructions_sysvar_account)?;
// OR in Anchor:
// #[account(address = sysvar::instructions::ID)]
// instructions_sysvar: AccountInfo<'info>,
```

***Fix***: Replace every call to `load_instruction_at` with `load_instruction_at_checked`, which performs `solana_program::sysvar::instructions::check_id(account.key)` before reading.

***References***:
- https://www.certik.com/resources/blog/wormhole-bridge-exploit-incident-analysis
- https://ackee.xyz/blog/2022-solana-hacks-explained-wormhole/
- https://kudelskisecurity.com/research/quick-analysis-of-the-wormhole-attack

---

## [II-W2] CRITICAL – `load_instruction_at` (Deprecated Unchecked Variant) Used in Production

***Protocol***: Generic / any Solana program using the Instructions sysvar pre-2022 SDK
***Severity***: Critical
***Vulnerability Class***: instruction_sysvar / unchecked function

***Description***:
`load_instruction_at` was deprecated precisely because it performs no validation on the sysvar account identity. Any program still calling this function, regardless of whether it also validates the key elsewhere, should be flagged. The Wormhole exploit demonstrated that a single missing check here is sufficient for critical funds loss. `load_instruction_at_checked` is a drop-in replacement.

***Affected code pattern***:
```rust
// VULNERABLE
use solana_program::sysvar::instructions::load_instruction_at;
let ix = load_instruction_at(idx, &acct)?;

// SAFE
use solana_program::sysvar::instructions::load_instruction_at_checked;
let ix = load_instruction_at_checked(idx, &acct)?;
```

***Fix***: Migrate to `load_instruction_at_checked`. Anchor's `#[account(address = sysvar::instructions::ID)]` constraint provides equivalent protection at the account-binding layer.

***References***:
- https://secure-contracts.com/not-so-smart-contracts/solana/improper_instruction_introspection/
- https://github.com/crytic/building-secure-contracts/blob/master/not-so-smart-contracts/solana/improper_instruction_introspection/README.md

---

## [II-W3] HIGH – Absolute Instruction Index Allows Multi-Mint Replay (Crytic / Trail of Bits Pattern)

***Protocol***: Generic – any program that verifies a companion instruction (e.g., a transfer or stake) by absolute index
***Severity***: High
***Vulnerability Class***: instruction_sysvar / absolute index / replay within transaction

***Description***:
When a program verifies the presence of a companion instruction using an absolute index (e.g., `get_instruction_relative(0, ...)` or `load_instruction_at_checked(0, ...)`), an attacker can craft a transaction with N copies of the protected instruction and a single companion instruction. All N copies verify against the same companion instruction at index 0, allowing the attacker to extract up to N times the intended benefit from a single companion instruction.

Trail of Bits (Crytic) documents this as the canonical "improper instruction introspection" pattern. A 4x token extraction scenario is the standard example: four mint instructions all verify one transfer at index 0.

***Attack steps***:
1. Protocol requires: `transfer` at instruction 0, then `mint` at instruction 1.
2. Attacker submits: `[transfer, mint, mint, mint, mint]` where each `mint` reads absolute index 0.
3. Each `mint` sees the same `transfer`; all four succeed; attacker receives 4x tokens for 1x payment.

***Affected code pattern***:
```rust
// VULNERABLE – absolute index
let transfer_ix = load_instruction_at_checked(0, &sysvar)?;
assert_eq!(transfer_ix.program_id, token_program::ID);

// SAFE – relative index ties each instruction to its immediate predecessor
let transfer_ix = get_instruction_relative(-1, &sysvar)?;
assert_eq!(transfer_ix.program_id, token_program::ID);
```

***Fix***: Use `get_instruction_relative` with a signed offset instead of an absolute index. The relative index is anchored to the currently executing instruction, so each copy of the consumer must have its own corresponding companion immediately before it.

***References***:
- https://secure-contracts.com/not-so-smart-contracts/solana/improper_instruction_introspection/
- https://github.com/crytic/building-secure-contracts/blob/master/not-so-smart-contracts/solana/improper_instruction_introspection/README.md

---

## [II-W4] HIGH – Flash Loan Sequence Gap: State-Modifying Instructions Executable Between Borrow and Repay (marginfi)

***Protocol***: marginfi v2 (reported by Asymmetric Research, ~$160M at risk)
***Severity***: High
***Vulnerability Class***: instruction_sysvar / instruction sequence validation / state gap

***Description***:
marginfi's flash loan implementation verifies, at the time of the borrow instruction, that a corresponding repay instruction is present later in the transaction. However, the check confirmed only *existence* of the repay, not that no other marginfi state-modifying instructions appeared between borrow and repay. A new `transfer_to_new_account` instruction allowed liabilities to be moved to a fresh account mid-loan. Because the repay instruction was still present (it just targeted the original account, now with zero liability), the repayment check passed while the borrowed funds remained unrepaid in the transferred account.

***Attack steps***:
1. Submit transaction: `[flash_borrow(accountA), transfer_to_new_account(accountA -> accountB), flash_repay(accountA)]`.
2. `flash_borrow` records the expected repay instruction index; checks pass.
3. `transfer_to_new_account` moves liability to `accountB` (no introspection guard).
4. `flash_repay` targets `accountA`, which now shows zero liability; repay passes.
5. Borrowed funds remain in attacker's `accountB` with no repayment.

***Fix***: Verify the complete instruction sequence between borrow and repay. Block any instruction that modifies account state (liability transfers, account disables) from executing within a flash loan window. Alternatively, snapshot state at borrow time and assert the identical state at repay time rather than trusting instruction presence.

***References***:
- https://blog.asymmetric.re/threat-contained-marginfi-flash-loan-vulnerability/
- https://blockworks.co/news/marginfi-flash-loan-bug

---

## [II-W5] HIGH – Introspection Sysvar Not Checked in CPI-Invoked Path (Generic / Local CSV Finding)

***Protocol***: Unnamed protocol (Solodit HIGH finding, row 7316)
***Severity***: High
***Vulnerability Class***: instruction_sysvar / sysvar address validation missing in CPI path

***Description***:
A protocol used the Instructions sysvar in its `deposit` and `set_service` instructions. The helper functions `validate_remaining_accounts` and `set_stake` both accept the sysvar account as a remaining account but perform no key validation. When these helpers are reached via CPI, the calling program controls the accounts array and can supply a fake account, allowing unauthorized instruction injection.

The fix (commit b221448) adds explicit `sysvar::instructions::check_id(account.key)` validation before any `load_instruction_at_checked` call in these helpers.

***Affected code pattern***:
```rust
// VULNERABLE – remaining accounts passed to helper without key check
fn validate_remaining_accounts(accounts: &[AccountInfo]) -> Result<()> {
    let ix = load_instruction_at_checked(0, &accounts[0])?; // accounts[0] not verified
    ...
}

// SAFE
fn validate_remaining_accounts(accounts: &[AccountInfo]) -> Result<()> {
    require_keys_eq!(accounts[0].key(), sysvar::instructions::ID);
    let ix = load_instruction_at_checked(0, &accounts[0])?;
    ...
}
```

***References***:
- Local CSV: solodit_findings.dedup.csv row 7316 (Solana HIGH)

---

## [II-W6] MEDIUM – CPI Invocation Renders `get_instruction_relative` Context Incorrect (Squads V4 / WBTC Controller)

***Protocol***: WBTC Controller integrated with Squads V4 (ChainSecurity audit)
***Severity***: Medium (DoS / authorization bypass for legitimate CPI callers)
***Vulnerability Class***: instruction_sysvar / CPI blind spot / `get_instruction_relative` context confusion

***Description***:
The WBTC controller verified the identity of its caller by calling `get_instruction_relative(0, ...)` and asserting the returned `program_id` matched the factory's expected program. This works when the factory is called directly as a top-level transaction instruction. When the factory is called via CPI (e.g., through a Squads multisig batch), the top-level instruction is `squads::batch_execute_transaction`, so `get_instruction_relative(0, ...)` returns the Squads program ID, not the factory's ID. The check fails, blocking all authorized Squads signers from burning or minting WBTC.

The Instructions sysvar exposes only *top-level* transaction instructions. CPI frames are invisible to it. Any program that relies on introspection to identify its caller will malfunction when invoked via CPI.

***Fix***: Replace the `get_instruction_relative` caller-identity check with a PDA signer check. A PDA signature is context-independent and unforgeable regardless of how deeply nested the CPI chain is. Do not use instruction introspection to determine the direct caller of a CPI-invokable instruction.

***References***:
- https://www.chainsecurity.com/blog/www-chainsecurity-com-blog-designing-for-squads-a-lesson-in-solana-authorization

---

## [II-W7] MEDIUM – Ed25519 / Secp256k1 Offset Fields Not Validated Against Actual Instruction Data (Relay Protocol)

***Protocol***: Relay Protocol (Asymmetric Research disclosure, ~Sep 2025)
***Severity***: Medium (signature forgery / double-spend)
***Vulnerability Class***: instruction_sysvar / ed25519 offset manipulation

***Description***:
Solana's Ed25519 (and Secp256k1) native programs verify a signature whose message, public key, and signature bytes are located by *offsets* inside the instruction data. A consuming program that reads the Ed25519 precompile instruction via introspection and trusts those offsets without independently verifying they point to the data it intends to protect can be fooled. In Relay's case, the program verified that an Ed25519 instruction existed and that the signature was valid, but did not verify that the signed message matched the allocator authorization it was trying to protect. An attacker could construct an Ed25519 instruction that signs an unrelated message and have the offset-based check pass, effectively forging the allocator signature and enabling double-spends.

***Attack steps***:
1. Attacker creates a valid Ed25519 instruction signing an arbitrary benign message M.
2. Transaction also includes Relay's protected instruction with different payload P.
3. Relay's introspection finds a valid Ed25519 instruction (check A passes) but does not bind the signed message to P (check B absent).
4. Attacker claims the authorization for P without ever signing it.

***Affected code pattern***:
```rust
// VULNERABLE – verifies signature validity but not what was signed
let ed_ix = load_instruction_at_checked(0, &sysvar)?;
assert_eq!(ed_ix.program_id, ed25519_program::ID);
// Missing: assert that ed_ix.data offsets point to the expected message bytes

// SAFE – extract and bind the message
let signed_message = extract_message_from_ed25519_ix(&ed_ix)?;
require!(signed_message == expected_authorization_hash, ErrorCode::InvalidSignature);
```

***Fix***: After loading the Ed25519 (or Secp256k1) instruction via introspection, parse the offset fields and verify the signed message matches the exact data the program expects to authorize. Do not treat the presence of a valid signature as authorization for an unrelated payload.

***References***:
- https://cantina.xyz/blog/signature-verification-risks-in-solana
- https://blog.asymmetric.re/wrong-offset-bypassing-signature-verification-in-relay/

---

## Summary

| ID | Severity | Root Cause | Real-World Anchor |
|----|----------|------------|-------------------|
| II-W1 | Critical | `load_instruction_at` (unchecked) + fake sysvar account | Wormhole $326M (Feb 2022) |
| II-W2 | Critical | Deprecated unchecked sysvar loader in production | Wormhole / general pattern |
| II-W3 | High | Absolute index allows N-copy replay | Trail of Bits / Crytic documented pattern |
| II-W4 | High | Flash loan sequence gap – state mutation between borrow/repay | marginfi ~$160M |
| II-W5 | High | Sysvar key unchecked in CPI helper path | Local CSV row 7316 |
| II-W6 | Medium | CPI blindspot – sysvar shows only top-level tx instructions | Squads V4 / WBTC (ChainSecurity) |
| II-W7 | Medium | Ed25519 offset fields not bound to protected message | Relay Protocol (Asymmetric Research) |


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Introspection Usage Inventory | YES | ✓/✗/? | For every introspection use |
| 2. Sysvar Address Validation | YES | ✓/✗/? | **CRITICAL** - sysvar address spoofing |
| 3. Checked Function Usage | YES | ✓/✗/? | _checked vs deprecated |
| 4. Instruction Sequence Validation | IF flash loan / atomic pattern | ✓/✗(N/A)/? | Gap between checks |
| 5. State Change Coverage | YES | ✓/✗/? | Between checked instructions |
| 6. Program ID Verification | YES | ✓/✗/? | For every inspected instruction |
