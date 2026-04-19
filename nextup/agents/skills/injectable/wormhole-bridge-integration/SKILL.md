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

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sources searched: Solodit, Halborn, Kudelski, Ackee Blockchain, Code4rena, GitHub wormhole-foundation, marcohextor, immunefi, sec3.dev, Pyth DAO forum.

---

## Finding 1

- Pattern: `verify_signatures` reads from a fake account instead of the real `sysvar::instructions` because `load_instruction_at` (deprecated) does not validate the account owner, allowing an attacker to substitute a crafted account that mimics successful Secp256k1 output.
- Where it hit: Wormhole Solana core bridge, `verify_signatures` instruction, February 2022 mainnet exploit.
- Severity: CRITICAL
- Source: https://ackee.xyz/blog/2022-solana-hacks-explained-wormhole/ | https://research.kudelskisecurity.com/2022/02/03/quick-analysis-of-the-wormhole-attack/ | https://www.halborn.com/blog/post/explained-the-wormhole-hack-february-2022
- Summary: The Wormhole Solana contract used `load_instruction_at` (deprecated) to verify that a Secp256k1 instruction preceded `verify_signatures`. The function does not assert that the source account is the canonical `Sysvar1nstructions` sysvar, so the attacker passed a crafted account containing fabricated instruction data showing verified signatures. No guardian signatures were actually checked; the VAA was marked valid and 120,000 wETH ($326M) were minted. The fix replaced the call with `load_instruction_at_checked`, which validates the sysvar account key. This is the canonical Solana account-ownership-check failure applied to the guardian quorum verification path.
- Map to: `wormhole_core_bridge`, `guardian_set`, `parse_and_verify_vaa`, `VAA`

---

## Finding 2

- Pattern: Guardian set expiration check uses `expiration_time == 0` as the sentinel for "never expires", but the first two guardian sets both used the same key and were never given a non-zero expiration time, allowing that single genesis key to pass any VAA instead of requiring the full 13-of-19 quorum.
- Where it hit: Wormchain (Wormhole's Cosmos chain), guardian set state logic; Wormhole team confirmed a parallel variant was also present on Solana and patched separately via a hardcoded exception for the initial guardian set.
- Severity: CRITICAL
- Source: https://marcohextor.com/wormhole-one-key-vulnerability/
- Summary: The VAA verification loop checks expiration as `if 0 < guardianSet.ExpirationTime && guardianSet.ExpirationTime < blockTime`. Because the genesis guardian set carries `ExpirationTime == 0` it is permanently treated as valid. The first two guardian sets shared one key, so one specific private key could satisfy any quorum check on its own. The Wormhole team confirmed that Solana received a parallel fix (hardcoded rejection of the initial set) before this was reported on Wormchain. Bug bounty paid $50,000 USDC, January 2024.
- Map to: `guardian_set`, `wormhole_core_bridge`, `VAA`, `parse_and_verify_vaa`

---

## Finding 3

- Pattern: A protocol that queues governance proposals via Wormhole VAAs and re-verifies them at execution time is broken when the guardian set rotates between queue and execute: the second `parseAndVerifyVM` call fails because the signature set in the stored VAA references the old guardian set index, which may now be expired.
- Where it hit: Moonwell `TemporalGovernor` contract, Code4rena audit July 2023 (issue #325).
- Severity: MEDIUM
- Source: https://github.com/code-423n4/2023-07-moonwell-findings/issues/325 | https://code4rena.com/reports/2023-07-moonwell
- Summary: `TemporalGovernor.executeProposal` re-runs `parseAndVerifyVM` on the raw VAA bytes stored at queue time. If Wormhole rotates its guardian set during the mandatory `proposalDelay` window, the stored VAA's signatures reference the now-expired set and the second verification reverts. The proposal can never execute, forcing a full re-submission from the source chain timelock and another delay cycle. Fix: store only the decoded, already-verified payload hash at queue time and skip re-verification at execution, or replace the raw VAA with a guardian-set-agnostic commitment.
- Map to: `guardian_set`, `VAA`, `parse_and_verify_vaa`, `wormhole_core_bridge`

---

## Finding 4

- Pattern: Token bridge transfer VAA specifies a recipient address on Solana that is the user's wallet pubkey (or an incorrect ATA), not the actual Associated Token Account for the mint. The Solana token bridge program requires the recipient to be a valid ATA for `(receiver, mint)`; any mismatch causes the redemption instruction to fail permanently and the tokens are locked with no refund path.
- Where it hit: Wormhole Solana token bridge, reported as a design-level issue in GitHub issue #3992 by the Wormhole team itself after user reports of locked funds.
- Severity: HIGH (funds permanently locked, no recovery before the fix)
- Source: https://github.com/wormhole-foundation/wormhole/issues/3992
- Summary: Users bridging tokens from EVM chains to Solana frequently supplied their Solana wallet address as the recipient rather than the ATA for `(wallet, mint)`. The token bridge's `complete_transfer` family of instructions validates the recipient account against the PDA-derived mint and rejects non-ATA recipients with no fallback. Tokens were permanently irrecoverable until Wormhole shipped a new instruction allowing the wallet owner to submit the original VAA for corrective redemption or cross-chain refund. The underlying risk pattern is: recipient canonicalization on Solana is stricter than on EVM; any program consuming Wormhole transfer VAAs must derive and enforce the ATA before accepting the recipient field.
- Map to: `token_bridge`, `VAA`, `wormhole_core_bridge`

---

## Finding 5

- Pattern: Wormhole's Solana core contract had a guardian set expiration bug (`OldGuardianSet` error) where the second guardian set upgrade caused VAAs signed by the transitional set to be rejected because the expiration timestamp was set incorrectly during the rotation governance instruction.
- Where it hit: Wormhole Solana core bridge, guardian set upgrade path, GitHub issue #110.
- Severity: HIGH (all VAAs from the transitional guardian set became unverifiable, breaking the bridge)
- Source: https://github.com/wormhole-foundation/wormhole/issues/110 | https://gitea.interbiznw.com/certusone/wormhole-entropybitcom/commit/82fd4293e2a869b1b83e1f8cfac808eec0276e8b
- Summary: After the second guardian set rotation on Solana mainnet, VAA verification returned `OldGuardianSet` for messages signed by the new set. Root cause: the governance upgrade instruction wrote the expiration time of the old set using an off-by-one in the clock value, causing the newly-active set to appear expired immediately. The fix (commit `82fd429`) corrected the expiration timestamp assignment logic in the guardian set rotation handler. This demonstrates that the guardian set index freshness check is fragile: both the acceptance logic (finding 2) and the rotation logic (this finding) must be correct or the entire bridge halts.
- Map to: `guardian_set`, `wormhole_core_bridge`, `VAA`, `parse_and_verify_vaa`

---

## Finding 6

- Pattern: Settlement instructions in a Wormhole CCTP-based fast-finality bridge assume `order_amount` from the `fastVAA` payload equals the token balance in the `prepared_custody_token` account. If fees or rounding create a discrepancy, the account-close instruction fails because it requires a zero balance, and the custody account cannot be reclaimed.
- Where it hit: Wormhole CCTP fast-finality auction settlement on Solana (local CSV, row 6364).
- Severity: HIGH
- Source: Local CSV (solodit_findings.dedup.csv row 6364); patch commit 307cc28 in wormhole-foundation repository.
- Summary: The settlement path reads `order_amount` directly from the decoded fastVAA payload and uses it as the transfer amount. If the actual token balance in `prepared_custody_token` differs (due to dust, rounding, or fee deductions), the transfer leaves a non-zero balance and the subsequent `close_account` CPI reverts. Fix: use the live token balance from the `prepared_custody_token` account rather than the VAA-derived amount, ensuring exact accounting before account closure.
- Map to: `VAA`, `token_bridge`, `wormhole_core_bridge`

---

## Coverage note

Six findings documented (1 from local CSV, 5 from web research). All are Solana-side consumer bugs or Wormhole core contract bugs affecting Solana. No live Solodit API was queried. Sources include post-mortem analyses, GitHub issues in the wormhole-foundation repository, a Code4rena audit report, and an independent bug bounty disclosure. The Cantina and OtterSec Solana-specific audit PDFs in wormhole-foundation/wormhole-audits were not directly accessible via search; those may contain additional emitter-address and payload-type findings not captured here.


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
