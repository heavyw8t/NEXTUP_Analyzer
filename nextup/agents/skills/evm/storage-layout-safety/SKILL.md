---
name: "storage-layout-safety"
description: "Type Thought-template (instantiate before use) - Trigger Pattern STORAGE_LAYOUT flag detected"
---

# Skill: Storage Layout Safety

> **Type**: Thought-template (instantiate before use)
> **Trigger Pattern**: STORAGE_LAYOUT flag detected
> **Inject Into**: depth-state-trace, depth-edge-case
> **Finding prefix**: `[SLS-N]`
> **Rules referenced**: R1, R4, R8, R10, R14

Covers: memory vs storage confusion, lost writes, proxy/upgrade storage collisions, inline assembly slot safety, and storage semantic corruption.

This vulnerability class exists ONLY on EVM - type-safe VMs (Move, Solana's Borsh model) enforce layout correctness at the runtime level. EVM's untyped 256-bit slot model permits silent corruption when layouts diverge.

---

## Trigger Patterns
```
proxy|upgradeable|diamond|delegatecall|EIP1967|StorageSlot|
sstore|sload|assembly\s*\{|tstore|tload|reinitializer|
UUPSUpgradeable|TransparentUpgradeableProxy|BeaconProxy
```

---

## Step 1: Storage Surface Inventory

Map the contract's persistent state surface before analyzing bugs:

| # | Variable | Type | Slot Assignment | Written By | Read By | Proxy-Relevant? |
|---|----------|------|----------------|-----------|---------|-----------------|

For each state variable, determine:
- Sequential layout (compiler-assigned) vs manual slot (EIP-1967, custom `bytes32` constant)?
- Accessed via Solidity or via assembly `sstore`/`sload`?
- For structs: trace slot computation (base + offset). For mappings: `keccak256(key . slot)`. For arrays: `keccak256(slot) + index`.

Tag: `[TRACE:variable={name} → slot={computation} → writers={functions}]`

---

## Step 2: Memory vs Storage Confusion

For each function operating on structs or complex types:

### 2a. Reference Type Assignment
Trace every local variable of struct, array, or mapping type:
- Declared as `storage` or `memory`?
- If `memory`: is the function INTENDING to modify persistent state? If yes → lost write (copy modified in memory, never persisted).
- If `storage`: does every code path that modifies the reference complete without early return before the write?

### 2b. Parameter Data Location
For each function accepting struct/array parameters:
- Is the parameter `memory` or `calldata`?
- Does the function modify the parameter expecting persistence? `function update(MyStruct memory s)` modifies `s.field` but `s` is a memory copy - original unchanged.

### 2c. Library Forwarding
For libraries called via `using ... for`:
- Does the library function take `storage` or `memory` references?
- Mismatch between caller expectation and library signature → silent behavioral change.

Tag: `[TRACE:function={name} → var={var} → location={memory/storage} → write_persisted={YES/NO}]`

---

## Step 3: Proxy Storage Layout Analysis

### 3a. Implementation vs Proxy Slot Overlap
- Map slots used by PROXY (admin, implementation, beacon).
- Map slots used by IMPLEMENTATION (state variables from slot 0).
- Any overlap? For EIP-1967: verify randomized slots match spec (`bytes32(uint256(keccak256("eip1967.proxy.implementation")) - 1)`).

### 3b. Upgrade Layout Continuity
For each upgrade path (V1 → V2):
- V1 variables in SAME slots in V2? (no reordering, no type changes, no removed mid-sequence variables)
- New variables APPENDED after existing? (not inserted)
- Inheritance order identical? (different order = different slot assignment)
- `__gap` storage slots reserved? New variables consuming gap correctly?

### 3c. Diamond / Namespaced Storage
For EIP-2535 or namespaced storage:
- Each facet uses unique namespace (keccak256 of distinct string)?
- Can two facets share the same namespace accidentally?
- Storage structs within namespace consistent across facet upgrades?

Tag: `[TRACE:proxy_slot={N} → impl_var={name} → collision={YES/NO}]`

---

## Step 4: Assembly Storage Safety

For each inline assembly block using `sstore` or `sload`:

### 4a. Slot Computation
- Target slot hardcoded, constant-derived, or influenced by external input?
- If input-influenced → can attacker target ARBITRARY slots? Is slot value bounded/validated before `sstore`?

### 4b. Value Encoding
- Correctly handles types < 32 bytes? (`sstore` writes full 32 bytes - masking/shifting correct for packed slots?)
- For packed storage (multiple variables in one slot): does assembly preserve neighboring values?

### 4c. Transient Storage (EIP-1153)
If `tstore`/`tload` used:
- Correctly distinguished from `sstore`/`sload`? (transient cleared after tx, permanent is not)
- Critical state accidentally stored with `tstore` instead of `sstore`?

Tag: `[BOUNDARY:user_input={MAX} → computed_slot={value} → target={what_gets_overwritten}]`

---

## Step 5: Storage Semantic Corruption

### 5a. Deletion Consistency
When mapping entries or array elements are deleted:
- ALL auxiliary structures updated? (index arrays, counters, totals, role flags)
- `delete mapping[key]` clears value but leaves stale entries in enumeration arrays?

### 5b. Bit Packing / Bitmap Operations
For manual bit packing:
- Every write correctly MASKs target bits without corrupting neighbors?
- Stale bits cleared on deletion? (`|= (1 << n)` to set but `= 0` instead of `&= ~(1 << n)` to clear → clears ALL bits)

### 5c. Uninitialized Storage Reads
Variables read before explicit write:
- Default value (0, address(0), false) a VALID state the code handles correctly?
- `require(configuredValue > 0)` but never set → permanent DoS. `if (admin == address(0)) { unrestricted }` → open access until set.

Tag: `[TRACE:delete={op} → auxiliary={state} → updated={YES/NO} → consumer={func} → reads_stale={YES/NO}]`

---

## Key Questions (must answer all)
1. Does the contract use sequential layout, manual slots, or both?
2. For proxy patterns: do implementation variables overlap with proxy admin slots?
3. For assembly: can any `sstore` target be influenced by external input?
4. For struct operations: are all memory-reference modifications intentional (not lost writes)?
5. For deletion: are all auxiliary data structures updated when primary state is removed?

## Common False Positives
- **EIP-1967 compliant**: Standard randomized slots with verified computation → no collision
- **Intentional memory copy**: Read-only computation on a copy, no intent to persist → not a lost write
- **Reserved gaps with matching inheritance**: `__gap` consumed correctly → no layout shift
- **Audited library assembly**: Well-tested library (e.g., OpenZeppelin `StorageSlot`) → lower risk

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

10 curated findings from the local vuln DB. Each entry maps to one sub-category tag.

---

## [SLS-EX-01] Storage slot collision via missing key in slot derivation
*Tag: storage_slot | Severity: HIGH*

EmissaryLib.sol computes the storage slot for an emissary's configuration without including the sponsor in the derivation. Because the slot is keyed only on the emissary address, any caller can overwrite the configuration for any user's emissary, redirecting fund flows and stealing from open resource locks.

*Root cause*: Incomplete preimage in a manual `keccak256` slot computation. The sponsor variable was omitted, making distinct (sponsor, emissary) pairs map to the same slot.

*Fix pattern*: Include every disambiguating key in the slot preimage: `keccak256(abi.encode(sponsor, emissary, NAMESPACE))`.

*Source row*: 1050

---

## [SLS-EX-02] Custom `_initializableSlot()` override inverts `_disableInitializers()`
*Tag: storage_slot | Severity: HIGH*

Overriding `_initializableSlot()` to return a non-default slot causes `_disableInitializers()` to write to a slot that is never read by the initialization guard, effectively enabling all initializers rather than locking them. A proxy's implementation contract left uninitialized can be re-initialized by an attacker.

*Root cause*: `_disableInitializers()` was not designed to be slot-agnostic; it hard-codes the default slot, so any override breaks the guard logic.

*Fix pattern*: Ensure `_disableInitializers()` reads from the same slot as `_initializableSlot()`, or prohibit overrides of the initializable slot.

*Source row*: 2932

---

## [SLS-EX-03] Timelock `cancel()` clears arbitrary storage slots
*Tag: storage_slot | Severity: HIGH*

The `cancel()` function in a Timelock contract accepts a raw `id` without recomputing it from the operation parameters. A caller with `CANCELLER_ROLE` can pass a crafted `id` matching the storage slot for `minDelay`, zeroing it and allowing the Timelock to be re-initialized with zero delay, which grants immediate control.

*Root cause*: No validation that the supplied `id` corresponds to a real pending operation. The function treats it as a direct storage key.

*Fix pattern*: Recompute the id inside `cancel()` from the operation's parameters rather than accepting it as caller input.

*Source row*: 2935

---

## [SLS-EX-04] Diamond `appStorage` placed at slot 0 collides with facet globals
*Tag: diamond_storage | Severity: HIGH*

`Swapper.sol`, `SwapperV2.sol`, and `DexManagerFacet.sol` each declare `appStorage` as a top-level global at slot 0. When these contracts are used as facets in a diamond, their storage overlaps with any other facet that also starts variables at slot 0. This can silently corrupt access-control state.

*Root cause*: Diamond facets must use namespaced storage (EIP-2535 `getStorage()` pattern). Using sequential slot layout from slot 0 in multiple facets creates unavoidable collisions.

*Fix pattern*: Replace `appStorage` declarations with the diamond namespaced storage pattern: derive a unique `bytes32` slot per facet using `keccak256("facet.name.storage")` and read/write via assembly.

*Source row*: 14651

---

## [SLS-EX-05] Diamond AppStorage struct size mismatch causes slot collision between DiamondCutStorage and UpgradeStorage
*Tag: diamond_storage | Severity: HIGH*

`AppStorage` in `Storage.sol` embeds both `DiamondCutStorage` and `UpgradeStorage` as sequential structs. A miscalculation in their sizes caused `UpgradeStorage` to start earlier than expected, overlapping the tail of `DiamondCutStorage`. The collision caused the operator to lose governor privileges and corrupted stored block info.

*Root cause*: Struct sizes were tracked manually rather than derived from the compiler. A field size was wrong by a factor (bits vs bytes), causing the layout to shift.

*Fix pattern*: Append new data only to the end of `AppStorage`. Maintain a machine-readable artifact of the deployed layout and validate it in CI before every upgrade.

*Source row*: 13423

---

## [SLS-EX-06] Proxy does not follow EIP-1967, implementation slot at slot 0 collides with logic contract
*Tag: EIP1967 | Severity: HIGH*

A delegating proxy stores its `implementation` address at sequential slot 0. The logic contract also has state variables starting at slot 0. On any delegatecall, the logic contract's writes to its slot-0 variables overwrite the proxy's `implementation` pointer, enabling a takeover or bricking the contract.

*Root cause*: Using sequential (Solidity compiler-assigned) layout for proxy administrative variables instead of EIP-1967 pseudo-random slots.

*Fix pattern*: Store `implementation` at `bytes32(uint256(keccak256("eip1967.proxy.implementation")) - 1)` and `admin` at `bytes32(uint256(keccak256("eip1967.proxy.admin")) - 1)`.

*Source row*: 18920

---

## [SLS-EX-07] Governor delegator proxy non-compliant with ERC-1967, vulnerable to state collision
*Tag: EIP1967 | Severity: MEDIUM*

`AnvilGovernorDelegator.sol` stores proxy administrative state (implementation address) using sequential Solidity layout rather than ERC-1967 unstructured slots. If the logic contract introduces a state variable at slot 0 in a future upgrade, the implementation pointer is overwritten, making the proxy inoperable or hijackable.

*Root cause*: Proxy contract predates EIP-1967 or was written without consulting the standard.

*Fix pattern*: Migrate proxy admin variables to ERC-1967 slots. Verify with `storageLayout` output from `solc` that no logic variable overlaps the chosen slots.

*Source row*: 4217

---

## [SLS-EX-08] Missing `__gap` in upgradeable base contract allows future variable insertion to shift child slots
*Tag: storage_gap | Severity: HIGH*

`UpgradableMeson` inherits from `MesonStates` and other contracts that have no `__gap` reserve. Adding any state variable to `MesonStates` in a future upgrade shifts all slots in every inheriting contract, corrupting storage and breaking the protocol.

*Root cause*: Upgradeable contracts in an inheritance hierarchy must reserve a fixed number of slots via `uint256[N] private __gap` so parent contract upgrades consume gap slots rather than shifting child variables.

*Fix pattern*: Add `uint256[100] private __gap;` as the last storage variable in every upgradeable parent contract. Adjust the gap size down by the number of added variables in each upgrade.

*Source row*: 14760

---

## [SLS-EX-09] Multiple top-level storage inheritance without gaps corrupts layout on parent upgrade
*Tag: storage_gap | Severity: HIGH*

`RibbonThetaVault` and `RibbonDeltaVault` inherit from both `OptionsVaultStorage` and a vault-specific storage contract. Upgrading `OptionsVaultStorage` to add variables shifts the slots of the subsequently inherited storage contract, corrupting all state in the child vaults.

*Root cause*: The multiple-inheritance storage pattern requires that each parent contract consume a fixed slot budget via `__gap`. Without gaps, any parent upgrade is a breaking change to every child.

*Fix pattern*: Reserve slots in `OptionsVaultStorage` with `__gap` sized to bring the total to a fixed budget (e.g., 50 slots). Alternatively, make `OptionsVaultStorage` non-upgradeable and allow only the leaf contracts to be upgraded.

*Source row*: 17474

---

## [SLS-EX-10] New mapping inserted between existing storage slots on upgrade corrupts layout
*Tag: struct_reorder | Severity: MEDIUM*

`MarketFactory` was upgraded by inserting a new mapping between two already-occupied storage slots. Because the Solidity compiler assigns slots sequentially, all variables after the insertion point shifted by one slot, causing the contract to read stale or zero values for critical state variables.

*Root cause*: Upgradeable contracts must only append new variables after all existing ones. Inserting mid-sequence is equivalent to reordering.

*Fix pattern*: Always add new state variables at the end of the storage declaration order. Use `__gap` arrays to reserve slots for anticipated future additions, consuming them in place rather than inserting.

*Source row*: 4524


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Storage Surface Inventory | YES | | All state variables with slots |
| 2. Memory vs Storage Confusion | IF structs/complex types | | Data location of all references |
| 3. Proxy Storage Layout | IF proxy/upgradeable | | Slot overlap, upgrade continuity |
| 4. Assembly Storage Safety | IF assembly with sstore/sload | | Slot computation, value encoding |
| 5. Storage Semantic Corruption | IF delete/restructure ops | | Auxiliary state consistency |
