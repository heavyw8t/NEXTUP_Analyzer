---
name: "metaplex-nft-standard"
description: "Protocol Type Trigger metaplex_nft_standard (detected when recon finds mpl_token_metadata|mpl_core|TokenStandard|Metadata|MasterEdition|verify_creator|verify_collection|RuleSet - protocol USES Metaplex standards)"
---

# Injectable Skill: Metaplex NFT Standard Security

> Protocol Type Trigger: `metaplex_nft_standard` (detected when recon finds: `mpl_token_metadata`, `mpl_core`, `TokenStandard`, `Metadata`, `MasterEdition`, `verify_creator`, `verify_collection`, `RuleSet`)
> Inject Into: depth-external, depth-edge-case
> Language: Solana only
> Finding prefix: `[MPL-N]`
> Relationship to compressed-nft-integration: both are NFT standards on Solana. Activate both when a protocol mixes cNFT and token-metadata NFTs.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-edge-case (creator verified flag)
- Section 2: depth-external (royalty enforcement across standards)
- Section 3: depth-external (update authority lifecycle)
- Section 4: depth-edge-case (burn and reclaim invariants)
- Section 5: depth-external (RuleSet / auth rules trust)
- Section 6: depth-external (MPL Core vs Token Metadata divergence)

## When This Skill Activates

Recon detects the protocol mints, transfers, burns, lists, or validates NFTs via Metaplex Token Metadata or MPL Core, such as marketplaces, lending markets, staking programs, or launchpads.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: mpl_token_metadata, mpl_core, TokenStandard, Metadata, MasterEdition, verify_creator, verify_collection
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[MPL-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Creator Verified Flag Enforcement

### 1a. Verified Creator Check
- Does the program verify the creator is `verified=true` in metadata, or trust the creator field?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program validates collection membership by any listed creator; attacker lists themselves as unverified creator and passes check.

### 1b. Collection Field vs Collection Creator
- Collection membership is proven by the `collection` field with `verified=true`, not by `creators`. Does the program use the right field?
- Real finding pattern (Cantina, pattern observed in multiple audits): Program uses creator index 0 as collection proxy; attacker sets first creator to legitimate collection key while actual NFT is unrelated.

### 1c. Partial Verification
- When only some creators are verified, royalty splits may distribute to unverified creators. Does the program ignore unverified?
- Real finding pattern (pattern observed in multiple audits): Royalty routed to attacker-listed unverified creator.

Tag: [TRACE:creator_verified_flag_checked=YES/NO → collection_field_used=YES/NO → unverified_creator_ignored=YES/NO]

---

## 2. Royalty Enforcement Across TokenStandard Variants

### 2a. TokenStandard Handling
- `TokenStandard::NonFungible`, `ProgrammableNonFungible`, `NonFungibleEdition` have different royalty paths. Does the program branch correctly?
- Real finding pattern (pattern observed in multiple audits): Marketplace enforces royalty only for `ProgrammableNonFungible`; legacy NFTs bypass royalty.

### 2b. Seller Fee Basis Points Upper Bound
- Upper bound on SFBP must be enforced (10000). Some programs allow arbitrary values causing overflow when scaled.
- Real finding pattern (pattern observed in multiple audits): Unbounded SFBP causes negative seller proceeds after scaling.

### 2c. Royalty Recipient Validation
- Royalty recipient list is from metadata. Does the program validate the token accounts provided match?
- Real finding pattern (pattern observed in multiple audits): Recipient token accounts user-supplied; attacker sends royalty to their own accounts.

Tag: [TRACE:token_standard_branching=correct/uniform → sfbp_upper_bound=YES/NO → royalty_recipient_validated=YES/NO]

---

## 3. Update Authority Lifecycle

### 3a. Update Authority Immutable
- Does the program assume update authority is immutable? It can be transferred.
- Real finding pattern (Solodit, pattern observed in multiple audits): Program caches update authority at registration; authority transferred; update check bypasses new owner.

### 3b. Authority Signature Path
- `update_v1` and `update` require the authority to sign; does the program verify?
- Real finding pattern (pattern observed in multiple audits): Program relies on delegate signer; unauthorized update succeeds.

### 3c. Frozen Metadata
- `primary_sale_happened` and `is_mutable` are one-way flags. Programs must not assume mutability.
- Real finding pattern (pattern observed in multiple audits): Program assumes metadata will be updated post-mint; NFT is immutable; update path reverts.

Tag: [TRACE:update_authority_rechecked=YES/NO → authority_signature_required=YES/NO → mutability_checked=YES/NO]

---

## 4. Burn and Reclaim Invariants

### 4a. Burn Requires Metadata Update
- Burning a programmable NFT requires closing associated metadata accounts. Does the program?
- Real finding pattern (pattern observed in multiple audits): Burn instruction closes mint but leaves metadata and master edition; NFT appears to exist in indexers.

### 4b. Reclaim Escrowed NFT
- Escrow patterns (lending, staking) must verify the escrowed NFT's metadata at reclaim.
- Real finding pattern (Cantina, pattern observed in multiple audits): Program reclaims on mint key only; attacker swaps metadata and steals an escrowed item.

### 4c. Master Edition Burn
- Burning the master edition of a printed set destroys the source of prints. Confirm the program wants this.
- Real finding pattern (pattern observed in multiple audits): Burn path reaches master edition unintentionally; collection supply broken.

Tag: [TRACE:burn_closes_all_accounts=YES/NO → reclaim_checks_metadata=YES/NO → master_edition_burn_guarded=YES/NO]

---

## 5. RuleSet Resolution and Auth-Rules Trust

### 5a. RuleSet Program Pin
- Programmable NFT transfers go through the `mpl_token_auth_rules` program. Does the program pin the ID?
- Real finding pattern (pattern observed in multiple audits): Attacker supplies an auth-rules-like program that approves any transfer.

### 5b. RuleSet Version Pin
- RuleSet revisions can change allowed actions. Does the program check a specific revision?
- Real finding pattern (pattern observed in multiple audits): RuleSet updated to allow self-approved transfers; protocol trust relies on old behavior.

### 5c. Delegate vs Authority
- Programmable NFTs have distinct delegate roles; does the program use the correct one for the action?
- Real finding pattern (pattern observed in multiple audits): Program calls `transfer` as authority without holding Transfer delegate; fails silently.

Tag: [TRACE:auth_rules_program_pinned=YES/NO → ruleset_revision_pinned=YES/NO → delegate_role_correct=YES/NO]

---

## 6. MPL Core vs Token Metadata Divergence

### 6a. Account Model Difference
- MPL Core uses a single `Asset` account. Token Metadata uses mint + metadata + edition. A program assuming one model fails on the other.
- Real finding pattern (pattern observed in multiple audits): Marketplace supports both but uses Token Metadata layout for MPL Core; parsing corrupts fields.

### 6b. Plugin Model Trust
- MPL Core plugins (royalty, freeze, attributes) live inside the Asset. Programs must check expected plugins.
- Real finding pattern (pattern observed in multiple audits): Royalty plugin absent; marketplace assumes default royalty; zero royalty paid.

### 6c. Collection Model
- MPL Core collections and Token Metadata collections have different verification. Does the program unify correctly?
- Real finding pattern (pattern observed in multiple audits): Program verifies collection via Token Metadata path for an MPL Core asset; verification always false.

Tag: [TRACE:account_model_branching=correct/uniform → plugin_expectations_checked=YES/NO → collection_verification_per_standard=YES/NO]

---

## Common False Positives

- Program only reads `name`/`symbol` for display, no economic effect. Most sections do not apply.
- Program handles one pinned collection and fixed TokenStandard. Section 2a and 6 reduced.
- Program uses a trusted delegate signer that enforces royalty in escrow. Section 2 partially delegated.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Verified Creator | YES | | flag enforced |
| 1b. Collection Field | YES | | correct proof |
| 1c. Unverified Creator Ignored | YES | | royalty routing |
| 2a. TokenStandard Branching | YES | | per-variant path |
| 2b. SFBP Upper Bound | YES | | 10000 enforced |
| 2c. Royalty Recipient | YES | | account validated |
| 3a. Update Authority Rechecked | YES | | rotation aware |
| 3b. Authority Signature | YES | | signed by authority |
| 3c. Mutability Checked | YES | | is_mutable honored |
| 4a. Burn Closes Accounts | YES | | full cleanup |
| 4b. Reclaim Checks Metadata | YES | | metadata matches |
| 4c. Master Edition Burn | IF master edition in scope | | guard |
| 5a. Auth Rules Program | IF pNFT used | | program id pinned |
| 5b. RuleSet Revision | IF pNFT used | | revision pinned |
| 5c. Delegate Role | IF pNFT used | | correct role |
| 6a. Account Model | IF MPL Core + TM both | | correct branch |
| 6b. Plugin Expectations | IF MPL Core | | plugin present |
| 6c. Collection per Standard | IF both | | verification path |
