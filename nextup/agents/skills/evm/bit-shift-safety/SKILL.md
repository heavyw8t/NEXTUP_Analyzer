---
name: "bit-shift-safety"
description: "Trigger Pattern Always (Solidity / Vyper / Yul assembly) - EVM shift semantics vary by context - Inject Into Breadth agents, depth-edge-case"
---

# BIT_SHIFT_SAFETY Skill

> **Trigger Pattern**: Always (Solidity, Vyper, Yul/inline assembly)
> **Inject Into**: Breadth agents, depth-edge-case

EVM shift semantics are inconsistent across contexts:

- Solidity >= 0.8.0 with checked arithmetic: `x << n` where `n >= bit_width(x)` reverts at runtime (Panic 0x11).
- Solidity < 0.8.0 or code wrapped in `unchecked { }`: `x << n` silently truncates to zero / wraps modulo the bit width.
- Yul and inline assembly (`shl(shift, x)`, `shr(shift, x)`, `sar(shift, x)`): never revert; any shift count is valid, including `>= 256`, which produces 0. The assembly `exp()` also silently wraps.
- Vyper: aborts on overflow in most arithmetic paths.

Any user-controllable or computed shift amount that can reach the operand bit width, OR any assembly shift that depends on external input, is a bug surface.

## 1. Shift Operation Inventory

**MANDATORY GREP**: search all `.sol` / `.vy` / `.yul` files for `<<`, `>>`, `shl(`, `shr(`, `sar(`.

For each shift operation:

| Location (file:line) | Context | Operand Type | Bit Width | Shift Amount Source | User-Controllable? | Bounded? |
|-----------------------|---------|-------------|-----------|---------------------|--------------------|----------|
| {file}:{line} | Solidity >=0.8 / unchecked / assembly | uint8/uint256/int256/... | 8/256/... | constant / parameter / computed | YES/NO | YES/NO --- {how} |

**Shift amount classification**:
- Constant: literal `1 << 64`. Safe if < bit width in checked context. In assembly, produces 0 if >= 256.
- Parameter: passed in by caller, can be user-controlled.
- Computed: `uint256(1) << (decimals - offset)`, `mask << pos`. Requires boundary analysis.

## 2. Bit Width Threshold Table

| Type | Bit Width | Checked (>=0.8) Max Safe Shift | Assembly / Unchecked Behavior |
|------|-----------|-------------------------------|-------------------------------|
| uint8 / int8 | 8 | 7 | silently → 0 or wraps |
| uint16 / int16 | 16 | 15 | silently → 0 or wraps |
| uint32 / int32 | 32 | 31 | silently → 0 or wraps |
| uint64 / int64 | 64 | 63 | silently → 0 or wraps |
| uint128 / int128 | 128 | 127 | silently → 0 or wraps |
| uint256 / int256 | 256 | 255 | assembly: always 0 when shift >= 256 |

## 3. Assembly Shift Audit (highest-risk surface)

Yul `shl`/`shr`/`sar` do not revert. Any audit finding involving assembly shifts deserves extra attention.

Common patterns:
- Packed storage: reading a struct byte at offset `shr(mul(idx, 8), slot)`. If `idx` is user-controlled and can exceed 31, the shift returns 0 for all fields.
- Bit masks: `and(shr(pos, x), mask)`. If `pos >= 256`, shift yields 0 and the mask returns 0 regardless of `x`.
- Packed calldata encoding / `calldataload(offset)` with computed offset and subsequent shift.

For each assembly shift, answer:
1. Can `shift` reach or exceed the operand width? (For `uint256`, exceed 256.)
2. Is the caller required to pass a bounded value, or does the function trust arbitrary inputs?
3. Does a later `require(x != 0)` or similar implicitly paper over a silent-zero outcome?

Tag: `[BOUNDARY:shift_count={val} → produces 0 silently]` for assembly-shift findings.

## 4. Solidity `unchecked` Blocks

Shifts inside `unchecked { }` revert to pre-0.8 semantics — wraparound is the default.

| Location | Block Type | Why Unchecked? | Risk Assessment |
|----------|-----------|---------------|-----------------|
| {file}:{line} | unchecked {} | gas optimisation / intentional wrap | confirm shift cannot exceed bit width |

Guarantee-style rule: a shift inside `unchecked` with a non-constant shift amount is presumed unsafe until proven otherwise.

## 5. Computed Shift Analysis

When the shift amount is the result of arithmetic, trace its range:

1. Declared type of each variable in the expression.
2. Any `require` / `if` guard that bounds it before the shift.
3. Subtraction anywhere (common footgun: `decimals - offset` that can underflow pre-0.8 or produce large positive in `unchecked`).

Use boundary substitution: Min = 0, Max = bit width - 1, Bit width, Bit width + 1, Bit width × 2. Each boundary feeds the shift; record output.

## Common False Positives

- Shift with explicit bound check via `require(n < 256)` immediately before the shift.
- Shift where the operand is `0` (output is `0` regardless).
- Shift amount is a literal less than bit width.
- Solidity >= 0.8 with NO `unchecked` wrapper AND no assembly AND the shift amount is a bounded function parameter.

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Selected from candidates.jsonl (13 rows). Only rows with genuine shift-semantics bugs are included.

---

- Pattern: Assembly shift used for namespace memory packing produces collisions due to incorrect bit-shift in getNamespace
  Where it hit: Unknown protocol / getNamespace function / assembly block
  Severity: HIGH
  Source: Solodit (row_id 31)
  Summary: The getNamespace function contained incorrect assembly code that failed to apply the required bit-shift when packing memory. Without the shift, two distinct namespaces could map to the same memory region. The fix added a shl/shr in the assembly block to prevent overlap.
  Map to: assembly_shift, shl, shr, packed_encoding

- Pattern: Shift amount expressed in bytes instead of bits, producing shifts 8x too small
  Where it hit: era-contracts / modexpGasCost and mloadPotentiallyPaddedValue
  Severity: HIGH
  Source: Solodit (row_id 1548)
  Summary: Both functions computed shift counts as byte offsets then passed them directly to shift operators that expect bit counts. Because 1 byte = 8 bits, every shift was 8x too small, causing incomplete reads and distorted parameter values. The bug was resolved in a subsequent pull request.
  Map to: shift_count, shr, shl, assembly_shift

- Pattern: Packed-byte codec uses bit index in encode path but byte index in decode path, corrupting permissions
  Where it hit: Concrete protocol / Uint8CodecLib._updateNthByte and _decodeNthByte
  Severity: HIGH
  Source: Solodit (row_id 4102)
  Summary: _updateNthByte computed its shift amount as a bit index (position * 8) while _decodeNthByte treated the same parameter as a byte index, making the two functions operate on different bit positions. The mismatch caused incorrect permission bits to be written and later read back. The fix standardised both functions to the same unit.
  Map to: bit_shift, shift_count, packed_encoding, shl, shr

- Pattern: Computed shift in Merkle subtree traversal uses wrong subtree height, corrupting midpoint comparison
  Where it hit: NamespaceMerkleTree.sol / verifyInner
  Severity: HIGH
  Source: Solodit (row_id 9552)
  Summary: The inner-node verification used 1 << (height - 1) to compute the subtree midpoint instead of 1 << (height - heightOffset - 1), making the midpoint too large whenever heightOffset > 0. The same off-by-one applied to the sideNodes length check. The patch adjusts both shift expressions to subtract heightOffset.
  Map to: bit_shift, shl, shift_count, assembly_shift

- Pattern: Prize count formula applies shift with wrong operator precedence, distributing more prizes than designed
  Where it hit: PoolTogether v4 / DrawCalculator.sol L423-431
  Severity: HIGH
  Source: Solodit (row_id 17357)
  Summary: The number-of-prizes expression evaluated (2^bitRange)^degree - (2^bitRange)^(degree-1) - ... instead of 2^(bitRange*degree) - 2^(bitRange*(degree-1)). The correct on-chain form is (1 << _bitRangeSize * _prizeTierIndex) - (1 << _bitRangeSize * (_prizeTierIndex - 1)), but Solidity operator precedence requires explicit parentheses to avoid treating the multiplication as the shift count. The bug caused the protocol to pay out more prizes than intended.
  Map to: bit_shift, shl, shift_count

- Pattern: MIPS SRAV instruction uses full rs register as shift count instead of masking to low 5 bits
  Where it hit: Optimism / MIPS-ISA dispute game implementation
  Severity: MEDIUM
  Source: Solodit (row_id 5745)
  Summary: The EVM implementation of the MIPS SRAV opcode passed the entire rs value as the arithmetic-right-shift count rather than applying & 0x1F first, as the MIPS spec requires and as sibling shift instructions in the same file already did. A shift count above 31 produces 0 on a 32-bit operand, so the dispute game could mark a valid root claim as false. The fix adds & 0x1F before the shift.
  Map to: sar, shr, shift_count, assembly_shift

- Pattern: shl discarded before sload in LibBytes16.storeBytes16, writing upper 128 bits into lower 128-bit slot
  Where it hit: Bean protocol / LibBytes16.storeBytes16
  Severity: MEDIUM
  Source: Solodit (row_id 11097)
  Summary: The storeBytes16 function loaded a storage slot and intended to isolate the lower 128 bits using shl(128, slot), but the result of shl was discarded before the sload. Consequently the upper 128 bits of the slot overwrote the lower 128 bits in the destination, producing corrupted reserve values and incorrect oracle output. The fix replaces the affected line with shr(128, shl(128, SLOT)) to properly clear the upper half.
  Map to: shl, shr, assembly_shift, packed_encoding

- Pattern: Left shift before division in liquidity calculation causes intermediate overflow
  Where it hit: Ammplify / PoolLib.getEquivalentLiq
  Severity: MEDIUM
  Source: Solodit (row_id 471)
  Summary: getEquivalentLiq applied a left shift to the numerator before dividing, allowing the shifted intermediate value to exceed uint256 and overflow to a truncated result. The truncation produced an incorrect denominator, leading to unfair liquidity distribution between users. The recommended fix replaces the shift-then-divide pattern with full 512-bit math.
  Map to: bit_shift, shl, unchecked_shift


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Shift Operation Inventory | YES | | All shifts enumerated |
| 2. Bit Width Threshold | YES | | Per-type table |
| 3. Assembly Shift Audit | IF any assembly shift present | | Yul `shl`/`shr`/`sar` review |
| 4. unchecked Block Review | IF any unchecked{} shift | | Wraparound risk |
| 5. Computed Shift Analysis | IF any non-constant shift | | Range proof |
