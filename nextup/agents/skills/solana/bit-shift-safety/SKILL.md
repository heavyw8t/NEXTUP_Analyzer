---
name: "bit-shift-safety"
description: "Trigger Pattern Always (Solana / Anchor Rust programs) - Rust shift semantics produce silent wrap in release builds - Inject Into Breadth agents, depth-edge-case"
---

# BIT_SHIFT_SAFETY Skill

> **Trigger Pattern**: Always (Rust / Anchor Solana programs)
> **Inject Into**: Breadth agents, depth-edge-case

Rust shift semantics on Solana:

- Default operators (`<<`, `>>`): in debug builds, panic if shift count >= bit width. In release builds (including all on-chain Solana programs), silently wrap the shift count modulo the operand bit width. `u64 << 64` in release mode is equivalent to `u64 << 0`, returning the original value unchanged.
- `checked_shl(n)` / `checked_shr(n)`: return `None` if `n >= bit_width`. This is the canonical safe form.
- `wrapping_shl(n)` / `wrapping_shr(n)`: match the release-mode default — wrap the count.
- `overflowing_shl(n)`: returns `(result, overflowed: bool)` so the caller can detect the wrap.
- `unchecked_shl(n)` (nightly): undefined behavior if `n >= bit_width`.

Because Solana programs run in release mode, any shift using `<<` / `>>` with a non-constant or user-controllable count is a silent-wrap risk, not a panic.

On top of this, Solana has unique surface patterns:
- Fixed-point decimal math in lending / perp protocols (spl-math `PreciseNumber`, `Decimal`, `WAD`).
- Bit-packed account layouts where a shift by a computed offset reads a field.
- Compressed-NFT Merkle tree proof math where right-shifting a node index walks the tree.
- ZK-adjacent code that right-shifts to compute lane indices in range proofs.
- CPI to programs that perform wide shifts (the `checked_shlw` pattern famously abused in the Cetus / Sui $223M exploit has direct analogs in Solana fixed-point libraries).

## 1. Shift Operation Inventory

**MANDATORY GREP**: search all `.rs` files for:
- ` << `, ` >> ` (spaces around to avoid matching `<<` in macros where harmless)
- `checked_shl`, `checked_shr`, `wrapping_shl`, `wrapping_shr`, `overflowing_shl`, `overflowing_shr`, `unchecked_shl`, `unchecked_shr`
- Custom fixed-point library calls that wrap shifts: `PreciseNumber::checked_div`, `Decimal::try_mul`, any `shlw` / `shlw_checked` / `shlw_unchecked` helper

For each shift operation found:

| Location (file:line) | Operator | Operand Type | Bit Width | Shift Count Source | Caller-Controllable? | Bounded? |
|-----------------------|----------|--------------|-----------|--------------------|-----------------------|----------|
| {file}:{line} | `<<` / `checked_shl` / `wrapping_shl` / `overflowing_shl` | u8/u16/u32/u64/u128/usize | 8/16/32/64/128 | constant / parameter / computed | YES/NO | YES/NO --- {how} |

## 2. Bit Width Threshold Table

| Type | Bit Width | Default (release) Behavior when shift >= width | checked_* Behavior |
|------|-----------|------------------------------------------------|--------------------|
| u8 | 8 | wraps: shift & 7 | returns None |
| u16 | 16 | wraps: shift & 15 | returns None |
| u32 | 32 | wraps: shift & 31 | returns None |
| u64 | 64 | wraps: shift & 63 | returns None |
| u128 | 128 | wraps: shift & 127 | returns None |
| usize (BPF 64-bit) | 64 | wraps: shift & 63 | returns None |

## 3. Non-checked Shift Audit

Any shift using raw `<<` / `>>` with a computed shift count is a finding candidate. For each:

1. What is the source of the shift count? Is it a function parameter, derived from a user-provided account, or from a cross-program-invocation response?
2. Is there an explicit `require!(n < BIT_WIDTH)` / `assert!(n < bit_width)` / `if n >= bit_width { return err }` guard immediately before the shift?
3. What is the user-visible consequence of a wrap? Silent zero? Wrong fee calculation? Incorrect index into a packed account?
4. Tag with `[BOUNDARY:shift_count={val} → wraps silently in release]`.

## 4. Fixed-Point and Wide-Shift Libraries

Protocols that implement their own fixed-point arithmetic (e.g., `decimal.rs`, `precise_number.rs`, `wide_math.rs`) often have custom `shl` / `shr` helpers. Audit each:

- Does the helper propagate errors from `checked_shl` / `checked_shr`, or does it fall back to raw shifts?
- Does the helper validate that the shift count fits in the destination width BEFORE the shift, not after?
- Is there a shortcut (`if shift == 0 return x`) that skips the bound check?

The Cetus pattern (Sui, May 2025) is directly applicable here: `checked_shlw` accepted an input that should have overflowed but masked the check with the wrong bound condition. Look for the same pattern in any Solana fixed-point code you encounter.

## 5. Compressed-NFT and Merkle Proof Shift Paths

If the program uses `spl_account_compression`, Merkle proof walking right-shifts a node index by `1` per level. Nothing exceeds bit width here but verify:

- That the index type is large enough for the tree depth (typically u32 is fine up to 2^32 leaves).
- That any iteration count is bounded to tree depth, not an untrusted parameter.

## Common False Positives

- `<< 0` or `>> 0` (no-op).
- `<< 1` on a type with at least 2 bits (compile-time safe).
- Shift inside a `require!()` / `Err()` branch that cannot be reached with the relevant operand.
- Shift inside a `checked_*` chain whose result is propagated with `?` — the wrap is already caught.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Multi-limb integer `shl_assign`/`shr_assign` silently produces wrong result when `limb_shift == 0` in release mode; fixed by replacing raw shift with `checked_shl`
  Where it hit: Uint<N> wide-integer arithmetic crate (Rust, generic)
  Severity: HIGH
  Source: Solodit (row_id 1253)
  Summary: The `shl_assign` and `shr_assign` implementations on a multi-limb `Uint<N>` type computed `limb_shift` then used it as a raw shift operand. When `limb_shift` was zero, the shift was effectively `<< 0` on a sub-limb, which was wrong but did not panic in release mode. The fix replaced the raw shift with `checked_shl` to surface the edge case. Directly illustrates the SKILL's core point that release builds silently wrap rather than panic.
  Map to: bit_shift, shl, shr, checked_shl, wrapping_shl, overflowing_shl, shift_count

- Pattern: Range-proof validation skips upper-bound check on `bit_lengths`, allowing right-shift of u128/u256 by > 64, producing overflow panic (debug) or silent wrap (release)
  Where it hit: `BatchedRangeProofU128Data::new` in `zk-token-sdk` (Solana SPL)
  Severity: HIGH
  Source: Solodit (row_id 10205)
  Summary: The function accepted caller-supplied `bit_lengths` without clamping them below 64. When a length exceeded 64 a right-shift on a u64 limb would overflow: panic in debug, silent wrap in release. The report includes a PoC and recommends validating each element of `bit_lengths` before the shift. This is a textbook unbounded-shift-count finding in production Solana code.
  Map to: bit_shift, shr, shift_count, checked_shr, fixed_point

- Pattern: `u256::shlw` called on an unchecked numerator, masking the overflow bound check with the wrong condition; patched by switching to `u256::checked_shlw`
  Where it hit: Fixed-point / wide-math arithmetic library (Rust)
  Severity: MEDIUM
  Source: Solodit (row_id 13579)
  Summary: The numerator value was not validated before being passed to `u256::shlw`, which accepted inputs that should have triggered an overflow but instead silently dropped non-zero high bytes. This is the direct Rust/Solana analog of the Cetus `checked_shlw` exploit the SKILL references. The fix is to replace every `shlw` call with `checked_shlw` and propagate the error.
  Map to: shlw, checked_shl, fixed_point, overflowing_shl, shift_count

- Pattern: `1 << role` used in ACL bit-mask without bounding `role`, allowing a shift count >= bit-width to silently wrap in release mode and fail to clear the intended bit
  Where it hit: ACL `remove_role` function (Rust)
  Severity: MEDIUM
  Source: Solodit (row_id 6784)
  Summary: The `remove_role` function computed `MAX_U128 - (1 << role)` to clear a permission bit. No check ensured `role < 128`, so a caller-supplied `role >= 128` would wrap the shift in release mode, leaving the permission set and bypassing access control. The fix adds an explicit bound check before the shift. Maps directly to the SKILL's user-controllable shift-count audit.
  Map to: bit_shift, shl, shift_count, checked_shl, wrapping_shl

- Pattern: Concurrent Merkle tree accepts leaf index equal to `1 << MAX_DEPTH`, which is out of range and causes `set_leaf` / `prove_leaf` to crash or corrupt tree state
  Where it hit: `spl_account_compression` concurrent Merkle tree program (Solana)
  Severity: MEDIUM
  Source: Solodit (row_id 14540)
  Summary: The `rightmost_proof.index` field can be set to `1 << MAX_DEPTH`, one past the last valid leaf. Functions that accept an index parameter do not check `index < (1 << MAX_DEPTH)`, so the computed tree-walk shifts operate on an out-of-range value, crashing the program. The SKILL's Section 5 covers exactly this tree-depth bound pattern in `spl_account_compression`.
  Map to: bit_shift, shl, shift_count, shr, fixed_point


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Shift Operation Inventory | YES | | All shifts enumerated |
| 2. Bit Width Threshold | YES | | Per-type table |
| 3. Non-checked Shift Audit | IF any raw `<<` / `>>` present | | Silent-wrap risk |
| 4. Fixed-Point Library Audit | IF the program has custom fp/shift helpers | | Cetus-pattern check |
| 5. Compressed-NFT / Merkle Shift | IF spl_account_compression present | | Tree-walk bound |
