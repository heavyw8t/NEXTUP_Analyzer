---
name: "squads-multisig-integration"
description: "Protocol Type Trigger squads_multisig_integration (detected when recon finds squads_mpl|squads_v4|Multisig|VaultTransaction|Proposal|create_proposal|approve|execute_vault_transaction|program_config - protocol USES Squads multisig)"
---

# Injectable Skill: Squads Multisig Integration Security

> Protocol Type Trigger: `squads_multisig_integration` (detected when recon finds: `squads_mpl`, `squads_v4`, `Multisig`, `VaultTransaction`, `Proposal`, `create_proposal`, `approve`, `execute_vault_transaction`, `program_config`)
> Inject Into: depth-external, depth-edge-case, depth-state-trace
> Language: Solana only
> Finding prefix: `[SQD-N]`
> Relationship to jito-mev-bundle-integration: multisig-triggered execution is sometimes submitted via bundles. Activate both when timing matters.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-state-trace (proposal-to-transaction binding)
- Section 2: depth-edge-case (time-lock bypass via re-proposal)
- Section 3: depth-state-trace (members list mutation mid-proposal)
- Section 4: depth-external (vault vs controlled authority derivation)
- Section 5: depth-state-trace (instruction buffer integrity)
- Section 6: depth-edge-case (stale proposal after threshold change)

## When This Skill Activates

Recon detects that the protocol uses Squads multisig (v3 / v4) for treasury or admin authorities, including authority PDAs, proposal creation and execution flows.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: squads, Multisig, VaultTransaction, Proposal, create_proposal, execute_vault_transaction
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[SQD-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Proposal-to-Transaction Binding / Buffer Tamper

### 1a. Transaction Hash Binding
- Proposal must bind to the exact instruction buffer hash. If binding is weak, an approved proposal can be executed with different instructions.
- Real finding pattern (Solodit, pattern observed in multiple audits): Integration stores proposal by index without hash check; a parallel buffer upload replaces instructions before execution.

### 1b. Buffer Upload Authority
- Buffer upload must be authorized to a proposer. Does the program enforce?
- Real finding pattern (pattern observed in multiple audits): Any signer can append to the buffer; attacker adds malicious instruction between approve and execute.

### 1c. Buffer Freeze Before Approve
- Does the program require the buffer be frozen (finalized) before approvals begin?
- Real finding pattern (pattern observed in multiple audits): Approvals can be cast against a mutable buffer; approvers think they approved A but execute B.

Tag: [TRACE:proposal_hash_binding=YES/NO → buffer_upload_authorized=YES/NO → buffer_frozen_before_approve=YES/NO]

---

## 2. Time-Lock Bypass via Re-Proposal

### 2a. Cooldown Reset
- If a proposal is canceled and re-created with identical payload, does time-lock reset properly?
- Real finding pattern (Cantina, pattern observed in multiple audits): Re-proposal inherits prior approvals; time-lock effectively skipped.

### 2b. Batch Execution
- Batch proposal executing many instructions should honor time-lock for each. Does the program check per-instruction?
- Real finding pattern (pattern observed in multiple audits): Batch executes all instructions under proposal-level time-lock; sensitive instructions need stricter lock.

### 2c. Emergency Path Exploit
- Emergency-bypass paths need strict signer gating.
- Real finding pattern (pattern observed in multiple audits): Emergency guardian key can bypass time-lock unilaterally; single-key compromise bypasses multisig entirely.

Tag: [TRACE:timelock_reset_on_replay=YES/NO → per_instruction_timelock=YES/NO → emergency_path_gated=YES/NO]

---

## 3. Members List Mutation Mid-Proposal

### 3a. Member Removal Mid-Vote
- Can a member be removed while an active proposal retains their approval?
- Real finding pattern (Solodit, pattern observed in multiple audits): Member removed after approve; count still includes their vote; proposal passes with stale signatures.

### 3b. Member Addition Mid-Vote
- New member added mid-proposal should not be able to approve a proposal from before their membership.
- Real finding pattern (pattern observed in multiple audits): Newly added member approves historical proposal; threshold achieved.

### 3c. Member Role Change
- Members have roles (Proposer, Approver, Executor). Role change mid-proposal must be consistent.
- Real finding pattern (pattern observed in multiple audits): Role downgraded from approver to proposer but prior approval still counts.

Tag: [TRACE:removal_invalidates_votes=YES/NO → new_member_cant_approve_old_proposal=YES/NO → role_change_invalidates=YES/NO]

---

## 4. Vault vs Controlled Authority Derivation

### 4a. Vault PDA Seed
- The vault PDA is derived from multisig pubkey and vault index. Does the integration use the expected seed?
- Real finding pattern (pattern observed in multiple audits): Integration derives vault with wrong seeds; expected authority mismatch; treasury not drainable through expected flow.

### 4b. Controlled Authority Claim
- Some integrations set a Squads vault as owner of downstream PDAs. Does each downstream program verify the vault signer correctly?
- Real finding pattern (pattern observed in multiple audits): Downstream PDA check allows any squads-derived authority, including an unrelated multisig's vault.

### 4c. Multi-Vault Confusion
- Multisigs can host multiple vaults. Integration must bind to a specific vault index.
- Real finding pattern (pattern observed in multiple audits): Integration accepts any vault from the multisig; attacker multisig member controls a low-index vault.

Tag: [TRACE:vault_pda_seeds_correct=YES/NO → downstream_authority_checks_multisig_pubkey=YES/NO → vault_index_bound=YES/NO]

---

## 5. Instruction Buffer Integrity Across Approve-Reject

### 5a. Reject-Then-Approve Replay
- Can a member reject, then approve again after edit? Does the program track stance?
- Real finding pattern (pattern observed in multiple audits): Stance toggles reset counters incorrectly, allowing double-count of approvals.

### 5b. Stale Approval After Edit
- If the buffer is edited, prior approvals should be invalidated.
- Real finding pattern (Solodit, pattern observed in multiple audits): Edit does not invalidate approvals; approvers bound to buffer A but execute payload B.

### 5c. Cross-Proposal Buffer Sharing
- If two proposals share a buffer, edit to one impacts the other.
- Real finding pattern (pattern observed in multiple audits): Proposal A and B point at the same buffer; execute A rewrites state that B depends on, causing replay to behave differently.

Tag: [TRACE:stance_tracked=YES/NO → edit_invalidates_approvals=YES/NO → buffer_per_proposal=YES/NO]

---

## 6. Stale Proposal After Threshold Change

### 6a. Threshold Retroactive
- When threshold increases, existing proposals with the old threshold may still be executable.
- Real finding pattern (pattern observed in multiple audits): Threshold raised from 2/3 to 3/3; a proposal with 2 approvals remains executable under the old rule.

### 6b. Proposal Expiration
- Does the program enforce expiry on proposals, or do they sit indefinitely?
- Real finding pattern (pattern observed in multiple audits): Indefinite proposals become security risk as membership changes.

### 6c. Config Change + Proposal Atomicity
- Config-change proposals and executable proposals need serialized ordering. Otherwise a config change creates a window for stale proposal execution.
- Real finding pattern (pattern observed in multiple audits): Stale proposal executed in a slot after config change; invariant broken.

Tag: [TRACE:threshold_retroactively_enforced=YES/NO → proposal_expiry=YES/NO → config_change_serialized=YES/NO]

---

## Common False Positives

- Protocol uses Squads only for owning a single admin PDA with a single instruction pattern. Sections 2 and 5 reduced.
- Protocol interacts with Squads only via UI, not CPI. Section 4 reduced.
- Time-lock disabled by policy. Section 2 does not apply but must be documented.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Proposal Hash Binding | YES | | hash match |
| 1b. Buffer Upload Authorized | YES | | authority check |
| 1c. Buffer Frozen Before Approve | YES | | frozen precondition |
| 2a. Timelock Reset on Replay | YES | | replay safe |
| 2b. Per-Instruction Timelock | IF batched | | per-instruction check |
| 2c. Emergency Gated | IF emergency path | | strict signer set |
| 3a. Removal Invalidates Votes | YES | | revocation |
| 3b. New Member Cannot Approve Old Proposal | YES | | timeline gate |
| 3c. Role Change Invalidates | YES | | role-aware |
| 4a. Vault PDA Seeds | YES | | correct derivation |
| 4b. Downstream Authority | YES | | multisig pubkey bound |
| 4c. Vault Index Bound | YES | | specific index |
| 5a. Stance Tracked | YES | | approve/reject logic |
| 5b. Edit Invalidates Approvals | YES | | hash-revote |
| 5c. Buffer per Proposal | YES | | separation |
| 6a. Threshold Retroactive | YES | | stale proposal closed |
| 6b. Proposal Expiry | YES | | finite lifetime |
| 6c. Config Change Serialized | YES | | ordering guarantee |
