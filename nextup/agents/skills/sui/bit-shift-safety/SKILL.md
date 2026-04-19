---
name: "bit-shift-safety"
description: "Trigger Pattern Always (Sui Move) -- Move VM aborts on shift = bit width - Inject Into Breadth agents, depth-edge-case"
---

# BIT_SHIFT_SAFETY Skill

> **Trigger Pattern**: Always (Sui Move) -- Move VM aborts on shift >= bit width
> **Inject Into**: Breadth agents, depth-edge-case

For every bit shift operation in the protocol:

**BACKGROUND**: The Move VM (shared by Sui and Aptos) aborts the entire transaction if a bit shift operand equals or exceeds the bit width of the type. For `u64`, shifting by 64 or more aborts. For `u128`, shifting by 128 or more aborts. This is NOT a revert with an error code -- it is a VM abort that cannot be caught. On Sui, a PTB (Programmable Transaction Block) abort means ALL commands in the PTB fail, and shared objects that were locked for the transaction are released without state changes.

## 1. Shift Operation Inventory

Enumerate ALL bit shift operations (`<<` and `>>`) across all modules:

| Module | Function | Line | Operation | Type | Bit Width | Shift Amount Source | Validated? |
|--------|----------|------|-----------|------|-----------|--------------------|-----------:|
| {mod} | {func} | {L} | `<<` / `>>` | u8/u64/u128/u256 | 8/64/128/256 | {literal/parameter/computed} | YES/NO |

**Grep pattern**: Search all `.move` files for `<<` and `>>` operators.

**Type-to-width mapping**:
| Type | Max Safe Shift |
|------|---------------|
| `u8` | 7 |
| `u64` | 63 |
| `u128` | 127 |
| `u256` | 255 |

## 2. Shift Amount Source Classification

For each shift operation, classify the shift amount source:

### 2a. Literal Shifts (Low Risk)
```move
let x = value << 32;  // Literal: always safe if < bit width
```
**Check**: Is the literal < bit width of the type? If yes -> SAFE. If no -> compilation may succeed but runtime aborts.

### 2b. Parameter-Derived Shifts (Medium Risk)
```move
public fun shift_by(value: u64, amount: u8): u64 {
    value << (amount as u8)  // Parameter: caller controls shift amount
}
```
**Check**: Is the `amount` parameter validated before the shift? Common patterns:
- `assert!(amount < 64, E_SHIFT_OVERFLOW)` -- explicit validation
- `amount % 64` -- wrapping (changes semantics but prevents abort)
- No validation -- FINDING

### 2c. Computed Shifts (High Risk)
```move
let shift = calculate_precision(decimals);  // Computed: depends on runtime state
let result = base << shift;
```
**Check**: Can the computation ever produce a value >= bit width? Trace the computation to its inputs. If any input is user-controlled or state-derived -> HIGH RISK.

## 3. Abort Impact Analysis

For each unvalidated shift operation, assess the abort impact:

| Function | Called By | Shared Objects Locked? | PTB Context | Abort Impact |
|----------|----------|----------------------|-------------|-------------|
| {func} | {callers} | YES/NO | {typical PTB} | {impact} |

**Sui-specific abort consequences**:
- **PTB abort**: All commands in the Programmable Transaction Block fail atomically. If the shift is in command 3 of a 5-command PTB, commands 1-2 are also rolled back.
- **Shared object locking**: If the aborting function locks shared objects (accessed via `&mut` reference), those objects are temporarily unavailable during consensus. Repeated aborts can cause transient unavailability. This is NOT permanent locking -- Sui releases locks after the transaction fails.
- **Gas consumption**: The sender pays gas for the aborted transaction up to the abort point.
- **Griefing vector**: If an attacker can trigger the abort via a public function with a user-controlled shift amount, they can grief other users by causing their PTBs to abort. This is especially impactful when the aborting function is called as part of a common user flow (deposit, swap, claim).

### 3a. Griefing Scenario Modeling

For each unvalidated shift in a public/entry function:

```
Scenario: Shift Abort Griefing
1. Attacker calls {FUNCTION} with shift amount = {BIT_WIDTH}
2. Move VM aborts the transaction
3. Impact on other users: {IMPACT}
   - If function modifies shared state: other PTBs depending on that state must retry
   - If function is part of a multi-step user flow: user loses gas + must restart
4. Attacker cost: gas for one failed transaction
5. Severity: {based on impact}
```

## 4. Common Vulnerable Patterns

### 4a. Decimal Conversion Shifts
```move
// VULNERABLE: decimals comes from token metadata, could be >= 64
let scale = 1u64 << decimals;
```
**Fix pattern**: `assert!(decimals < 64, E_INVALID_DECIMALS)` or use `math::pow(10, decimals)` instead.

### 4b. Bit Packing / Unpacking
```move
// VULNERABLE if position is not bounds-checked
let field = (packed >> position) & mask;
```
**Check**: Is `position` derived from user input or configuration? If yes and no validation -> FINDING.

### 4c. Fixed-Point Arithmetic
```move
// Common in DeFi: fixed-point multiplication with shift
let result = (a * b) >> PRECISION_BITS;
```
**Check**: Is `PRECISION_BITS` a constant? If yes and < bit width -> SAFE. If computed -> trace source.

### 4d. Loop-Based Shifts
```move
let mut i = 0;
while (i < n) {
    value = value << 1;  // Safe per iteration, but after 64 iterations value = 0 (not abort)
    i = i + 1;
};
```
**Note**: Shifting by 1 repeatedly does NOT abort (shift amount is always 1). But the value overflows silently to 0 after bit-width iterations. Check if this silent overflow causes logic errors.

## 5. Validation Pattern Verification

For each shift operation that IS validated, verify the validation is correct:

| Function | Validation | Correct? | Edge Case |
|----------|-----------|----------|-----------|
| {func} | `assert!(n < 64)` | YES | n=63 is max safe |
| {func} | `assert!(n <= 64)` | **NO** | n=64 aborts |
| {func} | `n % 64` | SAFE but semantic change | shift by 0 when n=64 |

**Common validation errors**:
- Off-by-one: `<= bit_width` instead of `< bit_width`
- Wrong bit width: validating against 64 for a `u128` shift (allows 64-127 to abort)
- Missing cast: `amount` is `u64` but shift operand must be `u8` -- does the cast truncate?

## 6. Cross-Function Shift Propagation

Trace shift amounts across function boundaries:

```
entry_function(user_input: u64)
  -> helper_a(derived_value)  // derived_value = user_input * 2
    -> helper_b(shift_amount) // shift_amount = derived_value + offset
      -> actual_shift: value << shift_amount  // Is shift_amount < bit_width?
```

**For each chain**: Can ANY combination of valid inputs to the entry function produce a shift amount >= bit width at the actual shift site? Document the full trace.

## Finding Template

```markdown
**ID**: [BS-N]
**Severity**: [HIGH if public function, MEDIUM if restricted caller, LOW if constant shift]
**Step Execution**: check1,2,3,4,5,6 | X(reasons) | ?(uncertain)
**Rules Applied**: [R4:Y, R10:Y, ...]
**Depth Evidence**: [BOUNDARY:shift=bit_width], [TRACE:user_input->shift_amount->abort]
**Location**: module::function:LineN
**Title**: Unvalidated bit shift in [function] causes VM abort on [condition]
**Description**: [Specific shift operation, source of shift amount, why it can reach bit width]
**Impact**: [Transaction abort, shared object locking, griefing potential, gas waste]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

Selected from `candidates.jsonl` (20 rows). 8 findings chosen for direct shift-mechanism relevance and cross-language applicability to Move's abort-on-shift-overflow semantics.

---

- Pattern: Incorrect bit-shift in assembly namespace packing causes storage slot collisions
  Where it hit: `getNamespace` function / era-contracts (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 31)
  Summary: The `getNamespace` assembly block applied a shift operation incorrectly, causing two distinct namespaces to resolve to the same storage slot. The fix required either correcting the shift direction or changing the packing layout. In Move, the equivalent risk is a computed slot key derived from a shift whose result aliases another key, producing silent data corruption rather than an abort.
  Language context: Solidity assembly. Applies to Move because any `<<`/`>>` used to derive a struct field index or table key from a user-supplied value can produce collisions if the shift amount is not bounds-checked before use.
  Map to: shl, shift_overflow, shift_count

- Pattern: Multi-limb integer shift assigns incorrect result when limb_shift is zero, causing silent wrong output or debug panic
  Where it hit: `shr_assign` / `shl_assign` in `Uint<N>` type (Rust)
  Severity: HIGH
  Source: Solodit (row_id 1253)
  Summary: In the `ruint` multi-limb unsigned integer library, `shr_assign` and `shl_assign` produced undefined results (panic in debug, wrong value in release) when the limb-level shift count was zero. The fix replaced the raw shift with `checked_shl`. Move's u128/u256 similarly aborts when the shift count equals the bit width; the off-by-one boundary (shift == width vs shift == width - 1) is the same class of error.
  Language context: Rust multi-limb integer. Applies directly to Move u128/u256 wide-type shifts where a computed shift amount of exactly the bit width causes a VM abort rather than a detectable error.
  Map to: shl, shr, shift_overflow, wide_shift

- Pattern: Shift amount computed in bytes used where bits are required, producing an 8x under-shift
  Where it hit: `modexpGasCost` / `mloadPotentiallyPaddedValue` in era-contracts (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 1548)
  Summary: Two functions computed a shift count as a byte offset (e.g. `n / 32`) but passed it directly to a bit-shift operator, so the effective shift was 8 times too small. This produced incorrect memory reads and gas calculations. In Move, the same bug class appears when `decimals` or a precision constant is fed to `<<` without converting units, yielding a scale factor that is orders of magnitude off.
  Language context: Solidity inline assembly. Applies to Move fixed-point and decimal-scaling code where the shift amount is derived from a byte-count or decimal-count variable.
  Map to: shl, shr, shift_count, bit_shift

- Pattern: Encoder uses bit-index semantics while decoder uses byte-index semantics for the same shift field, causing encode/decode mismatch
  Where it hit: `_updateNthByte` vs `_decodeNthByte` in `Uint8CodecLib` (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 4102)
  Summary: The encoding path treated `position` as a bit index (shifting by `position` bits), while the decoding path treated it as a byte index (shifting by `position * 8` bits). The mismatch meant stored permission bits were read back at the wrong positions. In Move, bit-packed structs that use `<<` in one direction and `>>` in another must use consistent units; any asymmetry silently corrupts stored state.
  Language context: Solidity permission bitmap. Directly applicable to Move bit-packing patterns where a packed u64/u128 field is written with one shift formula and read with another.
  Map to: shl, shr, bit_shift, shift_count

- Pattern: Merkle subtree midpoint computed with wrong shift expression, causing incorrect proof verification
  Where it hit: `verifyInner` in `NamespaceMerkleTree.sol` (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 9552)
  Summary: The subtree midpoint was calculated as `1 << (height - 1)` instead of the correct `1 << (height - heightOffset - 1)`. The wrong shift produced an incorrect midpoint, allowing invalid Merkle proofs to pass verification. In Move, any Merkle or binary-tree implementation that derives a midpoint via `1u64 << depth` must account for the full offset or the subtree traversal diverges from the committed structure.
  Language context: Solidity Merkle tree. Applies to Move Merkle or sparse-tree implementations where a shift-derived midpoint or child-index is sensitive to off-by-one in the exponent.
  Map to: shl, bit_shift, shift_count

- Pattern: Missing circuit constraint on `shr` divisor allows prover to set shift result to any sub-correct value
  Where it hit: `main_vm` / `MulDivRelation` circuit, zkSync Era (Rust/ZK)
  Severity: HIGH
  Source: Solodit (row_id 10160)
  Summary: The zkSync VM circuit converted `shr n` into division by `2^n` but failed to constrain the remainder to be less than the divisor. A malicious prover could supply any value satisfying the relaxed constraint, producing a fake shift result and breaking all contracts that depend on `shr`. In Move, if a shift result feeds into a security-critical comparison (e.g. a permission mask or a price tier), an incorrect shift silently changes the outcome without aborting.
  Language context: Rust ZK circuit. Applies to Move protocols that use `>>` to derive a security-relevant value: if the shift is unconstrained (no assert on the shift count) the result can be manipulated by a caller who controls the shift amount.
  Map to: shr, shift_overflow, shift_count

- Pattern: Missing validation of bit-length parameter allows right-shift overflow panic in batch range proof generation
  Where it hit: `BatchedRangeProofU128Data::new` in zk-token-sdk (Solana/Rust)
  Severity: HIGH
  Source: Solodit (row_id 10205)
  Summary: The function accepted caller-supplied bit lengths without checking that each value was below 64. When a bit length >= 64 was passed, a `>> bit_length` operation on a u64 overflowed and panicked in debug or produced 0 in release. This is the exact same failure mode as the Move VM abort: a user-controlled shift operand that reaches or exceeds the type bit width terminates execution. The fix was to validate each bit length before use.
  Language context: Solana/Rust. Direct parallel to Move: Move VM aborts (non-catchable) on shift >= bit_width, while Rust panics in debug. Both require an explicit `assert!(bit_length < 64)` guard before the shift.
  Map to: shr, shift_overflow, shift_count, bit_shift

- Pattern: Shift count taken from full register instead of low 5 bits, causing incorrect right-arithmetic-shift result
  Where it hit: `SRAV` instruction handler in MIPS-ISA dispute game (Solidity)
  Severity: MEDIUM
  Source: Solodit (row_id 5745)
  Summary: The MIPS `SRAV` opcode requires the shift count to be the low 5 bits of `rs` (masking with `0x1F`), but the implementation used the full register value. A shift count > 31 produced wrong results and allowed a dispute game to mark a valid claim as false. In Move, when a shift amount is derived from a value wider than the required range, it must be masked or asserted before use; using the raw value risks both abort (if >= bit width) and wrong-answer (if merely out of intended range).
  Language context: Solidity MIPS emulation. Applies to Move code that extracts a shift count from a packed field: failing to mask to the valid range causes either an abort or a semantically incorrect shift, both of which can subvert downstream logic.
  Map to: shr, shift_count, bit_shift

### From web-sourced audit reports

> Research date: 2026-04-19. Six findings across Aptos and Sui Move, ordered by financial impact.

---

## Finding 1: Cetus Protocol — flawed `checked_shlw` overflow guard drains $223M

- Pattern: wrong mask constant in a u256 pre-shift overflow guard causes silent left-shift truncation; the guard used `0xffffffffffffffff << 192` (= 2^256 - 2^192) instead of the correct threshold `1 << 192` (= 2^192), so any value in the range (2^192, 2^256 - 2^192) passed the check even though `value << 64` would overflow u256
- Where it hit: Cetus Protocol (largest CLMM DEX on Sui) — `checked_shlw` in the `integer-mate` library, called from `get_delta_a` in the liquidity-delta math
- Severity: CRITICAL
- Source: https://dedaub.com/blog/the-cetus-amm-200m-hack-how-a-flawed-overflow-check-led-to-catastrophic-loss/ ; https://blocksec.com/blog/blog-4cetus-incident-one-unchecked-shift-drains-223m-in-the-largest-defi-hack-of-2025 ; https://www.cyfrin.io/blog/inside-the-223m-cetus-exploit-root-cause-and-impact-analysis
- Summary: The `checked_shlw` function was intended to abort before `value << 64` when the result would exceed 256 bits. Due to the wrong mask constant and a strict `>` instead of `>=` comparison, inputs in a wide range above 2^192 bypassed the check. Move's left-shift operator truncates silently on overflow (unlike addition/multiplication which abort), so the shift produced a garbage numerator. `get_delta_a` then computed the required deposit as effectively 1 token while recording an enormous liquidity credit. The attacker repeated this across pools via flash swaps, draining ~$223M on May 22, 2025.
- Map to: `checked_shlw`, `shlw`, `shift_overflow`, `wide_shift`, `shl`

---

## Finding 2: OtterSec Cetus Aptos audit — unguarded `u256::shlw` on numerator (pre-cursor to Finding 1)

- Pattern: `u256::shlw` (raw left shift) applied to a numerator value that is not validated for overflow before the shift; the Aptos codebase had custom 256-bit integer support because Aptos Move did not natively support u256 at the time
- Where it hit: Cetus Protocol on Aptos — `get_delta_a` / `compute_swap_step` using a custom `u256` module; identified in OtterSec's 2023 Aptos audit as a suggestion (finding label OS-CTS-SUG-04 area)
- Severity: HIGH (overflow produces incorrect swap output; rated suggestion in the audit because exploitability depended on input ranges, but the Sui port of the same logic became CRITICAL)
- Source: https://github.com/CetusProtocol/Audit/blob/main/Cetus%20Aptos%20Audit%20Report%20by%20OtterSec.pdf ; https://dedaub.com/blog/the-cetus-amm-200m-hack-how-a-flawed-overflow-check-led-to-catastrophic-loss/
- Summary: OtterSec's 2023 audit of Cetus on Aptos noted that the numerator value was not validated before calling `u256::shlw`. The recommendation was to replace `u256::shlw` with `u256::checked_shlw` and add explicit overflow detection. The fix was applied on Aptos, but when the code was ported to Sui, the `checked_shlw` implementation itself contained the wrong threshold (Finding 1), meaning the underlying class of defect — an unvalidated shift on a wide integer — survived through two generations of audits.
- Map to: `shlw`, `shift_overflow`, `wide_shift`, `checked_shlw`

---

## Finding 3: Verichains — Kriya, FlowX, Turbo Finance exposed to same `integer-mate` shift bug

- Pattern: multiple Sui DEX/AMM protocols imported the same `integer-mate` library from CetusProtocol and used `checked_shlw` in their own liquidity math, inheriting the same flawed overflow guard
- Where it hit: Kriya DEX, FlowX Finance, Turbo Finance on Sui — all confirmed exposed by Verichains post-exploit scan of the Sui blockchain
- Severity: CRITICAL (same root cause as Finding 1; all three patched before exploitation)
- Source: https://blog.verichains.io/p/multiple-sui-projects-previously ; https://blog.verichains.io/p/cetus-protocol-hacked-analysis
- Summary: After the Cetus exploit Verichains scanned the entire Sui blockchain for contracts calling `checked_shlw` or sharing `integer-mate` code paths. They found three additional live protocols using the vulnerable version. All three had already patched before Verichains published. The incident illustrates a shared-library supply-chain vector: a bit-shift overflow guard in one upstream Move package can cascade silently to every downstream importer because Move does not abort on shift-result overflow.
- Map to: `checked_shlw`, `shift_overflow`, `wide_shift`, `shl`

---

## Finding 4: Aptos Move VM — stack-size integer overflow in bytecode verifier enables DoS (Numen Cyber, Oct 2022)

- Pattern: integer overflow in `stack_usage_verifier.rs` during stack-depth accounting for bytecode instructions; the verifier used fixed-width arithmetic without overflow protection, so a crafted bytecode sequence overflowed the counter and bypassed the depth limit
- Where it hit: Aptos Move VM itself (not a smart contract) — the `stack_usage_verifier` component that validates bytecode before execution
- Severity: CRITICAL (network-level DoS; crash of all full nodes executing the malicious bytecode)
- Source: https://medium.com/numen-cyber-labs/analysis-of-the-first-critical-0-day-vulnerability-of-aptos-move-vm-8c1fd6c2b98e ; https://www.globenewswire.com/news-release/2022/10/12/2533292/0/en/Critical-Vulnerability-in-Aptos-MoveVM-Disclovered-by-Singapore-Web3-Security-Company.html
- Summary: Numen Cyber Labs discovered and disclosed (October 2022) a critical vulnerability in the Aptos MoveVM bytecode verifier. By crafting bytecode that caused the stack-size counter to overflow, an attacker could bypass the depth limit and cause every node executing the transaction to crash, halting the network. Aptos Labs confirmed and patched the vulnerability. Although this is a VM-level integer overflow rather than a smart-contract shift bug, it demonstrates that the Move ecosystem's integer semantics — including overflow in verification arithmetic — represent a concrete, exploitable attack surface.
- Map to: `shift_overflow`, `shift_count` (verifier arithmetic overflow analogue)

---

## Finding 5: Aptos official security guidelines document — `<<` does not abort on result overflow (platform-wide pattern)

- Pattern: Move's left-shift operator truncates the high bits of the result silently when the shifted value exceeds the type width; this is documented as a known difference from all other arithmetic operators (which abort on overflow) and from Solidity 0.8.x (which reverts on shift overflow)
- Where it hit: Aptos Move platform-wide — documented in the official Aptos Move Security Guidelines as a class of vulnerability affecting any protocol that uses `<<` with a variable operand and relies on the absence of silent truncation
- Severity: HIGH (generic; individual instance severity depends on context — price math, liquidity math, or fee calculations using `<<` with user-influenced operands are direct HIGH/CRITICAL candidates)
- Source: https://aptos.dev/build/smart-contracts/move-security-guidelines ; https://aptos.dev/build/smart-contracts/book/integers
- Summary: The Aptos documentation explicitly warns: "Left Shift (`<<`), uniquely, does not abort in the event of an overflow. This means if the shifted bits exceed the storage capacity of the integer type, the program will not terminate, resulting in incorrect values or unpredictable behavior." All other arithmetic operators (`+`, `*`, `-`, `/`) abort. This asymmetry is the root class behind Findings 1-3. The documentation also notes that the *shift count* (RHS operand) must be `< bit_width`; exceeding it causes an abort — so the two failure modes are (a) shift-count abort (DoS) and (b) shift-result silent truncation (incorrect math).
- Map to: `shl`, `shift_overflow`, `bit_shift`

---

## Finding 6: SlowMist Sui Move Auditing Primer — bit-shift checklist item citing `checked_shlw` pattern as recurring audit finding

- Pattern: auditors must explicitly verify that every `<<` operation on a wide integer (u128, u256) either (a) proves the operand is bounded such that the result fits the type, or (b) wraps the shift in a correct overflow guard; the primer singles out the wrong-mask pattern from `checked_shlw` as a canonical example of a failure mode that passes code review
- Where it hit: published as a mandatory checklist item in SlowMist's Sui MOVE Smart Contract Auditing Primer (GitHub), citing the Cetus `checked_shlw` as a real-world demonstration
- Severity: HIGH (pattern-level; each instance requires per-context severity assessment)
- Source: https://github.com/slowmist/Sui-MOVE-Smart-Contract-Auditing-Primer ; https://slowmist.medium.com/slowmist-introduction-to-auditing-sui-move-contracts-da005149f6bc
- Summary: SlowMist's public auditing primer for Sui Move contracts includes a dedicated checklist item: "Verify whether bit shift operations may exceed the maximum value of the target type and be truncated." The primer provides an illustrative wrong-mask code snippet — structurally identical to the Cetus bug — as the canonical error pattern. This codifies the `checked_shlw`-class defect as a recurring, auditable finding class in Sui Move rather than a one-off mistake, and it serves as primary reference material for auditors examining any Sui protocol that performs fixed-point or liquidity math using left shifts on u256 values.
- Map to: `checked_shlw`, `shlw`, `shl`, `shift_overflow`, `wide_shift`


## Step Execution Checklist (MANDATORY)

> **CRITICAL**: You MUST report completion status for ALL sections. Findings with incomplete sections will be flagged for depth review.

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Shift Operation Inventory | YES | Y/X/? | Grep all `.move` files |
| 2. Shift Amount Source Classification | YES | Y/X/? | For each shift |
| 3. Abort Impact Analysis | IF unvalidated shifts found | Y/X(N/A)/? | |
| 3a. Griefing Scenario Modeling | IF unvalidated in public fn | Y/X(N/A)/? | |
| 4. Common Vulnerable Patterns | YES | Y/X/? | Check all 4 sub-patterns |
| 5. Validation Pattern Verification | IF validated shifts exist | Y/X(N/A)/? | Off-by-one check |
| 6. Cross-Function Shift Propagation | IF shift amount crosses functions | Y/X(N/A)/? | |

### Cross-Reference Markers

**After Section 1** (Shift Inventory):
- IF zero shift operations found -> mark skill as N/A, skip remaining sections
- IF shifts found in math/fixed-point libraries -> prioritize Section 4c

**After Section 3** (Abort Impact):
- IF abort affects shared objects -> cross-reference with ABILITY_ANALYSIS Section 2b (shared object analysis)
- IF abort is in a hot potato consumption path -> cross-reference with ABILITY_ANALYSIS Section 5 (hot potato enforcement) -- abort before consumption = permanent PTB failure

**After Section 6** (Cross-Function Propagation):
- IF any chain reaches bit width with valid inputs -> FINDING (minimum Medium)
- Tag: `[BOUNDARY:shift={bit_width}]`, `[TRACE:input_path->abort_site]`
