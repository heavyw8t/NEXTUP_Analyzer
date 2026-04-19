---
name: "ability-analysis"
description: "Trigger Pattern Always (Sui Move) -- foundational security check - Inject Into Breadth agents, depth agents"
---

# ABILITY_ANALYSIS Skill

> **Trigger Pattern**: Always (Sui Move) -- foundational security check
> **Inject Into**: Breadth agents, depth agents

For every struct defined in the protocol:

**STEP PRIORITY**: Steps 5 (Hot Potato Enforcement) and 7 (Dynamic Field Ability Propagation) are where HIGH/CRITICAL severity findings most commonly hide. Do NOT rush these steps. If constrained, skip conditional sections before skipping 5 or 7.

## 1. Struct Ability Inventory

Enumerate ALL structs across all modules:

| Module | Struct | Abilities | Has `id: UID`? | Is Object? | Transferable? | Notes |
|--------|--------|-----------|----------------|------------|---------------|-------|
| {mod} | {name} | {key, store, drop, copy} | YES/NO | YES/NO | YES/NO | {context} |

**Sui ability semantics**:
- `key` = Object type. MUST have `id: UID` as the first field. Can be owned, shared, or frozen.
- `store` = Can be transferred freely via `public_transfer` / `public_share_object`. Can be stored inside other objects via dynamic fields or wrapping.
- `drop` = Can be implicitly discarded. Without `drop`, the value MUST be explicitly consumed (unpacked, transferred, or destroyed).
- `copy` = Can be duplicated. `copy + key` is IMPOSSIBLE in Sui -- objects cannot be copied.
- No abilities at all = Hot potato pattern. Value must be consumed within the same transaction.

**Consistency check**: For each struct with `key`:
- [ ] Does it have `id: UID` as the FIRST field? If not -> compilation error (catch misplaced UID).
- [ ] Is `store` intentionally included or omitted? `key` without `store` = only the defining module can transfer it (custom transfer rules).

## 2. Object Model Classification

Classify each object (`key` ability) by ownership model:

| Object | Ownership | Created Via | Transfer Restricted? | Freeze Possible? |
|--------|-----------|-------------|---------------------|-----------------|
| {name} | Owned / Shared / Frozen / Wrapped | {function} | YES (no `store`) / NO (`store`) | YES/NO |

**Security checks per ownership type**:

### 2a. Owned Objects
- Can the owner transfer to themselves via `transfer::transfer` to reset state?
- Are there time-locks or cooldowns that reset on transfer?
- Can owned objects be wrapped inside other objects to bypass module restrictions?

### 2b. Shared Objects
- Is the object made shared via `transfer::share_object` at creation?
- Once shared, can never be un-shared -- is this intended?
- Shared objects require consensus ordering -- are there ordering-dependent operations?
- **Critical**: Can an attacker create a competing shared object of the same type?

### 2c. Frozen Objects (Immutable)
- Is the object frozen via `transfer::freeze_object`?
- Once frozen, can never be mutated -- is this intended?
- Are there references to the frozen object that expect mutation?

### 2d. Wrapped Objects
- Objects stored as fields inside other objects lose their independent existence.
- Can wrapping bypass transfer restrictions (object with `key` only, no `store`, wrapped inside a `key + store` parent)?
- When unwrapped, does the object retain its original ID and state?

## 3. Ability Mismatch Analysis

For each struct, verify ability assignments match intended behavior:

### 3a. Missing `drop` -- Intentional?
| Struct | Has `drop`? | Explicit Destroy Function? | Can Leak? |
|--------|------------|---------------------------|-----------|
| {name} | NO | YES: `destroy_{name}()` / NO | YES/NO |

**Rule**: A struct without `drop` that has no explicit destroy/consume path creates a resource leak. The transaction will abort if the value is not consumed. This is sometimes intentional (hot potato) but often a bug when the struct is created in error paths.

### 3b. Unnecessary `store` -- Over-Permissive?
| Struct | Has `store`? | Stored in Dynamic Fields? | Freely Transferable? | Should Be Restricted? |
|--------|-------------|--------------------------|---------------------|----------------------|
| {name} | YES | YES/NO | YES | {analysis} |

**Check**: If a struct has `store` but the protocol intends restricted transfers (e.g., non-transferable receipts, bound tickets), the `store` ability enables bypass via `public_transfer`. Does any security invariant depend on transfer restriction?

### 3c. `copy` Abuse Potential
| Struct | Has `copy`? | Contains Balances/IDs? | Duplication Dangerous? |
|--------|------------|----------------------|----------------------|
| {name} | YES/NO | YES/NO | YES/NO |

**Rule**: `copy` on a struct containing `Balance<T>`, capability tokens, or unique identifiers is almost always a bug -- it enables double-spending or capability duplication. `copy + key` is impossible (enforced by Sui), but `copy + store` on inner structs is allowed and dangerous if they hold value.

## 4. Capability Pattern Audit

Identify all capability/admin structs:

| Capability | Abilities | Created In | Transferred To | Can Be Duplicated? | Revocable? |
|-----------|-----------|------------|---------------|-------------------|-----------|
| {name} | {abilities} | `init()` | {recipient} | YES (`copy`) / NO | YES/NO |

**Checks**:
- Is the capability created only in `init()` (module initializer)? If created elsewhere, can it be minted by unauthorized parties?
- Does the capability have `store`? If yes, the holder can transfer it freely -- is this intended?
- Is there a revocation mechanism? (Capability patterns in Sui are typically one-way -- once issued, not revocable without wrapping in a shared object with access control.)
- **One-Time Witness (OTW) vs Capability**: Is this struct actually an OTW being misused as a persistent capability? OTW types should be consumed in `init`, not stored.

## 5. Hot Potato Enforcement

Identify all structs with NO abilities:

| Struct | Module | Created By | Must Be Consumed By | Enforced? |
|--------|--------|------------|--------------------|---------:|
| {name} | {mod} | {function} | {function} | YES/NO |

**Hot potato security checks**:
- [ ] Is the hot potato created and consumed within a single PTB (Programmable Transaction Block)?
- [ ] Can the consumption function be called by anyone, or only specific callers?
- [ ] Does the consumption function validate the hot potato's contents match expectations?
- [ ] Can an attacker create a fake hot potato of the same type from a different module? (NO -- Move type system prevents cross-module struct creation.)
- [ ] Can the hot potato be stored if someone adds `store` via a wrapper? (Check: is there a public wrapper that accepts arbitrary `store` types.)
- [ ] **Transaction abort impact**: If the hot potato cannot be consumed (e.g., consumption function reverts), the entire PTB aborts. Can this be used for griefing? (e.g., attacker causes the consumption precondition to fail after the hot potato is created.)

**Pattern validation**: Trace every hot potato from creation to consumption. Document the full lifecycle:
```
create: module::start_action() -> HotPotato
  ... intervening calls that rely on HotPotato's existence ...
consume: module::finish_action(potato: HotPotato)
```
If any code path creates a hot potato without a guaranteed consumption path -> FINDING (transaction will always abort on that path).

## 6. Transfer Restriction Analysis

For objects with `key` but NOT `store`:

| Object | Module Transfer Function | Custom Rules | Bypass Possible? |
|--------|------------------------|-------------|-----------------|
| {name} | {function or NONE} | {description} | YES/NO |

**Sui transfer rules**:
- `key + store`: Anyone can transfer via `transfer::public_transfer`.
- `key` only: Only the defining module can transfer via `transfer::transfer` (requires module-level access).
- **Bypass check**: Can the restricted object be wrapped inside a `store`-capable struct, then the wrapper transferred freely? If the wrapping struct is from a DIFFERENT module, this is a transfer restriction bypass.

**Check each restricted object**:
1. Does any public function accept this object type and wrap it?
2. Does any public function accept this object type and place it in a dynamic field of a freely transferable object?
3. If yes to either -> the transfer restriction is bypassable -> FINDING.

## 7. Dynamic Field Ability Propagation

For every use of `dynamic_field::add` or `dynamic_object_field::add`:

| Parent Object | Field Key Type | Field Value Type | Value Has `store`? | Parent Has `store`? |
|--------------|---------------|-----------------|-------------------|-------------------|
| {parent} | {key_type} | {value_type} | YES/NO | YES/NO |

**Rules**:
- `dynamic_field::add` requires the value type to have `store`.
- `dynamic_object_field::add` requires the value type to have `key + store`.
- **Security check**: If a value with `store` is added as a dynamic field, anyone who can access the parent object can potentially extract it via `dynamic_field::remove`. Is extraction access-controlled?
- **Orphan check**: If the parent object is destroyed, are dynamic fields cleaned up? Orphaned dynamic fields remain in storage and can never be accessed again -> permanent storage leak.
- **Type confusion**: Dynamic fields are keyed by type. Can an attacker add a dynamic field with a key type that collides with an expected key type? (Unlikely due to Move type system, but check for generic key types like `vector<u8>` or `String`.)

## 8. Module Initializer Audit

For each module with an `init` function:

| Module | `init` Parameters | Objects Created | Capabilities Issued | OTW Consumed? |
|--------|------------------|-----------------|--------------------|--------------:|
| {mod} | {params} | {list} | {list} | YES/NO/N/A |

**Checks**:
- Is `init` the ONLY place critical capabilities are created?
- Does `init` properly consume the One-Time Witness if one is passed?
- Can the module be re-initialized via package upgrade? (Sui package upgrades do NOT re-run `init`.)
- Are shared objects created in `init`? (They must be -- you cannot share an owned object after creation in Sui.)

## Finding Template

```markdown
**ID**: [AB-N]
**Severity**: [based on ability misuse impact]
**Step Execution**: check1,2,3,4,5,6,7,8 | X(reasons) | ?(uncertain)
**Rules Applied**: [R4:Y, R5:Y, R10:Y, ...]
**Location**: module::struct_name
**Title**: [Ability issue type] in [struct] enables [attack/bypass]
**Description**: [Specific ability misconfiguration with type-level trace]
**Impact**: [What breaks: transfer restriction bypass, capability duplication, resource leak, hot potato griefing]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: id_leak_verifier bypass via package upgrade — UID reuse across package versions enables object identity spoofing
  Where it hit: sui-verifier / `id_leak_verifier` check
  Severity: HIGH
  Source: Solodit (row_id 11775)
  Summary: The Sui verifier enforces that UIDs for objects bearing the `key` ability are not reused. However the check can be bypassed through the Sui upgrade model: upgrades can introduce new capabilities, the verifier does not validate structs that lack `key` at the time of the check, and objects can be passed between different versions of the same package. An attacker can therefore reuse a UID across a package upgrade, violating the invariant that every `key` object has a globally unique on-chain identity. The fix adds upgrade-aware validation that tracks UID lineage across package versions.
  Map to: key, ability

- Pattern: Hot-potato ticket not consumed on all exit paths — `UnstakeTicket` drop missing, causing PTB abort
  Where it hit: native_pool / `burn_ticket_non_entry`
  Severity: MEDIUM
  Source: Solodit (row_id 9957)
  Summary: `burn_ticket_non_entry` collects SUI coins for the user during unstaking but does not account for coins held in `NativePool::pending`. When the pending balance is non-zero the function fails to consume all resources, leaving the `UnstakeTicket` value alive and the PTB cannot complete — it aborts because the ticket struct has no `drop` ability. The fix adds `NativePool::pending` to the coin collection path so the ticket can always be fully consumed.
  Map to: hot_potato, drop, ability

- Pattern: Large-stake `UnstakeTicket` creation blocks epoch reclaim — hot-potato consumption path fails under size constraint
  Where it hit: native_pool / unstake flow
  Severity: MEDIUM
  Source: Solodit (row_id 9958)
  Summary: A user who creates an `UnstakeTicket` for a large stake amount triggers a condition check that prevents reclaiming during the current epoch. Because `UnstakeTicket` has no `drop` ability it must be consumed via the designated burn function; when that function's precondition fails the entire PTB aborts. An attacker can use this to grief users by ensuring the consumption precondition cannot be satisfied. The fix removes the blocking condition and sets a minimum value guard so the ticket's consumption path is always reachable.
  Map to: hot_potato, drop, ability

- Pattern: Vault receipt struct with `store` allows unrestricted public transfer, bypassing protocol-enforced redemption rules
  Where it hit: bluefin_vault / share/receipt structs
  Severity: HIGH
  Source: Solodit (row_id 8567)
  Summary: The bluefin_vault protocol issues receipt structs that carry `store`, making them freely transferable via `transfer::public_transfer`. A zero-balance vault state (total_balance == 0, shares > 0) allows an attacker to deposit and receive zero shares — effectively burning their deposit — while the receipt struct remains transferable to any address. The intended restriction that receipts can only be redeemed by the original depositor is bypassed because `store` enables arbitrary transfer. The fix locks a minimum share/token amount at initialization and asserts non-zero shares in deposit/withdrawal, but the root structural issue is that the receipt ability set should not include `store` if transfer restriction is a protocol invariant.
  Map to: store, ability, key

- Pattern: Spot-price oracle used inside Move module for domain pricing enables flash-loan manipulation — no TWAP witness requirement
  Where it hit: usernames module / Initia Move platform / domain registration pricing
  Severity: HIGH
  Source: Solodit (row_id 1804)
  Summary: The `usernames` module derives domain registration fees from the Dex module's spot price. Because the price source is a simple balance query rather than a time-weighted or oracle-witnessed value, an attacker can use a flash loan or large deposit to manipulate the spot price, buying domains cheaply and causing other users to overpay. In Sui/Move terms the absence of a witness type or capability that enforces price provenance means any caller can trigger pricing from a manipulated state. The team planned to hardcode price at 1 and later use Slinky oracle. The mapping to ability patterns: a `witness` or one-time capability type that proves a legitimate price feed was consulted would have enforced the invariant at the type level.
  Map to: witness, ability

- Pattern: Wallet address not removed from investor struct on `remove_wallet` — inaccurate balance calculations from stale object reference
  Where it hit: registry_service / `remove_wallet`
  Severity: HIGH
  Source: Solodit (row_id 3917)
  Summary: `registry_service::remove_wallet` deletes the wallet's data entry but leaves the address reference inside `investor.wallets`. Functions like `investor_wallet_balance_total` iterate over `investor.wallets` and access fields that no longer exist, producing incorrect balance sums. In Move ability terms the `investor.wallets` collection holds values by reference without `drop` semantics enforced at the struct level, so stale entries accumulate silently. The fix removes the address from `investor.wallets` in addition to deleting the wallet entry.
  Map to: drop, store, ability

- Pattern: Cross-chain give_coin uses `add_flow_out` for inbound token receipt — inverted flow tracking on `store`-bearing coin structs
  Where it hit: CoinManagement / `give_coin`
  Severity: HIGH
  Source: Solodit (row_id 6915)
  Summary: `give_coin` is called when receiving tokens via interchain transfer. The function invokes `add_flow_out` to record the movement, but the correct call is `add_flow_in`. Because the coin management struct carries `store`, it can be held and passed across module boundaries; the flow direction is not enforced by the type system and must be tracked manually. The bug causes the treasury capacity to be decremented on inbound transfers instead of incremented, eventually blocking legitimate operations. The fix changes the call to `add_flow_in`.
  Map to: store, ability, copy


## Step Execution Checklist (MANDATORY)

> **CRITICAL**: You MUST report completion status for ALL sections. Findings with incomplete sections will be flagged for depth review.

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Struct Ability Inventory | YES | Y/X/? | |
| 2. Object Model Classification | YES | Y/X/? | |
| 2b. Shared Object Analysis | IF shared objects | Y/X(N/A)/? | |
| 3. Ability Mismatch Analysis | YES | Y/X/? | |
| 3b. Unnecessary `store` Check | YES | Y/X/? | |
| 3c. `copy` Abuse Check | YES | Y/X/? | |
| 4. Capability Pattern Audit | YES | Y/X/? | |
| 5. Hot Potato Enforcement | IF hot potatoes exist | Y/X(N/A)/? | **HIGH PRIORITY** |
| 6. Transfer Restriction Analysis | IF `key`-only objects | Y/X(N/A)/? | |
| 7. Dynamic Field Ability Propagation | IF dynamic fields used | Y/X(N/A)/? | **HIGH PRIORITY** |
| 8. Module Initializer Audit | YES | Y/X/? | |

### Cross-Reference Markers

**After Section 4** (Capability Pattern Audit):
- Cross-reference with `TYPE_SAFETY.md` Section on OTW analysis
- IF capability has `store` -> flag for SEMI_TRUSTED_ROLES analysis

**After Section 5** (Hot Potato Enforcement):
- IF hot potato consumption depends on external state -> cross-reference with EXTERNAL_PRECONDITION_AUDIT
- IF hot potato abort causes shared object locking -> document consensus impact

**After Section 7** (Dynamic Field Ability Propagation):
- IF dynamic field values extractable by non-owners -> FINDING (minimum Medium)
- Cross-reference with TOKEN_FLOW_TRACING for dynamic field token storage
