# Rust / CosmWasm Pattern Hints

Language-specific markers for puzzle piece extraction in Rust smart contracts (CosmWasm, Grug, Sylvia).

## Arithmetic & Precision (Category A)

- **Floor rounding**: `checked_mul_dec_floor`, `checked_div_floor`, `checked_multiply_ratio_floor`, `into_int()`, `into_coins_floor()`
- **Ceil rounding**: `checked_mul_dec_ceil`, `checked_div_ceil`, `checked_multiply_ratio_ceil`, `into_coins_ceil()`
- **Precision loss**: `checked_into_dec::<N>()` (converting between decimal precisions), `Udec128` to `Uint128`, `as u64`
- **Unchecked ops**: `-=`, `+=`, `*=` operators (Rust trait ops, may panic on overflow/underflow in release builds depending on type), `wrapping_add`, `wrapping_sub`, `saturating_add`
- **Zero checks**: Look for missing `is_non_zero()`, `ensure!(!amount.is_zero())`, or guards placed AFTER state mutation

## Access Control (Category B)

- **Owner check**: `ctx.sender == ctx.querier.query_owner()?`, `ensure_admin`, `info.sender == config.admin`
- **Self-callback**: `ctx.sender == ctx.contract`, `info.sender == env.contract.address`
- **No check**: `execute` match arms without sender validation
- **Pause**: `ensure!(!PAUSED.load(deps.storage)?)`, `is_paused` checks

## State & Storage (Category C)

- **Storage in loop**: `.save()`, `.remove()`, `.update()` inside `for`/`while`/`.for_each`
- **Unbounded iteration**: `.range(..)` without `.take(N)`, or with `params.limit` (admin-controlled cap)
- **Collect-then-iterate**: `.collect::<Vec<_>>()?` followed by iteration (snapshot pattern)
- **Counter**: `NEXT_ID.update(|id| Ok(id + 1))`

## External Dependencies (Category D)

- **Oracle**: `OracleQuerier`, `query_price`, `oracle_price`
- **Staleness**: `MAX_ORACLE_STALENESS`, timestamp comparison
- **Cross-contract**: `Message::execute(addr, &msg, coins)`, `SubMessage::reply_on_*`
- **Queries**: `ctx.querier.query_*`, `QuerierWrapper`

## Economic Logic (Category E)

- **First depositor**: `if supply.is_zero()`, `MINIMUM_LIQUIDITY`
- **Share calculation**: `supply.checked_multiply_ratio(deposit, total)`, `mint_ratio`
- **Fee**: `checked_mul_dec(fee_rate)`, `1 - fee_rate`
- **Slippage**: `minimum_output`, `ensure!(output >= min)`

## Control Flow (Category F)

- **Cron**: `cron_execute`, `BeginBlocker`, `EndBlocker`
- **Reply handler**: `#[sv::msg(reply)]`, `reply()`, `ReplyOn::Error`
- **Multi-hop**: `.iter().fold(initial, |acc, step| ...)`, sequential swap routing

## Token Handling (Category G)

- **Fund check**: `ensure!(funds ==`, `info.funds.amount_of`
- **Refund**: `TransferBuilder`, `refunds = funds - deposits`
- **Mint/Burn**: `bank::ExecuteMsg::Mint`, `bank::ExecuteMsg::Burn`
