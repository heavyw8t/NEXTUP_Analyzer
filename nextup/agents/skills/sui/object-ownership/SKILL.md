---
name: "object-ownership"
description: "Trigger Pattern Always required for Sui Move audits -- object lifecycle and ownership model - Inject Into Breadth agents, depth-state-trace, depth-token-flow"
---

# OBJECT_OWNERSHIP Skill

> **Trigger Pattern**: Always required for Sui Move audits -- object lifecycle and ownership model
> **Inject Into**: Breadth agents, depth-state-trace, depth-token-flow
> **Finding prefix**: `[OO-N]`
> **Rules referenced**: R4, R5, R9, R10, R13

Sui's object-centric model is fundamentally different from account-based chains. Every struct with the `key` ability is an on-chain object with a globally unique ID, and its ownership model (owned/shared/frozen/wrapped) determines who can access and mutate it. Incorrect ownership choices, missing transfer restrictions, orphaned UIDs, and uncontrolled dynamic fields are the primary Sui-specific vulnerability classes.

---

## 1. Object Inventory

For EVERY struct with `key` ability in the codebase, build this table:

| # | Object Name (Module) | Abilities | Ownership Model | Created Where | Transferred Where | Destroyed Where | Has `store`? |
|---|---------------------|-----------|-----------------|---------------|-------------------|-----------------|-------------|
| 1 | {name} ({module}) | {key, store, ...} | OWNED / SHARED / FROZEN / WRAPPED / MIXED | {function:line} | {function:line or NEVER} | {function:line or NEVER} | YES/NO |

**Ability rules**:
- `key` alone: Object can exist on-chain but CANNOT be transferred by generic `transfer::public_transfer` (requires module-defined transfer logic).
- `key + store`: Object CAN be transferred by anyone via `transfer::public_transfer`. This is a **permissive** choice -- verify it is intentional.
- `key + store + copy`: Object can be duplicated -- extremely rare for value-bearing objects. FLAG if found on any object holding balances.
- `key + store + drop`: Object can be silently discarded without calling a destructor. FLAG if the object holds `Balance<T>` or other value -- tokens can be lost.

**Ownership model classification**:
- **OWNED**: Created and transferred to a specific address via `transfer::transfer` or `transfer::public_transfer`. Only the owner can pass it as a transaction argument.
- **SHARED**: Made accessible to all via `transfer::public_share_object`. Any transaction can read/write it. CRITICAL access control implications.
- **FROZEN**: Made immutable via `transfer::public_freeze_object`. Anyone can read, no one can mutate.
- **WRAPPED**: Stored as a field inside another object (not directly addressable on-chain). Accessible only through the parent.
- **MIXED**: Object starts as one type and transitions to another (e.g., created as owned, then shared). Document the transition path.

---

## 2. Ownership Model Analysis

### 2a. Owned Object Audit

For each OWNED object:

| Object | Should Be Shared Instead? | Ownership Transfer Possible? | Transfer Restriction Correct? | Assumption Risk |
|--------|--------------------------|-----------------------------|-----------------------------|----------------|
| {name} | YES/NO ({reason}) | YES (has `store`) / NO (no `store`) | {analysis} | {risk if ownership changes} |

**Check patterns**:
- **Should this be shared?** If multiple unrelated parties need to mutate the object in the same epoch, owned model creates bottlenecks or requires trust delegation. Common mistake: config objects that should be shared are kept owned, forcing single-admin bottleneck.
- **Ownership change undermines assumptions?** If code assumes "only admin holds AdminCap", but AdminCap has `store` ability, it can be transferred to anyone. Verify that transfer does not break invariants downstream.
- **Phantom ownership**: Object is "owned" but the owner address is a PDA-like derived address that nobody controls (e.g., `@0x0`). The object is effectively inaccessible -- equivalent to locked funds if it holds value.

### 2b. Shared Object Audit

For each SHARED object:

| Object | Mutation Functions | Access Guards | Concurrent Mutation Risk | Ordering Dependency |
|--------|-------------------|---------------|------------------------|-------------------|
| {name} | {list all functions that take `&mut` ref} | {what prevents unauthorized mutation} | YES/NO ({analysis}) | YES/NO ({analysis}) |

**CRITICAL checks**:
- **Access control on mutation**: Shared objects can be passed as arguments by ANY transaction. If a function takes `&mut SharedObj` without verifying the caller has authority (e.g., checking a capability object), anyone can mutate it. This is the #1 Sui vulnerability pattern.
- **Consensus ordering**: Transactions touching the same shared object are ordered by Sui's consensus. If the protocol relies on specific transaction ordering (e.g., "admin sets fee before user trades"), front-running is possible because consensus ordering is non-deterministic from the user's perspective.
- **Race conditions**: Two transactions that both mutate the same shared object field can produce different final states depending on execution order. If the protocol assumes sequential access, this is a bug.
- **Gas-based DoS**: An attacker can submit many transactions touching a shared object to increase contention and gas costs for legitimate users.

### 2c. Frozen Object Audit

For each FROZEN object:

| Object | Should Updates Be Possible? | Freezing Reversible? | Data Staleness Risk |
|--------|-----------------------------|---------------------|-------------------|
| {name} | YES/NO ({reason}) | NO (by design) | {risk if frozen data becomes stale} |

**Check**: If frozen object holds configuration that may need updating (fee rates, oracle addresses, admin keys), freezing is likely wrong -- should be shared with access control instead.

### 2d. Wrapped Object Audit

For each WRAPPED object:

| Parent Object | Wrapped Object | Unwrap Path Exists? | Dynamic Fields on Wrapped? | Destruction Safety |
|--------------|---------------|--------------------|--------------------------|--------------------|
| {parent} | {wrapped} | YES ({function}) / NO | YES/NO | {what happens to wrapped when parent destroyed} |

**Check patterns**:
- **No unwrap path**: If a wrapped object holds value (Balance, Coin) but there is no function to extract it, funds are permanently locked inside the parent. Apply Rule 9: stranded asset = minimum MEDIUM.
- **Parent destruction without unwrap**: If the parent object can be destroyed (has `drop` ability or explicit destructor) without first unwrapping/extracting the inner object, the inner object's value is lost.
- **Dynamic fields on wrapped objects**: Dynamic fields added to a wrapped object's UID are NOT accessible when the object is wrapped. They become orphaned until unwrap. If the protocol adds dynamic fields and then wraps, those fields are inaccessible.

---

## 3. Object Transfer Analysis

For each `transfer::transfer`, `transfer::public_transfer`, `transfer::share_object`, `transfer::public_share_object`, `transfer::freeze_object`, `transfer::public_freeze_object` call:

| # | Transfer Call | Object Type | Initiator | `store` Required? | `store` Present? | Recipient Validation | Stranded Risk |
|---|-------------|------------|-----------|-------------------|-----------------|---------------------|---------------|
| 1 | {function:line} | {type} | {who calls} | YES (public_*) / NO (module-only) | YES/NO | {is recipient validated?} | {can object be sent to address that cannot use it?} |

**Check patterns**:
- **`store` ability gate**: `transfer::public_transfer` requires `store`. `transfer::transfer` does not -- it is module-restricted. If an object should NOT be freely transferable by holders, it should NOT have `store`.
- **Recipient validation**: If an object is transferred to an arbitrary address and that address does not have the matching module to use it, the object is stranded. This is especially dangerous for capability objects (AdminCap sent to a contract that cannot invoke admin functions).
- **Transfer to self**: Transferring an object to the transaction sender is sometimes used as a "commit" pattern. Verify this does not bypass any state transitions.
- **Conditional transfer**: If transfer happens inside a conditional branch, check the else branch -- does the object leak (neither transferred, shared, frozen, wrapped, nor destroyed)?

---

## 4. Shared Object Mutation Safety

For each shared object, build the mutation map:

| Shared Object | Function | Mutation Type | Guard | Re-entrancy Risk | Ordering Sensitivity |
|--------------|----------|--------------|-------|-----------------|---------------------|
| {obj} | {func} | FIELD_UPDATE / BALANCE_CHANGE / CHILD_ADD / CHILD_REMOVE | {capability check, address check, or NONE} | {can another function on same object be called mid-execution?} | {does outcome depend on call order?} |

**Sui-specific re-entrancy note**: Move's borrow checker prevents re-entrancy within a single module (you cannot pass `&mut Obj` to a function that also borrows `&mut Obj`). However, cross-module re-entrancy is possible if Object A's mutation calls a function in Module B that calls back to Module A with a different entry point that accesses a DIFFERENT shared object whose state is coupled with Object A.

**Concurrent mutation checklist**:
- [ ] Can two independent transactions mutate the same field to conflicting values?
- [ ] Does the protocol rely on reading a value from the shared object and then writing back a derived value? (TOCTOU with consensus ordering)
- [ ] Can an attacker observe a pending transaction on a shared object and submit a competing transaction that front-runs it?
- [ ] Are balance operations on shared objects atomic? (Balance::split + Balance::join should not be interruptible across objects)

---

## 5. Object Wrapping/Unwrapping

For each wrapping relationship (object stored as field in another object):

| Wrapper | Wrapped | Wrap Point | Unwrap Point | Dynamic Fields Before Wrap | UID Preserved on Unwrap? |
|---------|---------|-----------|-------------|--------------------------|-------------------------|
| {parent} | {child} | {function:line} | {function:line or NONE} | YES/NO | YES/NO/N/A |

**Check patterns**:
- **Dynamic field orphaning**: If `dynamic_field::add(child_uid, ...)` is called before `child` is wrapped into `parent`, those dynamic fields become inaccessible. They still exist on-chain (consuming storage) but cannot be read or removed until the child is unwrapped.
- **UID preservation**: When an object is unwrapped and re-created, does it get the same UID or a new one? If new UID, all dynamic fields on the old UID are orphaned permanently.
- **Nested wrapping depth**: Objects wrapped inside objects wrapped inside objects create deep access chains. Each level adds complexity and potential for state inconsistency.
- **Balance preservation invariant**: If the wrapped object holds `Balance<T>`, verify that total balance is preserved across wrap/unwrap cycles. No balance should be created or destroyed during wrapping.

---

## 6. UID Lifecycle Audit

Every call to `object::new(ctx)` creates a UID. Every UID must be either:
1. Stored in an object with `key` ability (the object's `id` field), OR
2. Explicitly destroyed via `object::delete(id)`

For each `object::new(ctx)` call:

| # | Creation Location | UID Stored In | Destruction Location | Lifecycle Complete? | Orphan Risk |
|---|------------------|--------------|---------------------|--------------------|-----------|
| 1 | {function:line} | {object field or VARIABLE} | {function:line or NONE} | YES/NO | {if NO: resource leak} |

**Check patterns**:
- **Orphaned UID**: If `object::new(ctx)` is called but the resulting UID is not stored in an object that gets transferred/shared/frozen, and not deleted, it is a resource leak. The UID exists on-chain consuming storage but is unreachable.
- **UID in error paths**: If a function creates a UID, then hits an abort/assert before storing it -- the transaction reverts, so no leak. BUT if the function returns early (non-abort) with the UID in a local variable -- this is a compiler error in Move (linear type), so it should not be possible. Verify the compiler catches this.
- **UID reuse**: A UID should never be reused after `object::delete`. Move's type system should prevent this, but verify in any `unsafe` or `native` code paths.
- **Dynamic field cleanup before delete**: Before calling `object::delete(id)`, ALL dynamic fields on that UID should be removed. Otherwise, the dynamic fields become permanently orphaned (the UID no longer exists to access them through). Apply Rule 9: orphaned dynamic fields holding value = stranded assets = minimum MEDIUM.

---

## 7. Dynamic Field Audit

For each `dynamic_field::add`, `dynamic_field::remove`, `dynamic_object_field::add`, `dynamic_object_field::remove`:

| # | Operation | Parent UID | Field Name/Type | Value Type | Access Control | Unbounded Growth? | Cleanup on Delete? |
|---|-----------|-----------|----------------|-----------|---------------|-------------------|-------------------|
| 1 | ADD | {parent:line} | {name type + value} | {type} | {who can add} | YES/NO | {is field removed before parent UID deleted?} |

**Check patterns**:
- **Unbounded growth**: If `dynamic_field::add` is called in a loop or user-facing function without a cap, the parent object's dynamic field set grows without limit. This increases gas costs for operations that iterate related state and can be used as a DoS vector.
- **Unauthorized field addition**: If ANY caller can add dynamic fields to a shared object's UID, an attacker can pollute the object's field namespace. This may cause `dynamic_field::borrow` to return unexpected data if field names collide.
- **Name collision**: Dynamic fields are keyed by `(TypeTag, name_value)`. If two different code paths add fields with the same key type and value, they overwrite each other. Verify field name uniqueness across all add operations on the same UID.
- **Type safety**: `dynamic_field::borrow<Name, Value>` will abort if the stored value type does not match `Value`. Verify all borrow calls use consistent type parameters with the corresponding add calls.
- **Object fields vs value fields**: `dynamic_object_field::add` stores objects (with `key` ability) that retain their own UID and are independently addressable. `dynamic_field::add` wraps values. Using the wrong variant can make objects inaccessible or create unexpected behavior.
- **Removal completeness**: Before an object is destroyed (`object::delete`), ALL dynamic fields must be removed. Build a removal completeness table:

| Parent Object | Destruction Function | Dynamic Fields Added | Dynamic Fields Removed Before Delete | Complete? |
|--------------|---------------------|---------------------|--------------------------------------|----------|
| {obj} | {func:line} | {list all add operations} | {list all remove operations in destructor} | YES/NO |

---

## Finding Template

```markdown
## Finding [OO-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED / CONTESTED
**Step Execution**: checkmark1,2,3,4,5,6,7 | x(reasons) | ?(uncertain)
**Rules Applied**: [R4:Y/N, R5:Y/N, R9:Y/N, R10:Y/N, R13:Y/N]
**Severity**: Critical/High/Medium/Low/Info
**Location**: sources/{module}.move:LineN
**Description**: [Specific ownership/lifecycle issue with code reference]
**Impact**: [What can happen -- fund loss, state corruption, DoS, stranded assets]

### Precondition Analysis (if PARTIAL or REFUTED)
**Missing Precondition**: [What blocks this attack]
**Precondition Type**: STATE / ACCESS / TIMING / EXTERNAL / BALANCE
**Why This Blocks**: [Specific reason]

### Postcondition Analysis (if CONFIRMED or PARTIAL)
**Postconditions Created**: [What conditions this creates]
**Postcondition Types**: [STATE, ACCESS, TIMING, EXTERNAL, BALANCE]
**Who Benefits**: [Who can use these]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

# Source: WebSearch — MoveBit, Zellic, SlowMist, Mirage Audits, OpenZeppelin, Hacken, Monethic, Sui Docs
# Populated: 2026-04-19
# Local CSV hits: 0 → WebSearch fallback

---

## Finding [OO-W1]: AdminCap or Governance Capability Shared Publicly via `transfer::public_share_object`

**Verdict**: CONFIRMED
**Category**: shared_object / object_ownership
**Severity**: Critical
**Sources**: MoveBit "Sui Objects Security Principles and Best Practices"; SlowMist Sui Move Auditing Primer; Monethic Sui Move Security Workshop

**Description**:
A capability object (AdminCap, OwnerCap, GovernanceCap) is created and then passed to `transfer::public_share_object` (or `transfer::share_object`) instead of being transferred exclusively to the deploying admin address via `transfer::transfer`. This makes the capability permanently and irreversibly accessible to every address on the network as a shared object. Any transaction can pass the shared capability as an argument to admin-gated functions, effectively granting every user admin privileges.

**Pattern**:
```move
// Vulnerable: AdminCap becomes globally mutable
let cap = AdminCap { id: object::new(ctx) };
transfer::public_share_object(cap);  // WRONG — should be transfer::transfer(cap, ctx.sender())
```

**Impact**: Complete loss of access control over all admin-gated functions. Any user can call `set_fee`, `pause`, `upgrade`, or any function that accepts `&AdminCap` or `&mut AdminCap` by passing the shared object.

**Invariant broken**: `object_ownership` — the capability no longer enforces "only admin can call this."

**References**:
- https://www.movebit.xyz/blog/post/Sui-Objects-Security-Principles-and-Best-Practices.html
- https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc
- https://medium.com/@monethic/sui-move-security-workshop-writeup-material-480c5e7d1da3

---

## Finding [OO-W2]: Capability Object Has `store` Ability — Custom Transfer Rules Bypassed via `public_transfer`

**Verdict**: CONFIRMED
**Category**: transfer_share / object_ownership
**Severity**: High
**Sources**: Sui Docs "Custom Transfer Rules"; MoveBit security blog; Hacken Move Audit Checklist; Mirage Audits ability mistakes

**Description**:
A capability or restricted object (AdminCap, VaultCap, MintCap) is declared with the `store` ability. When an object has `key + store`, anyone holding the object can call `sui::transfer::public_transfer` to transfer it to an arbitrary address, bypassing any custom transfer rules the module defined. If the module defines a transfer function that enforces fees, role checks, or other restrictions, those checks are entirely skipped when `public_transfer` is used.

**Pattern**:
```move
// Vulnerable: store ability enables public_transfer bypass
struct MintCap has key, store {   // "store" is the problem
    id: UID,
    max_supply: u64,
}

// Module-defined transfer enforces a fee check — but it is bypassed because:
// anyone can call sui::transfer::public_transfer(cap, recipient) directly
```

**Impact**: Capability holder can transfer the cap to any address including attacker-controlled accounts without going through the module's intended verification logic. If the module intended "cap can only be transferred to verified addresses," the invariant is broken.

**Invariant broken**: `transfer_share` — `public_transfer` is an escape hatch that bypasses module-defined access control when `store` is present.

**References**:
- https://docs.sui.io/concepts/transfers/custom-rules
- https://www.movebit.xyz/blog/post/Sui-Objects-Security-Principles-and-Best-Practices.html
- https://hacken.io/discover/move-smart-contract-audit-checklist/
- https://www.mirageaudits.com/blog/sui-move-ability-security-mistakes

---

## Finding [OO-W3]: Object with `store` Ability Frozen by Third Party via `public_freeze_object`

**Verdict**: CONFIRMED
**Category**: object_ownership / shared_object
**Severity**: High
**Sources**: Zellic "Move Fast & Break Things Part 2"; Hacken Move Audit Checklist

**Description**:
When a Sui object has the `store` ability, any address holding a reference to it — not just the module that defined it — can call `transfer::public_freeze_object` on it. Freezing is irreversible: once frozen, the object can never be mutated again. If the object holds mutable configuration (fee parameters, oracle addresses, admin keys, protocol state), a malicious holder or front-runner can freeze it before the protocol has finished its initialization or at a point that locks in unfavorable state forever.

**Pattern**:
```move
// Config object with store: third party can freeze it
struct ProtocolConfig has key, store {
    id: UID,
    fee_bps: u64,
    oracle: address,
}

// After the deployer creates and transfers this to admin, a third party
// who receives or borrows the object (in a PTB) can call:
// transfer::public_freeze_object(config);
// — making it permanently immutable at whatever state it was in
```

**Impact**: Protocol configuration permanently locked at possibly incorrect or attacker-chosen values. No future upgrades, parameter adjustments, or emergency corrections are possible.

**Invariant broken**: `object_ownership` — the module's expectation that only the module controls mutability of its own config object is violated.

**References**:
- https://www.zellic.io/blog/move-fast-break-things-move-security-part-2/
- https://hacken.io/discover/move-smart-contract-audit-checklist/

---

## Finding [OO-W4]: Shared Object Mutation Function Has No Access Guard

**Verdict**: CONFIRMED
**Category**: shared_object
**Severity**: Critical
**Sources**: SlowMist Sui Move Auditing Primer; MoveBit security blog; Sui Docs shared objects; Hacken checklist

**Description**:
A function that takes `&mut SharedObj` performs a state mutation (balance update, fee change, configuration update, pool parameter change) without verifying that the caller has the necessary capability or matches the expected admin address. Because shared objects can be passed as arguments by ANY transaction, the mutation is callable by anyone.

**Pattern**:
```move
// Vulnerable: no guard on mutation of shared pool config
public entry fun set_fee(pool: &mut Pool, new_fee: u64) {
    pool.fee_bps = new_fee;  // No capability check, no address check
}
```

**Impact**: Any user can call `set_fee` (or equivalent state mutation function) and set parameters to arbitrary values. Depending on the mutated field: fee extraction, pool draining, denial of service, or complete protocol corruption.

**Invariant broken**: `shared_object` — shared object mutation must be guarded; absence of guard means the "shared" access model has no restriction at all.

**References**:
- https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc
- https://www.movebit.xyz/blog/post/Sui-Objects-Security-Principles-and-Best-Practices.html
- https://docs.sui.io/concepts/object-ownership/shared

---

## Finding [OO-W5]: `object::delete` Called Without Removing Dynamic Fields — Permanent Orphan

**Verdict**: CONFIRMED
**Category**: UID
**Severity**: Medium
**Sources**: Sui Docs "Dynamic Fields"; The Move Book dynamic fields chapter; SlowMist Sui Auditing Primer

**Description**:
When `object::delete(id)` is called to destroy an object's UID, the Sui runtime does NOT automatically remove dynamic fields attached to that UID. Any dynamic fields added via `dynamic_field::add` or `dynamic_object_field::add` on the now-deleted UID become permanently orphaned: they still consume on-chain storage, they are not subject to storage fee rebate, and they can never be accessed or removed because the parent UID no longer exists.

**Pattern**:
```move
// Vulnerable: dynamic fields added, then parent UID deleted without cleanup
fun destroy_position(pos: Position) {
    let Position { id, ... } = pos;
    // Dynamic fields (e.g., reward trackers) were added to `id`
    // but are never removed here
    object::delete(id);  // UID deleted, dynamic fields orphaned permanently
}
```

**Impact**: On-chain storage leak — storage fees are paid but never rebated. If the orphaned dynamic fields hold `Balance<T>` or `Coin<T>`, those funds are permanently stranded with no recovery path. Severity escalates to HIGH/CRITICAL if value-bearing fields are orphaned.

**Invariant broken**: `UID` — every dynamic field on a UID must be removed before `object::delete` is called.

**References**:
- https://move-book.com/programmability/dynamic-fields/
- https://docs.sui.io/concepts/dynamic-fields
- https://github.com/slowmist/Sui-MOVE-Smart-Contract-Auditing-Primer

---

## Finding [OO-W6]: Wrapped Object Has No Unwrap Path — Value Permanently Locked

**Verdict**: CONFIRMED
**Category**: object_ownership / shared_object
**Severity**: High
**Sources**: Sui Docs "Wrapped Objects"; Zellic Sui Security Primer; SlowMist auditing primer

**Description**:
An object holding value (Balance, Coin, NFT) is embedded as a direct field inside a parent wrapper object (direct wrapping). The wrapped object loses its independent on-chain identity and can no longer be accessed directly — only through the parent. If no function exists to unwrap (extract) the inner object, or if the only unwrap path is guarded behind conditions that can never be satisfied (e.g., requires a destroyed capability), the value inside is permanently locked.

**Pattern**:
```move
struct Vault has key {
    id: UID,
    locked_coin: Coin<SUI>,  // Directly wrapped — not accessible independently
}

// If destroy_vault() is never defined, or is only callable by an
// AdminCap that was already consumed/transferred to @0x0,
// the Coin<SUI> inside is permanently locked.
```

**Impact**: Permanent loss of any value held by wrapped objects that lack a viable unwrap path. Users cannot recover deposited funds.

**Invariant broken**: `object_ownership` — wrapped objects must have accessible extraction paths for any value they hold.

**References**:
- https://docs.sui.io/concepts/object-ownership/wrapped
- https://www.zellic.io/blog/move-fast-break-things-move-security-part-2/
- https://github.com/slowmist/Sui-MOVE-Smart-Contract-Auditing-Primer

---

## Finding [OO-W7]: Shared Object Transaction Ordering Dependency — TOCTOU via Consensus

**Verdict**: CONFIRMED
**Category**: shared_object
**Severity**: Medium
**Sources**: Sui Docs "Consensus"; Sui Lutris paper; SlowMist auditing primer

**Description**:
A protocol function on a shared object performs a read-modify-write pattern where the result depends on the ordering of concurrent transactions. Because Sui's consensus layer (Mysticeti/Bullshark) determines transaction ordering for shared objects non-deterministically from the user's perspective, a user's transaction outcome depends on which other transactions executed first against the same shared object. Protocols that assume sequential or atomic access — for example, a price oracle read followed by a swap — are vulnerable to front-running or sandwich attacks via transaction ordering manipulation.

**Pattern**:
```move
// Shared pool: attacker submits tx B before user's tx A completes
public entry fun swap(pool: &mut Pool, coin_in: Coin<A>, min_out: u64, ctx: &mut TxContext) {
    let price = pool.reserve_a / pool.reserve_b;  // Read
    // Attacker's tx mutates reserve_a and reserve_b here (ordering attack)
    let out = calculate_out(coin_in, price);       // Stale price used
    assert!(out >= min_out, ESlippage);
    // ...
}
```

**Impact**: Front-running and sandwich attacks on AMM pools, lending protocols, and any shared-object protocol that relies on a consistent view of state across a read-then-write sequence. Financial loss for users; profit extraction for attackers with insight into pending transaction queues.

**Invariant broken**: `shared_object` — protocols using shared objects must account for non-deterministic ordering at the consensus layer.

**References**:
- https://docs.sui.io/develop/sui-architecture/consensus
- https://sonnino.com/papers/sui-lutris.pdf
- https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc

---

## Finding [OO-W8]: Receipt / Hot-Potato Struct Given `drop` or `store` Ability — Flash Loan Repayment Bypass

**Verdict**: CONFIRMED
**Category**: object_ownership / transfer_share
**Severity**: Critical
**Sources**: MoveBit "Sui Objects Security Principles and Best Practices"; Mirage Audits ability mistakes; Hacken Move Audit Checklist

**Description**:
A "hot potato" struct (a receipt or proof object with no abilities, designed to force a repayment call within the same PTB) is accidentally given the `drop` and/or `store` ability. A hot potato with `drop` can be discarded without calling the repayment/settlement function, allowing a borrower to take flash-loaned assets without repaying. A hot potato with `store` can be wrapped inside another object and transferred out of the current transaction context, deferring or permanently avoiding repayment.

**Pattern**:
```move
// Vulnerable: FlashReceipt can be dropped without repayment
struct FlashReceipt has drop, store {  // WRONG — should have zero abilities
    amount_borrowed: u64,
    pool_id: ID,
}

public fun borrow(pool: &mut Pool, amount: u64, ctx: &mut TxContext): (Coin<SUI>, FlashReceipt) {
    // ...
}

public fun repay(pool: &mut Pool, coin: Coin<SUI>, receipt: FlashReceipt) {
    // Receipt is consumed here — but with `drop`, caller never needs to call this
    let FlashReceipt { amount_borrowed, pool_id: _ } = receipt;
    // ...
}
// Attacker calls borrow(), takes Coin<SUI>, and simply drops FlashReceipt
```

**Impact**: Flash loan repayment entirely bypassed. Attacker drains pool liquidity without returning assets.

**Invariant broken**: `object_ownership` — zero-ability hot potato structs must not have `drop` or `store`; adding either destroys the enforcement mechanism.

**References**:
- https://www.movebit.xyz/blog/post/Sui-Objects-Security-Principles-and-Best-Practices.html
- https://www.mirageaudits.com/blog/sui-move-ability-security-mistakes
- https://hacken.io/discover/move-smart-contract-audit-checklist/

---

## Finding [OO-W9]: Object Transferred to Uncontrolled Address (`@0x0` or Contract-Only Address) — Phantom Ownership

**Verdict**: CONFIRMED
**Category**: address_ownership / object_ownership
**Severity**: Medium
**Sources**: Sui Docs object ownership; Hacken Move Audit Checklist; SlowMist Sui Auditing Primer

**Description**:
An object is transferred to an address that has no corresponding private key or module capable of using it — for example, `@0x0`, a burned address, a module address with no entry functions that accept this object type, or a hardcoded placeholder. The object still exists on-chain, still consumes storage, but is permanently inaccessible. If the object holds `Balance<T>`, `Coin<T>`, or other value types, those assets are permanently lost. This pattern sometimes appears in protocol initialization code where a capability is "burned" to restrict admin access, but the wrong object is sent instead of the cap.

**Pattern**:
```move
// Intended: burn admin cap by transferring to a dead address
// Actual: accidentally transfers a fee-collecting vault instead of the cap
transfer::transfer(fee_vault, @0x0);  // Vault with accumulated fees permanently stranded
```

**Impact**: Any value held by the transferred object is permanently stranded. If the object is a protocol capability, the capability is permanently lost and no admin actions can be performed, potentially bricking the protocol.

**Invariant broken**: `address_ownership` — transfer recipients must be verified to be addresses that can use the transferred object.

**References**:
- https://docs.sui.io/guides/developer/sui-101/object-ownership
- https://hacken.io/discover/move-smart-contract-audit-checklist/
- https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc

---

## Finding [OO-W10]: Dynamic Fields Added to Wrapped Object UID Before Wrapping — Inaccessible Until Unwrap

**Verdict**: CONFIRMED
**Category**: UID / object_ownership
**Severity**: Low-Medium
**Sources**: Sui Docs "Wrapped Objects" and "Dynamic Fields"; Zellic Sui Security Primer; The Move Book

**Description**:
`dynamic_field::add` is called on a child object's UID before the child is embedded (wrapped) inside a parent object. Once the child is wrapped, it loses its independent on-chain identity. Its UID is no longer directly addressable, so all dynamic fields attached to that UID become inaccessible until the child is unwrapped. If the protocol then reads those dynamic fields from the parent context without unwrapping first, the reads will fail or return stale state. If the child is later destroyed without being unwrapped, the dynamic fields are orphaned.

**Pattern**:
```move
// Vulnerable: dynamic fields added before object is wrapped
let mut child = ChildObj { id: object::new(ctx), value: 0 };
dynamic_field::add(&mut child.id, b"rewards", reward_balance);  // Field added here

// Object is then wrapped into parent — dynamic fields become inaccessible
let parent = ParentObj { id: object::new(ctx), child: child };
transfer::transfer(parent, ctx.sender());
// reward_balance is now inaccessible until parent is destroyed and child unwrapped
```

**Impact**: Protocol state inconsistency — dynamic fields that should be readable are silently inaccessible. Value-bearing fields (reward balances, accumulated fees) become stranded until the object is unwrapped. If the unwrap path does not handle these dynamic fields, they are orphaned on destruction.

**Invariant broken**: `UID` — dynamic fields on a UID that will be wrapped must be managed carefully; access is blocked for the duration of wrapping.

**References**:
- https://docs.sui.io/concepts/object-ownership/wrapped
- https://docs.sui.io/concepts/dynamic-fields
- https://www.zellic.io/blog/move-fast-break-things-move-security-part-2/


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Object Inventory | YES | Y/N/? | Every struct with `key` ability |
| 2a. Owned Object Audit | IF owned objects exist | Y/N(none)/? | Transfer restriction + assumption risk |
| 2b. Shared Object Audit | IF shared objects exist | Y/N(none)/? | Access control on mutation |
| 2c. Frozen Object Audit | IF frozen objects exist | Y/N(none)/? | Staleness risk |
| 2d. Wrapped Object Audit | IF wrapped objects exist | Y/N(none)/? | Unwrap path + value preservation |
| 3. Object Transfer Analysis | YES | Y/N/? | Every transfer/share/freeze call |
| 4. Shared Object Mutation Safety | IF shared objects mutated | Y/N(none)/? | Concurrent mutation + ordering |
| 5. Object Wrapping/Unwrapping | IF wrapping relationships exist | Y/N(none)/? | Dynamic field orphaning + UID preservation |
| 6. UID Lifecycle Audit | YES | Y/N/? | Every `object::new` matched to storage or delete |
| 7. Dynamic Field Audit | IF dynamic fields used | Y/N(none)/? | Growth bounds + cleanup completeness |

### Cross-Reference Markers

**After Section 2b (Shared Object Audit)**: Feed unguarded mutation functions to SEMI_TRUSTED_ROLES skill if roles are involved in access control.

**After Section 3 (Transfer Analysis)**: Feed objects with `store` ability to TOKEN_FLOW_TRACING skill for balance flow analysis.

**After Section 6 (UID Lifecycle)**: Feed orphaned UIDs and incomplete dynamic field cleanup to depth-edge-case for stranded asset analysis (Rule 9).

**After Section 7 (Dynamic Field Audit)**: Feed unbounded growth patterns to ECONOMIC_DESIGN_AUDIT for DoS cost analysis.
