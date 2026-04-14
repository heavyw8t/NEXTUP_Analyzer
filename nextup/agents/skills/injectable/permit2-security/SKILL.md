---
name: "permit2-security"
description: "Protocol Type Trigger permit2_integration (detected when recon finds IPermit2|IAllowanceTransfer|ISignatureTransfer|permit2|PermitTransferFrom|PermitBatchTransferFrom - protocol USES Permit2 for token approvals)"
---

# Injectable Skill: Permit2 Integration Security

> **Protocol Type Trigger**: `permit2_integration` (detected when recon finds: `IPermit2`, `IAllowanceTransfer`, `ISignatureTransfer`, `permit2`, `PermitTransferFrom`, `PermitBatchTransferFrom`, `AllowanceTransfer`, `SignatureTransfer`, `PERMIT2` constant - AND the protocol uses Permit2 for token transfers, not implements it)
> **Inject Into**: Breadth agents, depth-external, depth-state-trace
> **Language**: EVM only
> **Finding prefix**: `[P2-N]`

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (Permit2 mode selection, interface correctness)
- Sections 2, 3: depth-state-trace (nonce management, allowance lifecycle, expiration)
- Section 4: depth-external + depth-edge-case (signature replay, cross-chain, batch atomicity)
- Section 5: depth-token-flow (transfer amount validation, fee-on-transfer interaction)

## When This Skill Activates

Recon detects that the protocol uses Uniswap's Permit2 contract for token approvals and transfers. Permit2 provides two modes (Allowance Transfer and Signature Transfer) with different security models. Incorrect use of either mode can lead to token theft, signature replay, or permanent approval exposure.

---

## 1. Permit2 Mode Analysis

Permit2 has two distinct transfer modes with different security properties.

### 1a. Mode Classification

For each Permit2 usage in the protocol, classify the mode:

| Mode | Interface | Approval Model | Key Risk |
|------|-----------|---------------|----------|
| **Allowance Transfer** | `IAllowanceTransfer` | On-chain allowance (amount + expiration + nonce) set via `permit()` then consumed via `transferFrom()` | Allowance persists until revoked — if protocol is compromised, attacker can drain within allowance |
| **Signature Transfer** | `ISignatureTransfer` | Off-chain signature consumed atomically — no on-chain state | Signature can be replayed if nonce is not unique or if witness data is missing |

- Which mode does the protocol use? Some protocols use both (e.g., Allowance for recurring operations, Signature for one-time transfers).
- Is the mode choice appropriate for the use case? Allowance mode for one-time operations is unnecessarily risky. Signature mode for recurring operations requires repeated off-chain signatures.

### 1b. Permit2 Address

- Is the Permit2 contract address hardcoded or configurable?
- If configurable: can an admin set a malicious Permit2 address that steals approved tokens?
- **Real finding pattern (Sherlock)**: Protocol stores `permit2` address as a constructor parameter. Admin deploys with a malicious contract that mimics Permit2 but forwards all tokens to the admin. All user signatures execute against the fake Permit2, draining approvals.
- If hardcoded: is it the canonical Permit2 address (`0x000000000022D473030F116dDEE9F6B43aC78BA3`) for all target chains?
- Does the protocol verify the Permit2 address on deployment?

Tag: `[TRACE:permit2_mode={allowance/signature/both} → address_source={hardcoded/configurable} → canonical={YES/NO}]`

---

## 2. Allowance Transfer Security

If the protocol uses `IAllowanceTransfer`:

### 2a. Allowance Scope

- What amount is approved? `type(uint160).max` (unlimited) or specific amounts?
- Unlimited allowances in Permit2 persist until explicitly revoked — unlike standard ERC-20 `approve`, Permit2 allowances have an expiration, but if set far in the future, they're effectively unlimited.
- What is the expiration set to? `type(uint48).max` means the allowance never expires.
- Does the protocol set the minimum necessary allowance and expiration?

### 2b. Allowance Lifecycle

- After the protocol consumes tokens via `transferFrom()`: does it revoke or reduce the remaining allowance?
- If the protocol is upgradeable: can a compromised upgrade exploit existing Permit2 allowances that users granted to the old implementation?
- If the protocol uses a router pattern (user → router → protocol): which contract holds the Permit2 allowance? Can the router be swapped to a malicious one that drains allowances?

### 2c. Nonce Management (Allowance Mode)

Permit2 Allowance mode uses a bitmap-based nonce system (48-bit nonce packed with 48-bit expiration and 160-bit amount):
- Does the protocol specify a nonce when calling `permit()`? If not, the default nonce (0) may conflict with other protocols using the same Permit2 allowance slot.
- Can a user's allowance for protocol A be consumed by protocol B if they share the same token + spender slot?
- Does the protocol check the nonce after `permit()` to confirm it was consumed?

Tag: `[TRACE:allowance_amount={unlimited/specific} → expiration={value} → revoked_after_use={YES/NO} → nonce_specified={YES/NO}]`

---

## 3. Signature Transfer Security

If the protocol uses `ISignatureTransfer`:

### 3a. Nonce Uniqueness

Permit2 Signature mode uses a 256-bit nonce that is consumed (invalidated) on use:
- Does the protocol generate unique nonces for each transfer?
- Can the same nonce be used twice? (Permit2 prevents this at the contract level, but the protocol's nonce generation might produce collisions)
- Does the protocol use sequential nonces or random nonces? Sequential nonces can leak operation count; random nonces are safer but must avoid collision.
- Is there an off-chain nonce registry that could desync from on-chain state?

### 3b. Witness Data

Permit2 Signature mode supports "witness" data — additional typed data included in the signature hash:
- Does the protocol use witness data to bind the signature to a specific operation (e.g., order ID, recipient, deadline)?
- If NO witness data: the signature authorizes a token transfer to `msg.sender` with no additional constraints. An attacker who intercepts the signature can front-run and claim the tokens.
- **Real finding pattern (C4)**: Protocol uses `ISignatureTransfer.permitTransferFrom()` without witness data for order matching. Attacker monitors mempool, front-runs order submission, calls `permitTransferFrom` with the same signature but their own `to` address. Tokens go to attacker instead of intended recipient.
- If witness data is used: is the witness type registered with a unique `WITNESS_TYPEHASH`? Can the typehash collide with another protocol?
- **Real finding pattern**: Two protocols use the same `WITNESS_TYPEHASH` string for different witness struct layouts. A signature created for protocol A can be submitted to protocol B — the bytes decode differently but the typehash matches, so Permit2 accepts it.

### 3c. Deadline Enforcement

- Does the `PermitTransferFrom` struct include a `deadline`?
- Is the deadline set tight enough to prevent stale signatures from being executed?
- In a cross-chain scenario: is the deadline valid across chains, or is it chain-specific?

### 3d. Permitted Target Validation

- The `SignatureTransfer.permitTransferFrom()` call specifies the `to` address. Is this the protocol contract or a user-specified address?
- If user-specified: can an attacker create a signature that redirects tokens to their own address?
- Does the protocol validate that `to` matches the expected recipient before submitting the transfer?

Tag: `[TRACE:nonce_generation={sequential/random/caller-specified} → witness_used={YES/NO} → witness_type={hash} → deadline={value} → to_validated={YES/NO}]`

---

## 4. Cross-Cutting Risks

### 4a. Cross-Chain Signature Replay

- Permit2 signatures include `DOMAIN_SEPARATOR` which contains the chain ID. However:
  - If the protocol operates on multiple chains: can a signature intended for chain A be submitted on chain B?
  - The canonical Permit2 address is the same on all chains (CREATE2 deployed). So the domain separator differs only by chain ID.
  - Does the protocol include chain ID in its own signature validation (if any)?

### 4b. Batch Transfer Atomicity

If the protocol uses `PermitBatchTransferFrom`:
- Are all transfers in the batch intended to succeed or fail atomically?
- Can partial batch execution leave state inconsistent? (Permit2 batches ARE atomic, but the protocol's state updates around them might not be)
- Does the protocol validate the batch length matches expected transfers?

### 4c. Front-Running and MEV

- Can a pending Permit2 signature be observed in the mempool and front-run?
  - For Signature mode: if the signature has no witness binding it to a specific operation, anyone can submit it.
  - For Allowance mode: the `permit()` transaction can be front-run with a `transferFrom()` if allowance already exists.
- Does the protocol use private mempools or commit-reveal to protect signatures?

### 4c2. Permit Front-Run DoS (Nonce Advancement Grief)

- If the protocol calls `token.permit()` or `Permit2.permit()` as a SEPARATE step before `transferFrom()`: an attacker can extract `v,r,s` from the mempool and front-run the permit call with identical arguments. This advances the nonce. The legitimate transaction's permit call then fails (nonce already used), reverting the entire operation.
- **Real finding pattern (C4: LoopFi #205)**: `transferAndSwap()` called `token.safePermit(v,r,s)` then `token.safeTransferFrom()`. Attacker front-ran the permit — legitimate user's swap permanently reverted. Repeatable at low cost (attacker pays only gas).
- Fix: Make permit and transferFrom atomic (same call), or use try/catch around the permit call and fall back to existing allowance if the permit was already consumed.

### 4d. Integration with Fee-on-Transfer Tokens

- If the protocol accepts fee-on-transfer tokens via Permit2: does it validate the received amount matches the signed amount?
- Permit2 transfers the signed amount, but fee-on-transfer tokens deliver less. The protocol must check `balanceOf` delta, not the signed value.
- **Real finding pattern**: Protocol uses Permit2 `SignatureTransfer` for deposits. User signs for 1000 USDT (fee-on-transfer). Permit2 transfers 1000, protocol receives 998 (2 USDT fee). Protocol credits user with 1000, creating a 2 USDT deficit per deposit that drains the contract over time.

Tag: `[TRACE:cross_chain_replay={possible/prevented} → batch_atomicity={full/partial} → frontrun_protection={YES/NO} → fee_on_transfer_aware={YES/NO}]`

---

## 5. Common Integration Patterns

### 5a. Router + Permit2 Pattern

Many protocols use: User → approve Permit2 → Permit2 approves Router → Router calls Protocol.

- Is the router address validated? Can it be changed to a malicious router?
- Does the user's Permit2 allowance scope to the router or to the protocol?
- If the router is upgraded: does the new router automatically inherit existing Permit2 allowances?

### 5b. Permit2 + Standard Approve Fallback

Some protocols accept both Permit2 and standard ERC-20 approvals:
- Is the fallback path secure? (Often less scrutinized than the Permit2 path)
- Can an attacker force the fallback path by manipulating the Permit2 call to revert?
- Are both paths equivalent in terms of access control and amount validation?

### 5c. Permit2 Allowance as Access Control

Some protocols use existing Permit2 allowances as a form of access control (e.g., "you can call this function if you have a Permit2 allowance for token X"):
- This conflates token approval with function authorization — a Permit2 allowance is NOT an access control mechanism.
- Can an unrelated Permit2 allowance (granted for a different protocol) satisfy the check?

Tag: `[TRACE:pattern={router/fallback/access_control} → router_upgradeable={YES/NO} → fallback_equivalent={YES/NO}]`

---

## Common False Positives

- **Canonical Permit2 address on mainnet only**: If the protocol only deploys to Ethereum mainnet and hardcodes the canonical address, cross-chain replay is not applicable
- **Single-use signature with tight deadline**: If the signature includes witness data, a unique nonce, and a deadline within minutes, replay and front-running risks are minimal
- **Protocol-controlled transfers only**: If the protocol never exposes Permit2 signatures to users (only uses them internally between its own contracts), external replay is not applicable
- **Allowance mode with immediate revocation**: If the protocol calls `permit()` then `transferFrom()` then `invalidateNonces()` atomically, allowance persistence is not a concern

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Mode Classification | YES | | Allowance vs Signature vs both |
| 1b. Permit2 Address | YES | | Hardcoded, canonical, configurable |
| 2a. Allowance Scope | IF Allowance mode | | Amount, expiration |
| 2b. Allowance Lifecycle | IF Allowance mode | | Revocation, upgradeability |
| 2c. Nonce Management (Allowance) | IF Allowance mode | | Bitmap nonce, conflicts |
| 3a. Nonce Uniqueness | IF Signature mode | | Generation, collision |
| 3b. Witness Data | IF Signature mode | | Binding, typehash |
| 3c. Deadline Enforcement | IF Signature mode | | Tight deadline |
| 3d. Permitted Target | IF Signature mode | | `to` address validation |
| 4a. Cross-Chain Replay | YES | | Chain ID in domain separator |
| 4b. Batch Atomicity | IF batch transfers | | State consistency |
| 4c. Front-Running | YES | | MEV protection |
| 4d. Fee-on-Transfer | IF FoT tokens accepted | | Amount validation |
| 5a-c. Integration Patterns | YES | | Router, fallback, access control |
