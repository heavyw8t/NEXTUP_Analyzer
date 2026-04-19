---
name: "jito-mev-bundle-integration"
description: "Protocol Type Trigger jito_mev_bundle_integration (detected when recon finds jito_tip|tip_account|bundle|searcher_tip|TIP_PROGRAM_ID|jito_block_engine - protocol USES Jito bundles / MEV tips)"
---

# Injectable Skill: Jito MEV Bundle Integration Security

> Protocol Type Trigger: `jito_mev_bundle_integration` (detected when recon finds: `jito_tip`, `tip_account`, `bundle`, `searcher_tip`, `TIP_PROGRAM_ID`, `jito_block_engine`)
> Inject Into: depth-external, depth-edge-case
> Language: Solana only
> Finding prefix: `[JMEV-N]`
> Relationship to drift-perps-integration and jupiter-aggregator-integration: any MEV-sensitive protocol may send bundles. Activate alongside.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (tip account allowlist)
- Section 2: depth-edge-case (bundle atomicity vs fallback path)
- Section 3: depth-edge-case (tip placement ordering)
- Section 4: depth-external (leader-slot assumption)
- Section 5: depth-edge-case (searcher ordering coupling)
- Section 6: depth-edge-case (tip sizing griefing)

## When This Skill Activates

Recon detects interaction with Jito's tip program, bundle submission patterns, or instructions that assume bundle atomicity such as keeper rebalancers, liquidators, or searcher programs.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/solana.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: jito_tip, tip_account, bundle, searcher_tip, block_engine
3. For every match, record the taxonomy `id` (e.g. `SOL-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[JMEV-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/solana.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Tip Account Allowlist (Eight-Account Rotation)

### 1a. Recipient Allowlist
- Jito publishes eight tip accounts that rotate. Does the program pin the 8-account set, or accept any account?
- Real finding pattern (Solodit, pattern observed in multiple audits): Program accepts any recipient as `tip_account`; griefer redirects tip to their own wallet.

### 1b. Rotation Awareness
- If the program hardcodes one tip account, off-rotation slots may still accept but with no execution benefit.
- Real finding pattern (pattern observed in multiple audits): Program uses one hardcoded account; when that account is off rotation, tips effectively burned with no priority.

### 1c. Owner Check for Tip Program
- Tip accounts are owned by the Jito tip program; owner verification must match.
- Real finding pattern (pattern observed in multiple audits): Program accepts tip account without owner check; attacker passes identically-named account.

Tag: [TRACE:tip_allowlist_size=<n> → rotation_aware=YES/NO → tip_program_owner_checked=YES/NO]

---

## 2. Bundle Atomicity vs Fallback Path

### 2a. Assumed All-or-Nothing
- Bundles are atomic only when scheduled by the Jito block engine. If sent as ordinary transactions, they can partially land.
- Real finding pattern (Sherlock, pattern observed in multiple audits): Program assumes all bundle txs commit together; first tx lands alone leaving state inconsistent.

### 2b. Fallback After Bundle Drop
- When the block engine drops a bundle, the program must recover. Does it retry or fall back?
- Real finding pattern (pattern observed in multiple audits): Dropped bundle leaves funds in an intermediate PDA; no cleanup path.

### 2c. Idempotent Leaves
- Each transaction in the bundle must be idempotent or guarded, because re-submission after drop can repeat.
- Real finding pattern (pattern observed in multiple audits): Rebalance tx increments a counter each call; replay after bundle drop doubles the counter.

Tag: [TRACE:atomicity_assumed_without_bundle_api=YES/NO → fallback_cleanup=YES/NO → idempotent=YES/NO]

---

## 3. Tip Placement Ordering

### 3a. Tip-First vs Tip-Last
- Placing the tip first means dropped payload still pays; tip-last means drops are free but may deprioritize.
- Real finding pattern (pattern observed in multiple audits): Program places tip first; payload consistently drops while tip recurs, draining treasury.

### 3b. Tip Signature Authority
- Tip tx must be signed by the paying authority. Ensure the authority is not a user PDA that lets users grief by revoking.
- Real finding pattern (pattern observed in multiple audits): User-PDA signs tip; user cancels instruction before chain, treasury still out.

### 3c. Tip Amount Source
- Tip funds from a dedicated subaccount or treasury; commingling with user funds is a vulnerability.
- Real finding pattern (pattern observed in multiple audits): Tip pulled from user's remaining balance post-swap; under-delivered swaps have 0 tip, losing inclusion priority when most needed.

Tag: [TRACE:tip_position=first/last → tip_authority_correct=YES/NO → tip_source_segregated=YES/NO]

---

## 4. Leader-Slot Assumption

### 4a. Leader Is Jito
- Bundles only execute when the leader runs the Jito client. Does the program detect and abort if not?
- Real finding pattern (pattern observed in multiple audits): Program submits bundle to non-Jito leader; tip paid, bundle never executes atomically.

### 4b. Slot Boundary
- Bundles target a specific slot; cross-slot execution breaks atomicity.
- Real finding pattern (pattern observed in multiple audits): Program inserts a future-slot assumption; off-by-one slot misses execution.

### 4c. Validator-Set Trust
- Some Jito validators may drop bundles for policy reasons. Does the program monitor success and retry?
- Real finding pattern (pattern observed in multiple audits): Program blindly retries; repeated drops drain tip budget.

Tag: [TRACE:leader_is_jito_check=YES/NO → slot_boundary_honored=YES/NO → retry_budget_bounded=YES/NO]

---

## 5. Searcher Ordering Coupled to State

### 5a. Cross-Transaction State Assumption
- If a later tx in the bundle reads state written by the earlier tx, bundle ordering is load-bearing.
- Real finding pattern (pattern observed in multiple audits): Program assumes tx2 reads tx1's output; when bundle reordered by block engine, tx2 fails.

### 5b. Searcher-Controlled Payload
- If an external searcher constructs the bundle, they can craft tx ordering to front-run or back-run the protocol.
- Real finding pattern (Cantina, pattern observed in multiple audits): Searcher inserts malicious tx between protocol txs in the bundle, extracting value.

### 5c. Oracle Timing Coupling
- If the bundle assumes oracle refresh inside the bundle, it may run across slot boundaries where price changes.
- Real finding pattern (pattern observed in multiple audits): Oracle update tx and consume tx separated by slot transition; race.

Tag: [TRACE:ordering_assumption_documented=YES/NO → searcher_trust_boundary=tight/loose → oracle_same_slot_required=YES/NO]

---

## 6. Tip Sizing Griefing

### 6a. Unbounded Tip
- User or caller can set tip. Excessive tip drains treasury.
- Real finding pattern (Solodit, pattern observed in multiple audits): Instruction accepts `tip_lamports` without bound; malicious keeper drains rebalancer wallet.

### 6b. Tip Below Inclusion Threshold
- Bundles below a minimum tip are ignored. Does the program enforce a floor?
- Real finding pattern (pattern observed in multiple audits): Program submits zero-tip bundles that never execute; protocol effectively offline.

### 6c. Tip Multiplier
- Programs that multiply tip by volatility or urgency need bounded multipliers.
- Real finding pattern (pattern observed in multiple audits): Multiplier unbounded; during volatility, tip hits treasury cap per tx.

Tag: [TRACE:tip_ceiling=YES/NO → tip_floor=YES/NO → multiplier_bounded=YES/NO]

---

## Common False Positives

- Program only uses Jito to broadcast a single tx (no bundle assumption). Sections 2, 5 reduced.
- Program treats tip as a best-effort latency hint only. Section 6b does not apply.
- Program is itself a searcher that trusts its own ordering. Section 5b reduced.

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 0. Taxonomy Pre-Search | YES | | solana.json markers |
| 1a. Recipient Allowlist | YES | | 8-account set |
| 1b. Rotation Aware | YES | | rotation handled |
| 1c. Tip Program Owner | YES | | owner check |
| 2a. Atomicity Assumption | YES | | via bundle API only |
| 2b. Fallback Cleanup | YES | | recovery path |
| 2c. Idempotent | YES | | replay safe |
| 3a. Tip Position | YES | | first vs last choice documented |
| 3b. Tip Authority | YES | | correct signer |
| 3c. Tip Source Segregated | YES | | dedicated wallet |
| 4a. Leader Is Jito | YES | | pre-submit check |
| 4b. Slot Boundary | YES | | target slot correct |
| 4c. Retry Budget | YES | | bounded |
| 5a. Ordering Assumption | IF multi-tx bundle | | documented |
| 5b. Searcher Trust | IF external searcher | | tight boundary |
| 5c. Oracle Same-Slot | IF oracle coupled | | required |
| 6a. Tip Ceiling | YES | | caller bounded |
| 6b. Tip Floor | YES | | inclusion threshold |
| 6c. Multiplier Bound | IF multiplier used | | cap |
