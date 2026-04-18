# Solana Puzzle-Piece Taxonomy - Design

Language: Solana (native + Anchor). ID prefix: `SOL-`. New native categories start at J.
Schema preserved: id, type, category, file, function, line_start, line_end, description, state_touched, actor, direction, call_context, contract (=program), depends_on, snippet.

Inherited A-I types are re-prefixed with `SOL-` and keep their numeric suffix. Markers are rewritten for Solana idioms (Anchor attributes, `solana_program`, `anchor_lang::prelude`, `anchor_spl::token`, `anchor_spl::token_2022`, `spl_token`, `spl_token_2022`, `pyth_sdk_solana`, `switchboard_solana`, raw `solana_program::program::invoke`, `solana_program::program::invoke_signed`, `Clock::get`, `Rent::get`, etc.).

---

## 1. Inherited A-I types

### A Arithmetic and Precision

SOL-A01 ROUNDING_FLOOR (INCLUDED). Integer division or `checked_div` that truncates toward zero when computing shares, rewards, or token amounts in a Solana program.
Markers: `checked_div`, `checked_div_euclid`, `u64::checked_div`, `u128::checked_div`, `saturating_div`, `.floor()` on `f64`, `Decimal::try_floor_u64` (spl-math), `amount / shares`, manual `mul_div` where final step is `/`.
typical_direction: favors_protocol.

SOL-A02 ROUNDING_CEIL (INCLUDED). Ceiling division applied to user-owed amounts (fee deduction, debt rounding, rent-exempt top-up).
Markers: `(a + b - 1) / b`, `spl_math::precise_number::ceiling_div`, `Decimal::try_ceil_u64`, `u64::div_ceil` (nightly / custom), `amount.checked_add(denom - 1)?.checked_div(denom)`.
typical_direction: favors_user (when user receives), favors_protocol (when user pays).

SOL-A03 MIXED_ROUNDING_DIRECTION (INCLUDED). Floor and ceil used in the same deposit/withdraw or borrow/repay pair in a Solana vault or lending program.
Markers: floor on mint and ceil on burn in the same `lib.rs`, paired `try_floor_u64` + `try_ceil_u64`, asymmetric rounding between `deposit.rs` and `withdraw.rs`.
typical_direction: neutral.

SOL-A04 PRECISION_TRUNCATION (INCLUDED). Downcasting `u128` to `u64`, `i64` to `i32`, or `Decimal` to raw integer units that loses information.
Markers: `as u64` after `u128` math, `try_into::<u64>()`, `spl_math::uint::U192 -> u64`, `Decimal::to_u64`, explicit `Pubkey::to_bytes()[..8]` truncation for discriminators.
typical_direction: favors_protocol.

SOL-A05 MULT_BEFORE_DIV (INCLUDED). `a * b / c` ordering in reward per share, fee, or share price math without widening to `u128`.
Markers: `a.checked_mul(b)?.checked_div(c)`, raw `a * b / c` on `u64`, missing upcast to `u128` before the multiply, absence of `spl_math::precise_number` / `mul_div` helpers.
typical_direction: neutral.

SOL-A06 CHECKED_ARITHMETIC_GAP (INCLUDED). Mixing `checked_*` with raw `+`, `-`, `*`, `/`, or `wrapping_*` / `saturating_*` in the same flow.
Markers: `wrapping_add`, `wrapping_sub`, `saturating_sub` next to `checked_add` on same state field, `unsafe { ... }` arithmetic blocks, debug-only overflow checks (Solana programs compiled in release lose default overflow panics unless `overflow-checks = true`).
typical_direction: neutral.

SOL-A07 ZERO_AMOUNT_PASSTHROUGH (INCLUDED). Deposit, stake, swap, or claim instruction that accepts `amount == 0` and still mutates state (counter bump, checkpoint update, PDA init).
Markers: missing `require!(amount > 0, ...)`, missing `require_neq!(amount, 0)`, absence of Anchor `#[account(constraint = amount > 0)]`.
typical_direction: favors_user.

### B Access Control and Authorization

SOL-B01 SIGNER_AUTHORITY (INCLUDED, RE-FRAMED from OWNER_ONLY). Instruction gated by `Signer`, `has_one = authority`, PDA authority match, or multisig vote rather than an EVM owner address.
Markers: `Signer<'info>`, `#[account(has_one = authority)]`, `#[account(constraint = ctx.accounts.authority.key() == state.authority)]`, `require_keys_eq!`, `invoke_signed` with PDA seeds as authority, `spl_governance` vote record check.
typical_direction: neutral.

SOL-B02 SELF_CALLBACK_GATE (EXCLUDED). Solana has no self-callback pattern. Programs do not call themselves by address; reentrancy is structurally different. If re-entry matters it is covered by SOL-L03 CPI_REENTRY.

SOL-B03 NO_ACCESS_CONTROL (INCLUDED). Public instruction handler that mutates state or moves lamports/tokens with no `Signer` constraint, no `has_one`, and no PDA authority check.
Markers: handler uses only `AccountInfo<'info>` or `UncheckedAccount<'info>` without manual owner/signer checks, no `Signer` in `Accounts` struct, no `require!` gate on `authority.is_signer`.
typical_direction: favors_user.

SOL-B04 GENESIS_BYPASS (INCLUDED, RE-FRAMED). Initialization-only path in Solana: `initialize` instruction that runs once and sets program state.
Markers: `#[account(init, payer = ..., space = ...)]`, `#[account(init, seeds = [...], bump)]`, Anchor `#[state]` deprecated, one-shot `is_initialized` flag, `init_if_needed` (also a footgun, see SOL-J07).
typical_direction: neutral.

SOL-B05 PAUSE_GATE (INCLUDED). Instruction gated by a `paused`/`halted`/`emergency_stop` flag stored in a config PDA.
Markers: `require!(!config.paused, ...)`, `#[account(constraint = !config.is_paused)]`, guardian-operated `pause` instruction.
typical_direction: neutral.

### C State and Storage

SOL-C01 LOOP_STORAGE_MUTATION (INCLUDED). Loop body that mutates an account (PDA vec, remaining_accounts state) per iteration.
Markers: `for acc in remaining_accounts.iter()` with `acc.try_borrow_mut_data()`, `for entry in state.vec.iter_mut()` followed by `state.exit()`, per-iteration `account.reload()`.
typical_direction: neutral.

SOL-C02 UNBOUNDED_ITERATION (INCLUDED). Loop over `remaining_accounts`, a `Vec<Pubkey>` inside a PDA, or an `AccountLoader` range without a hard cap enforced on-chain.
Markers: `for r in ctx.remaining_accounts.iter()` with no length check, `for p in state.queue.iter()` where `queue` is user-appendable, `AccountLoader::load_init` with attacker-controlled size.
typical_direction: neutral. CU-budget-aware: cap at 200k CU per instruction or 1.4M per tx.

SOL-C03 READ_WRITE_GAP (INCLUDED). Account field read, CPI executes, then the same field written or relied on without `reload`.
Markers: `let x = ctx.accounts.vault.amount; cpi::..(); use(x)` with no `vault.reload()?;` in between, cached `token_account.amount` across `invoke`.
typical_direction: neutral.

SOL-C04 DELETE_IN_LOOP (INCLUDED). `swap_remove`/`remove` from a `Vec` inside a PDA while iterating that same vec, or `close_account` inside a loop over accounts.
Markers: `state.entries.swap_remove(i)` inside `for i in 0..state.entries.len()`, per-iteration `close_account` CPI.
typical_direction: neutral.

SOL-C05 COUNTER_INCREMENT (INCLUDED). Monotonic counter inside a PDA used as nonce, order id, or position id.
Markers: `state.next_id = state.next_id.checked_add(1)?`, `state.nonce += 1`, `order_id: u64` field incremented in handler.
typical_direction: neutral.

SOL-C06 COLLECT_THEN_ITERATE (INCLUDED). Snapshot a `Vec` from an account before iterating, to avoid mutable-borrow conflicts or to isolate from in-flight CPI mutations.
Markers: `let snapshot: Vec<_> = state.entries.clone()` then `for e in snapshot`, `collect::<Vec<_>>()` over `AccountLoader` iterator.
typical_direction: neutral.

### D External Dependencies and Oracles

SOL-D01 ORACLE_PRICE_DEP (INCLUDED). Computation depends on Pyth, Switchboard, or in-program oracle feed.
Markers: `pyth_sdk_solana::load_price_feed_from_account_info`, `PriceFeed::get_price_unchecked`, `PriceFeed::get_price_no_older_than`, `switchboard_solana::AggregatorAccountData::get_result`, `switchboard_v2::AggregatorAccountData::check_staleness`.
typical_direction: neutral.

SOL-D02 ORACLE_STALENESS (INCLUDED). Explicit staleness check on oracle `publish_time` vs `Clock::get()?.unix_timestamp`.
Markers: `get_price_no_older_than(&clock, max_age)`, `clock.unix_timestamp - price.publish_time > MAX_AGE`, Switchboard `aggregator.check_staleness(clock.unix_timestamp, staleness_threshold)`.
typical_direction: neutral.

SOL-D03 CPI (INCLUDED, RE-FRAMED from CROSS_CONTRACT_CALL). Any Cross-Program Invocation. This is the Solana analog of external call and is also listed as bridge under Category L.
Markers: `solana_program::program::invoke`, `solana_program::program::invoke_signed`, `CpiContext::new`, `CpiContext::new_with_signer`, `anchor_spl::token::transfer`, `anchor_spl::token_2022::transfer_checked`, `spl_token::instruction::transfer`.
typical_direction: neutral.

SOL-D04 ACCOUNT_STATE_READ (INCLUDED, RE-FRAMED from QUERY_DEPENDENCY). Read of another program's account state (no RPC on Solana; all reads are account-passed-in).
Markers: `Account<'info, T>` where `T` is owned by a different program, `AccountLoader<'info, T>` on foreign program, raw `account.try_borrow_data()` with external owner, `pyth_sdk_solana::load_price_feed_from_account_info` (read of Pyth state).
typical_direction: neutral.

SOL-D05 ORACLE_ERROR_SWALLOWED (INCLUDED). Oracle load or price fetch that falls back to a default value, zero, or last-known price on error.
Markers: `get_price_no_older_than(...).unwrap_or(default)`, `if let Ok(p) = ... { ... } else { skip }`, `.unwrap_or_default()` on a `PriceFeed`, `match pyth_load { Err(_) => Price::default(), ... }`.
typical_direction: neutral.

### E Economic and DeFi Logic

SOL-E01 FIRST_DEPOSITOR_PATH (INCLUDED). Branch when `total_supply == 0` in an SPL-share vault.
Markers: `if vault.total_shares == 0 { shares = amount } else { shares = amount * total_shares / total_assets }`, seeding `MINIMUM_LIQUIDITY` to dead address.
typical_direction: neutral.

SOL-E02 PROPORTIONAL_SHARE (INCLUDED). SPL share mint proportional to deposit amount / total assets.
Markers: `shares = amount.checked_mul(supply)?.checked_div(vault.total_assets)?`, `mint_to` CPI keyed to that computation, LP mint authority held by vault PDA.
typical_direction: neutral.

SOL-E03 FEE_COMPUTATION (INCLUDED). Fee computed as bps of a user amount, with optional protocol fee split.
Markers: `amount * fee_bps / 10_000`, `fee = amount.checked_mul(config.fee_bps)?.checked_div(BPS_DENOMINATOR)?`, `protocol_fee_share`.
typical_direction: favors_protocol.

SOL-E04 SLIPPAGE_PROTECTION (INCLUDED). User-supplied `min_amount_out` / `max_amount_in` passed in `InstructionData`.
Markers: `require_gte!(amount_out, min_amount_out, ErrorCode::SlippageExceeded)`, `minimum_amount_out: u64` in `ix_data`.
typical_direction: favors_user.

SOL-E05 PRICE_FROM_RESERVES (INCLUDED). AMM spot price from on-chain token-account reserves.
Markers: `pool.reserve_a / pool.reserve_b`, `token_a_vault.amount`, `token_b_vault.amount` in price computation, constant-product swap math on Solana DEX.
typical_direction: neutral.

SOL-E06 PASSIVE_ORDER_GEN (INCLUDED). Program-generated orders placed by crank (e.g., Phoenix seat market makers, Meteora DLMM bin liquidity).
Markers: crank instruction places orders without a user signer, algorithmic bin rebalancing, `place_order` invoked by PDA authority.
typical_direction: neutral.

SOL-E07 CLEARING_PRICE_SELECTION (INCLUDED). Auction or batch clearing price inside a Solana order-book or auction program.
Markers: `settlement_price`, `clearing_slot`, `uniform_price_auction` helper, `FairAuction::clear`.
typical_direction: neutral.

SOL-E08 MINIMUM_SIZE_CHECK (INCLUDED). Minimum order/deposit size enforced to prevent dust.
Markers: `require_gte!(amount, MIN_DEPOSIT)`, `min_lot_size`, `MINIMUM_LIQUIDITY`.
typical_direction: favors_protocol.

### F Control Flow and Ordering

SOL-F01 CRON_BATCH (EXCLUDED). Solana has no native cron. Keepers/bots run off-chain and submit transactions just like any other signer. The pattern is captured by SOL-M-crank (see Category L and the semi-trusted-role vocabulary).

SOL-F02 CANCEL_BEFORE_CREATE (INCLUDED). Batch instruction that processes cancellations before new creations in the same tx or the same crank pass.
Markers: `process_cancels(&mut book)?; process_places(&mut book)?;` ordering, batch `close_orders` before `place_orders`.
typical_direction: neutral.

SOL-F03 MULTI_HOP_CHAIN (INCLUDED). Multi-hop swap route: output of hop N feeds hop N+1 via CPI.
Markers: Jupiter-style `SwapRoute`, `route_plan: Vec<RoutePlanStep>`, `shared_accounts_route`, `exact_out_route`, sequential CPI into multiple AMM programs.
typical_direction: neutral.

SOL-F04 REPLY_ON_ERROR (EXCLUDED). Solana transactions are atomic: any instruction that aborts rolls back the whole tx, so there is no committed-on-error state for the caller to observe. `try_find_program_address` fallibles and `CpiContext` Results do not create partial-state reply patterns. Intra-tx account-state staleness after a CPI is covered by SOL-L05 ACCOUNT_RELOAD_MISSING and SOL-C03 READ_WRITE_GAP.

SOL-F05 EARLY_RETURN_BRANCH (INCLUDED). Conditional `return Ok(())` that skips state updates (checkpoints, fee accrual, reward index bump).
Markers: `if amount == 0 { return Ok(()); }` before `state.save`, guard clause returning `Ok(())` before invariant update.
typical_direction: neutral.

### G Token and Asset Handling

SOL-G01 FUND_VERIFICATION (INCLUDED). Assertion that a token account actually received the expected amount.
Markers: balance-before/balance-after around a `token::transfer` CPI, `require_eq!(vault.amount - pre, amount)`, post-CPI `reload()` + check.
typical_direction: favors_protocol.

SOL-G02 REFUND_CALCULATION (INCLUDED). Computation of excess lamports / tokens returned to user after an operation (e.g., minting order fills, over-collateralized deposits).
Markers: `refund_lamports = deposited - used`, `token::transfer(cpi_ctx, refund_amount)?`, `system_program::transfer` for lamport refund.
typical_direction: neutral.

SOL-G03 MINT_AND_BURN (INCLUDED). Mint or burn SPL / Token-2022 supply via CPI.
Markers: `anchor_spl::token::mint_to`, `anchor_spl::token::burn`, `anchor_spl::token_2022::mint_to`, `spl_token::instruction::mint_to`, `spl_token_2022::instruction::burn_checked`.
typical_direction: neutral.

SOL-G04 DUST_ACCUMULATION (INCLUDED). Repeated floor rounding in a per-user loop (e.g., reward distribution to a vec of users, per-validator delegation) that accumulates residual lamports in the vault PDA.
Markers: floor in `for user in users` loop, per-iteration `checked_div` with remainder dropped, missing `remainder` accounting.
typical_direction: favors_protocol.

### H Ordering and Timing

SOL-H01 SLOT_DISCRIMINATION (INCLUDED, RE-FRAMED from BLOCK_HEIGHT_DISCRIMINATION). Logic that treats items created in the current `Clock::slot` differently from prior slots. Also covers current-epoch vs prior-epoch logic.
Markers: `if entry.created_slot == clock.slot`, `if position.open_epoch == clock.epoch`, slot-age comparisons.
typical_direction: neutral.

SOL-H02 MAKER_TAKER_SPLIT (INCLUDED). Different fee rates based on order timing in a Solana orderbook (Phoenix, OpenBook, Zeta).
Markers: `maker_fee_bps`, `taker_fee_bps`, fill-side fee selection inside `match_orders`.
typical_direction: neutral.

SOL-H03 ORDER_ID_MANIPULATION (INCLUDED). Packed encoding of price+sequence into a `u128` order id for sort-order control (OpenBook-style).
Markers: `order_id = (price as u128) << 64 | seq_num`, bitwise NOT for descending sort, `FixedOrderedVec` / critbit tree node keys.
typical_direction: neutral.

### I Validation and Invariants

SOL-I01 INVARIANT_PRESERVATION (INCLUDED). Explicit mathematical invariant assertion after state mutation (constant product, total_shares tracks total_assets, `sum(user_deposit) == vault.total_deposit`).
Markers: post-op `require!(reserve_a * reserve_b >= k_before)`, `require_eq!(sum_of_users, vault.total)`.
typical_direction: neutral.

SOL-I02 BALANCE_ACCOUNTING (INCLUDED). Assertion that token/lamport inflows equal outflows plus fees, typically in a swap/deposit/withdraw handler.
Markers: balance-before / balance-after deltas around CPI transfers, vault `amount` diff matches `state.total_deposited` diff.
typical_direction: neutral.

### Excluded summary

- SOL-B02 (self-callback): no on-chain self-call pattern; reentrancy replaced by CPI-reentry.
- SOL-F01 (cron batch): keepers are off-chain signers; captured by permissionless_crank actor + standard CPI pieces.
- SOL-F04 (reply on error): Solana tx atomicity means no partial-commit reply pattern.

---

## 2. New native categories

### J Account Model

SOL-J01 MISSING_OWNER_CHECK. category J.
description: An `AccountInfo` or `UncheckedAccount` is deserialized or trusted without verifying `account.owner == expected_program_id`.
markers: `AccountInfo<'info>` used without `require_keys_eq!(acc.owner, &expected::ID)`, raw `Account::try_from` on untrusted input, missing `#[account(owner = expected)]`, manual `from_account_info` without owner guard.
typical_direction: favors_user.

SOL-J02 MISSING_SIGNER_CHECK. category J.
description: Authority-dependent instruction where the supposed authority is not constrained to be a `Signer`.
markers: authority passed as `AccountInfo` or `UncheckedAccount`, `require!(ctx.accounts.authority.is_signer)` missing, no `Signer<'info>` on authority field, `#[account(signer)]` absent.
typical_direction: favors_user.

SOL-J03 MISSING_DISCRIMINATOR_CHECK. category J.
description: Account data deserialized without checking the 8-byte Anchor discriminator or a manual type tag, enabling type confusion.
markers: manual `try_from_slice` on raw data, `zero_copy(unsafe)` without `AccountLoader::load`, `Account::try_deserialize_unchecked`, missing magic-number check in non-Anchor programs.
typical_direction: favors_user.

SOL-J04 ACCOUNT_ALIASING. category J.
description: Two or more mutable accounts in the same instruction are not constrained to be distinct, allowing the same account to alias `from` and `to`.
markers: two `Account<'info, T>` fields both marked `mut` with no `constraint = a.key() != b.key()`, missing `require_keys_neq!`, no `has_one` discriminating them, seeds that can collide.
typical_direction: favors_user.

SOL-J05 ACCOUNT_TYPE_CONFUSION. category J.
description: Same discriminator prefix or overlapping layout used by multiple account types so one can be substituted for another.
markers: shared `#[account]` struct prefix, manual discriminator assignment with reused constants, duplicate `Account<T>` sizes with similar leading fields, Anchor v0.24-class collisions.
typical_direction: favors_user.

SOL-J06 UNINITIALIZED_ACCOUNT_READ. category J.
description: Program reads account data before verifying the account has been initialized (all-zero state treated as valid).
markers: missing `is_initialized` flag check, no discriminator verification, `account.data_len() > 0` used as proxy for init, `init_if_needed` with default-zero exploitable state.
typical_direction: favors_user.

SOL-J07 REINITIALIZATION_ATTACK. category J.
description: Account can be closed (or becomes rent-insolvent) and then re-initialized with attacker-controlled state, or `init_if_needed` silently reuses an existing account with residual data.
markers: `init_if_needed`, manual close without discriminator-to-CLOSED sentinel, re-fundable closed account, revival-after-close-in-same-tx pattern.
typical_direction: favors_user.

SOL-J08 REMAINING_ACCOUNTS_INJECTION. category J.
description: `ctx.remaining_accounts` is iterated and used without per-account owner/type/signer/key-uniqueness validation.
markers: `for acc in ctx.remaining_accounts` with no `require_keys_eq!(acc.owner, &expected::ID)`, no discriminator load, no duplicate detection against named accounts.
typical_direction: favors_user.

### K PDA and Seeds

SOL-K01 UNCHECKED_PDA_DERIVATION. category K.
description: PDA supplied by the caller is not verified via `find_program_address` or an Anchor `seeds = [...]` constraint on-chain.
markers: PDA passed as `UncheckedAccount` with no `Pubkey::find_program_address` comparison in handler, missing `seeds = [...]` on `#[account]`, `create_program_address` used with attacker-influenced bump.
typical_direction: favors_user.

SOL-K02 SEED_COLLISION. category K.
description: Two PDA seed schemas can produce identical byte sequences, enabling one PDA to masquerade as another.
markers: variable-length user-controlled byte seed adjacent to a static-length seed without separator, shared `b"data"` prefix across multiple account types, no length-prefix byte.
typical_direction: favors_user.

SOL-K03 BUMP_NOT_STORED. category K.
description: Program re-derives a PDA on every access with `find_program_address` (expensive) or recomputes bump inconsistently, or accepts a user-supplied bump without canonicalization.
markers: `find_program_address` called inside handler instead of storing `bump` in account, no `bump` field on the PDA's account struct, bump read from instruction data.
typical_direction: neutral (correctness + CU).

SOL-K04 CANONICAL_BUMP_MISSING. category K.
description: PDA created or signed with a non-canonical bump (not the highest valid bump), or using `create_program_address` with user bump rather than `find_program_address`.
markers: `Pubkey::create_program_address(&seeds_with_user_bump, &program_id)`, `bump: u8` from ix data used in `invoke_signed`, no Anchor `bump` constraint.
typical_direction: favors_user.

SOL-K05 PDA_AUTHORITY_LEAK. category K.
description: A PDA used as signer in `invoke_signed` also controls unrelated resources; weaker instructions can use that PDA authority in ways the stricter ones forbid.
markers: single PDA seed schema signs transfers in both privileged and permissionless instructions, shared authority PDA across `swap` and `emergency_withdraw`.
typical_direction: favors_user.

SOL-K06 ATTACKER_CONTROLLED_SEEDS. category K.
description: PDA seeds include attacker-controlled bytes (strings, pubkeys, amounts) whose uniqueness or length is not bounded, enabling grinding or collision.
markers: seeds include unbounded `String::as_bytes()`, user-supplied `Pubkey` without `has_one`, numeric seeds without domain separator, front-runnable init seeds.
typical_direction: favors_user.

### L CPI

SOL-L01 CPI_TARGET_UNCHECKED. category L.
description: Target program id for the CPI is not validated against a hardcoded constant; attacker substitutes a malicious program matching the expected interface.
markers: `invoke(&instruction, &[accounts])` where `instruction.program_id` comes from an `AccountInfo` without `require_keys_eq!`, missing `#[account(address = spl_token::ID)]`, missing `Program<'info, Token>` type.
typical_direction: favors_user.

SOL-L02 MISSING_SIGNER_SEEDS. category L.
description: `invoke_signed` uses empty or wrong `signers_seeds`, or authority PDA is not actually signing, causing the CPI to fail or succeed with wrong authority.
markers: `invoke_signed(&ix, accounts, &[])`, incorrect `&[&[seed, &[bump]]]` order, mismatched bump with stored canonical bump.
typical_direction: neutral (correctness).

SOL-L03 CPI_REENTRY_RISK. category L.
description: CPI target program may re-enter the caller (via another CPI or indirect call) while the caller holds a mutable borrow on an account or has not yet updated state.
markers: CPI issued before `state.save`, CPI to program that itself can call back into this program, nested CPI chains approaching the 4-level depth limit, mutable account still in scope during CPI.
typical_direction: favors_user.

SOL-L04 CPI_RETURN_UNCHECKED. category L.
description: `sol_get_return_data()` is not read, or is read without verifying the returning program id matches the expected target (stale return data from an earlier program persists).
markers: CPI issued with expected return data but no `get_return_data()` call, return-data used without `program_id` check, assumption that empty return data means success.
typical_direction: favors_user.

SOL-L05 ACCOUNT_RELOAD_MISSING. category L.
description: After a CPI modifies an account, caller reads cached pre-CPI data (Anchor accounts cache at instruction start) without calling `reload()` or re-deserializing. The #1 most common Solana vulnerability pattern.
markers: post-CPI read of `ctx.accounts.x.amount` with no `ctx.accounts.x.reload()?` between CPI and read, stale `token_account.amount` after `token::transfer`.
typical_direction: favors_user.

SOL-L06 ARBITRARY_CPI. category L.
description: Instruction forwards attacker-supplied program id and account list into `invoke`, letting the attacker pick any program to call with the caller's authority/PDA.
markers: `invoke(&Instruction { program_id: user_supplied, ... }, ...)`, routing loop over `remaining_accounts` with user-controlled program ids, DEX-aggregator-style generic forwarder without allowlist.
typical_direction: favors_user.

SOL-L07 CPI_OWNER_CHANGE. category L.
description: CPI target can call `system_program::assign`, changing the owner of an account the caller still treats as its own. `reload()` alone does not re-check owner.
markers: post-CPI use of `account.try_borrow_data()` without `require_keys_eq!(account.owner, &crate::ID)`, trust in `account.owner` as stable across CPI.
typical_direction: favors_user.

### M Lamports and Rent

SOL-M01 DIRECT_LAMPORT_ARITHMETIC. category M.
description: Program mutates `account.lamports` via `try_borrow_mut_lamports` or `**acc.lamports.borrow_mut() -= x` bypassing `system_program::transfer`, potentially violating rent-exemption or conservation invariants.
markers: `**from.try_borrow_mut_lamports()? -= amount`, `**to.try_borrow_mut_lamports()? += amount`, manual lamport movement between program-owned accounts without System Program CPI.
typical_direction: favors_user (if arithmetic is wrong).

SOL-M02 RENT_EXEMPT_CHECK_MISSING. category M.
description: Account shrunk via `realloc`, or lamport withdrawn, without checking the remaining balance still covers `Rent::minimum_balance(data_len)`.
markers: `account.realloc(new_len, false)` with no `Rent::get()?.minimum_balance(new_len)` comparison, `lamports_to -= amt` followed by use of `from` account without rent check.
typical_direction: neutral.

SOL-M03 REALLOC_NO_ZERO_FILL. category M.
description: `realloc(new_len, false)` used when growing an account, leaving stale residual bytes; or `realloc` with `false` shrinks-and-regrows exposing old state.
markers: `account.realloc(new_len, false)` on growth path, missing zero-fill of the newly-extended region, trust in `realloc` default.
typical_direction: favors_user.

SOL-M04 RENT_SKIM_ON_CLOSE. category M.
description: Close handler drains lamports before the Anchor `close = receiver` mechanism or before setting discriminator to CLOSED sentinel, leaving rent partially recoverable by attacker or stranded.
markers: manual `**acc.lamports.borrow_mut() = 0` without also zeroing data + setting discriminator, partial lamport transfer in close, missing `close = recipient` on `#[account(close = recipient)]`.
typical_direction: favors_user.

SOL-M05 SIZE_DISCREPANCY_ON_REALLOC. category M.
description: `realloc` length does not match the serialized size of the new struct, causing truncation or over-read.
markers: `realloc(CONST_SIZE, ...)` that diverges from `INIT_SPACE`, hand-counted byte sizes that drift, Borsh-serialized length > allocated length.
typical_direction: favors_user.

### N Sysvar and Clock

SOL-N01 CLOCK_DRIFT_ASSUMPTION. category N.
description: Program relies on `Clock::unix_timestamp` precision below the +/-1-2s validator-estimation drift, or treats it as strictly monotonic.
markers: cooldown / timelock windows shorter than ~5s keyed on `unix_timestamp`, equality check `==` on `unix_timestamp`, absence of slot-based alternative.
typical_direction: neutral.

SOL-N02 SLOT_VS_UNIX_TIMESTAMP_CONFUSION. category N.
description: Program mixes `Clock::slot` and `Clock::unix_timestamp` for the same timing concept, or compares a stored slot against `unix_timestamp` or vice versa.
markers: config stores `period_slots: u64` but handler reads `clock.unix_timestamp` (or vice versa), arithmetic `slot - unix_timestamp`, inconsistent units across initiate/complete handlers.
typical_direction: neutral.

SOL-N03 SYSVAR_SHARED_READ. category N.
description: Same sysvar account (`Clock`, `Rent`, `Instructions`, `SlotHashes`, `StakeHistory`, `EpochSchedule`, `RecentBlockhashes`) is read by multiple pieces and used as a shared trust anchor.
markers: `Sysvar<'info, Clock>` referenced across multiple instructions, `sysvar::instructions::load_instruction_at_checked` in several flash-loan guards, `SlotHashes` read for randomness or ancestry.
typical_direction: neutral. Bridge piece.

SOL-N04 RECENT_BLOCKHASHES_MISUSE. category N.
description: Use of deprecated `RecentBlockhashes` sysvar (or `SlotHashes`) as a source of randomness without understanding the validator can influence it.
markers: `sysvar::recent_blockhashes::RecentBlockhashes`, `SlotHashes` read as entropy, commit-reveal schemes keyed on last blockhash only.
typical_direction: favors_user.

SOL-N05 STAKE_HISTORY_ASSUMPTION. category N.
description: Staking logic that assumes `StakeHistory` is always current or available without validating the account.
markers: `sysvar::stake_history::StakeHistory` read without owner/address check, assumption of full activation/deactivation schedule coverage.
typical_direction: neutral.

SOL-N06 SYSVAR_SPOOFING. category N.
description: Sysvar passed as raw `AccountInfo` with no address check, so an attacker passes a fake account (Wormhole-class bug on Instructions sysvar).
markers: `AccountInfo` named `instructions` without `#[account(address = sysvar::instructions::ID)]`, `load_instruction_at_checked(&acc, ...)` on unchecked account, missing `require_keys_eq!(acc.key(), &sysvar::clock::ID)`.
typical_direction: favors_user.

### O SPL Token and Token-2022

SOL-O01 MINT_AUTHORITY_UNVERIFIED. category O.
description: Program trusts a mint without checking `mint.mint_authority` matches the expected PDA or revoked state; or program holds mint authority but does not guard against authority transfer.
markers: missing `require_keys_eq!(mint.mint_authority.unwrap(), expected_pda)`, missing `has_one = mint_authority`, unchecked `COption<Pubkey>`.
typical_direction: favors_user.

SOL-O02 ATA_NOT_CANONICAL. category O.
description: Associated Token Account is not validated against the canonical `get_associated_token_address(owner, mint)` (or `get_associated_token_address_with_program_id` for Token-2022).
markers: `TokenAccount` passed without `#[account(associated_token::mint = ..., associated_token::authority = ...)]`, manual ATA derivation skipped, `create_associated_token_account` without address check.
typical_direction: favors_user.

SOL-O03 TRANSFER_HOOK_IGNORED. category O.
description: Program interacts with a Token-2022 mint that may carry the TransferHook extension and does not account for CU or revert risk from the hook program.
markers: `anchor_spl::token_2022::transfer_checked` without extension allowlist, missing `ExtensionType::TransferHook` check, missing additional-account list for hook.
typical_direction: favors_user.

SOL-O04 TRANSFER_FEE_IGNORED. category O.
description: Program assumes `transfer_checked` moves the gross amount; Token-2022 TransferFee extension deducts a fee so `amount_received < amount_sent`.
markers: accounting uses gross `amount` after `transfer_checked` on a fee-bearing mint, missing `ExtensionType::TransferFeeConfig` handling, no `calculate_epoch_fee` call.
typical_direction: favors_user.

SOL-O05 FREEZE_AUTHORITY_IGNORED. category O.
description: Mint has a live freeze authority that can freeze protocol-owned ATAs or user ATAs, DoS'ing redemption / rewards.
markers: `mint.freeze_authority` check missing, unchecked `COption<Pubkey>` for freeze authority, no allowlist of safe freeze-authority pubkeys.
typical_direction: neutral.

SOL-O06 DECIMALS_ASSUMPTION. category O.
description: Program hardcodes decimals (usually 6 or 9) rather than reading `mint.decimals`, or uses one mint's decimals in arithmetic against another mint's amount.
markers: `const DECIMALS: u8 = 9`, `amount * 10u64.pow(9)`, cross-mint math with single `decimals` constant, missing `mint.decimals` read.
typical_direction: favors_user.

SOL-O07 INTEREST_BEARING_IGNORED. category O.
description: Token-2022 InterestBearing extension means `mint.supply` / UI amount drifts over time; static-amount accounting treats it as flat.
markers: `ExtensionType::InterestBearingConfig` present but no `amount_to_ui_amount` usage, accounting on raw amount without interest factor.
typical_direction: favors_user.

SOL-O08 NON_TRANSFERABLE_IGNORED. category O.
description: NonTransferable extension prevents third-party transfer; protocol expects to move user tokens but will revert at runtime.
markers: `ExtensionType::NonTransferable` not checked, DEX/vault that assumes it can always `transfer` custody.
typical_direction: neutral (DoS).

SOL-O09 CONFIDENTIAL_TRANSFER_IGNORED. category O.
description: ConfidentialTransfer extension hides balances from direct reads; protocol that keys accounting off `token_account.amount` reads zero.
markers: `ExtensionType::ConfidentialTransferAccount`, direct `token_account.amount` usage on confidential-capable mints, missing non-confidential pending-balance check.
typical_direction: favors_user.

SOL-O10 PERMANENT_DELEGATE_PRESENT. category O.
description: Mint has `PermanentDelegate` extension that can transfer FROM any ATA of that mint without owner approval.
markers: `ExtensionType::PermanentDelegate` present, vault PDA holds tokens of such a mint with no drain mitigation, no allowlist of trusted permanent delegates.
typical_direction: favors_user.

SOL-O11 MINT_CLOSE_AUTHORITY. category O.
description: Mint has `MintCloseAuthority` extension; mint can be closed (supply == 0) and subsequent reads return zero decimals / supply.
markers: `ExtensionType::MintCloseAuthority`, reads of `mint.decimals` / `mint.supply` without MintCloseAuthority-aware guard.
typical_direction: favors_user.

SOL-O12 DEFAULT_ACCOUNT_STATE_FROZEN. category O.
description: DefaultAccountState extension makes new ATAs start frozen; protocol's init-then-use pattern fails until a thaw.
markers: `ExtensionType::DefaultAccountState` == Frozen, protocol that does `init_associated_token_account` then immediately `transfer` without thaw handling.
typical_direction: neutral (DoS).

SOL-O13 CPI_GUARD_VS_DELEGATION. category O.
description: User enabled CPI Guard on their token account; program relies on delegated CPI transfer, which fails silently or errors.
markers: `ExtensionType::CpiGuard`, protocol expects `approve` + CPI `transfer`, missing fallback to direct signer transfer.
typical_direction: neutral.

---

## 3. Actor vocabulary

Solana uses capability-based auth via `Signer`, PDA-derived authority, and per-account ownership. The EVM `owner / any_user` dichotomy is too coarse.

- signer. Any account whose `is_signer == true` in the current instruction. Baseline capability: can authorize instructions; identity-bound to a keypair.
- non_signer. Account passed without `is_signer`. Must NOT be used as an authority; many J-category findings hinge on this.
- pda. Program Derived Address; cannot sign an outer tx, can only sign via `invoke_signed` from its owning program with canonical seeds.
- program. `Program<'info, X>` account; executable. Used as CPI target; identity is its program id.
- upgrade_authority. Account stored in `BPFLoaderUpgradeable`'s ProgramData; can replace the program binary. Often overlooked as centralization risk.
- permissionless_crank. Any signer that can call a crank/keeper instruction designed to be economically open. Differs from `signer` by intent, not by auth.
- token_authority. Authority stored on an SPL Token account (`owner` field, OR `delegate` when approved). Governs `transfer`, `burn`, `close`.
- mint_authority. `Mint::mint_authority` optional pubkey; can `mint_to`. May be revoked (`None`).
- multisig_signer. Member of an `spl_token::Multisig` or `spl_governance` set; threshold of M-of-N signers collectively act as `signer`.
- freeze_authority. `Mint::freeze_authority`; can freeze/thaw any ATA of that mint. Treated as a high-centralization actor.

---

## 4. Bridge types

Solana bridges are accounts that are shared across pieces rather than function signatures as on EVM.

- SOL-D03 CPI. Every CPI is a bridge from the caller's state (passed accounts) to the target program's state. Rationale: a CPI piece in one instruction transitively links pieces in the target program, making it the canonical cross-program bridge.
- SOL-L01 CPI_TARGET_UNCHECKED. Bridge candidate: if the target is attacker-controllable, the bridge connects to an arbitrary unknown program, expanding reachability.
- SOL-L05 ACCOUNT_RELOAD_MISSING. Bridge between pre-CPI reads and post-CPI reads on the same account in a single instruction; staleness here connects otherwise independent pieces.
- SOL-L06 ARBITRARY_CPI. Strongest bridge type: connects to any program in the ledger by construction.
- SOL-N03 SYSVAR_SHARED_READ. Clock, Rent, Instructions, SlotHashes sysvars link pieces that read them even when no other account is shared. Classic pattern: two timelock pieces read the same `Clock` and become correlated via `unix_timestamp` monotonicity.
- SOL-J04 ACCOUNT_ALIASING. Bridges pieces that operate on supposedly-distinct accounts when the caller can make them the same account; connects `from` and `to` flow graphs.
- SOL-K01 UNCHECKED_PDA_DERIVATION. Bridges a piece to any PDA-derived state of the same program; unchecked derivation collapses many logical accounts into one address.
- SOL-K02 SEED_COLLISION. Bridges two PDA populations whose seed spaces overlap; collision means pieces on one account type can affect the other.
- SOL-K05 PDA_AUTHORITY_LEAK. Bridges privileged and permissionless pieces that share the same PDA as signer.
- SOL-L07 CPI_OWNER_CHANGE. Bridges a program-owned piece to a post-CPI attacker-owned version of the same account.

---

## 5. Conflicting actor pairs

Solana capability model is narrow: if you don't have `is_signer` you can't act as a signer. Most EVM actor conflicts collapse into one pair.

- (signer, non_signer). Required minimum. Justification: any piece that expects a `Signer` cannot be satisfied by a piece where the same account is `non_signer`. This is the core `is_signer` invariant.
- (pda, signer). PDAs cannot sign outer transactions. A piece that requires the outer signer to be a PDA is unreachable in real instructions. Useful as a negative conflict to prune impossible puzzles.
- (upgrade_authority, non_upgrade_authority). Distinct because upgrade authority controls program binary; findings combining upgrade authority with user instructions are almost always centralization findings, not exploit chains. Keep them conflicting to avoid spurious puzzles.
- (mint_authority, token_authority). Different capabilities; a piece that needs to `mint_to` cannot be satisfied by a piece that only has ATA-owner authority.

Optional soft conflicts (score penalty rather than elimination):
- (multisig_signer alone, single signer). Multisig threshold must be met; a single multisig member signing in isolation is insufficient.

No conflict needed between `permissionless_crank` and `signer`: permissionless crank IS a signer (just any signer).

---

## 6. Extra elimination rules

Beyond the shared elimination library, Solana uses account-topology and capability rules.

SOL-R1 ACCOUNT_OVERLAP_REQUIREMENT. Connectivity on Solana is via shared accounts, not function-call graphs. Eliminate a puzzle if:
- no two pieces touch any overlapping account, AND
- no piece is in category L (CPI), AND
- no piece is in category K (PDA derivation that could target a shared PDA), AND
- no piece is SOL-N03 (shared sysvar read).
Rationale: without any shared account, CPI, shared PDA, or shared sysvar, pieces are genuinely independent and cannot combine into a chain.

SOL-R2 ALL_QUERY_ELIMINATION. If every piece in the combo is read-only (only SOL-D04 ACCOUNT_STATE_READ or SOL-D01 ORACLE_PRICE_DEP with no accompanying state-mutating piece, no CPI, no lamport arithmetic, no token flow), eliminate. Solana programs manifest impact only through account mutation.

SOL-R3 PDA_MISSING_OWNER_BONUS. If a combo contains both a SOL-K* piece (PDA derivation) and a SOL-J01 piece (missing owner check) reachable in the same instruction, apply a scoring bonus; do NOT eliminate. Rationale: PDA + missing owner is the classic Solana substitution exploit; this is evidence of higher severity, not redundancy.

SOL-R4 SIGNER_REQUIREMENT_COHERENCE. Eliminate a combo where one piece's `actor` is `signer` but all state-mutating pieces act on accounts whose authority in those pieces is `non_signer`. Rationale: the signer is incidental and cannot be chained into the mutation.

SOL-R5 CU_BUDGET_FEASIBILITY. Eliminate a combo whose estimated compute cost exceeds the per-transaction 1.4M CU limit when all pieces execute sequentially in one transaction. Rule-of-thumb weights: each CPI piece 5k CU, each SHA256-keyed PDA derivation 1.5k CU, per-account-access 100 CU, Token-2022 with TransferHook add 50k CU. Keep cross-transaction chains for staleness-class combos.

SOL-R6 TOKEN22_EXTENSION_COHERENCE. Eliminate a combo containing two mutually exclusive Token-2022 extensions on the same mint (e.g., SOL-O08 NON_TRANSFERABLE and SOL-O10 PERMANENT_DELEGATE - the spec forbids both on one mint). Avoids impossible-mint puzzles.

SOL-R7 CPI_DEPTH_LIMIT. Eliminate combos whose CPI chain depth exceeds 4 (Solana runtime limit). Count each SOL-D03 / SOL-L* piece as a depth step; a puzzle needing 5 nested CPIs is unreachable.

SOL-R8 REMAINING_ACCOUNTS_DEPENDENCY. If a combo depends on SOL-J08 REMAINING_ACCOUNTS_INJECTION, require at least one other piece in categories C/G/L that actually uses `remaining_accounts`. Eliminate combos that include J08 but no consumer.

---

## 7. Scoring weight recommendations

Baseline category weights override the shared defaults for Solana.

- Category J Account Model: weight 1.4. Rationale: missing owner / missing signer / aliasing are the empirical majority of Solana exploits.
- Category K PDA and Seeds: weight 1.3. PDA bugs are high severity and Solana-specific.
- Category L CPI: weight 1.3. Account reload missing and CPI target unchecked are high frequency.
- Category O SPL Token and Token-2022: weight 1.25. PermanentDelegate / TransferHook / TransferFee cause real fund impact.
- Category N Sysvar and Clock: weight 1.1. Sysvar spoofing is critical when present; clock drift is generally Medium.
- Category M Lamports and Rent: weight 1.1. Direct lamport arithmetic bugs are high severity but rare.
- Category A Arithmetic: weight 1.0.
- Category B Access Control: weight 1.0 (most Solana access control is expressed through J + K).
- Category C State: weight 1.0.
- Category D External: weight 1.0 (oracle-specific pieces inherit the default).
- Category E Economic: weight 1.1.
- Category F Control Flow: weight 0.9 (F01/F04 dropped).
- Category G Token: weight 1.0.
- Category H Ordering: weight 1.0.
- Category I Invariants: weight 1.1.

Per-type overrides (multiplicative on top of category weight):

- SOL-J01 MISSING_OWNER_CHECK: 1.5.
- SOL-J02 MISSING_SIGNER_CHECK: 1.5.
- SOL-J08 REMAINING_ACCOUNTS_INJECTION: 1.4.
- SOL-K01 UNCHECKED_PDA_DERIVATION: 1.4.
- SOL-K02 SEED_COLLISION: 1.4.
- SOL-K04 CANONICAL_BUMP_MISSING: 1.3.
- SOL-L01 CPI_TARGET_UNCHECKED: 1.5.
- SOL-L05 ACCOUNT_RELOAD_MISSING: 1.5 (Solana's #1 bug class).
- SOL-L06 ARBITRARY_CPI: 1.5.
- SOL-L07 CPI_OWNER_CHANGE: 1.3.
- SOL-M01 DIRECT_LAMPORT_ARITHMETIC: 1.3.
- SOL-N06 SYSVAR_SPOOFING: 1.5 (Wormhole class).
- SOL-O03 TRANSFER_HOOK_IGNORED: 1.3.
- SOL-O04 TRANSFER_FEE_IGNORED: 1.4.
- SOL-O10 PERMANENT_DELEGATE_PRESENT: 1.5 (direct drain vector).
- SOL-J07 REINITIALIZATION_ATTACK: 1.4.

Combo bonuses (applied once per combo that matches):

- SOL-K* + SOL-J01 in same instruction: +0.3.
- SOL-L05 + SOL-E* (pricing/fees): +0.3 (stale balance used in pricing).
- SOL-L01 + SOL-G03 MINT_AND_BURN: +0.4 (fake token program for mint/burn).
- SOL-J08 + SOL-L06: +0.4 (arbitrary CPI over attacker-injected remaining accounts).
- SOL-O10 + any vault-holding piece: +0.3.
- SOL-N06 + any flash-loan-guard piece: +0.4.

---

## 8. Cross-check notes

Source: `nextup/prompts/solana/generic-security-rules.md`.
R1 (CPI return + reload) maps to SOL-L04, SOL-L05, SOL-L07. R2 (griefable preconditions) maps to SOL-J*, SOL-K06, SOL-O*, and influences elimination rule SOL-R2. R3 (transfer side effects) maps directly to SOL-O03 / O04 / O10 / O13. R4 (uncertainty handling) is procedural and does not add a type. R5 (combinatorial impact, CU) informs SOL-R5 (CU budget feasibility). R6 (semi-trusted roles) motivates the `permissionless_crank` actor. R7 (donation DoS) maps to SOL-O*, SOL-M01 and is a direct input to SOL-E01 FIRST_DEPOSITOR_PATH analysis. R8 (cached parameters) maps to SOL-N01/N02 plus SOL-C03. R9 (stranded asset severity floor) is a severity modifier, not a type. R10 (worst-state calibration) is procedural. R11 (unsolicited transfer) maps to SOL-O*, SOL-M01, SOL-E05. R12 (enabler enumeration) is procedural. R13/R14 are scoring/coherence rules that justify SOL-R3 and the combo bonuses in section 7. R15 (flash-loan-via-composition) motivates the SOL-N06 + guard combo bonus. R16 (oracle integrity) maps to SOL-D01, SOL-D02, SOL-D05. S1 (account validation completeness) maps to SOL-J01, SOL-J02, SOL-J03, SOL-J08. S2 (PDA security) maps to the entire K category. S3 (CPI security) maps to the entire L category. S4 (close + revival) maps to SOL-J07, SOL-M04. S5 (stale data after CPI) maps to SOL-L05. S6 (remaining accounts) maps to SOL-J08. S7 (duplicate mutable accounts) maps to SOL-J04. S8 (sysvar spoofing) maps to SOL-N06. S9 (Token-2022 extensions) maps to the entire O category. S10 (instruction introspection) maps to SOL-N03 + SOL-N06 + SOL-L05 under the instruction-introspection skill. S11 (zero copy struct layout) is a correctness rule covered by SOL-J03 (discriminator) + SOL-M05 (size discrepancy) in combination; may be worth a dedicated SOL-J09 later. R17 (state transition completeness) is best expressed as a combo rule across SOL-C* and SOL-E* pieces rather than a new type.

Source: `pda-security` SKILL. Threat surface (canonical bump, seed collision, seed uniqueness, PDA isolation, PDA sharing, init front-running) is fully covered by SOL-K01 through SOL-K06 plus SOL-J07 (init-front-run is reinitialization-adjacent). Coverage: new J/K.

Source: `cpi-security` SKILL. Threat surface (CPI inventory, target validation, signer propagation, reload, lamport conservation, owner re-check, CPI depth) is covered by SOL-L01, SOL-L02, SOL-L04, SOL-L05, SOL-L07, and CPI depth is handled by SOL-R7. Lamport conservation around CPI lives in SOL-M01. Coverage: new L + M.

Source: `token-2022-extensions` SKILL. Threat surface (extension inventory, allowlist, permanent delegate, transfer hook, transfer fee, CPI Guard, default state, mint close authority) is covered one-to-one by SOL-O01 through SOL-O13. Coverage: new O.

Source: `token-flow-tracing` SKILL. Entry/exit flow, self-transfer, unsolicited transfer matrix, CPI return type, side effects are covered by SOL-G01, SOL-G02, SOL-G03 (inherited G) plus SOL-J04 (aliasing for self-transfer accounting) plus SOL-L04/L05 plus the O category. Coverage: inherited G + new J/L/O.

Source: `account-lifecycle` SKILL. Close inventory, completeness, revival, rent recovery, token account closure, reinitialization are covered by SOL-J07 (reinit/revival) plus SOL-M02 / SOL-M04 (rent, skim on close) plus SOL-M03 (realloc zero fill). Coverage: new J + M.

Source: `account-validation` SKILL. Account type inventory, owner check, discriminator check, cross-account references (has_one), remaining accounts, duplicate mutable accounts, sysvar validation, trust chain are covered by SOL-J01, SOL-J03, SOL-J04, SOL-J08, SOL-N06. Cross-account `has_one` relationships surface in the piece's `depends_on` field rather than a dedicated type. Coverage: new J + N.

Source: `instruction-introspection` SKILL. Introspection inventory, sysvar address validation, checked function usage, sequence validation, state change coverage, program id verification are covered by SOL-N06 (sysvar spoofing on Instructions sysvar) plus SOL-N03 (shared sysvar read) plus SOL-L01 (program id unchecked) plus elimination rule SOL-R-flash-coherence. Coverage: new N + L.

Source: `economic-design-audit` SKILL. Parameter boundary, invariants, rate/supply interaction, fee formula, emission sustainability, CU cost, rent and account creation economics are covered by inherited SOL-E01 through SOL-E08 plus SOL-I01, SOL-I02, SOL-A*, and on the rent side SOL-M02. CU modeling is expressed as elimination rule SOL-R5. Coverage: inherited A/E/I + new M.

Source: `fork-ancestry` SKILL. Parent detection, divergence (account validation, CPI target, PDA seed, Token-2022), new attack surface is procedural during recon and feeds meta_buffer. The threat classes it surfaces are covered by J/K/L/O via the divergent-code pieces the breadth agents then produce. Coverage: inherits into new J/K/L/O.

Source: `external-precondition-audit` SKILL. CPI inventory and validation, signer propagation, reload, return data, state dependency, oracle data quality, lamport conservation are covered by SOL-L01, SOL-L02, SOL-L04, SOL-L05, SOL-D01, SOL-D02, SOL-M01. Oracle data quality checks map to SOL-D02, SOL-D05. Coverage: new L + M + inherited D.

Source: `temporal-parameter-staleness` SKILL. Multi-step operations, cached parameters, staleness direction, update source, retroactive application, Solana clock semantics are covered by SOL-N01, SOL-N02, SOL-H01 (slot discrimination), plus SOL-C03 (read-write gap across steps). Retroactive fee changes cross-reference into SOL-B01/SOL-E03. Coverage: inherited C/H + new N.

Source: `share-allocation-fairness` SKILL. Allocation classification, late entry, cross-address deposit, pre-setter timing, pre-configuration state, queue processing, redemption symmetry, aggregate constraint coherence are covered by SOL-E01 FIRST_DEPOSITOR_PATH, SOL-E02 PROPORTIONAL_SHARE, SOL-J06 UNINITIALIZED_ACCOUNT_READ (zero-default checkpoint exploit), SOL-J07 REINITIALIZATION_ATTACK, plus SOL-I01 / SOL-I02 for aggregate invariants. Freeze-authority risk on redemption maps to SOL-O05. Coverage: inherited E/I + new J/O.

Source: `centralization-risk` SKILL. Privilege inventory, upgrade authority, freeze/close authorities, PDA self-authority are covered by the actor vocabulary (`upgrade_authority`, `freeze_authority`, `mint_authority`, `multisig_signer`) plus SOL-O05 (freeze authority ignored) plus SOL-K05 (PDA authority leak). No new type needed. Coverage: actor vocabulary + new K/O.

Source: `cross-chain-timing` SKILL. Bridge message verification, finality asymmetry, nonce/sequence replay, relay staleness are partly covered by SOL-D01/D02 (oracle/relay price staleness) plus SOL-N01/N02 (slot vs timestamp) plus SOL-L01 (bridge program id validation) plus SOL-C05 (nonce counter). Full bridge coverage may later warrant a Cross-Chain sub-category; out of scope for v1. Coverage: inherited D + new L/N.

Source: `flash-loan-interaction` SKILL. Flash loan via instruction composition is covered by SOL-N03 (shared sysvar read for introspection), SOL-N06 (sysvar spoofing), SOL-L05 (stale reload post-CPI), plus the SOL-R5 CU-budget rule and the N06+guard combo bonus. Coverage: new L + N.

Source: `migration-analysis` SKILL. Program upgrades, account layout changes, deprecated instructions, token migrations are covered by SOL-J07 (reinit on new layout), SOL-M03 / SOL-M05 (realloc size discrepancy), SOL-J03 (discriminator for versioned types), SOL-O01 (mint authority on migrated mints). Coverage: new J + M + O.

Source: `semi-trusted-roles` SKILL. Crank/bot/operator/keeper role analysis is supported by the `permissionless_crank` actor plus SOL-B01 SIGNER_AUTHORITY for authority-gated instructions. No new type needed. Coverage: actor vocabulary + inherited B.

Source: `verification-protocol` SKILL. Used in Phase 5 verification; does not define piece types. Coverage: not applicable.

Source: `zero-state-return` SKILL. Return-to-zero state after operations, residual assets when supply goes to zero, re-entry after exit are covered by SOL-E01 FIRST_DEPOSITOR_PATH (applies symmetrically at re-seeding), SOL-J07 REINITIALIZATION_ATTACK, SOL-I02 BALANCE_ACCOUNTING. Coverage: inherited E/I + new J.

Source: `trident-api-reference` SKILL. Tooling reference for the Trident fuzzer; not a threat-surface source. Coverage: not applicable.
