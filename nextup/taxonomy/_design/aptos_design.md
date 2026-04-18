# Aptos Move Puzzle-Piece Taxonomy -- Design Doc

Scope: design for an Aptos-Move-specific puzzle-piece taxonomy that a later
authoring agent turns into JSON. Source ground truth: the 45-type base
taxonomy in `nextup/taxonomy/puzzle_taxonomy.json`,
`nextup/prompts/aptos/generic-security-rules.md`, and every
`nextup/agents/skills/aptos/*/SKILL.md`.

ID convention: inherited entries use `APT-A01` etc. New native categories are
`J`-`N`. Piece-entry schema is preserved: id, type, category, file, function,
line_start, line_end, description, state_touched, actor, direction,
call_context, contract (= module), depends_on, snippet. The `contract` slot
holds the fully-qualified Move module (`addr::module_name`). Marker
conventions: `std::*`, `aptos_framework::*`, `aptos_std::*`,
`aptos_token_objects::*`, and Move keywords (`acquires`, `move_to`,
`move_from`, `borrow_global`, `borrow_global_mut`, `has key`, `has store`,
`has drop`, `has copy`, `phantom`, `public entry`, `public(friend)`,
`#[view]`, `#[randomness]`, `#[module_lock]`).

---

## 1. Inherited A-I types

All 45 base ids below. INCLUDED = kept under `APT-*` prefix with Move-specific
description and markers. EXCLUDED = dropped with rationale.

### A -- Arithmetic & Precision (all INCLUDED)

| id | status | description (Move) | markers | direction |
|----|--------|--------------------|---------|-----------|
| APT-A01 ROUNDING_FLOOR | INCLUDED | Integer truncation toward zero via `/` or `mul_div`. | `/` (u64/u128), `aptos_std::math64::mul_div`, `aptos_std::math128::mul_div` | favors_protocol |
| APT-A02 ROUNDING_CEIL | INCLUDED | Ceiling division in Move. | `(a + b - 1) / b`, `math64::mul_div_round`, `math128::mul_div_round` | favors_user |
| APT-A03 MIXED_ROUNDING_DIRECTION | INCLUDED | Floor and ceil mixed in one flow (deposit floor, withdraw ceil or reverse). | both `mul_div` and `mul_div_round` in one function or caller chain | neutral |
| APT-A04 PRECISION_TRUNCATION | INCLUDED | Narrowing `as` cast loses information. | `(x as u64)`, `(x as u32)`, `(x as u128)` after `mul_div` | favors_protocol |
| APT-A05 MULT_BEFORE_DIV | INCLUDED | Raw `a * b / c` risks u64 intermediate overflow before division. | `a * b / c` without `math64::mul_div` | neutral |
| APT-A06 CHECKED_ARITHMETIC_GAP | INCLUDED | Move aborts on overflow by default; variant is bypass via widen-then-cast or manual branches. | widen to u128 then cast back with no bound check, manual wrap helpers, `if (overflow) ...` branches | neutral |
| APT-A07 ZERO_AMOUNT_PASSTHROUGH | INCLUDED | Entry function accepts `amount == 0` and proceeds. | missing `assert!(amount > 0, E_ZERO)`, `coin::value(&c)`/`fungible_asset::amount(&fa)` unguarded | favors_user |

### B -- Access Control & Authorization

| id | status | description / rationale | markers | direction |
|----|--------|------------------------|---------|-----------|
| APT-B01 SIGNER_GATED (renamed from OWNER_ONLY) | INCLUDED | Function gated by `signer::address_of(s) == @admin` or address field in `Config`. | `signer::address_of`, `assert!(addr == @admin)`, `system_addresses::assert_aptos_framework` | neutral |
| APT-B02 SELF_CALLBACK_GATE | EXCLUDED | No `msg.sender == address(this)` in Move. Closest analog (`public(friend)`, `ExtendRef`-generated signer) is structural; runtime caller-address gate does not exist. Captured by APT-M (entry) and APT-K (capabilities). | -- | -- |
| APT-B03 NO_ACCESS_CONTROL | INCLUDED | `public entry` or `public` that mutates global state with no `&signer` check, or unchecked `&signer` address. | `public entry fun` with no `signer::address_of`, state-mutating `public fun` with no signer arg | favors_user |
| APT-B04 INIT_MODULE_PATH (renamed from GENESIS_BYPASS) | INCLUDED | Logic that only runs in `init_module` or guarded by `exists<Config>` / `initialized` flag. | `fun init_module(admin: &signer)`, `exists<Config>(@addr)` gate, `move_to<Config>(...)` with no re-init guard | neutral |
| APT-B05 PAUSE_GATE | INCLUDED | Function gated by pause flag in a `Config` resource. | `assert!(!config.paused, E_PAUSED)`, `borrow_global<Config>(@addr).paused` | neutral |

### C -- State & Storage (all INCLUDED)

| id | description (Move) | markers | direction |
|----|--------------------|---------|-----------|
| APT-C01 LOOP_STORAGE_MUTATION | `borrow_global_mut`, `move_to`, `move_from`, or `Table`/`SmartTable` write per iteration. | `borrow_global_mut<T>(addr)` in `while`/`vector::for_each`, `table::upsert` in loop | neutral |
| APT-C02 UNBOUNDED_ITERATION | Loop over user-influenced `vector`/`SmartVector`/`SimpleMap` with no cap. | `vector::length(&v)` bound with no `MAX`, `smart_vector::length` bound | neutral |
| APT-C03 READ_WRITE_GAP | `borrow_global` read, external call, write back. Reentrancy-equivalent window via dispatchable FA / closures. | `let v = borrow_global<T>(addr)` ... `other_mod::f(...)` ... write | neutral |
| APT-C04 DELETE_IN_LOOP | `table::remove`, `smart_table::remove`, `vector::remove`/`swap_remove` inside related loop. | `vector::remove(&mut v, i)` in `while (i < len)` | neutral |
| APT-C05 COUNTER_INCREMENT | Auto-incrementing nonce/id in a resource. | `counter.value = counter.value + 1`, `account::get_sequence_number` as app counter | neutral |
| APT-C06 COLLECT_THEN_ITERATE | Snapshot a collection before iterating. | `let snapshot = *collection;` then `vector::for_each` | neutral |

### D -- External Dependencies & Oracles (all INCLUDED)

| id | description (Move) | markers | direction |
|----|--------------------|---------|-----------|
| APT-D01 ORACLE_PRICE_DEP | Decision consumes Pyth / Switchboard / custom price feed. | `pyth::pyth::get_price`, `pyth::price_feed::get_price`, `switchboard::aggregator::latest_value` | neutral |
| APT-D02 ORACLE_STALENESS | Explicit staleness check vs `timestamp::now_seconds()` or Pyth `publish_time`. | `timestamp::now_seconds() - publish_time < MAX_AGE`, `pyth::price::get_publish_time` | neutral |
| APT-D03 CROSS_MODULE_CALL (renamed from CROSS_CONTRACT_CALL) | Call into another published module (synchronous, statically resolved). | `use other_addr::mod;` + `mod::f(...)`, `coin::transfer<T>`, `aptos_account::transfer`, `primary_fungible_store::transfer` | neutral |
| APT-D04 QUERY_DEPENDENCY | Read-time dependency on state owned by another module that can change. | `borrow_global` on external resource, `object::owner(obj)`, `fungible_asset::balance(store)` of external store | neutral |
| APT-D05 ORACLE_ERROR_SWALLOWED | `option::is_none` branch on oracle fetch returns default or skips validation. | `if (option::is_none(&price)) { return ... }`, `pyth::get_price_unsafe` | neutral |

### E -- Economic & DeFi Logic (all INCLUDED)

Economic patterns are chain-agnostic; only markers change.

| id | markers (Move) | direction |
|----|----------------|-----------|
| APT-E01 FIRST_DEPOSITOR_PATH | `if (total_supply == 0)`, `if (fungible_asset::supply(metadata) == 0)` | neutral |
| APT-E02 PROPORTIONAL_SHARE | `amount * total_supply / total_assets`, `math64::mul_div(amount, supply, assets)` | neutral |
| APT-E03 FEE_COMPUTATION | `amount * fee_bps / 10000`, `math64::mul_div(amount, fee_bps, BPS)` | favors_protocol |
| APT-E04 SLIPPAGE_PROTECTION | `assert!(amount_out >= min_amount_out, E_SLIPPAGE)` | favors_user |
| APT-E05 PRICE_FROM_RESERVES | `reserve_x / reserve_y`, DEX-module reserve reads (Thala, LiquidSwap, Pontem) | neutral |
| APT-E06 PASSIVE_ORDER_GEN | `reflect_curve`, `auto_fill_orders` | neutral |
| APT-E07 CLEARING_PRICE_SELECTION | `clearing_price`, `settlement_price` field access | neutral |
| APT-E08 MINIMUM_SIZE_CHECK | `assert!(amount >= MIN_AMOUNT, E_DUST)` | favors_protocol |

### F -- Control Flow & Ordering

| id | status | description / rationale | markers | direction |
|----|--------|------------------------|---------|-----------|
| APT-F01 CRON_BATCH | EXCLUDED | No built-in keeper/cron primitive in Aptos. Off-chain keepers call permissionless `public entry`, already covered by APT-M + APT-B03. Framework `aptos_framework::block` epoch hooks are not authored by user modules. | -- | -- |
| APT-F02 CANCEL_BEFORE_CREATE | INCLUDED | Within one entry or script, cancellations before creations over same set. | sequential `vector::remove` then `vector::push_back` | neutral |
| APT-F03 MULTI_HOP_CHAIN | INCLUDED | Step N output feeds step N+1 (multi-hop DEX, staged liquidation). | `for (i in 0..len)` with `amount = step(amount, route[i])`, `swap_exact_in_route` | neutral |
| APT-F04 REPLY_ON_ERROR | EXCLUDED | No CosmWasm reply/submessage. A Move tx commits fully or aborts fully. Partial-commit across transactions is captured by APT-H01 plus temporal-staleness skill. | -- | -- |
| APT-F05 EARLY_RETURN_BRANCH | INCLUDED | `if (cond) return` before critical state update or assertion. | `if (...) return`, `if (...) abort E_X` early in body | neutral |

### G -- Token & Asset Handling (all INCLUDED)

| id | description (Move) | markers | direction |
|----|--------------------|---------|-----------|
| APT-G01 FUND_VERIFICATION | Asserts supplied `Coin<T>` / `FungibleAsset` matches expected amount and metadata. | `assert!(coin::value(&c) >= required, ...)`, `assert!(fungible_asset::amount(&fa) == expected, ...)`, `assert!(fungible_asset::metadata_from_asset(&fa) == expected_metadata, ...)` | favors_protocol |
| APT-G02 REFUND_CALCULATION | Excess split off and returned via `extract`. | `coin::extract(&mut coin, refund)`, `fungible_asset::extract(&mut fa, refund)` | neutral |
| APT-G03 MINT_AND_BURN | Mint/burn via stored `MintRef`/`BurnRef` or legacy `MintCapability<T>`/`BurnCapability<T>`. | `fungible_asset::mint`, `fungible_asset::burn`, `coin::mint<T>`, `coin::burn<T>`, `managed_coin::mint` | neutral |
| APT-G04 DUST_ACCUMULATION | Floor truncation per-position in a loop. | `math64::mul_div(...)` in per-position loop | favors_protocol |

### H -- Ordering & Timing (all INCLUDED)

| id | description (Move) | markers | direction |
|----|--------------------|---------|-----------|
| APT-H01 BLOCK_HEIGHT_DISCRIMINATION | Current-block vs past-block item discrimination (~1s Aptos block time). | `block::get_current_block_height()`, `timestamp::now_microseconds()` compare, `created_at == current` | neutral |
| APT-H02 MAKER_TAKER_SPLIT | Maker vs taker fee split in an order book. | `maker_fee_bps`, `taker_fee_bps` fields | neutral |
| APT-H03 ORDER_ID_MANIPULATION | Bit packing on ids for sort. Note APT-J06 interaction: shift amount must be `< bit_width`. | `id << k`, `id | tag`, `!id` | neutral |

### I -- Validation & Invariants (all INCLUDED)

| id | description (Move) | markers | direction |
|----|--------------------|---------|-----------|
| APT-I01 INVARIANT_PRESERVATION | Explicit math invariant (`x*y >= k`, cross-resource sum). | `assert!(invariant_ok(...), E_INVARIANT)`, `assert!(pool.total == sum_user_amounts, ...)` | neutral |
| APT-I02 BALANCE_ACCOUNTING | Inflows == outflows + fees across `FungibleStore`/`CoinStore` vs internal books (R14). | `fungible_asset::balance(store) == config.total_deposited`, `coin::balance<T>(addr) == record.deposited` | neutral |

Summary: 42 of 45 inherited ids kept. Dropped: B02 SELF_CALLBACK_GATE,
F01 CRON_BATCH, F04 REPLY_ON_ERROR (all EVM / CosmWasm-idiomatic with no
Aptos analog). Renamed: B01 -> SIGNER_GATED, B04 -> INIT_MODULE_PATH,
D03 -> CROSS_MODULE_CALL.

---

## 2. New native categories (J-N)

### J -- Abilities

Sources: MR1, MR2, MR3 in generic-security-rules.md;
`ability-analysis/SKILL.md`; `bit-shift-safety/SKILL.md`;
`type-safety/SKILL.md`.

| id | description | markers | direction |
|----|-------------|---------|-----------|
| APT-J01 COPY_ON_VALUE_TYPE | Value-bearing struct (share, receipt, voucher) declared `has copy` -- duplication possible. | `struct Ticket has copy, drop { ... }`, any value struct with `copy` | favors_user |
| APT-J02 DROP_ON_OBLIGATION | Hot-potato / obligation struct declared `has drop`, permitting silent discard. | `struct FlashReceipt has drop { ... }`, `struct LockTicket has drop` | favors_user |
| APT-J03 STORE_ON_CAPABILITY | Capability wrapping `MintRef`/`BurnRef`/`TransferRef`/`ExtendRef`/`SignerCapability` declared `has store`, escaping module control. | `struct MintCap has store { ref: MintRef }`, `struct OwnerCap has store { cap: SignerCapability }` | favors_user |
| APT-J04 PHANTOM_TYPE_ESCAPE | `phantom` param with no runtime `type_info::type_of<T>()` check, allowing attacker substitution. | `struct Pool<phantom X, phantom Y> has key`, generic `fun deposit<T>` missing allowlist | favors_user |
| APT-J05 ABILITY_DOWNGRADE_VIA_WRAPPER | Wrapper struct grants abilities the inner value was denied (e.g. `copy` wrapper over non-copy ref). | wrapper abilities wider than inner warrants | favors_user |
| APT-J06 BIT_SHIFT_OVERFLOW | `<<`/`>>` with shift amount reaching/exceeding operand bit width -- VM aborts (Cetus root cause). | `1u128 << k` where `k` is parameter or computed, no `assert!(k < 128)` | favors_user |

### K -- Resources & Global Storage

Sources: MR1, AR1, R9; `ref-lifecycle/SKILL.md`; `reentrancy-analysis/SKILL.md`.

| id | description | markers | direction |
|----|-------------|---------|-----------|
| APT-K01 GLOBAL_BORROW_COLLISION | Two simultaneous borrows on same resource at same address -- runtime abort; often nested calls where callee also does `borrow_global_mut<T>(addr)`. | nested `borrow_global_mut<T>(addr)` caller + callee on same `T`/`addr`, `acquires T` chain collision | favors_user (DoS) |
| APT-K02 CAPABILITY_LEAK_VIA_RETURN | `public` function returns `*Ref` or `SignerCapability`, granting permanent irrevocable rights. | `public fun get_mint_ref(): MintRef`, return type containing `*Ref`/`SignerCapability` | favors_user |
| APT-K03 RESOURCE_INIT_RACE | Resource created lazily on first use rather than in `init_module`; attacker pre-creates at expected address. | `if (!exists<Config>(@addr)) { move_to<Config>(...) }` in permissionless fn, named-object pre-creation | favors_user |
| APT-K04 RESOURCE_NEVER_DESTROYED | No `move_from` path; object holds assets with no stored `DeleteRef`. Storage grows; assets stranded (R9). | resource defined with no `move_from<T>` anywhere, `generate_delete_ref` never called | neutral |
| APT-K05 SIGNER_CAP_AUTH_GAP | Stored `SignerCapability` used to sign as resource account with no caller-authority gate, or gate on admin-settable field. | `account::create_signer_with_capability(&cap)` in `public` fn with no signer assertion | favors_user |
| APT-K06 ACQUIRES_NOT_DECLARED | `acquires` list omits a resource accessed transitively (design smell, refactor-bug surface). | body calls `borrow_global<T>` or callee that does, no `acquires T` in signature | neutral |

### L -- FungibleAsset

Sources: R3, AR2; `fungible-asset-security/SKILL.md`;
`token-flow-tracing/SKILL.md`.

| id | description | markers | direction |
|----|-------------|---------|-----------|
| APT-L01 METADATA_NOT_VALIDATED | Function accepts `FungibleAsset` or reads `FungibleStore` with no metadata match check. | `fa: FungibleAsset` param with no `assert!(fungible_asset::metadata_from_asset(&fa) == expected, ...)`; `fungible_asset::balance(store)` without metadata check | favors_user |
| APT-L02 PRIMARY_STORE_DIRECT_WITHDRAW | Direct `fungible_asset::withdraw` via held `WithdrawRef` bypasses `dispatchable_fungible_asset::withdraw` hook. | `fungible_asset::withdraw(&withdraw_ref, store, amount)`, stored `WithdrawRef` | favors_user |
| APT-L03 SECONDARY_STORE_BYPASS | Protocol treats `primary_fungible_store` as authoritative but user holds secondary store balance (or reverse). | `primary_fungible_store::balance(addr, metadata)` as sole read, no secondary enumeration | favors_user |
| APT-L04 SPONSOR_FEE_BYPASS | Fee-on-transfer / sponsor hook charged but protocol uses pre-hook amount, or bypasses hook entirely. | protocol records `amount` before dispatch call, fee field in hook not reflected in books | favors_user |
| APT-L05 FREEZE_NOT_CHECKED | `deposit`/`withdraw` with no `fungible_asset::is_frozen(store)` gate -- DoS when store frozen. | `fungible_asset::deposit`/`withdraw` with no `is_frozen` gate | favors_user (DoS) |
| APT-L06 DEPOSIT_HOOK_MISSING | Custom FA has mint/burn refs but no `register_dispatch_functions` call; accounting assumes a hook that was never wired. | `dispatchable_fungible_asset::register_dispatch_functions` absent for asset whose design needs it | neutral |
| APT-L07 WITHDRAW_EVENT_INCONSISTENCY | Protocol's withdraw event amount differs from framework `fungible_asset` event amount (pre- vs post-fee), corrupting indexers. | custom `event::emit` before hook, framework event with different amount after | neutral |

### M -- Entry & Access

Sources: MR5, AR4; `semi-trusted-roles/SKILL.md`;
`centralization-risk/SKILL.md`.

| id | description | markers | direction |
|----|-------------|---------|-----------|
| APT-M01 UNSAFE_PUBLIC_ENTRY | `public entry` mutates privileged state with no `&signer` assertion, or asserts on a field not the address. | `public entry fun ...(s: &signer, ...)` with no `signer::address_of(s)`, or missing `&signer` while writing admin resource | favors_user |
| APT-M02 INTERNAL_VIA_ENTRY | Logical internal helper exposed as `public`/`public entry`, letting any caller skip the orchestrator. | helpers like `_apply_fee`, `recompute_shares` marked `public`/`public entry` instead of `public(friend)` | favors_user |
| APT-M03 VIEW_MUTATES | `#[view]` function mutates state via `borrow_global_mut`/`move_to`/`move_from`/event emit. | `#[view]` above body containing those ops | favors_user |
| APT-M04 RANDOMNESS_COMPOSABILITY | `randomness::*` usage missing `#[randomness]`, or `public`/`public entry` instead of `entry`-only -- undergasing / test-and-abort (AR4). | `randomness::u64_range` in `public entry` without `#[randomness]`, or in `public fun` | favors_user |
| APT-M05 FRIEND_BOUNDARY_TOO_WIDE | Wide `friend` list grants each friend access to every `public(friend)` function. | many `friend addr::mod;`, large `public(friend)` surface | favors_user |

### N -- Reentrancy via Back-Call

Sources: AR3; `reentrancy-analysis/SKILL.md`; Move 2.2 closures; dispatchable FA.

| id | description | markers | direction |
|----|-------------|---------|-----------|
| APT-N01 DISPATCHABLE_REENTRY | `dispatchable_fungible_asset::withdraw/deposit/transfer` called mid-state-update; hook in another module re-enters. | state mutation both before AND after `dispatchable_fungible_asset::*`, no `#[module_lock]` | favors_user |
| APT-N02 CLOSURE_CALLBACK_REENTRY | Function accepts caller-supplied closure (Move 2.0) and invokes it between state mutations; closure re-enters. | parameter of function type (`cb: |u64| -> u64`), `move |x|` capture, `FunctionValue` param | favors_user |
| APT-N03 EVENT_HOOK_BACK_CALL | Event triggers off-chain relay that calls back in same block, or framework dispatch forwards before protocol state settles. | `event::emit` immediately before cross-module call, no post-emit finalization | neutral |
| APT-N04 TRANSITIVE_CALL_CYCLE | A -> B -> C -> A cycle where C re-enters A through a `public` fn while A's borrow is still active -- abort (DoS) or stale-read exploit. | module graph has a cycle with mid-stream borrow; at least one leg is cross-module `public fun` | favors_user |

---

## 3. Actor vocabulary

Aptos uses capability- and signer-based authorization; no EVM-style
`msg.sender`. Actors are roles, not addresses.

- signer: holder of a `&signer` passed to an entry fn. Default end-user.
  Address extracted via `signer::address_of`.
- framework: code running as `aptos_framework`, `aptos_std`, `object`, or
  `primary_fungible_store`. Trusted; upgradeable via governance.
- governance: `aptos_framework::aptos_governance` signer; publishes framework
  updates and config changes.
- cap_holder: any address holding a capability resource (`MintRef`,
  `BurnRef`, `TransferRef`, `ExtendRef`, `DeleteRef`, `SignerCapability`,
  `coin::MintCapability<T>`, `coin::BurnCapability<T>`). Permission is by
  possession.
- module_publisher: owns the package; can publish module upgrades under
  `upgrade_policy` (arbitrary / compatible / immutable).
- multisig_signer: one of N on `aptos_framework::multisig_account`; action
  needs M-of-N across transactions.
- delegate: address to whom capability or signer authority has been
  delegated, typically via wrapped `SignerCapability` or a
  `dispatchable_fungible_asset` hook module.

---

## 4. Bridge types

Bridge types connect pieces across module / address / capability boundaries.
The combinator treats chains that touch at least one bridge as candidates;
chains with zero bridge pieces are filtered by APT-R1.

- APT-M01 UNSAFE_PUBLIC_ENTRY and APT-M02 INTERNAL_VIA_ENTRY: bridge
  external-transaction actors into internal module logic. Every chain
  starting from a user tx crosses an M-type piece.
- APT-N01 / APT-N02 / APT-N04: bridge forward-call and back-call halves of a
  reentrancy chain (CEI-violating mutation paired with hook-registered
  module call).
- APT-K02 CAPABILITY_LEAK_VIA_RETURN and APT-K05 SIGNER_CAP_AUTH_GAP: bridge
  far-apart code via capability handoff (cap created or stored in one piece,
  used in a distant piece).
- APT-L01 / APT-L02 / APT-L04: bridge cross-module token movement. An FA
  deposit in module A is often a withdraw from module B's store; the
  FungibleAsset object carries state across the boundary and is where
  accounting-desync findings bind.
- APT-D03 CROSS_MODULE_CALL: generic bridge whenever a chain crosses a
  `use other_addr::mod` boundary.

---

## 5. Conflicting actor pairs

Smaller than EVM. Aptos has no msg.sender spoofing or arbitrary-caller
patterns, so most pairs concern capability vs signer authority.

- (signer, non_signer_impersonator): a function reads an address field from
  a resource and treats it as authenticated while the true signer is
  different. Conflict when one piece proves the address and another assumes
  it.
- (governance, module_publisher): governance is expected to gate publisher
  actions but the module's `upgrade_policy` or admin setter allows the
  publisher to act without governance consent.
- (cap_holder, signer): capability- and signer-based authorizations guard
  overlapping actions; the weaker gate wins.
- (delegate, cap_holder): delegated cap use while the original cap_holder
  still holds the cap -- two actors with the same right.
- (framework, module_publisher): reliance on a framework invariant (primary
  store auto-creation, object non-deletability) while the publisher writes
  logic that would violate that invariant under a framework upgrade.

---

## 6. Extra elimination rules

Applied after the combinator produces candidate chains.

- APT-R1 SAME_MODULE_DISJOINT_RESOURCES: if every piece is in the same
  module, touches a resource-disjoint state set (no shared resource type,
  no shared address), and no capability (`*Ref`, `SignerCapability`) is
  shared, eliminate. No information flows between the pieces.
- APT-R2 ALL_VIEW_NO_ENTRY: if every piece has `#[view]` and the chain has
  no `public entry` / `public` mutating piece, eliminate. Exception:
  APT-M03 VIEW_MUTATES is itself the finding and bypasses this rule.
- APT-R3 TYPE_PARAM_INCOMPATIBLE: if two generic pieces require different
  concrete `T` at runtime (`Coin<USDC>` vs `Coin<APT>`) with no phantom or
  `type_info` bridge, eliminate. Monomorphization blocks the chain.
- APT-R4 UPGRADE_POLICY_IMMUTABLE: if the chain requires an upgrade-driven
  behavior change but the target module is published `upgrade_policy::immutable`,
  eliminate that chain variant.
- APT-R5 ABILITY_FORBIDS_CHAIN: if the chain requires duplicating a value
  or silently dropping an obligation and the struct abilities forbid it
  (no `copy` on value, no `drop` on obligation), eliminate.
- APT-R6 REF_NOT_GENERATED: if the chain depends on a capability that was
  never generated during object construction (assumes `DeleteRef` exists
  but `generate_delete_ref` was never called), eliminate.

---

## 7. Scoring weight recommendations

Weight multipliers applied to severity during chain scoring.

- Category J (Abilities): 1.5x. MR1 / MR2 -- ability misuse and shift
  overflow are root causes of Critical Aptos incidents (duplicated
  receipts, Cetus $223M shift bug).
- Category K (Resources & Global Storage): 1.4x. Capability leak, signer-cap
  auth gap, global-borrow collision -- high-impact and uniquely Aptos (AR1).
- Category L (FungibleAsset): 1.3x. FA is the default standard going forward;
  metadata-not-validated and dispatchable-hook bypass are common real findings
  (R3, AR2).
- Category N (Reentrancy): 1.3x. Move was historically reentrancy-free; Move
  2.2 closures + dispatchable FA broke the assumption; underweighted by
  default and needs boost.
- Category M (Entry & Access): 1.1x. Overlaps with inherited B-category; a
  small boost suffices.
- Inherited A / C / E / F / G / H / I: 1.0x unchanged.
- Category D with Pyth / Switchboard pieces: 1.2x (matches R16 emphasis).
- Chains containing BOTH a Section-4 bridge type AND a J- or N-category
  piece: additional +0.2x.

---

## 8. Cross-check notes

One paragraph per source. States whether each source is covered by the
inherited band (A-I), the new band (J-N), or both.

### `nextup/prompts/aptos/generic-security-rules.md`

R1 (call return / state validation) -> APT-D03 + APT-L01, both bands. R2
(griefable preconditions) -> APT-B05 + APT-K03 + APT-L05, both. R3 (transfer
side effects) -> APT-L, new only. R5 (combinatorial) -> I-category plus
scoring. R7 (donation DoS) -> APT-B05 + APT-K03, both. R8 (cached parameters)
-> APT-H01 + APT-D04, inherited. R9 (stranded assets) -> APT-K04, new. R11
(unsolicited transfers) -> APT-L03 + APT-I02, both. R12 (enabler enumeration)
is methodology, not a type. R14 (cross-variable invariant) -> APT-I01 /
APT-I02, inherited. R15 (flash loan) -> APT-J02 + APT-E*, both. R16 (oracle)
-> APT-D01 / APT-D02, inherited. R17 (state transition completeness) ->
APT-C03 / APT-F05, inherited. MR1 (abilities) -> APT-J01 / J02 / J03 / J05,
new. MR2 (bit shift) -> APT-J06, new. MR3 (generics / phantom) -> APT-J04
+ APT-K02, new. MR4 (dependency) cross-cuts into APT-D03 / APT-D04,
inherited. MR5 (visibility) -> APT-M, new. AR1 (ref lifecycle) ->
APT-K02 / K05, new. AR2 (dispatchable hooks) -> APT-L + APT-N01, new. AR3
(reentrancy) -> APT-N, new. AR4 (randomness) -> APT-M04, new.

### `ability-analysis/SKILL.md`

Drives APT-J01 / J02 / J03 / J05. New band only; A-I has no Move-ability
type.

### `bit-shift-safety/SKILL.md`

Drives APT-J06 (Cetus $223M precedent). New band only.

### `centralization-risk/SKILL.md`

Drives APT-B05, APT-M01 / M05, and the (governance, module_publisher)
conflict pair. Mixed -- B inherited for pause/owner, M new for
Move-specific access.

### `cross-chain-timing/SKILL.md`

Drives APT-H01 and APT-D04 plus APT-C05 (nonce). Inherited band primarily,
with APT-M01 (entry exposed to relayers) from the new band.

### `dependency-audit/SKILL.md`

Drives APT-D03 / D04 inherited and APT-R4 (upgrade-policy elim rule) new.
Both bands, main surface via scoring weight and `module_publisher` actor.

### `economic-design-audit/SKILL.md`

Drives APT-E* entirely. Inherited band only (E-category preserved because
DeFi economic patterns are chain-agnostic).

### `external-precondition-audit/SKILL.md`

Drives APT-D04, APT-B05, APT-L05. Mixed -- D inherited, L new.

### `flash-loan-interaction/SKILL.md`

Drives APT-J02 (drop-on-receipt), APT-E*, and APT-N01 / N02 when the
protocol is the flash lender with a hook-registered repay path. Both bands.

### `fork-ancestry/SKILL.md`

Not a type source -- informs weighting and enabler priors via Recon. Not
covered by either band; runs at recon, not piece extraction.

### `fungible-asset-security/SKILL.md`

Drives the entire APT-L category (L01-L07). New band only. Metadata
validation (L01) is the most common real FA finding.

### `migration-analysis/SKILL.md`

Drives APT-K04 (resource never destroyed), APT-K03 (init race during
re-init paths), APT-L06 (hook missing after Coin-to-FA migration),
APT-R4 (upgrade policy elim rule). Primarily new band with APT-D04
inherited for legacy V2/V3 reads.

### `oracle-analysis/SKILL.md`

Drives APT-D01 / D02 / D05 on Aptos-specific Pyth / Switchboard markers.
Inherited band only -- the skill refines markers rather than adding a type.

### `reentrancy-analysis/SKILL.md`

Drives APT-N01 / N02 / N04 entirely. New band only. Explicitly refutes the
"Move cannot reenter" assumption via Move 2.2 closures and dispatchable FA.

### `ref-lifecycle/SKILL.md`

Drives APT-K02 (cap leak), APT-K05 (signer-cap gap), APT-L02 (direct
withdraw bypassing hook), APT-R6 (ref-not-generated elim rule). New band
only.

### `semi-trusted-roles/SKILL.md`

Drives APT-M01, APT-M05, APT-K05, and (cap_holder, signer) /
(delegate, cap_holder) conflicts. Mixed -- B inherited for admin gating,
K/M new for capability and signer lifecycle.

### `share-allocation-fairness/SKILL.md`

Drives APT-E01 / E02 / E04 / E08. Inherited band only.

### `temporal-parameter-staleness/SKILL.md`

Drives APT-H01 and APT-D04 plus APT-C05 (counter drift). Inherited band
only.

### `token-flow-tracing/SKILL.md`

Drives APT-G01 / G02 / G03 / G04 inherited and APT-L01-L07 new. Both bands.

### `type-safety/SKILL.md`

Drives APT-J04 (phantom escape) and APT-K02 (type-witness forgery) new,
plus APT-R3 (type-param-incompat elim rule). New band only.

### `verification-protocol/SKILL.md`

Methodology source, not a type source. Not covered by either band.

### `zero-state-return/SKILL.md`

Drives APT-E01 (first-depositor) and APT-K03 (init race). Mixed band.

---

End of design document.
