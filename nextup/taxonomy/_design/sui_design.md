# Sui Move Puzzle-Piece Taxonomy (Design)

Target output: `nextup/taxonomy/sui_puzzle_taxonomy.json` (authored later from this doc).
ID prefix: `SUI-`. Inherited A-I ids become `SUI-A01`, `SUI-A02`, etc. New native categories start at `J`.
Piece-entry schema preserved: id, type, category, file, function, line_start, line_end, description, state_touched, actor, direction, call_context, contract (=module/package), depends_on, snippet.

This design is grounded in:
- `nextup/taxonomy/puzzle_taxonomy.json` (source of A-I, 45 types).
- `nextup/prompts/sui/generic-security-rules.md` (R1-R17, MR1-MR5, SR1-SR4).
- `nextup/agents/skills/sui/*/SKILL.md` (object-ownership, ptb-composability, package-version-safety, plus 19 shared skills).

Do not import Aptos global-storage primitives (`borrow_global`, `move_to`, `FungibleAsset`). Sui is object-centric: `object::new(ctx)`, `transfer::*`, `Coin<T>`, `Balance<T>`, `dynamic_field`, `dynamic_object_field`, `sui::package::UpgradeCap`.

---

## 1. Inherited A-I types

For each of the 45 existing types, decide INCLUDED (becomes `SUI-<id>`) or EXCLUDED. Rationale given for exclusions and for any Sui-specific marker reshaping on inclusions.

Category A (Arithmetic & Precision). All INCLUDED; Sui uses `u8..u256` Move integers with abort-on-overflow. Markers should drop `rust_cosmwasm`/`solidity`, keep a `sui_move` key that reuses the existing `move` markers and adds Sui-specific helpers where applicable.

- SUI-A01 ROUNDING_FLOOR. INCLUDED. Markers: `/` integer division, `sui::math::mul_div`, `std::u64::divide_and_round_down` (if present in framework version in scope).
- SUI-A02 ROUNDING_CEIL. INCLUDED. Markers: `sui::math::mul_div_ceil`, `(a + b - 1) / b`.
- SUI-A03 MIXED_ROUNDING_DIRECTION. INCLUDED. Markers: both `mul_div` and `mul_div_ceil` in same flow.
- SUI-A04 PRECISION_TRUNCATION. INCLUDED. Markers: `(x as u64)`, `(x as u8)` downcasts, `Balance<T>` -> `u64` via `balance::value`.
- SUI-A05 MULT_BEFORE_DIV. INCLUDED. Markers: `a * b / c` without `mul_div` helper.
- SUI-A06 CHECKED_ARITHMETIC_GAP. INCLUDED. Note: Move aborts on overflow by default, so this is rarer. Real signal: explicit wrapping via `std::u64::diff` patterns, mixed `u128` widening and narrowing.
- SUI-A07 ZERO_AMOUNT_PASSTHROUGH. INCLUDED. Markers: missing `assert!(amount > 0)` before `balance::split`, `coin::split`, `coin::mint`.

Category B (Access Control & Authorization). Reconsider in Sui terms: Sui has no `msg.sender` equivalent; authentication uses `TxContext::sender`, signer addresses, and capability objects. Owner-gating is usually cap-based, not address-based.

- SUI-B01 OWNER_ONLY. INCLUDED, with reshaping. In Sui this is cap-based: holding `AdminCap` authorizes, not an address check. Markers: function signature takes `&AdminCap`, `&mut AdminCap`, or any `key`-only cap type; `tx_context::sender(ctx) == ...`.
- SUI-B02 SELF_CALLBACK_GATE. EXCLUDED. Sui has no `address(this)`; modules are not callable objects and there is no self-call pattern in the EVM sense. Cross-module calls are direct. Replaced by SUI-K pieces for PTB composition.
- SUI-B03 NO_ACCESS_CONTROL. INCLUDED. Sui-specific phrasing: `public` or `entry` function that takes `&mut SharedObject` without requiring a cap or sender check. This is the #1 Sui access-control bug.
- SUI-B04 GENESIS_BYPASS. INCLUDED. Sui marker: `fun init(otw: OTW, ctx: &mut TxContext)` one-time-witness module initializer.
- SUI-B05 PAUSE_GATE. INCLUDED. Markers: `assert!(!is_paused(&config))`, `config.paused == false` on a shared config object.

Category C (State & Storage). Sui has no global storage; state lives in objects (owned/shared/wrapped/frozen). Semantics shift but the patterns still exist.

- SUI-C01 LOOP_STORAGE_MUTATION. INCLUDED. Marker: `dynamic_field::add`, `dynamic_object_field::add`, `table::add`, `object_table::add`, `bag::add`, or field writes on `&mut SharedObj` inside a loop.
- SUI-C02 UNBOUNDED_ITERATION. INCLUDED. Markers: `vector::length(v)` bound, `table::length`, `bag::length`, `while (i < n)` where `n` is user- or attacker-influenced.
- SUI-C03 READ_WRITE_GAP. INCLUDED. In Sui this shows up primarily across PTB command boundaries (see SUI-K03) and across cross-module calls; single-module RMW is not interruptible within a Move function because Move lacks true reentrancy. Keep the piece, narrow the typical call_context to cross-module or cross-command.
- SUI-C04 DELETE_IN_LOOP. INCLUDED. Markers: `vector::remove`, `table::remove`, `dynamic_field::remove` inside a while/for.
- SUI-C05 COUNTER_INCREMENT. INCLUDED. Markers: `counter.value = counter.value + 1`; monotonic ids on shared objects.
- SUI-C06 COLLECT_THEN_ITERATE. INCLUDED. Less common in Move, but valid.

Category D (External Dependencies & Oracles). Reconsider in Sui terms: there is no arbitrary external contract call with attacker-controlled bytecode at the callee; instead, cross-module calls resolve at link time (within published packages) and oracles are read from shared objects (Pyth, SupraOracles, Switchboard Sui).

- SUI-D01 ORACLE_PRICE_DEP. INCLUDED. Markers: `pyth::price_info::get_price`, `switchboard::aggregator::latest_value`, `supra_oracle_holder::get_price`.
- SUI-D02 ORACLE_STALENESS. INCLUDED. Markers: timestamp comparison against `clock::timestamp_ms(clock)` on a `&Clock` shared object (`0x6`).
- SUI-D03 CROSS_CONTRACT_CALL. INCLUDED, reshaped. In Sui this is a call into another PUBLISHED package's public function. The risk is not arbitrary-callee reentrancy; it is version pinning (the called package can be upgraded) and PTB composability (return values routed elsewhere). Typical_direction: neutral. Markers: any `module_x::function_y(...)` call where `module_x` is outside the current package.
- SUI-D04 QUERY_DEPENDENCY. INCLUDED. Markers: reads from shared objects owned by a different package version.
- SUI-D05 ORACLE_ERROR_SWALLOWED. INCLUDED. Markers: `option::is_none(&maybe_price) => return`, fallback to stale price.

Category E (Economic & DeFi Logic). All INCLUDED. Sui DEXes (Cetus, Turbos, Aftermath, DeepBook) all hit these patterns.

- SUI-E01 FIRST_DEPOSITOR_PATH. INCLUDED. Markers: `balance::value(&pool.reserve_x) == 0`.
- SUI-E02 PROPORTIONAL_SHARE. INCLUDED. Markers: `amount * total_supply / total_assets` patterns on LP/share `Coin<T>`.
- SUI-E03 FEE_COMPUTATION. INCLUDED.
- SUI-E04 SLIPPAGE_PROTECTION. INCLUDED. Markers: `assert!(amount_out >= min_out, ESlippage)`.
- SUI-E05 PRICE_FROM_RESERVES. INCLUDED. Relevant to all on-chain Sui AMMs (spot price manipulable within a single PTB, see SUI-K).
- SUI-E06 PASSIVE_ORDER_GEN. INCLUDED. Relevant to DeepBook resting orders.
- SUI-E07 CLEARING_PRICE_SELECTION. INCLUDED. Relevant to auction modules.
- SUI-E08 MINIMUM_SIZE_CHECK. INCLUDED.

Category F (Control Flow & Ordering). Reconsider in Sui terms. PTBs are atomic; there is no EVM-style `try/catch` and no `SubMessage::reply_on_error` partial-commit pattern.

- SUI-F01 CRON_BATCH. INCLUDED. Sui equivalent: off-chain keeper bot calling an entry function that iterates a shared queue. Markers: functions taking `&mut Queue` with bot-like naming.
- SUI-F02 CANCEL_BEFORE_CREATE. INCLUDED. Markers: same transaction removing then adding entries in a dynamic-field-backed queue.
- SUI-F03 MULTI_HOP_CHAIN. INCLUDED. Sui markers: sequential `Coin<T>` outputs feeding next `swap_exact_in` (either inside one function or across PTB commands; the latter overlaps with SUI-K01).
- SUI-F04 REPLY_ON_ERROR. EXCLUDED. Move has no partial-commit error-reply mechanism. An `abort` aborts the entire PTB atomically (Move's abort semantics + Sui's PTB atomicity). Retain no Sui piece for this; code that looks like it relies on partial rollback is a bug captured by SUI-K03 instead.
- SUI-F05 EARLY_RETURN_BRANCH. INCLUDED. Markers: `if (...) return`, guard clauses before state updates.

Category G (Token & Asset Handling). Sui uses `Coin<T>` (a resource with `key + store`) and `Balance<T>` (inner value type). Drop `FungibleAsset` language entirely.

- SUI-G01 FUND_VERIFICATION. INCLUDED. Markers: `assert!(coin::value(&payment) >= price)`, `balance::value(&b) >= amount`.
- SUI-G02 REFUND_CALCULATION. INCLUDED. Markers: `coin::split(&mut payment, refund_amount, ctx)`, `balance::split`.
- SUI-G03 MINT_AND_BURN. INCLUDED. Markers: `coin::mint(&mut TreasuryCap<T>, amount, ctx)`, `coin::burn(&mut TreasuryCap<T>, coin)`, `balance::create_supply`, `balance::increase_supply`.
- SUI-G04 DUST_ACCUMULATION. INCLUDED.

Category H (Ordering & Timing). Sui has checkpoints (not blocks) and epoch boundaries. Transaction order within a checkpoint is determined by consensus for shared-object transactions; owned-object transactions are processed without consensus.

- SUI-H01 BLOCK_HEIGHT_DISCRIMINATION. INCLUDED, renamed in description only (still `BLOCK_HEIGHT_DISCRIMINATION` for id/name parity). Markers: `tx_context::epoch(ctx)`, `tx_context::epoch_timestamp_ms(ctx)`, `clock::timestamp_ms(clock)` comparisons.
- SUI-H02 MAKER_TAKER_SPLIT. INCLUDED. DeepBook-style markers.
- SUI-H03 ORDER_ID_MANIPULATION. INCLUDED. Markers: `id << bits | data` on DeepBook order ids.

Category I (Validation & Invariants). All INCLUDED.

- SUI-I01 INVARIANT_PRESERVATION. INCLUDED. Markers: `assert!` checks on `x * y >= k` or `total_shares * reserve_a == constant`.
- SUI-I02 BALANCE_ACCOUNTING. INCLUDED. Markers: `balance::value` before/after, `supply` reconciliation, `Coin<T>` conservation.

Excluded count: 2 (SUI-B02 SELF_CALLBACK_GATE, SUI-F04 REPLY_ON_ERROR). Both are EVM/CosmWasm idioms with no Sui analogue; their hole is covered by the new J/K categories below.

---

## 2. New native categories

Five new categories: J, K, L, M, N. Each type has id, name, category, description, markers (Sui-specific), typical_direction.

### Category J: Object Model

Sui's defining primitive. Every struct with `key` ability is an on-chain object with a UID. Ownership (owned / shared / frozen / wrapped) determines access paths. Mistakes here are the #1 Sui vulnerability class (per object-ownership SKILL.md).

- id: SUI-J01, name: SHARED_OBJECT_UNGUARDED_WRITE, category: J.
  description: `public` or `entry` function accepts `&mut SharedObject` without a capability check or sender check; any transaction can mutate it.
  markers: function signature pattern `fun foo(obj: &mut T, ...)` where `T` is shared-at-init (created via `transfer::public_share_object` or `transfer::share_object`) and the body contains no `assert!(tx_context::sender(ctx) == obj.owner)` or cap-holding parameter.
  typical_direction: favors_user.

- id: SUI-J02, name: OWNED_OBJECT_UID_REUSE, category: J.
  description: UID from `object::new(ctx)` allocated then stored on an unreachable path, or an object is destructured and a stale `ID` is reused in a later equality check.
  markers: `object::new(ctx)` paired with no matching `transfer::*` / `object::delete` / field store; `id::copy` or manual id comparison with destructured ids.
  typical_direction: neutral.

- id: SUI-J03, name: VERSION_BUMP_MISSING, category: J.
  description: Mutation to a shared object that holds a `version: u64` or similar monotonic field does not bump the field, so cross-version access (SUI-L) cannot be gated.
  markers: struct field named `version` / `schema_version` present; mutating function body writes other fields but does not increment `version`.
  typical_direction: favors_user.

- id: SUI-J04, name: IMMUTABLE_OBJECT_WRONGLY_MUTATED, category: J.
  description: Function attempts logical mutation of state that was frozen via `transfer::public_freeze_object` (either via dynamic field on a frozen parent, or via a freeze that happens before config finalization).
  markers: `transfer::public_freeze_object` or `transfer::freeze_object` call on object whose dynamic fields are still being added, or where subsequent functions expect to update the object.
  typical_direction: favors_protocol (bricks functionality) or neutral depending on context.

- id: SUI-J05, name: OBJECT_DELETE_WITHOUT_UID_DELETE, category: J.
  description: Struct is destructured but its `UID` field is not passed to `object::delete(id)`; or destructor drops the object while dynamic fields still exist on its UID.
  markers: `let T { id, ... } = obj;` pattern without subsequent `object::delete(id)`; dynamic-field add sites on the same UID with no corresponding remove before destruction.
  typical_direction: neutral (resource leak / stranded dynamic-field assets).

- id: SUI-J06, name: WRAPPING_A_SHARED_OBJECT, category: J.
  description: Shared object is moved into a wrapper struct's field; once wrapped, the shared object is inaccessible to other parties because it is no longer addressable on-chain. Dynamic fields on its UID become orphaned.
  markers: assignment of a shared-at-init object into another struct's field, absence of unwrap/extract path.
  typical_direction: favors_protocol (traps user funds) or neutral.

### Category K: PTB Composition

Programmable Transaction Blocks allow up to 1024 chained commands with typed return-value routing. Single-call security assumptions break under PTB composition.

- id: SUI-K01, name: PTB_OBJECT_HANDOFF_MISMATCH, category: K.
  description: Function returns `Coin<T>` / `Object` / hot-potato that a caller is assumed to forward to a specific follow-up function, but the return value is composable in a PTB and can be routed to any function taking that type.
  markers: `public fun` returning `Coin<T>`, struct with `key` ability, or hot-potato (zero-ability struct) where downstream expectation is implicit.
  typical_direction: favors_user.

- id: SUI-K02, name: PTB_TYPE_ARGUMENT_MISMATCH, category: K.
  description: A PTB routes a generic value across steps where `TypeArgument<T>` on one step does not match `TypeArgument<U>` expected on the next, but the module fails to assert phantom-type equality (e.g., `Coin<USDC>` handed to a pool expecting `Coin<USDT>`).
  markers: generic functions taking `Coin<T>` with no phantom-type pairing assertion; lack of `type_name::get<T>() == type_name::get<U>()` checks where pool pairing matters.
  typical_direction: favors_user.

- id: SUI-K03, name: PARTIAL_PTB_ROLLBACK_ASSUMPTION, category: K.
  description: Code assumes that a later PTB command can fail and leave earlier commands committed (EVM `try/catch` mental model). In Sui, PTBs are all-or-nothing: any abort rolls back the entire PTB. Any "safety net" built around partial commit is vacuous.
  markers: comments or code structure like "if step 2 fails, step 1 persists", use of `option::is_none` to handle "partial" outcomes across what turn out to be entry calls in a PTB.
  typical_direction: favors_user (the "defense" doesn't exist).

- id: SUI-K04, name: SPLIT_TRANSFER_REENTRY, category: K.
  description: Within one PTB, an attacker calls `SplitCoins` and `TransferObjects` between protocol commands to intercept a returned `Coin<T>` or to split it and deposit a subset back, creating a flash-loan-like pattern without an explicit flash-loan protocol.
  markers: protocol functions returning `Coin<T>` combined with protocol functions that read balances or compute rewards based on pool state; absence of same-transaction reward-claim gating.
  typical_direction: favors_user.

### Category L: Package Versioning

Sui packages are immutable at a given address. An "upgrade" publishes a new address linked via `UpgradeCap` lineage. Old-version code is callable forever unless the shared objects it touches enforce version guards.

- id: SUI-L01, name: UPGRADE_POLICY_TOO_PERMISSIVE, category: L.
  description: `UpgradeCap` retains `compatible` policy when `additive` or `dep_only` would be sufficient, widening the attack surface for future malicious upgrades.
  markers: `sui::package::UpgradeCap` present; no call to `sui::package::only_additive_upgrades`, `only_dep_upgrades`, or `make_immutable`.
  typical_direction: favors_protocol (more power to upgrader).

- id: SUI-L02, name: ENTRY_FN_SIGNATURE_CHANGE, category: L.
  description: New package version silently changes the behavior of an entry function whose signature is preserved (Move compatibility only enforces signatures and layouts, not semantics). Callers relying on prior behavior are broken.
  markers: v1 / v2 pairs of the same entry function with different internal logic; absence of version-gated dispatch.
  typical_direction: neutral.

- id: SUI-L03, name: FRIEND_VISIBILITY_LOST_ON_UPGRADE, category: L.
  description: `public(friend)` / `public(package)` visibility is re-declared across an upgrade in a way that exposes previously friend-only state to any module in the upgraded package.
  markers: visibility qualifier change between versions; new modules in v2 that call v1-era friend functions.
  typical_direction: favors_user.

- id: SUI-L04, name: UPGRADECAP_EXPOSURE, category: L.
  description: `UpgradeCap` has `store` (default) and is held by a single EOA, a shared object, or a wrapper with weak access control. Key compromise or accidental transfer replaces all package logic.
  markers: `UpgradeCap` transferred via `transfer::public_transfer` to deployer address; `UpgradeCap` stored inside a shared object; no multisig / timelock / DAO wrapper.
  typical_direction: favors_protocol (privilege escalation for whoever holds it).

### Category M: Dynamic Object Fields

`dynamic_field` and `dynamic_object_field` (DOF) let modules attach arbitrary typed children to any `UID`. This is powerful but expensive, unbounded by default, and easy to orphan.

- id: SUI-M01, name: DOF_UNBOUNDED_GROWTH, category: M.
  description: Code path that calls `dynamic_field::add` / `dynamic_object_field::add` in a loop or in a user-facing entry function with no cap. Growth increases storage costs for every subsequent operation and is a DoS vector.
  markers: `dynamic_field::add`, `dynamic_object_field::add`, `table::add`, `bag::add`, `object_bag::add` inside a loop or in a function with user-controlled call frequency.
  typical_direction: favors_user (griefing) or favors_protocol (rent capture).

- id: SUI-M02, name: DOF_KEY_COLLISION, category: M.
  description: Two distinct code paths add fields under the same `(TypeTag, name)` key. The second write silently overwrites the first (or aborts on type mismatch), corrupting state.
  markers: overlapping key types across modules, shared integer name-spaces for different logical children.
  typical_direction: neutral.

- id: SUI-M03, name: DOF_REMOVED_WITHOUT_DELETE_CASCADE, category: M.
  description: Parent object's destructor calls `object::delete(id)` without first removing all dynamic fields; the fields are orphaned on-chain, and if they hold `Balance<T>` or `Coin<T>` the value is stranded.
  markers: destructor pattern that destructures and deletes UID; audit-site `dynamic_field::add` calls on the same UID that are not matched by `dynamic_field::remove` calls prior to destruction.
  typical_direction: neutral (stranded assets, minimum MEDIUM per R9).

### Category N: Capabilities & Witnesses

Sui's cap pattern (objects with `key` ability used as proof-of-authorization) and one-time witness (OTW) pattern (struct type instantiated once in `init`) underpin access control. Both have characteristic failure modes.

- id: SUI-N01, name: ONE_TIME_WITNESS_REUSE, category: N.
  description: A type intended as a one-time witness is accepted outside `init`, or the module fails to assert `sui::types::is_one_time_witness(&otw)`, allowing the witness-gated function to be called more than once.
  markers: function accepting `OTW` type where OTW is not in `init` signature; missing `assert!(sui::types::is_one_time_witness(&otw))`.
  typical_direction: favors_user.

- id: SUI-N02, name: DISPLAY_CAP_EXPOSURE, category: N.
  description: `sui::display::Display<T>` or `sui::publisher::Publisher` object is made shared or transferred to an untrusted holder, letting anyone rewrite NFT metadata or claim publisher authority on types from this package.
  markers: `transfer::public_share_object(publisher)`, `Display<T>` transferred to non-admin, `Publisher` held by shared object.
  typical_direction: favors_user.

- id: SUI-N03, name: TREASURY_CAP_LEAK_VIA_PUBLIC_TRANSFER, category: N.
  description: `TreasuryCap<T>` (mint authority over a `Coin<T>`) is transferred via `transfer::public_transfer` to a recipient computed from function arguments, or stored inside a shared object with weak gating. Recipient gains unlimited mint authority.
  markers: `transfer::public_transfer(treasury_cap, recipient)` with attacker-influenced `recipient`; `TreasuryCap<T>` stored in a shared object with no cap-of-cap gating.
  typical_direction: favors_user.

---

## 3. Actor vocabulary

Sui-specific actor labels used in the `actor` field of piece entries. One-liner per actor.

- sender. The `tx_context::sender(ctx)` address that submitted the transaction / PTB. Default actor for user-facing entry calls.
- shared_object_updater. Any transaction that holds a `&mut` reference to a shared object for the duration of one PTB command; distinct from `sender` because anyone can be a shared_object_updater on an unguarded shared object.
- package_upgrader. Holder of the `UpgradeCap` for a given package; the only party who can publish a new version of the package.
- cap_holder. Holder of a non-upgrade capability object (`AdminCap`, `TreasuryCap<T>`, `Publisher`, `Display<T>`, protocol-specific caps). Generic role for privileged functions.
- consensus. The Sui consensus layer (Narwhal/Bullshark), which orders shared-object transactions. Relevant when a piece's outcome depends on ordering of two competing transactions.
- module_publisher. The address that originally published the package (holds the one-time witness via `init`, usually also initial `Publisher` and `UpgradeCap` holder). Distinct from package_upgrader only if `UpgradeCap` has been transferred.

---

## 4. Bridge types

Bridge pieces are piece types that connect otherwise-disconnected chunks of state or code and therefore act as composition hubs. These pieces should be weighted higher in puzzle-combination scoring.

- SUI-K pieces (all of K01..K04). PTB command handoff is the primary cross-function bridge in Sui. A `Coin<T>` or object returned by function A and consumed by function B via a PTB edge is exactly a bridge piece; combinations involving a SUI-K piece plus two independent state pieces are where flash-loan-style exploits live.
- SUI-L pieces (all of L01..L04). Package upgrade crosses TIME: v1 pieces and v2 pieces coexist and both touch the same shared-object state. SUI-L pieces bridge across the version axis.
- SUI-M pieces (M01, M02, M03). Dynamic (object) fields connect arbitrary code to arbitrary state: any module that knows the `(TypeTag, name)` key and has access to the parent UID can read or write. SUI-M pieces bridge unrelated modules.
- SUI-J pieces, specifically J01 and J06. Shared-object unguarded writes (J01) and shared-object wrapping (J06) bridge across callers: anyone can take the shared path. Object transfer across functions (J01 consumed by later J03 version-bump) is a typical bridge combo.

For the JSON authoring step: add a `bridge: true` field (or equivalent) on the above type ids.

---

## 5. Conflicting actor pairs

Pairs of actors whose co-occurrence on the same piece combination should lower feasibility score (they cannot both satisfy the piece in the same transaction unless one actor also controls the other).

- (sender, package_upgrader). An upgrade-path exploit requires the sender to hold `UpgradeCap`; if the finding assumes a generic sender, the combination is infeasible unless `UpgradeCap` is exposed (then collapse to just package_upgrader).
- (sender, cap_holder). Functions requiring a specific cap are not executable by an arbitrary sender; combos that assume both "any user" and "cap required" are internally contradictory.
- (shared_object_updater, consensus). Not a true conflict (consensus orders shared_object_updater txs) but a flag: combos that assume deterministic ordering from the sender's viewpoint conflict with consensus ordering being adversarial. Score this pair as reduced-feasibility, not infeasible.
- (module_publisher, sender). After publish time, `module_publisher` is an historical actor; combos that require module_publisher to act at audit-time are only feasible if the publisher address is still active and holds the relevant cap. Otherwise treat as infeasible.
- (package_upgrader, consensus). A package upgrade is an owned-object transaction (UpgradeCap is owned), so consensus ordering is NOT a factor. Combos that model upgrader-vs-consensus race conditions are infeasible.

For the JSON authoring step: encode as a `conflicting_actor_pairs: [[a, b], ...]` list with per-pair `feasibility_penalty`.

---

## 6. Extra elimination rules

Sui-specific rules applied during combination scoring to prune or downrank combos. Draft set of five.

- SUI-R1: Immutable-only combo. If every piece in a combination is anchored on a frozen (immutable) object and none of the pieces is from category L (package versioning), eliminate the combo. Immutable state cannot produce a state-transition exploit, and without a version axis the combo cannot change over time. Rationale: removes noise combinations involving config objects that were frozen at init.

- SUI-R2: PTB atomicity. Any combination whose exploit narrative requires "step X fails while step Y persists" within a single PTB is eliminated (or capped at LOW feasibility). Sui PTBs are atomic: an abort in command N rolls back commands 1..N-1. Pair this with SUI-K03 as a red-flag piece: if a combo includes SUI-K03 the combo is still valid (the finding IS the invalid assumption), but combos that independently invent a partial-rollback assumption are eliminated.

- SUI-R3: Owned-object cross-sender. A combination that requires two different senders to both hold the same owned object in the same transaction is eliminated. Owned objects have one owner; the only way two senders both "act on" the same owned object in one flow is via an intermediate transfer, which is itself a distinct piece that must appear explicitly in the combo.

- SUI-R4: UpgradeCap immutability. If the target package has called `sui::package::make_immutable(cap)` (detected during recon), eliminate every combination that includes a category-L piece. Upgrade path is closed.

- SUI-R5: Cap-gated + NO_ACCESS_CONTROL contradiction. Combinations that include both SUI-B01 (cap-gated owner-only) AND SUI-B03 (no access control) on the SAME function are eliminated as internally contradictory. A function either requires a cap or it doesn't.

- SUI-R6: DOF without shared UID. Combinations that route a dynamic-field key collision (SUI-M02) through an owned-object UID are downranked: owned UIDs cannot be concurrently written by multiple parties, so collision requires the owner to be both attacker and victim. Downrank to minimum feasibility unless the combo also includes a transfer piece that moves the owned object between actors.

---

## 7. Scoring weight recommendations

Baseline weight = 1.0 per piece. Recommend the following multipliers in the Sui taxonomy JSON.

Priority tier (weight 2.0): all of category J (Object Model), all of category K (PTB Composition), all of category L (Package Versioning). These are where Sui-specific HIGH/CRITICAL findings cluster, per the object-ownership, ptb-composability, and package-version-safety skills. Combinations missing at least one priority-tier piece should be further downranked by 0.5x at combo-score time (in addition to individual piece weights).

Medium tier (weight 1.5): category M (Dynamic Object Fields), category N (Capabilities & Witnesses). Individually serious but usually only CRITICAL when combined with a priority-tier piece.

Inherited tier (weight 1.0): SUI-A*, SUI-C*, SUI-D*, SUI-E*, SUI-F*, SUI-G*, SUI-H*, SUI-I* except where noted below. Unchanged from EVM defaults.

Boost overrides (weight 1.3):
- SUI-B03 (NO_ACCESS_CONTROL) in Sui is near-equivalent to a shared-object unguarded write; boost above the B baseline.
- SUI-D03 (CROSS_CONTRACT_CALL) represents cross-package calls that survive package upgrades (overlaps with L axis); boost.
- SUI-E05 (PRICE_FROM_RESERVES) because spot-price manipulation inside a single PTB is trivially atomic in Sui; boost.

Demotion override (weight 0.7):
- SUI-C03 (READ_WRITE_GAP): intra-function RMW is not interruptible in Move, so the only realization is cross-PTB-command, which is already captured by SUI-K pieces. Demote to avoid double-counting.

Encoding: author the JSON with a top-level `scoring` block:
`{ "default_weight": 1.0, "priority_categories": ["J", "K", "L"], "priority_multiplier": 2.0, "medium_categories": ["M", "N"], "medium_multiplier": 1.5, "per_type_overrides": { "SUI-B03": 1.3, "SUI-D03": 1.3, "SUI-E05": 1.3, "SUI-C03": 0.7 }, "combo_requires_priority": true, "combo_no_priority_penalty": 0.5 }`.

---

## 8. Cross-check notes

One paragraph per source, describing which design types cover which rule / skill, and any gaps.

`nextup/prompts/sui/generic-security-rules.md`. R1 (module call return validation) maps to SUI-D03, SUI-K01. R2 (griefable preconditions) maps to SUI-J01 (anyone can submit a tx touching a shared object and griefing preconditions) and SUI-K04. R3 (transfer side effects) maps to SUI-G01..G04 and SUI-J05. R4 (uncertainty + adversarial assumption) is methodology, not a piece. R5 (combinatorial impact) is exactly what the taxonomy feeds into; no piece. R6 (semi-trusted roles) maps to SUI-B01, SUI-N02, SUI-N03, SUI-L04. R7 (donation-based DoS) maps to SUI-J01 + SUI-M01 combos. R8 (cached parameters in multi-step) maps to SUI-C03 + SUI-K01. R9 (stranded asset floor) maps to SUI-J05, SUI-J06, SUI-M03. R10 (worst-state severity) is methodology. R11 (unsolicited transfers) maps to SUI-G01, SUI-N03 (anyone can send you Coins but specifically TreasuryCap leak covers the dangerous case). R12 (enabler enumeration) maps to every actor in section 3. R13 (anti-normalization user impact) is methodology. R14 (cross-variable invariants) maps to SUI-I01, SUI-I02, SUI-J03. R15 (flash-loan / PTB precondition manipulation) maps directly to all of K (SUI-K01..K04). R16 (oracle integrity) maps to SUI-D01, D02, D05, E05. R17 (state transition completeness) maps to SUI-J03, SUI-J05. MR1 (ability analysis) maps to SUI-J02, SUI-J05, SUI-N01..N03, SUI-L03. MR2 (bit-shift overflow) maps to SUI-A04, SUI-H03. MR3 (type safety / generics) maps to SUI-K02. MR4 (dependency / package version) maps to all of L. MR5 (visibility) maps to SUI-B03, SUI-L03. SR1 (object ownership model) maps to all of J and to SUI-N02, SUI-N03. SR2 (PTB composability) maps to all of K. SR3 (package version / upgrade safety) maps to all of L. SR4 (hot potato / capability) maps to SUI-K01 (hot-potato handoff), SUI-N01..N03. Gap: no piece explicitly models Sui `Clock` shared-object reads; it is implicit in SUI-D02 (staleness) and SUI-H01 (timestamp discrimination) and does not warrant its own type.

`nextup/agents/skills/sui/object-ownership/SKILL.md`. The full skill maps onto category J. Section 1 (Object Inventory) underpins the recon that populates J pieces. Section 2a (Owned Object Audit) -> SUI-J02. Section 2b (Shared Object Audit) -> SUI-J01. Section 2c (Frozen Object Audit) -> SUI-J04. Section 2d (Wrapped Object Audit) -> SUI-J06. Section 3 (Transfer Analysis) -> SUI-G* bleed plus SUI-J01/J05. Section 4 (Shared Object Mutation Safety) -> SUI-J01 + SUI-K04 combo. Section 5 (Object Wrapping/Unwrapping) -> SUI-J06, SUI-M03. Section 6 (UID Lifecycle Audit) -> SUI-J02, SUI-J05. Section 7 (Dynamic Field Audit) -> all of M. Full coverage.

`nextup/agents/skills/sui/ptb-composability/SKILL.md`. The full skill maps onto category K. Step 1 (Entry Point Inventory) and 1b (Single-Call Assumption Audit) -> SUI-K01 + SUI-K04. Step 2 (Multi-Step Composition Analysis) and 2b (Value Interception Pattern) -> SUI-K01, SUI-K02. Step 3 (Flash Loan via PTB, including hot-potato) -> SUI-K04 + SUI-E05 + SUI-I02. Step 4 (Shared Object Mutation Ordering, including 4a oracle, 4b balance, 4c state toggle, 4d reorder sensitivity) -> SUI-J01 + SUI-K04 combos. Step 5 (Hot Potato Enforcement) -> SUI-K01. Step 6 (Object Wrapping/Unwrapping in PTB) -> SUI-J06 + SUI-K04. Step 7 (Gas Budget Manipulation) -> SUI-M01. Full coverage.

`nextup/agents/skills/sui/package-version-safety/SKILL.md`. The full skill maps onto category L. Step 1 (Upgrade Policy Inventory) + 1b (Governance Assessment) -> SUI-L01, SUI-L04. Step 2 (Version Consistency Check) -> SUI-L02 + SUI-J03 combo. Step 3 (Dependency Version Pinning) -> SUI-L01 (indirectly via transitive dep policy). Step 4 (Type Compatibility Across Versions) -> SUI-L02, SUI-L03. Step 5 (Upgrade Migration Safety, version guard pattern) -> SUI-J03 + SUI-L02 combo. Step 6 (UpgradeCap Governance) -> SUI-L04. Full coverage.

`nextup/agents/skills/sui/ability-analysis/SKILL.md`. Shared Move skill. Maps onto SUI-J05 (drop ability on value-bearing objects), SUI-N01 (OTW typing), SUI-G03 (TreasuryCap abilities via MR1). No gap introduced.

`nextup/agents/skills/sui/bit-shift-safety/SKILL.md`. Shared Move skill. Maps onto SUI-A04 + SUI-H03. No Sui-specific addition needed.

`nextup/agents/skills/sui/centralization-risk/SKILL.md`. Maps onto SUI-B01, SUI-L04, SUI-N02, SUI-N03. Adequate.

`nextup/agents/skills/sui/cross-chain-timing/SKILL.md`. Niche skill for bridged assets; maps onto SUI-H01 + SUI-D02. No new piece needed.

`nextup/agents/skills/sui/dependency-audit/SKILL.md`. Maps onto SUI-L01 (third-party package pinning). Adequate.

`nextup/agents/skills/sui/economic-design-audit/SKILL.md`. Maps onto all of category E. Adequate.

`nextup/agents/skills/sui/external-precondition-audit/SKILL.md`. Maps onto SUI-K01 + SUI-K04 + SUI-D03. Adequate.

`nextup/agents/skills/sui/flash-loan-interaction/SKILL.md`. Maps onto SUI-K04 + SUI-E05 + SUI-I02. Adequate.

`nextup/agents/skills/sui/fork-ancestry/SKILL.md`. Sui has no fork ancestry; skill applies only to cross-chain projects. No piece needed in Sui taxonomy.

`nextup/agents/skills/sui/migration-analysis/SKILL.md`. Maps onto SUI-L02 + SUI-J03. Adequate.

`nextup/agents/skills/sui/oracle-analysis/SKILL.md`. Maps onto SUI-D01, D02, D05, E05. Adequate.

`nextup/agents/skills/sui/semi-trusted-roles/SKILL.md`. Maps onto SUI-B01, SUI-L04, SUI-N02, SUI-N03. Adequate.

`nextup/agents/skills/sui/share-allocation-fairness/SKILL.md`. Maps onto SUI-E01, E02, E04, I01. Adequate.

`nextup/agents/skills/sui/temporal-parameter-staleness/SKILL.md`. Maps onto SUI-D02, SUI-H01, SUI-C03. Adequate.

`nextup/agents/skills/sui/token-flow-tracing/SKILL.md`. Maps onto all of G + SUI-I02 + SUI-K01. Adequate.

`nextup/agents/skills/sui/type-safety/SKILL.md`. Maps onto SUI-K02 (TypeArgument mismatch) and MR3. Adequate.

`nextup/agents/skills/sui/verification-protocol/SKILL.md`. Methodology skill; does not need a piece type.

`nextup/agents/skills/sui/zero-state-return/SKILL.md`. Maps onto SUI-A07 + SUI-E01 + SUI-E08. Adequate.

Overall: every Sui skill's analysis output lands on at least one piece type. Two pieces (SUI-J04, SUI-L03) are slightly speculative; flag for revisit after first audit run on a real Sui codebase.
