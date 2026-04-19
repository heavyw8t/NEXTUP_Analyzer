---
name: "nft-protocol-security"
description: "Protocol Type Trigger nft (detected when ERC721/ERC1155 with marketplace, minting, staking, or collateral logic found) - Inject Into Breadth agents, depth-token-flow, depth-edge..."
---

# Injectable Skill: NFT Protocol Security

> **Protocol Type Trigger**: `nft` (detected when ERC721/ERC1155 with marketplace, minting, staking, or collateral logic found)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case
> **Language**: EVM only (Solana/Move NFT models use different mechanisms without callbacks or enumeration)
> **Finding prefix**: `[NFT-N]`

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Sections 1, 2: depth-token-flow (callback flows, approval/transfer paths)
- Section 3: depth-edge-case (enumeration invariants, boundary states)
- Section 4: depth-state-trace (ownership state consistency, metadata integrity)

## When This Skill Activates

Recon detects NFT protocol patterns: ERC721/ERC1155 with state-modifying logic beyond simple transfer (marketplace listing, staking, collateral, minting with conditions, royalty enforcement, batch operations).

Pure ERC721/ERC1155 token implementations without protocol logic do NOT trigger this skill.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `ERC721`, `ERC1155`, `onERC721Received`, `safeTransferFrom`, `royalty`, `tokenURI`, `enumerable`, `approval`, `_safeMint`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[NFT-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Callback Reentrancy Surface

For each function that triggers NFT callbacks:

### 1a. Safe Transfer Callback Inventory
Enumerate all code paths that invoke `_safeMint`, `_safeTransfer`, `safeTransferFrom`, or `onERC1155Received`/`onERC1155BatchReceived`:

| # | Function | Callback Triggered | State Modified BEFORE Callback | State Modified AFTER Callback | Reentrancy Guard? |
|---|----------|-------------------|-------------------------------|------------------------------|-------------------|

For each entry:
- Is all critical state updated BEFORE the callback? (checks-effects-interactions)
- Can the callback recipient re-enter the calling contract?
- Can the callback recipient REVERT selectively to reject unwanted outcomes and retry until a desired outcome occurs?
- Pattern: `_safeMint(to, tokenId)` → `onERC721Received` callback → recipient reverts if assigned token has undesirable properties → retry until desired properties assigned.

### 1b. Batch Callback Completeness
For contracts implementing ERC1155:
- Is `onERC1155Received` implemented for single transfers?
- Is `onERC1155BatchReceived` implemented for batch transfers?
- If batch callback is MISSING: `safeBatchTransferFrom` will revert, blocking batch settlement/distribution.
- Do both callbacks return the correct selector?

Tag: `[TRACE:_safeMint → onERC721Received callback → state_before={list} → reentrant_path={YES/NO}]`

---

## 2. Approval and Transfer Path Analysis

### 2a. Approval Scope
For each approval mechanism:
- `approve(address, tokenId)`: per-token approval. Is approval cleared on transfer?
- `setApprovalForAll(address, bool)`: blanket approval. Can an approved operator transfer ANY token?
- Is there a mechanism to revoke approvals? Can approval persist across ownership changes?

### 2b. Transfer Authorization
For each transfer function:
- Who can transfer? (owner, approved, operator)
- Is authorization checked for ALL transfer code paths? (direct, marketplace, staking, collateral seizure)
- Pattern: protocol custody contract has `setApprovalForAll` from users → contract can transfer any user's NFTs → compromise of contract = compromise of all approved NFTs.

### 2c. Royalty Bypass
If royalties are enforced:
- Can transfers occur through paths that bypass royalty checks? (direct `transferFrom` vs marketplace `executeSale`)
- Are royalties enforced at the token level (ERC2981) or marketplace level?
- If marketplace-level only: direct transfer bypasses royalties.

Tag: `[TRACE:transfer_path={function} → auth_check={method} → royalty_enforced={YES/NO}]`

---

## 3. Enumeration and Index Integrity

For contracts using ERC721Enumerable or custom enumeration:

### 3a. Index Structure Consistency
- What data structures track token ownership enumeration? (`_ownedTokens`, `_allTokens`, index mappings)
- For every state-changing operation (mint, burn, transfer): are ALL index structures updated atomically?
- Pattern: override `_beforeTokenTransfer` (OZ v4) or `_update` (OZ v5) without calling `super` → index structures become stale.

### 3b. Burn and Transfer Edge Cases
- After burn: does `tokenOfOwnerByIndex` still return correct values? Is `totalSupply` decremented?
- After transfer: does old owner's index shrink and new owner's index grow?
- At boundary: single-token owner burns their only token → empty enumeration handles correctly?

### 3c. Batch Operation Atomicity
For batch mint/burn/transfer:
- Are indices updated for EACH token in the batch, or only once at the end?
- Can a partial failure in a batch leave indices in an inconsistent state?
- Gas cost at maximum batch size: does it exceed block gas limit?

Tag: `[BOUNDARY:burn_last_token → _ownedTokens[owner].length={0} → tokenOfOwnerByIndex={result}]`

---

## 4. Metadata and State Consistency

### 4a. Token URI Integrity
If `tokenURI` or `uri` returns dynamic content:
- For ERC1155: does `uri(uint256 id)` return a template with literal `{id}` placeholder per spec? Or a fully resolved URL? (clients expect to substitute the zero-padded hex ID client-side)
- Can metadata be changed after mint? By whom? Does change emit event?
- Is metadata stored on-chain or off-chain? If off-chain: what happens if the URI host is unreachable?

### 4b. Token Property Assignment
If tokens have properties assigned at mint time (rarity, type, attributes):
- Is the assignment deterministic or random?
- If random: is the randomness source manipulable? (block.timestamp, block.prevrandao, weak PRNG)
- Can the minter influence which properties are assigned? (selective minting via callback revert)
- Cross-reference FLASH_LOAN_INTERACTION if properties affect economic value.

### 4c. Ownership State During Custody
When tokens are deposited into protocol custody (staking, collateral, escrow):
- Does `ownerOf(tokenId)` return the protocol address or the depositor?
- Are user rights (claim, withdraw, liquidate) tracked correctly in protocol state?
- If the protocol is compromised: can deposited NFTs be recovered?

Tag: `[TRACE:mint → property_assignment={method} → randomness_source={source} → manipulable={YES/NO}]`

---

## Key Questions (must answer all)
1. For each `_safeMint`/`_safeTransfer`: is critical state updated BEFORE the callback?
2. For ERC1155: are BOTH single and batch callbacks implemented with correct selectors?
3. For enumerable tokens: do burn/transfer operations update ALL index structures?
4. For metadata: does `uri()` follow the spec for the token standard used?
5. For custody protocols: is depositor ownership tracked independently from `ownerOf`?

## Common False Positives
- **Non-reentrant safe transfers**: `_safeMint` within `nonReentrant` modifier → callback reentrancy blocked
- **Standard OZ implementation**: Inherits `ERC721Enumerable` or `ERC1155` without overriding internal hooks → indices maintained by parent
- **Immutable metadata**: Token URI set at mint and never changeable → no metadata manipulation
- **Trusted recipients only**: Safe transfers only to protocol-controlled addresses (not user-supplied) → callback revert/reentrancy not user-exploitable

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Reentrancy via `_safeMint` / `onERC721Received` callback before state update
  Where it hit: `partnerFreeMint` in ZkImagine NFT; `HoneyBox.claim` batch-mint; `LeverageModule._safeMint` in limit-order module
  Severity: HIGH
  Source: Solodit (row_id 6062, 12987, 8676)
  Summary: All three contracts invoke `_safeMint` before updating critical accounting (cooldown timestamps, claim flags, fee state). A malicious recipient's `onERC721Received` callback re-enters the minting function, bypassing per-user limits or stealing trading fees. Fixes applied the checks-effects-interactions pattern and/or a `nonReentrant` guard.
  Map to: ERC721, safeMint, onERC721Received

- Pattern: Royalty calculation uses returned `royaltyAmount` as a percentage rather than an absolute value, or double-charges pool instead of buyer
  Where it hit: Bridge contract `_getRoyaltyPercentage` (row 3634); Caviar `PrivatePool.buy` double-call to `_getRoyalty` (row 12398); NFTX `MarketplaceUniversalRouterZap` overstated `wethSpent` (row 10496)
  Severity: HIGH
  Source: Solodit (row_id 3634, 12398, 10496)
  Summary: In the bridge contract, `ERC2981.royaltyInfo` returns a token amount, not a basis-point percentage; treating it as a percentage causes massive overcharges. In Caviar, calling `_getRoyalty` twice lets a malicious NFT owner change the fee between calls and drain the pool. In NFTX, the sale price used for royalty calculation is overstated, causing buyers to overpay. All three demonstrate that royalty enforcement logic must be validated end-to-end against the actual sale price.
  Map to: ERC721, ERC1155, marketplace, royalty

- Pattern: Marketplace listing state not cleared on completion, enabling NFT theft via stale listing re-use
  Where it hit: KimNFTMarketplace `_isListingValid()` weak check (row 3694); `ProtectedListings.sol` unlocked NFT front-run (row 4500)
  Severity: HIGH
  Source: Solodit (row_id 3694, 4500)
  Summary: KimNFT fails to mark listings as completed, so an attacker can re-enter a finished listing and steal NFTs from other users. In Flayer's ProtectedListings, an unlocked-but-not-yet-withdrawn NFT is not considered an active listing, allowing a front-runner to redeem it before the rightful owner withdraws. Both require atomic state transitions from listed to withdrawn.
  Map to: ERC721, marketplace

- Pattern: `onERC721Received` not implemented in a contract that receives NFTs via `safeTransferFrom`, causing permanent revert / DoS
  Where it hit: `UniswapV3Staking.stake()` (row 3978); `YieldAccount` unstake NFT from Ether.fi (row 5615); `TGKMainContract` (row 10776)
  Severity: HIGH
  Source: Solodit (row_id 3978, 5615, 10776)
  Summary: Each contract attempts to receive an ERC721 via `safeTransferFrom` but does not implement `IERC721Receiver.onERC721Received`, causing every incoming transfer to revert. In the staking and unstaking cases, users cannot deposit or withdraw positions at all. The fix is to implement `onERC721Received` returning `IERC721Receiver.onERC721Received.selector`.
  Map to: ERC721, onERC721Received, safeMint

- Pattern: ERC1155 `_mint` triggers `_doSafeTransferAcceptanceCheck`, allowing a malicious receiver to revert and block the entire deposit queue
  Where it hit: Y2K Finance `Carousel.sol` deposit queue (row 12631)
  Severity: HIGH
  Source: Solodit (row_id 12631)
  Summary: The ERC1155 base `_mint` always calls back to the receiver, identical to ERC721 `safeMint`. A malicious depositor sets their receiver to always revert, which blocks processing of all preceding queued deposits and causes fund loss for other users. The fix overrides `_mint` to remove the safe-transfer acceptance check.
  Map to: ERC1155, onERC721Received, safeMint

- Pattern: NFT approval / operator rights persist across ownership changes, enabling the previous owner to drain the new owner's assets
  Where it hit: FootiumEscrow ERC20/ERC721 approvals persist after club sale (row 11985); Magnetar router allows any approved-for-all operator to call `ERC721.approve` for arbitrary token IDs (row 8308)
  Severity: HIGH
  Source: Solodit (row_id 11985, 8308)
  Summary: FootiumEscrow never revokes ERC721 approvals when a club NFT is transferred; the previous owner retains operator rights and can drain all player NFTs after the sale. Magnetar's `_processPermitOperation` lets any `isApprovedForAll` operator issue per-token approvals on behalf of the actual owner, escalating operator scope without owner consent. Both highlight that approvals must be cleared or validated on every ownership transition.
  Map to: ERC721, marketplace

- Pattern: NFT used as collateral can be withdrawn / re-used while a lien or loan remains active, causing bad debt
  Where it hit: Particle Exchange `withdrawNftWithInterest` without active-lien check (row 11722); Astaria `settleAuction` called without verifying auction outcome (row 13270); stNXM vault owner retains NFT while vault appears under-collateralised (row 147)
  Severity: HIGH
  Source: Solodit (row_id 11722, 13270, 147)
  Summary: Particle Exchange lets a lender withdraw the NFT collateral even while a second lien is still outstanding. Astaria's `settleAuction` does not check whether the underlying NFT was actually transferred, allowing a spoofed Seaport order to settle a non-existent auction. In stNXM, the vault owner can manipulate the staked NFT value to mint excess shares. All three result in under-collateralised positions and fund loss for counterparties.
  Map to: ERC721, marketplace

- Pattern: `tokenURI` / metadata manipulation via flash-loan inflated voting power or mutable on-chain state
  Where it hit: VotingEscrow `balanceOfTokenAt` missing flash-loan guard (row 6713); `partnerFreeMint` NFT ID reuse across wallets bypasses per-ID time restriction (row 6063)
  Severity: HIGH
  Source: Solodit (row_id 6713, 6063)
  Summary: In Alchemix's VotingEscrow, a missing snapshot check in `balanceOfTokenAt` allows a flash-loan of veALCX tokens to artificially inflate voting power and alter the `tokenURI` for any token. In ZkImagine, the time-restriction on `partnerFreeMint` tracks the wallet address but not the specific NFT ID, so transferring the partner NFT to a fresh wallet resets the cooldown and enables unlimited minting. Both demonstrate that token-level state tied to economic value must be anchored to immutable identifiers, not transferable addresses.
  Map to: ERC721, tokenURI, safeMint


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Callback Reentrancy Surface | IF safe mint/transfer used | | Callback inventory, batch completeness |
| 2. Approval and Transfer Paths | YES | | Authorization, scope, royalty bypass |
| 3. Enumeration and Index Integrity | IF enumerable | | Index consistency across operations |
| 4. Metadata and State Consistency | YES | | URI spec, property assignment, custody |
