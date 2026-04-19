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

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Domain: metaplex-nft-standard (mpl_token_metadata, mpl_core, TokenStandard, MasterEdition, verify_creator, verify_collection, RuleSet)
> Sources searched: OShield/MadShield audit reports, Bonfida vulnerability disclosure, Andy Kutruff blog, Perma DAO audit summary, SolShield writeups.

---

- Pattern: Unauthorized collection assignment via delegated collection authority record lacking update-authority binding
  Where it hit: mpl_token_metadata `verify_collection` / `set_and_verify_collection` instruction; collection authority record PDA
  Severity: CRITICAL
  Source: https://medium.com/@oshield/a-smorgasbord-or-on-how-to-nitpick-your-metaplex-nft-collection-84dfd172e574
  Summary: The collection authority record did not store the update authority that approved the delegation. An attacker could therefore approve themselves as a delegate for any NFT's collection field, set the collection to their own collection NFT, and then burn the collection NFT, permanently locking the on-chain collection field to a fraudulent value. Marketplaces, AMMs, and staking programs that accept NFTs by verified collection membership were directly exposed. The fix added the update authority to the collection authority record PDA and validated it on every assert.
  Map to: verify_collection, mpl_token_metadata

---

- Pattern: Re-initialization of an already-initialized Candy Machine account, allowing the attacker to redirect sale proceeds to themselves
  Where it hit: Metaplex Candy Machine v2 `initialize` instruction; candy machine config account
  Severity: CRITICAL
  Source: https://medium.com/@oshield/smashing-the-candy-machine-for-fun-and-profit-a3bcc58d6c30
  Summary: The `initialize` instruction did not verify that the candy machine account was uninitialized before writing to it. An attacker could pass an already-created candy machine account back to the instruction and overwrite the `wallet` field with their own address, hijacking all future mint proceeds. The same flaw also allowed minting an unlimited number of NFTs from the collection and draining the rent-lamport balance held by every deployed candy machine. Fixed by changing the account constraint from `init_if_needed` to `init` in the Anchor definition.
  Map to: mpl_token_metadata (Candy Machine uses mpl_token_metadata for minting)

---

- Pattern: Bidder-pot token account substitution in `place_bid` allows an attacker to merge another bidder's funds and drain them via `cancel_bid`
  Where it hit: Metaplex Auction program `place_bid` instruction; `bidder_pot_token` account parameter
  Severity: CRITICAL
  Source: https://github.com/Bonfida/metaplex-vulnerability-012022
  Summary: The `place_bid` instruction accepted a caller-supplied `bidder_pot_token` account with only the constraint that it be owned by the auction program. Nothing prevented the caller from supplying a `bidder_pot_token` that already contained another bidder's funds. Calling `cancel_bid` then drained the merged account to the attacker's wallet, stealing the other bidder's bid. All active Metaplex auction accounts were at risk. Metaplex awarded a 100 k USD bug bounty. Fixed by requiring the bidder pot token to be an uninitialized PDA.
  Map to: mpl_token_metadata (Auction program mints and transfers Token Metadata NFTs)

---

- Pattern: Auction House creation without authority signature allows attacker to register a fraudulent auction house for any wallet and redirect treasury withdrawals
  Where it hit: Metaplex Auction House `create_auction_house` instruction; `authority` and `treasury_withdrawal_destination` accounts
  Severity: HIGH
  Source: https://akutruff.github.io/blog/posts/2022-10-25-auction-house-creation-account-poisoning
  Summary: The `create_auction_house` instruction did not require the `authority` account to sign the transaction. An attacker could create an auction house for any existing marketplace's wallet, specifying their own address as the `treasury_withdrawal_destination`. When the legitimate marketplace later called the withdraw instruction, funds would flow to the attacker's account. The attack also enabled creating and executing auctions that the marketplace would not have authorized. The fix added a signer check on the `authority` account.
  Map to: mpl_token_metadata (Auction House transfers NFTs via Token Metadata)

---

- Pattern: pNFT burn instruction can be abused to permanently disable all programmable NFT operations on the targeted asset
  Where it hit: mpl_token_metadata `burn` instruction for `ProgrammableNonFungible` TokenStandard; token record account
  Severity: CRITICAL
  Source: https://medium.com/@perma_dao/metaplex-releases-audit-report-addresses-issues-in-pnfts-token-integration-fe7aa95c9d0e
  Summary: The MadShield 2023 audit of mpl_token_metadata (covering releases February through November 2023) identified a critical flaw in the `burn` path for programmable NFTs where the instruction could be triggered in a way that permanently broke the token record state, making the NFT non-transferable and non-burnable thereafter. This rendered the asset economically worthless while still appearing to exist on-chain. The vulnerability was resolved before public disclosure.
  Map to: mpl_token_metadata, TokenStandard (ProgrammableNonFungible)

---

- Pattern: Transfer instruction for pNFTs does not enforce the assigned RuleSet, allowing royalty and transfer rules to be bypassed entirely
  Where it hit: mpl_token_metadata `transfer` instruction for `ProgrammableNonFungible`; `mpl_token_auth_rules` RuleSet evaluation
  Severity: CRITICAL
  Source: https://medium.com/@perma_dao/metaplex-releases-audit-report-addresses-issues-in-pnfts-token-integration-fe7aa95c9d0e
  Summary: The same MadShield 2023 audit found that the `transfer` instruction for programmable NFTs failed to correctly invoke or assert the auth-rules program under certain code paths, meaning all configured RuleSet rules (including royalty-enforcement allowlists) could be bypassed. A second critical finding showed that the `allowlist` rule specifically within the RuleSet could be bypassed even when the RuleSet was evaluated. Both issues were fixed and resolved before public disclosure.
  Map to: mpl_token_metadata, TokenStandard (ProgrammableNonFungible), RuleSet

---

- Pattern: Non-canonical bump seed accepted by Token Entangler allows permanent lock-up of entangled NFTs
  Where it hit: Metaplex Token Entangler `create_entanglement` / swap instructions; `token_a_escrow` and `token_b_escrow` PDAs; `bump` parameter
  Severity: HIGH
  Source: https://akutruff.github.io/blog/posts/2022-10-19-token-entangler-overview
  Summary: The Token Entangler accepted a caller-supplied `bump` value to derive escrow PDAs instead of requiring the canonical bump from `find_program_address`. Anchor internally uses the canonical bump when creating the account, so a non-canonical bump stored in the account diverged from the one the program later expected when trying to sign for the PDA. This caused swap instructions to fail permanently, locking both NFTs in escrow forever. An attacker could target high-value NFTs and trigger permanent lock-up, suppressing supply and collapsing collection floor prices.
  Map to: mpl_token_metadata (Token Entangler operates on Token Metadata NFTs)


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
