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
