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

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `permit2`, `allowanceTransfer`, `signatureTransfer`, `PermitSingle`, `PermitBatch`, `witness`, `permitWitnessTransferFrom`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[P2-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

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

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Configurable permit2 address with no access control on initializer
  Where it hit: SwapProxy / SwapImpl contract — `initialize()` callable by anyone, multiple times, accepting arbitrary `permit2` address
  Severity: HIGH
  Source: Solodit (row_id 121)
  Summary: The `initialize` function lacked access control and could be called repeatedly. An attacker reinitialized the proxy with a malicious contract as the `permit2` address. All subsequent token operations routed through the fake Permit2, draining WETH approvals.
  Map to: IPermit2

- Pattern: Block number used as Permit2 nonce — collision when multiple orders execute in the same block
  Where it hit: BunniHook rebalance order creation
  Severity: HIGH
  Source: Solodit (row_id 3806)
  Summary: The code passed `block.number` as the Permit2 signature nonce. Permit2 rejects a nonce that has already been consumed, so only the first rebalance order per block succeeded. An attacker could also grief pools by submitting a dummy rebalance order each block, consuming the nonce before the legitimate one.
  Map to: ISignatureTransfer, PermitTransferFrom

- Pattern: No validation that `permitSingle.token` matches the order's `inputToken` — cross-order permit substitution
  Where it hit: StarBaseLimitOrder / StarBaseDCA order fill logic
  Severity: HIGH
  Source: Solodit (row_id 5234)
  Summary: The fill function accepted a `permitSingle` struct without verifying that its token field matched the order's `makerToken`. A malicious filler supplied the permit data from one user's order to fill a different order, redirecting tokens and profiting from the mismatch.
  Map to: IAllowanceTransfer, ISignatureTransfer, PermitTransferFrom

- Pattern: `permitTransferFrom()` called without validating the permitted token against the expected vault asset
  Where it hit: V3Vault — three call sites of `permit2.permitTransferFrom()` accepted any ERC20
  Severity: HIGH
  Source: Solodit (row_id 8104)
  Summary: The vault used Permit2 signature transfers for USDC deposits but never checked that `TokenPermissions.token == vaultAsset`. An attacker crafted a permit signature over a worthless ERC20, deposited it, and received USDC credit, draining the vault's USDC balance.
  Map to: ISignatureTransfer, PermitTransferFrom

- Pattern: Protocol allows arbitrary external calls to Permit2 inside order execution, enabling theft of another user's signature
  Where it hit: BeefyZapRouter order execution and relay paths
  Severity: HIGH
  Source: Solodit (row_id 9246)
  Summary: The router permitted external calls to the Permit2 contract as part of step execution. An attacker constructed an order whose steps called `permitTransferFrom` with a valid signature from a different user, redirecting that user's tokens to themselves.
  Map to: ISignatureTransfer, PermitTransferFrom, PermitBatchTransferFrom

- Pattern: Signature Transfer used without witness data — signature is not bound to a specific operation or recipient
  Where it hit: SablierV2ProxyTarget — proxy used the signature for any transfer without committing to the target contract or function
  Severity: HIGH
  Source: Solodit (row_id 11456)
  Summary: The proxy consumed a bare `permitTransferFrom` signature that carried no witness data. Because the signature did not encode the intended operation, a user or attacker could front-run the proxy and submit the same signature for a different purpose, draining the authorized amount to an unintended destination.
  Map to: ISignatureTransfer, PermitTransferFrom

- Pattern: `uint160` silent truncation of token amount in Permit2 transfer
  Where it hit: Permit2 integration in a token transfer helper function
  Severity: MEDIUM
  Source: Solodit (row_id 235)
  Summary: A large token amount cast to `uint160` was silently truncated, causing the actual transfer amount to differ from the signed amount. The truncation only occurred for amounts exceeding `type(uint160).max`, but the protocol did not guard against this, so the signer's intent was violated.
  Map to: IAllowanceTransfer, ISignatureTransfer, PermitTransferFrom

- Pattern: Incorrect `PERMIT2_ORDER_TYPE` / malformed witness typehash breaks EIP-712 encoding
  Where it hit: ERC7683Across — `PERMIT2_ORDER_TYPE` omitted fields from `GaslessCrossChainOrder` and `AcrossOrderData`
  Severity: MEDIUM
  Source: Solodit (row_id 1624)
  Summary: The witness type string did not include all struct members required by EIP-712 and the Permit2 witness specification. The resulting `CROSS_CHAIN_ORDER_TYPE` hash was incorrect, meaning signatures generated off-chain could not be verified on-chain, and in the worst case, a collision with a correctly encoded type string from another protocol was possible.
  Map to: ISignatureTransfer, PermitTransferFrom

- Pattern: Permit front-run DoS via nonce advancement (missing try-catch around `Permit2.permit`)
  Where it hit: P2pLendingProxy `deposit` function
  Severity: MEDIUM
  Source: Solodit (row_id 2867)
  Summary: The deposit function called `Permit2.permit` as a separate step before `transferFrom`. An attacker extracted the permit call from the mempool and front-ran it with identical arguments, consuming the nonce. The victim's transaction then reverted on the permit call, permanently blocking the deposit at negligible cost to the attacker.
  Map to: IAllowanceTransfer, ISignatureTransfer

- Pattern: Canceled order's `permitSingle` nonce not invalidated — permit remains usable after order cancellation
  Where it hit: StarBase limit-order `cancelOrder` function
  Severity: MEDIUM
  Source: Solodit (row_id 5226)
  Summary: When a user canceled an order, the contract updated its own order state but did not call `invalidateNonces` on Permit2. The permit signature remained valid and could be replayed by anyone who observed it, filling the order even after the user intended to cancel.
  Map to: IAllowanceTransfer, ISignatureTransfer, PermitTransferFrom

- Pattern: Fee-on-transfer token amount discrepancy with `permitTransferFrom` — protocol credits signed amount, not received amount
  Where it hit: DonationVotingMerkleDistributionVaultStrategy `_afterAllocate()`
  Severity: MEDIUM
  Source: Solodit (row_id 10255)
  Summary: The protocol used `permitTransferFrom` to pull a donation then credited the recipient with the signed amount. For fee-on-transfer tokens, the vault received less than the signed amount. The deficit accumulated with every deposit, eventually draining the vault of the shortfall.
  Map to: ISignatureTransfer, PermitTransferFrom


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
