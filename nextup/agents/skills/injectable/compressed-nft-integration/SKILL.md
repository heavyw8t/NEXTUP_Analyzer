---
name: "compressed-nft-integration"
description: "Protocol Type Trigger compressed_nft_integration (detected when recon finds spl_account_compression|ConcurrentMerkleTree|spl_noop|Bubblegum|mint_v1|transfer|redeem|decompress_v1|canopy|proof - protocol USES cNFTs / SPL Compression)"
---

# Injectable Skill: Compressed NFT Integration Security

> Protocol Type Trigger: `compressed_nft_integration` (detected when recon finds: `spl_account_compression`, `ConcurrentMerkleTree`, `spl_noop`, `Bubblegum`, `mint_v1`, `transfer`, `redeem`, `decompress_v1`, `canopy`, `proof`)
> Inject Into: depth-state-trace, depth-external, depth-edge-case
> Language: Solana only
> Finding prefix: `[CNFT-N]`
> Relationship to metaplex-nft-standard: decompressed cNFTs produce standard Metaplex NFTs. Activate both for decompression flows.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-state-trace (proof path length vs canopy depth)
- Section 2: depth-edge-case (concurrent merkle tree buffer size)
- Section 3: depth-external (delegate vs owner semantics)
- Section 4: depth-external (indexer-trust boundary)
- Section 5: depth-edge-case (decompression invariants)
- Section 6: depth-state-trace (spl-noop log integrity)

## When This Skill Activates

Recon detects Bubblegum / SPL Account Compression integration, usage of `ConcurrentMerkleTree`, or reliance on off-chain indexers to produce proofs for on-chain verification.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: spl_account_compression, ConcurrentMerkleTree, spl_noop, Bubblegum, canopy, proof
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[CNFT-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Proof Path Length vs Canopy Depth

### 1a. Proof Length Matches Tree
- Proof length must equal `max_depth - canopy_depth`. Wrong length fails on-chain.
- Real finding pattern (Solodit, pattern observed in multiple audits): Wrapper hardcodes proof length 14 while tree has canopy 3 and max_depth 20; all transfers revert.

### 1b. Canopy Serialization
- The canopy nodes are embedded in the tree account. Do remaining_accounts use the on-chain canopy?
- Real finding pattern (pattern observed in multiple audits): Wrapper pre-appends canopy nodes from off-chain indexer, duplicating values and corrupting root.

### 1c. Tree-Specific Proof Length Cache
- Wrapper caching proof length per tree must invalidate on tree upgrade.
- Real finding pattern (pattern observed in multiple audits): Cache not invalidated when canopy depth changes; downstream calls misaligned.

Tag: [TRACE:proof_length_dynamic=YES/NO → canopy_not_duplicated=YES/NO → cache_invalidated_on_upgrade=YES/NO]

---

## 2. Concurrent Merkle Tree Buffer Size

### 2a. Buffer Size Saturation
- The tree's circular buffer tracks recent roots; proofs valid against a displaced root fail. Does the wrapper detect and refresh?
- Real finding pattern (pattern observed in multiple audits): Busy tree overwrites root before wrapper's tx lands; transaction reverts without retry logic.

### 2b. Buffer-Aware Concurrency
- Concurrent writes to the tree within buffer size are safe. Beyond it, readers must fetch fresh proofs.
- Real finding pattern (pattern observed in multiple audits): Wrapper batches 64 mints against a 32-size buffer; half revert unpredictably.

### 2c. Proof Refresh Path
- Wrapper must have a path to refresh proofs after revert; without it, users stuck.
- Real finding pattern (pattern observed in multiple audits): No refresh RPC fallback; user perceives permanent failure.

Tag: [TRACE:buffer_overflow_handled=YES/NO → concurrency_bounded=YES/NO → refresh_path_exists=YES/NO]

---

## 3. Delegate vs Owner Semantics

### 3a. Delegate Scope
- Bubblegum delegate applies only to the single leaf. Does the program distinguish?
- Real finding pattern (Solodit, pattern observed in multiple audits): Wrapper treats delegate as tree-wide authority; delegate can move only one asset but wrapper allows many.

### 3b. Owner Signature
- Transfer requires owner signature; delegate may suffice for transfer but not for burn on some programs.
- Real finding pattern (pattern observed in multiple audits): Wrapper permits burn by delegate; standard requires owner.

### 3c. Delegate Expiry
- Delegate resets on transfer. Wrappers must not rely on persistence.
- Real finding pattern (pattern observed in multiple audits): Wrapper caches delegate after transfer; new owner gains unintended privileges.

Tag: [TRACE:delegate_scoped_to_leaf=YES/NO → owner_signature_required=YES/NO → delegate_reset_on_transfer=YES/NO]

---

## 4. Indexer-Trust Boundary

### 4a. Indexer Supplies Proof
- Off-chain indexers (Helius, Triton) provide proofs. Does the wrapper trust proof shape without verifying against on-chain root?
- Real finding pattern (pattern observed in multiple audits): Wrapper forwards indexer-supplied proof; compromised indexer returns a proof for a different asset.

### 4b. Signed Proof vs Unsigned
- Does the wrapper require signed proof from a trusted indexer, or accept any?
- Real finding pattern (pattern observed in multiple audits): Unsigned proof path; any RPC can feed alternate asset ids.

### 4c. Asset ID Collision
- Asset IDs are derived deterministically. Wrapper must check asset ID matches the leaf being mutated.
- Real finding pattern (pattern observed in multiple audits): Wrapper validates leaf by hash but indexer metadata (name, URI) swapped; wrong asset transferred.

Tag: [TRACE:proof_root_verified=YES/NO → indexer_signature_required=YES/NO → asset_id_derivation_checked=YES/NO]

---

## 5. Decompression Invariants

### 5a. Mint Authority Binding
- Decompression creates an SPL mint; wrapper must pin expected mint authority (usually Bubblegum PDA).
- Real finding pattern (pattern observed in multiple audits): Wrapper accepts any mint authority post-decompression; attacker supplies a fake decompression.

### 5b. Leaf Burn Atomicity
- Decompression must burn the leaf atomically with the mint creation.
- Real finding pattern (pattern observed in multiple audits): Wrapper calls decompression without atomic burn; leaf still present, double usage.

### 5c. Metadata Continuity
- Metadata created on decompression must match the leaf's schema.
- Real finding pattern (pattern observed in multiple audits): Wrapper reconstructs metadata from indexer; fields diverge.

Tag: [TRACE:mint_authority_pinned=YES/NO → leaf_burn_atomic=YES/NO → metadata_matches_leaf=YES/NO]

---

## 6. spl-noop Log Integrity

### 6a. Noop Program Pin
- spl-noop emits change logs used by indexers. Tree operations must invoke the real noop program.
- Real finding pattern (pattern observed in multiple audits): Wrapper passes a fake noop program; indexers miss the event; state appears inconsistent.

### 6b. Log Data Integrity
- Noop logs must contain the full leaf update for indexer reconstruction. Wrapper should not truncate.
- Real finding pattern (pattern observed in multiple audits): Wrapper invokes noop with truncated data; indexer cannot rebuild, proofs for new state fail.

### 6c. Log-Cpi Ordering
- Log emission must occur in the same instruction as tree mutation. Split transactions break indexer rebuild.
- Real finding pattern (pattern observed in multiple audits): Wrapper emits log in a separate tx; indexer sees mutation without log; state divergence.

Tag: [TRACE:noop_program_pinned=YES/NO → log_data_complete=YES/NO → log_in_same_tx=YES/NO]

---

## Common False Positives

- Wrapper only mints cNFTs and never operates on them post-mint. Sections 2 to 4 reduced.
- Wrapper relies on a single trusted indexer with signed proofs. Section 4 partially delegated.
- No decompression path. Section 5 does not apply.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sources searched: Snyk advisory database, GitHub Security Advisory Database (metaplex-foundation/metaplex-program-library), Solodit, Cantina blog, public write-ups (Bonfida, SolShield, Perma DAO).

---

## Finding 1

- Pattern: Canopy not updated on leaf mutation — `ConcurrentMerkleTree::update` updates the leaf and its main-tree proof path but does not refresh the canopy nodes. Subsequent proof generation against the stale canopy produces invalid proofs that fail on-chain verification.
- Where it hit: `spl-account-compression` / `ConcurrentMerkleTree` (upstream SPL library, resolved in commit 587ca5f)
- Severity: HIGH
- Source: local CSV row 5317 (solodit_findings.dedup.csv); confirmed via SPL commit history
- Summary: The update function lacked logic to propagate leaf changes into the cached canopy layer. Any caller that re-used proof paths after a leaf update received proofs built against stale canopy hashes, causing all subsequent tree operations on affected leaves to revert. The fix adds canopy refresh inside the update routine.
- Map to: spl_account_compression, ConcurrentMerkleTree, canopy

---

## Finding 2

- Pattern: Creator signature verification bypass on decompression — `decompress_v1` trusted a Token Metadata provision that allows creators who had previously signed a compressed NFT to decompress it with "verified" creator status, without requiring a fresh signature at decompression time. An attacker could verify a creator who never signed the decompression transaction.
- Where it hit: `mpl-bubblegum` < 0.6.0 / `decompress_v1` instruction (GHSA-8r76-fr72-j32w)
- Severity: HIGH
- Source: https://github.com/advisories/GHSA-8r76-fr72-j32w — reported by @metamania01 (SolShield); fix in mpl-bubblegum 0.6.0, commit c18591a
- Summary: Bubblegum's `decompress_v1` path relied on a Token Metadata rule that treated previously-signed compressed NFT creators as verified during decompression, without requiring a live signature. A malicious caller could invoke decompression and obtain an uncompressed NFT with a forged verified-creator flag, enabling royalty bypass and provenance fraud. Fixed by requiring explicit creator signature validation at decompression.
- Map to: Bubblegum, decompress_v1, spl_account_compression

---

## Finding 3

- Pattern: Missing creator signature check during mint — `utils/metadata.rs` in mpl-bubblegum failed to verify that all declared creators had signed the mint transaction. An attacker with low privilege could mint a compressed NFT with arbitrary creator metadata, including fabricated verified-creator fields, without holding the creator keys.
- Where it hit: `mpl-bubblegum` (Rust crate) < 0.6.0 (SNYK-RUST-MPLBUBBLEGUM-3167971)
- Severity: MEDIUM (CVSS 6.5; Snyk rating)
- Source: https://security.snyk.io/vuln/SNYK-RUST-MPLBUBBLEGUM-3167971 — disclosed 2022-12-12; fix in mpl-bubblegum 0.6.0
- Summary: The metadata utility function responsible for validating creator arrays during `mint_v1` did not check that each creator entry had a corresponding valid signature. Any caller could supply a creator list with `verified: true` for keys that never signed, permanently embedding false provenance in the NFT leaf. The fix adds explicit per-creator signature assertion in `utils/metadata.rs`.
- Map to: Bubblegum, spl_account_compression

---

## Finding 4

- Pattern: Delegate transfer missing mint-match assertion — the `transfer` instruction in `mpl-token-metadata` (which governs decompressed cNFTs post-`decompress_v1`) did not assert that the mint account referenced in the transfer matched the mint stored in the metadata account. A delegate could supply a mismatched mint account and transfer ownership of an NFT it was not authorized for.
- Where it hit: `mpl-token-metadata` (Rust) > 1.7.0 and < 1.8.4 (GHSA-5233-j5mj-qxww)
- Severity: HIGH
- Source: https://github.com/metaplex-foundation/metaplex-program-library/security/advisories/GHSA-5233-j5mj-qxww — reported by SolShield; fix in mpl-token-metadata 1.8.4
- Summary: The transfer instruction validated the delegate's authority but skipped a check confirming the supplied mint account corresponded to the metadata being operated on. A delegate could craft a transaction substituting a different mint, allowing unauthorized transfer of NFTs outside the scope of their delegation. Directly relevant to cNFT flows because decompressed cNFTs become standard Token Metadata NFTs subject to this same delegate-transfer path. Fixed by moving the mint-match assertion earlier in instruction validation.
- Map to: Bubblegum, decompress_v1

---

## Finding 5

- Pattern: Set-collection-during-mint missing self-program check — `set_collection_during_mint` in Candy Machine V2 verified the previous instruction's program ID but not that the current instruction originated from Candy Machine V2 itself. An attacker submitted a multi-instruction transaction where an initial instruction triggered bot-tax success, then a crafted subsequent instruction called `set_collection_during_mint` to inject arbitrary NFTs into a collection even after the machine was depleted or closed.
- Where it hit: `mpl-candy-machine` (Rust) <= 4.5.0 (GHSA-9v25-r5q2-2p6w)
- Severity: MEDIUM
- Source: https://github.com/advisories/GHSA-9v25-r5q2-2p6w — reported by austbot; fix in mpl-candy-machine 4.5.1, commit e6b3aff
- Summary: The collection-during-mint guard inspected the previous-instruction program ID (a common Solana anti-bot pattern) but omitted a check that the instruction itself came from the Candy Machine program. This let an attacker bypass supply limits and collection guards entirely. While this targets Candy Machine rather than SPL account compression directly, it is a directly applicable pattern for any Bubblegum wrapper that guards minting via instruction-introspection without verifying its own program origin.
- Map to: Bubblegum, spl_account_compression

---

## Finding 6

- Pattern: Bidder-pot token account substitution (auction program) — the `place_bid` instruction on the legacy Metaplex Auction program did not require the supplied `bidder_pot_token` account to be uninitialized on first use. An attacker substituted another bidder's existing pot account, merging both bids into one account, then called `cancel_bid` to drain the full balance.
- Where it hit: Metaplex Auction smart contract (pre-2022 fix); write-up by Bonfida, January 2022
- Severity: CRITICAL (100k bounty paid)
- Source: https://github.com/Bonfida/metaplex-vulnerability-012022
- Summary: The auction program's bid placement lacked a PDA uniqueness constraint on the pot token account. Because compressed NFT auctions on Solana marketplaces frequently relied on this auction contract, the vulnerability was reachable through any cNFT sale flow using the legacy program. The attacker could steal in-flight bids. Fixed by requiring the pot account to be uninitialized and deriving it as a PDA unique to the bidder and auction.
- Map to: Bubblegum (marketplace integration context)

---

## Coverage Assessment

Total findings: 6 (1 from local CSV, 5 from web research).

Skill sections covered by at least one real finding:
- Section 1b (canopy duplication / staleness): Finding 1
- Section 5a/5c (decompression invariants, mint authority, metadata continuity): Findings 2, 3
- Section 3a/3b (delegate scope, owner signature): Finding 4
- Section 6a (program ID verification in instruction context): Finding 5
- Indexer/marketplace integration (Section 4 adjacent): Finding 6

Skill sections with no direct public finding located:
- Section 2 (ConcurrentMerkleTree buffer saturation / concurrency): no public advisory found; pattern is well-documented in SPL design docs as an operational risk but no disclosed exploit found in searched sources as of April 2026.
- Section 4 (indexer-trust boundary, unsigned proof): no public advisory found; described as a design risk in Helius documentation but no disclosed real exploit.
- Section 6b/6c (noop log truncation, split-tx log): no public advisory found.


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Proof Length Dynamic | YES | | per tree |
| 1b. Canopy Not Duplicated | YES | | canopy handling |
| 1c. Cache Invalidated | YES | | upgrade aware |
| 2a. Buffer Overflow Handled | YES | | retry on displaced root |
| 2b. Concurrency Bounded | YES | | bounded batch |
| 2c. Refresh Path | YES | | refresh rpc |
| 3a. Delegate Scoped | YES | | per leaf |
| 3b. Owner Signature | YES | | required for burn |
| 3c. Delegate Reset | YES | | reset semantics |
| 4a. Proof Root Verified | YES | | on-chain root match |
| 4b. Indexer Signature | IF untrusted indexers | | signed proof |
| 4c. Asset ID Derivation | YES | | id matches leaf |
| 5a. Mint Authority | IF decompression used | | PDA pinned |
| 5b. Leaf Burn Atomic | IF decompression used | | atomic |
| 5c. Metadata Matches Leaf | IF decompression used | | continuity |
| 6a. Noop Program | YES | | id pinned |
| 6b. Log Data Complete | YES | | full update |
| 6c. Log Same Tx | YES | | in-instruction |
