---
name: "token-2022-extensions"
description: "Trigger Pattern TOKEN_2022 flag detected (token_2022/spl_token_2022/transfer_checked usage) - Inject Into Breadth agents, depth agents"
---

# TOKEN_2022_EXTENSIONS Skill

> **Trigger Pattern**: TOKEN_2022 flag detected (token_2022/spl_token_2022/transfer_checked usage)
> **Inject Into**: Breadth agents, depth agents
> **Finding prefix**: `[T22-N]`
> **Rules referenced**: S9, R3, R11

For every token mint the program interacts with that may use Token-2022:

## 1. Extension Inventory

For each mint:

| Mint | Token Program | Extensions Detected | Extension Impact |
|------|--------------|--------------------:|-----------------|
| {mint} | token / token-2022 | {list: TransferFee, TransferHook, PermanentDelegate, MintCloseAuthority, DefaultAccountState, etc.} | {brief per-extension impact} |

**Detection**: Check if program uses `spl_token_2022` or `token_2022` imports. Check mint account data length (Token-2022 mints are larger due to extension data).

## 2. Extension Allowlist

Does the program explicitly check which extensions are supported?

| Check | Present? | Location | Missing Extensions Handled? |
|-------|---------|----------|---------------------------|
| Extension allowlist / blocklist | YES/NO | {line} | {what happens with unsupported extension} |

**Attack (S9)**: Program designed for basic SPL Token interacts with Token-2022 mint that has unexpected extensions (e.g., PermanentDelegate). Program doesn't check → extension silently affects behavior.
**Defense**: Explicitly check mint extensions and reject unsupported ones.

## 3. Permanent Delegate Risk

For each mint with PermanentDelegate extension:

| Mint | Permanent Delegate | Trust Level | Vault Drain Scenario | Mitigation |
|------|-------------------|------------|---------------------|-----------|
| {mint} | {delegate pubkey} | {trusted/untrusted/unknown} | {can delegate drain vault?} | {what prevents it} |

**Attack**: Permanent delegate can transfer tokens FROM any token account of that mint, without the account owner's approval. If protocol holds tokens of a PermanentDelegate mint → delegate can drain them at any time.

## 4. Transfer Hook Analysis

For each mint with TransferHook extension:

| Mint | Hook Program | Hook Verified? | CU Budget Impact | Recursion Risk? |
|------|-------------|---------------|-----------------|----------------|
| {mint} | {program_id} | YES/NO | {estimated CU} | YES/NO |

**Risks**:
- Hook program can consume significant CU, causing transactions to fail
- Hook program can revert, blocking all transfers of this token
- Hook program may have its own CPI chain, adding depth
- Hook may read additional accounts not provided by the caller

## 5. Transfer Fee Accounting

For each mint with TransferFeeConfig:

| Mint | Fee Rate | Fee Accounted in Protocol Math? | Amount Received < Amount Sent? |
|------|---------|-------------------------------|-------------------------------|
| {mint} | {bps} | YES/NO | {if NO: accounting mismatch} |

**Attack**: Protocol calculates expected amounts without deducting transfer fee → accounting mismatch, potential insolvency.
**Pattern**: `transfer_checked` returns the gross amount. The net amount received is `gross - fee`. Protocol must use net amount in accounting.

## 6. CPI Guard Handling

For transfers through delegation (CPI transfers):

| Transfer Type | Uses CPI? | CPI Guard Enabled on Mint? | Transfer Works? |
|--------------|-----------|---------------------------|----------------|
| {type} | YES/NO | YES/NO/Unknown | {if CPI Guard + delegation: may fail} |

**CPI Guard**: When enabled, prevents token account delegates from transferring via CPI. Programs that rely on delegated transfers via CPI will fail silently.

## 7. Default Account State

For mints with DefaultAccountState extension:

| Mint | Default State | Protocol Handles Frozen? | Impact |
|------|-------------|------------------------|--------|
| {mint} | Frozen / Initialized | YES/NO | {if frozen: new token accounts start frozen, need thaw} |

## 8. Mint Existence Verification (MintCloseAuthority)

For mints with MintCloseAuthority extension:

| Mint | Close Authority | Checked Before Read? | Impact if Mint Closed |
|------|----------------|---------------------|---------------------|
| {mint} | {authority} | YES/NO | {if NO: reading zeroed data, incorrect decimals/supply} |

**Attack**: Mint with MintCloseAuthority can be closed (if supply == 0). Protocol reads closed mint → gets zeroed data → decimals = 0, incorrect calculations.

## Finding Template

```markdown
**ID**: [T22-N]
**Severity**: [PermanentDelegate drain = Critical, transfer fee mismatch = High, CPI Guard = Medium]
**Step Execution**: ✓1,2,3,4,5,6,7,8 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [S9:✓, R3:✓, R11:✓/✗]
**Location**: program/src/{file}.rs:LineN
**Title**: Token-2022 [extension] in [context] enables [attack]
**Description**: [Specific extension vulnerability with data flow]
**Impact**: [Fund drain / accounting mismatch / DoS]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sources: Neodyme blog (neodyme.io/en/blog/token-2022/), Halborn Token-2022 bugfix review, Solana post-mortem (June 2025), Zealynx Security 2026 audit guide, Solana Foundation security audits (anza-xyz/security-audits).

---

## [T22-W1] Transfer Fee Not Deducted From Received Amount — Protocol Accounting Mismatch

**Severity**: High
**Extension**: TransferFeeConfig
**Source**: Neodyme — "SPL Token-2022: Don't shoot yourself in the foot with extensions"

**Description**: The transfer fee is deducted from the *recipient's* received amount, not from the sender's balance. When a protocol records the gross amount sent rather than the net amount received, internal accounting diverges from actual token balances. Every deposit, swap, or escrow operation that uses the pre-transfer amount as its book entry accumulates error proportional to the fee rate.

**Attack pattern**: Attacker deposits `X` tokens into a lending or AMM vault. Protocol records `X` as collateral. Vault actually holds `X - fee`. Attacker borrows against the inflated collateral value. Repeated at scale this produces a shortfall equal to `N * fee` per round-trip.

**Required check**: Use `transfer_checked_with_fee` and pass the calculated fee, or read the recipient token account balance before and after transfer and use the delta as the book entry — never use the instruction `amount` parameter directly for accounting.

**References**:
- https://neodyme.io/en/blog/token-2022/
- https://chainstack.com/solana-token-2022-fee-transfer-hooks/

---

## [T22-W2] Transfer Fee Circumvention via Confidential Transfer Deposit/Withdraw

**Severity**: Critical
**Extension**: ConfidentialTransfer + TransferFeeConfig
**Source**: Halborn Token-2022 Bugfix Review (November 2022 audit)

**Description**: The `deposit` and `withdraw` instructions in the ConfidentialTransfer extension did not validate that source and destination token wallets matched. An attacker could specify different token wallets in these instructions, converting them into fee-free transfer vectors that bypassed TransferFeeConfig entirely. Identified as a critical pre-production finding; fixed by Solana Labs by removing the `destination_token` parameter from both instructions (commit `3ddb3c7404d23146a390150e241831e116c5cc8d`).

**Attack pattern**: Caller invokes `deposit` with source account A and destination account B (different accounts). Tokens move without triggering fee collection logic. Works even when TransferFeeConfig mandates a non-zero basis-point fee.

**References**:
- https://www.halborn.com/blog/post/solana-token-ception-token-2022-bugfix-review

---

## [T22-W3] NonTransferable Token Bypass via Confidential Transfer

**Severity**: Critical
**Extension**: ConfidentialTransfer + NonTransferable
**Source**: Halborn Token-2022 Bugfix Review (November 2022 audit)

**Description**: The ConfidentialTransfer extension did not check whether a mint had the NonTransferable extension enabled. Users could deposit soulbound (non-transferable) tokens into a confidential account and then transfer them to a third party, completely bypassing the transfer restriction. Identified in the same pre-production audit; fixed across three commits (`6a102589`, `92a8e6b2`, `b973e474`).

**Protocol-level impact**: Any lending protocol that uses NonTransferable tokens as collateral (e.g., staked-position receipts, soulbound loyalty tokens) could receive collateral that should never leave the depositor's wallet. If the protocol later attempts to seize or liquidate the collateral it cannot transfer it back out, causing stuck funds or liquidation failure.

**References**:
- https://www.halborn.com/blog/post/solana-token-ception-token-2022-bugfix-review
- https://solana.com/docs/tokens/extensions/non-transferrable-tokens

---

## [T22-W4] TransferHook Account Injection via Unvalidated ExtraAccountMetaList Seeds

**Severity**: High
**Extension**: TransferHook
**Source**: Neodyme blog + Zealynx Security 2026 audit guide

**Description**: The TransferHook extension passes an `ExtraAccountMetaList` PDA containing additional accounts the hook program reads during execution. If the hook program does not strictly validate the PDA derivation seeds, an attacker can craft a spoofed `ExtraAccountMetaList` that substitutes controlled accounts (e.g., a fake whitelist, a fake oracle) for the legitimate ones. The hook then reads attacker-controlled state and may approve transfers that should be blocked.

**Three required validations a hook program must perform**:
1. Verify the mint is whitelisted/expected — reject calls from unknown mints.
2. Check the `transferring` flag is set to `true` on the source and destination token accounts — prevents calling the hook directly outside of an actual transfer context.
3. Verify all token accounts passed actually belong to the called mint — prevents cross-mint account spoofing.

**References**:
- https://neodyme.io/en/blog/token-2022/
- https://www.zealynx.io/blogs/solana-2026-security

---

## [T22-W5] TransferHook Infinite Recursion / CPI Depth Exhaustion

**Severity**: Medium (DoS)
**Extension**: TransferHook
**Source**: Zealynx Security 2026 audit guide

**Description**: If a TransferHook program triggers a CPI that initiates another transfer of the same mint, a recursion loop begins. Solana's runtime halts execution when CPI depth (max 4 levels) is exhausted, causing the entire transaction to fail. An attacker who controls or influences the hook's CPI call chain can grief any vault or AMM that interacts with that mint by making every transfer revert.

**Composability impact**: Deep transfer hook chains (hook -> CPI -> hook -> CPI) break DeFi protocols that compose multiple token operations in a single transaction, even if neither protocol is directly responsible for the hook.

**References**:
- https://www.zealynx.io/blogs/solana-2026-security

---

## [T22-W6] PermanentDelegate Drains Protocol Vault Without Authorization

**Severity**: Critical
**Extension**: PermanentDelegate
**Source**: Neodyme blog + active exploit pattern documented 2026

**Description**: The PermanentDelegate extension grants a designated authority unconditional power to transfer or burn tokens from *any* token account of that mint without the account owner's signature. A protocol vault holding tokens of a PermanentDelegate mint can be drained at any time by the delegate, bypassing all protocol-level access controls.

**Observed real-world pattern (2026)**: Malicious token deployers set the PermanentDelegate to the deployer wallet, create liquidity pools, generate fake volume, and then call `Burn` on buyer token accounts within 1-60 seconds of purchase.

**Protocol risk**: An AMM, lending protocol, or yield vault accepting user-supplied mint addresses must check whether PermanentDelegate is set, assess trust in that authority, and either reject such mints or account for unexpected balance reductions in all invariant checks.

**References**:
- https://neodyme.io/en/blog/token-2022/
- https://dev.to/ohmygod/solanas-permanent-delegate-burn-scam-how-token-2022-extensions-power-2026s-largest-automated-rug-4579

---

## [T22-W7] DefaultAccountState Freezes Newly Created Vaults, Blocking Protocol Operations

**Severity**: High
**Extension**: DefaultAccountState
**Source**: Neodyme blog

**Description**: When a mint has DefaultAccountState set to `Frozen`, every newly initialized token account for that mint starts in the frozen state and cannot send or receive tokens until explicitly thawed by the freeze authority. If a protocol creates a vault or escrow token account for such a mint during deposit or initialization logic — without checking for DefaultAccountState or calling `ThawAccount` — the account is created frozen and all subsequent transfers into or out of it revert. This can lock deposited funds or halt protocol operations entirely depending on whether the freeze authority is accessible.

**References**:
- https://neodyme.io/en/blog/token-2022/

---

## [T22-W8] MintCloseAuthority + Mint Reinitialization Bypasses Transfer Fees on Pre-Existing Accounts

**Severity**: High
**Extension**: MintCloseAuthority + TransferFeeConfig
**Source**: Neodyme blog

**Description**: Mints with MintCloseAuthority can be closed when supply reaches zero. A coordinated group can: (1) create a mint without extensions, (2) set up token accounts for themselves, (3) drain supply to zero, (4) close the mint, (5) reinitialize the mint with TransferFeeConfig. Because the fee extension check inspects the *source token account's* extension data (not just the mint), the pre-existing token accounts created before the extension was added do not carry the fee extension record and transfers from them avoid fee collection. The same technique can bypass NonTransferable or other per-account extension requirements.

**References**:
- https://neodyme.io/en/blog/token-2022/

---

## [T22-W9] ZK ElGamal Fiat-Shamir Flaw Allows Forged Confidential Transfer Proofs (Unlimited Mint)

**Severity**: Critical
**Extension**: ConfidentialTransfer
**Source**: Anza/Solana Foundation post-mortem, April 2025 (patched before exploitation)

**Description**: The ZK ElGamal Proof program — which verifies zero-knowledge proofs used in ConfidentialTransfer — contained missing algebraic components in the Fiat-Shamir transformation used for cryptographic randomness. The flaw allowed an attacker to craft forged proofs that the verifier accepted as valid. A successful exploit would have allowed minting arbitrary amounts of any Token-2022 token using the ConfidentialTransfer extension and draining user accounts. The vulnerability was disclosed April 16 2025, patched privately to validators April 17, and a supermajority of validators adopted the fix by April 18. No exploitation occurred.

**Audit implication**: Any protocol that accepts ConfidentialTransfer-enabled mints and relies on on-chain ZK proof verification for balance correctness is exposed to proof-forgery attacks if the underlying proof program has soundness gaps. This class of bug requires formal verification, not just functional testing.

**References**:
- https://solana.com/news/post-mortem-june-25-2025
- https://www.theblock.co/post/353055/solana-validators-patch-zero-day-bug-that-could-have-led-to-unlimited-minting-of-certain-tokens
- https://cryptoslate.com/solana-averts-catastrophe-with-quiet-patch-of-major-token-vulnerability/

---

## [T22-W10] Insufficient Account Space for Token-2022 Mints Causes Initialization Failure

**Severity**: Medium (DoS / integration failure)
**Extension**: Any extension (variable-length mint accounts)
**Source**: Local CSV candidate (row_index 919) — OtterSec finding on Raydium staking

**Description**: Token-2022 mint accounts are larger than standard SPL Token mint accounts because extension data is appended inline. A protocol that hard-codes 165 bytes (the standard Token mint size) when allocating a new token account for a Token-2022 mint will cause `initialize_account3` to fail. In the Raydium staking context, `stake_clmm_position` allocated exactly 165 bytes for the vault token account of a Raydium position mint, preventing all users from staking their positions and blocking the farming pool.

**Fix pattern**: Compute required space dynamically using `ExtensionType::get_account_len` (or equivalent) based on the mint's actual extension list before allocating the account, not a compile-time constant.

**References**:
- Local CSV row_index 919 (Solana / HIGH)


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Extension Inventory | YES | ✓/✗/? | For every mint |
| 2. Extension Allowlist | YES | ✓/✗/? | Explicit check present? |
| 3. Permanent Delegate Risk | IF PermanentDelegate | ✓/✗(N/A)/? | Vault drain scenario |
| 4. Transfer Hook Analysis | IF TransferHook | ✓/✗(N/A)/? | CU + revert risk |
| 5. Transfer Fee Accounting | IF TransferFee | ✓/✗(N/A)/? | Net vs gross |
| 6. CPI Guard Handling | IF delegated CPI transfers | ✓/✗(N/A)/? | Delegation + CPI Guard |
| 7. Default Account State | IF DefaultAccountState | ✓/✗(N/A)/? | Frozen by default |
| 8. Mint Existence Verification | IF MintCloseAuthority | ✓/✗(N/A)/? | Closed mint reads |
