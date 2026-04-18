# Solana pattern hints

Language-specific markers for Solana/Anchor program audits. Used by the extraction agent alongside `nextup/taxonomy/solana.json`.

## Framework fingerprints

- Anchor: `#[program]`, `#[derive(Accounts)]`, `#[account]`, `#[instruction(...)]`, `ctx: Context<X>`, `ctx.accounts.*`, `anchor_lang::prelude::*`, `Anchor.toml`.
- Native Solana: `solana_program::{program::{invoke, invoke_signed}, account_info::AccountInfo, entrypoint, program_error::ProgramError, pubkey::Pubkey, sysvar::{clock, rent, instructions}}`.
- SPL Token v1: `anchor_spl::token::{Token, TokenAccount, Mint, Transfer, MintTo, Burn}`, `spl_token::instruction::*`.
- SPL Token-2022: `anchor_spl::token_2022::*`, `spl_token_2022::extension::*` (transfer_hook, transfer_fee, permanent_delegate, confidential_transfer, non_transferable, default_account_state, immutable_owner, interest_bearing_mint, cpi_guard, metadata_pointer, metadata).
- Oracles: `pyth_sdk_solana::load_price_feed_from_account_info`, `pyth_sdk_solana::state::SolanaPriceAccount`, `switchboard_solana::AggregatorAccountData`, Chainlink `chainlink_solana`.

## Account-model markers (SOL-J)

- Missing owner check: absence of `require!(account.owner == expected_program_id, ...)` or `#[account(owner = expected)]` constraint on a raw `AccountInfo`.
- Missing signer check: reading `AccountInfo` without `Signer<'info>` typing or `require!(account.is_signer, ...)`.
- Missing discriminator: deserializing account data with `try_from_slice` directly rather than via Anchor's `Account<'info, T>` (which enforces discriminator) or a manual `account.data[0..8]` compare.
- Account aliasing: two `Pubkey` parameters compared with `==` to detect reuse; or absence of such a check when one is expected. Look for `ctx.accounts.foo.key() == ctx.accounts.bar.key()`.
- Type confusion: treating a `Mint` account as `TokenAccount` (or vice versa) without constraints.
- Uninitialized-read: reading `account.data` before `account.data_is_empty()` check or before an `init` instruction has populated it.
- Close-then-reinit attack: `close = destination` constraint followed by the same account being used in a later instruction without the discriminator check preventing reinitialization.

## PDA & seeds markers (SOL-K)

- Unchecked derivation: `Pubkey::find_program_address(&[...], program_id)` result compared loosely, or no compare at all.
- Seed collision: seeds that include attacker-controlled fields without length-prefixing or domain separation.
- Bump not stored: calling `find_program_address` every time without storing the bump in an account, OR using `create_program_address` with a bump that isn't the canonical one.
- Canonical bump missing: `invoke_signed` with seeds that don't include the stored canonical bump byte.
- Authority leak: `#[account(seeds = [...], bump)]` where the seeds are derivable by any user, allowing impersonation.

## CPI markers (SOL-L)

- Target not checked: `invoke`/`invoke_signed` where the program id of the called program is not verified against an expected constant.
- Missing signer seeds: `invoke` used where `invoke_signed` is required (calling program needs to act as a PDA).
- Reentry: CPI into a program that may call back into this one without a reentry guard (state flag).
- Return unchecked: `invoke(...)` ignoring the `Result` (rare; rust idiom catches most) OR `Ok(())` returned without inspecting data written by the callee.
- Reload missing: reading `account.data` after a CPI without calling `account.reload()` (Anchor) or re-borrowing; stale data is silent.

## Lamports & rent markers (SOL-M)

- Direct lamport arithmetic: `**account.lamports.borrow_mut() -= amount` (bypasses System Program transfer semantics and rent checks).
- Rent-exempt check missing: `**account.lamports.borrow_mut() -= amount` or `transfer` that leaves the account below `rent.minimum_balance(data_len)`.
- Realloc without zero-fill: `account.realloc(new_len, true)` — wait, the second arg IS the zero-init flag; flag `realloc(new_len, false)` as risk because growing without zero-fill leaks old data.
- Rent skim on close: lamports drained via direct arithmetic before the Anchor `close` constraint transfers the remainder; the `close` destination sees less than expected.

## Sysvar & clock markers (SOL-N)

- Clock drift: `Clock::get()?.unix_timestamp` used as the authoritative time source for short windows; validators have ±150s skew tolerance.
- Slot vs unix confusion: comparing `Clock::slot` to a unix timestamp threshold, or vice versa.
- recent_blockhashes misuse: using `recent_blockhashes` sysvar (deprecated) as entropy source.

## SPL Token / Token-2022 markers (SOL-O)

- Mint authority not verified: accepting a `Mint` account without checking `mint.mint_authority`.
- ATA not checked: accepting any token account without deriving the canonical ATA via `get_associated_token_address` and comparing.
- Transfer-hook ignored: on Token-2022 transfers, not invoking the transfer-hook program via `TransferHookInstruction`.
- Transfer-fee ignored: assuming `amount` on Token-2022 transfers is received net; transfer-fee extension can deduct at the token-program level.
- Freeze authority: not checking whether a mint has an active freeze authority before treating a token account as spendable.
- Decimals assumption: hard-coded `10u64.pow(9)` or similar instead of reading `mint.decimals`.
- Interest-bearing, non-transferable, default-account-state, immutable-owner, cpi-guard: each extension changes invariants; flag their absence in a program that accepts arbitrary Token-2022 mints.

## Generic Rust/Solana idioms to capture

- `checked_add` / `checked_sub` / `checked_mul` gaps — piece type `SOL-A06`.
- `as u64` / `as u128` narrowing — piece type `SOL-A04`.
- `try_from_slice(&data)` on attacker-provided bytes without length check — boundary input.
- Missing `msg!` on error paths for debuggability (not a vulnerability, do not tag).

## Scope filtering

In-scope: `programs/*/src/**/*.rs` (Anchor programs), `src/entrypoint.rs`, `src/processor.rs`, `src/instruction.rs`, `src/state.rs` (native). Out-of-scope: `tests/`, `migrations/`, `client/`, `scripts/`, `target/`, `node_modules/`.
