# Move Pattern Hints (Aptos & Sui)

Language-specific markers for puzzle piece extraction in Move smart contracts.

## Arithmetic & Precision (Category A)

- **Floor rounding**: Integer division `a / b` (always truncates), `math::mul_div`
- **Ceil rounding**: `math::mul_div_ceil`, `(a + b - 1) / b`
- **Precision loss**: `(value as u64)` casts, `u256` to `u128` to `u64` downcasts
- **Overflow risk**: Bit shift `<<`/`>>` where shift >= bit width aborts in Move VM, `u64` multiplication overflow
- **Zero checks**: Missing `assert!(amount > 0)` before division or transfer

## Access Control (Category B)

- **Owner check**: `assert!(signer::address_of(account) == @admin)`, `only_admin` functions
- **Module authority**: `&signer` parameter validation, `@module_addr` checks
- **No check**: `public entry fun` without signer address validation
- **Object ownership (Sui)**: `transfer::share_object` vs `transfer::transfer` (shared vs owned)

## State & Storage (Category C)

- **Storage in loop**: `borrow_global_mut` inside while/loop, `table::upsert` in iteration
- **Unbounded iteration**: `while (i < vector::length(&v))` without cap, `simple_map` iteration
- **Resource lifecycle**: `move_to`, `move_from`, `borrow_global`, `borrow_global_mut` patterns
- **Object wrapping (Sui)**: `dynamic_field::add/remove`, object wrapping/unwrapping

## External Dependencies (Category D)

- **Oracle**: `pyth::get_price`, `switchboard::aggregator`, custom oracle modules
- **Cross-module call**: Calling functions from other published packages
- **Coin operations**: `coin::transfer`, `coin::merge`, `coin::extract` (external coin module)

## Economic Logic (Category E)

- **First depositor**: `if (total_supply == 0)`, initial LP calculation
- **Share calculation**: `amount * total_supply / total_assets`, proportional mint
- **Fee**: `amount * fee_bps / 10000`, `math::mul_div(amount, fee_rate, FEE_DENOMINATOR)`
- **Fungible Asset (Aptos)**: `fungible_asset::transfer`, `primary_fungible_store`, dispatchable hooks (reentrancy risk!)

## Control Flow (Category F)

- **Programmable Transaction Blocks (Sui)**: Composable calls within PTB -- atomic multi-step operations
- **Abort codes**: `abort ERROR_CODE` -- check what state was modified before abort
- **Package upgrades (Sui)**: `UpgradeCap`, version compatibility between old and new package versions

## Token Handling (Category G)

- **Coin split/merge**: `coin::extract`, `coin::merge` -- dust can be lost
- **Object transfer (Sui)**: `transfer::public_transfer`, `transfer::share_object`
- **Capabilities**: `MintCap`, `BurnCap`, `FreezerCap` -- who holds them matters

## Move-Specific Concerns

- **Ability constraints**: `key`, `store`, `copy`, `drop` -- missing abilities can lock assets
- **Type safety**: Generic type parameters `<T>` -- different `T` creates different resources
- **Hot potato pattern**: Structs without `drop` that must be consumed -- forced execution order
- **Ref lifecycle (Aptos)**: `ConstructorRef` → `TransferRef`/`MintRef`/`BurnRef` -- ref stored vs dropped
