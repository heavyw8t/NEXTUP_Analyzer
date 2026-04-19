---
name: "wormhole-bridge-integration"
description: "Protocol Type Trigger wormhole_bridge_integration (detected when recon finds wormhole_core_bridge|wormhole_anchor|VAA|PostedVaaV1|post_vaa|token_bridge|nft_bridge|guardian_set|emitter_chain|parse_and_verify_vaa - protocol USES Wormhole)"
---

# Injectable Skill: Wormhole Bridge Integration Security

> Protocol Type Trigger: `wormhole_bridge_integration` (detected when recon finds: `wormhole_core_bridge`, `wormhole_anchor`, `VAA`, `PostedVaaV1`, `post_vaa`, `token_bridge`, `nft_bridge`, `guardian_set`, `emitter_chain`, `parse_and_verify_vaa`)
> Inject Into: depth-external, depth-edge-case, depth-state-trace
> Language: Solana only
> Finding prefix: `[WH-N]`
> Relationship to metaplex-nft-standard: NFT bridge VAAs interact with Metaplex metadata. Activate both when NFT bridging is in scope.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (guardian signature quorum and set freshness)
- Section 2: depth-state-trace (VAA replay protection)
- Section 3: depth-external (emitter chain + address validation)
- Section 4: depth-edge-case (payload length / field bounds)
- Section 5: depth-edge-case (attestation vs transfer VAA type confusion)
- Section 6: depth-edge-case (foreign-address canonicalization)

## When This Skill Activates

Recon detects use of Wormhole core bridge or token bridge on Solana, including relayer programs, cross-chain messaging integrations, or any consumption of `PostedVaaV1` accounts.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: wormhole, VAA, PostedVaaV1, parse_and_verify_vaa, guardian_set, emitter_chain, token_bridge
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[WH-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Guardian Signature Quorum and Set Freshness

### 1a. Active Guardian Set
- Does the program verify the VAA was signed by the current `guardian_set_index`? Expired sets can sign under historical indices.
- Real finding pattern (Solodit, pattern observed in multiple audits): Program accepts VAAs signed by old guardian set index; compromised historical guardians can forge messages.

### 1b. Quorum Arithmetic
- Wormhole quorum is `(2*num_guardians/3) + 1`. Does the program recompute or trust the VAA?
- Real finding pattern (pattern observed in multiple audits): Program reads `num_signatures` from the VAA directly; attacker crafts a VAA claiming high signatures.

### 1c. Core Bridge Owner Check
- Does the program verify `posted_vaa.owner == core_bridge_program`?
- Real finding pattern (pattern observed in multiple audits): Posted VAA account not owned-checked; attacker supplies a crafted account.

Tag: [TRACE:guardian_set_current=YES/NO → quorum_recomputed=YES/NO → core_bridge_owner_checked=YES/NO]

---

## 2. VAA Replay Protection

### 2a. Consumed VAA Marker
- A VAA must be processed only once. Does the program create a PDA `consumed_vaa` to prevent replay?
- Real finding pattern (Sherlock, pattern observed in multiple audits): Program processes the same VAA twice because the consumed marker used sequence only, and attacker replays with different hash but same sequence.

### 2b. Hash-Based Dedup
- Dedup must be based on the full VAA hash, not merely sequence or emitter.
- Real finding pattern (pattern observed in multiple audits): Program dedups on (emitter_chain, emitter_address, sequence); attacker posts a second valid VAA with same seq after guardians re-sign a recovery message.

### 2c. Consume-Before-Effect
- Mark VAA consumed before side effects (token transfer, call). Otherwise a failed side effect leaves VAA replayable.
- Real finding pattern (pattern observed in multiple audits): Program transfers tokens, then marks consumed. Revert on transfer leaves consumed unset; user replays.

Tag: [TRACE:consumed_vaa_pda=YES/NO → dedup_uses_hash=YES/NO → mark_before_effect=YES/NO]

---

## 3. Emitter Chain and Address Validation

### 3a. Expected Emitter
- Every message must come from an expected emitter (chain, address). Does the program enforce both?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program checks only emitter chain; attacker uses a different emitter on that chain.

### 3b. Emitter Allowlist
- If the program handles multiple emitters, the allowlist must be tight and governance-controlled.
- Real finding pattern (pattern observed in multiple audits): Program uses a single mutable emitter key; attacker's governance proposal adds their own address.

### 3c. Emitter Address Padding
- Addresses are 32 bytes; EVM addresses are 20. Does the program compare canonical left-padded form?
- Real finding pattern (pattern observed in multiple audits): Program compares raw 32 bytes to a right-padded literal; legitimate emitter rejected.

Tag: [TRACE:emitter_chain_and_address_checked=YES/NO → allowlist_tight=YES/NO → address_canonicalization=YES/NO]

---

## 4. Payload Length / Field Bounds

### 4a. Payload Offset Bounds
- The program reads fields at fixed offsets; out-of-bounds reads panic in debug, wrap in release.
- Real finding pattern (pattern observed in multiple audits): Program indexes payload without length check; crafted short payload read uninitialized zeros as `amount`.

### 4b. Integer Width
- Token bridge uses 256-bit amounts truncated to u64 on Solana. Does the program check high bits are zero?
- Real finding pattern (Cantina, pattern observed in multiple audits): High bits ignored; amount wraps to a small positive value.

### 4c. Variable-Length Memo Fields
- Payload type 3 (transfer with payload) has a variable-length memo. Parsing must respect declared length.
- Real finding pattern (pattern observed in multiple audits): Memo parsed by slicing to end-of-vaa; extra bytes let attackers smuggle commands.

Tag: [TRACE:payload_length_checked=YES/NO → u256_high_bits_zero=YES/NO → memo_length_bounded=YES/NO]

---

## 5. Attestation vs Transfer VAA Type Confusion

### 5a. Payload Type Byte
- Token Bridge payload type 1 = transfer, 2 = attestation, 3 = transfer with payload. Does the program check before acting?
- Real finding pattern (pattern observed in multiple audits): Program processes any VAA as transfer; attestation VAA's fields reinterpreted as amount and recipient.

### 5b. Attestation-Only State
- Attestation should only update metadata, not transfer tokens. A type check prevents misuse.
- Real finding pattern (pattern observed in multiple audits): Attestation handler also increments balances; bug produces tokens out of thin air.

### 5c. Governance VAA
- Governance VAAs (config changes) must be distinguished from user VAAs. Merging paths lets users rotate fees.
- Real finding pattern (pattern observed in multiple audits): Governance VAA processed via user path; sensitive config fields misread as amount.

Tag: [TRACE:payload_type_checked=YES/NO → attestation_isolated=YES/NO → governance_vaa_isolated=YES/NO]

---

## 6. Foreign-Address Canonicalization

### 6a. Address Derivation
- Programs that mint wrapped representations must derive mint from (origin chain, origin address). Mismatch gives wrong mint.
- Real finding pattern (pattern observed in multiple audits): Program uses lowercase hex for EVM address; VAA carries raw bytes; mint mismatch created two distinct wrapped mints for same asset.

### 6b. Self-Asset vs Foreign-Asset
- The program must distinguish "this chain's token being redeemed" vs "a foreign token being minted".
- Real finding pattern (pattern observed in multiple audits): Foreign-asset branch chosen for native SOL; wrapped SOL mint created on home chain.

### 6c. Recipient Canonicalization
- Recipient address on Solana must be a valid token account for the correct mint.
- Real finding pattern (pattern observed in multiple audits): Program uses `recipient` as raw pubkey and creates an ATA when the recipient is actually a program account; tokens locked.

Tag: [TRACE:wrapped_mint_derivation=canonical/broken → self_vs_foreign_branch_correct=YES/NO → recipient_is_valid_token_account=YES/NO]

---

## Common False Positives

- Program only posts messages and never consumes VAAs. Sections 2 to 6 do not apply.
- Program uses a dedicated relayer SDK that verifies VAAs on its behalf with pinned versions.
- Program handles only one specific token with a single emitter and pinned mint. Section 3b reduced.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Active Guardian Set | YES | | current index |
| 1b. Quorum Recomputed | YES | | 2/3+1 |
| 1c. Core Bridge Owner | YES | | owner check |
| 2a. Consumed VAA PDA | YES | | replay guard |
| 2b. Hash-Based Dedup | YES | | full hash |
| 2c. Mark Before Effect | YES | | ordering |
| 3a. Chain + Address | YES | | both verified |
| 3b. Allowlist Tight | YES | | governance controlled |
| 3c. Address Canonicalization | YES | | padding form |
| 4a. Payload Length | YES | | bounds checked |
| 4b. u256 High Bits | YES | | zero check |
| 4c. Memo Length | IF payload type 3 | | length respected |
| 5a. Payload Type | YES | | type byte checked |
| 5b. Attestation Isolation | YES | | no token effects |
| 5c. Governance Isolation | YES | | separate path |
| 6a. Wrapped Mint Derivation | IF wrapping used | | canonical |
| 6b. Self vs Foreign | YES | | branch correctness |
| 6c. Recipient Token Account | YES | | valid ATA |
