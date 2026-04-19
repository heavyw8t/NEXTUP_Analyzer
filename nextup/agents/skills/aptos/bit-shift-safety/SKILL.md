---
name: "bit-shift-safety"
description: "Trigger Pattern Always (Aptos Move) - Move VM aborts on shift = bit width - Inject Into Breadth agents, depth-edge-case"
---

# BIT_SHIFT_SAFETY Skill

> **Trigger Pattern**: Always (Aptos Move) --- Move VM aborts on shift >= bit width
> **Inject Into**: Breadth agents, depth-edge-case

The Move VM performs a runtime check on every bit shift operation: if the shift amount is greater than or equal to the bit width of the operand type, the transaction aborts. This is not a silent wraparound --- it is a hard abort that reverts the entire transaction. Any user-controllable or computed shift amount that can reach the bit width threshold is a denial-of-service vector.

## 1. Shift Operation Inventory

**MANDATORY GREP**: Search all `.move` files for `<<` and `>>` operators.

For each shift operation found:

| Location (file:line) | Operand Type | Bit Width | Shift Amount Source | User-Controllable? | Bounded? |
|-----------------------|-------------|-----------|--------------------|--------------------|----------|
| {file}:{line} | u8/u16/u32/u64/u128/u256 | 8/16/32/64/128/256 | constant / parameter / computed | YES/NO | YES/NO --- {how} |

**Classification of shift amount sources**:
- **Constant**: Hardcoded literal (e.g., `1 << 64`). Safe if < bit width, abort if >= bit width. Check constants that equal or exceed the bit width --- this is a compile-time-detectable bug but Move does not always catch it.
- **Parameter**: Passed into the function from a caller. Trace the call chain to determine if externally controllable.
- **Computed**: Result of arithmetic (e.g., `1 << (decimals - offset)`). Requires boundary analysis.

## 2. Shift Amount Bound Verification

For each shift operation where the shift amount is NOT a safe constant:

### 2a. Bit Width Threshold Table

| Type | Bit Width | Max Safe Shift | Abort Condition |
|------|-----------|---------------|-----------------|
| u8 | 8 | 7 | shift >= 8 |
| u16 | 16 | 15 | shift >= 16 |
| u32 | 32 | 31 | shift >= 32 |
| u64 | 64 | 63 | shift >= 64 |
| u128 | 128 | 127 | shift >= 128 |
| u256 | 256 | 255 | shift >= 256 |

### 2b. Bound Verification Per Shift

For each non-constant shift:

| Location | Shift Amount Expression | Minimum Value | Maximum Value | Exceeds Bit Width? | Guard Present? |
|----------|------------------------|---------------|---------------|-------------------|----------------|
| {location} | {expression} | {min} | {max} | YES/NO | YES --- {assert/min/if} / NO |

**Verification method**: Trace the shift amount back to its origin. For each variable in the expression:
1. What is its declared type? (constrains range)
2. Is there an `assert!()` that bounds it before the shift?
3. Is there a `min()` or `if` guard?
4. Can the variable be set by an external caller (entry function parameter, stored value set by a public function)?

Tag: `[BOUNDARY:shift_amount={val} → abort at bit_width={W}]`

## 3. Computed Shift Analysis

For shift amounts derived from arithmetic, perform boundary value analysis:

### 3a. Subtraction Underflow in Shift Amount

Pattern: `1 << (a - b)` where both `a` and `b` are unsigned integers.

| Location | Expression | Can `b > a`? | Underflow Result | Impact |
|----------|-----------|-------------|-----------------|--------|
| {location} | `1 << (decimals - 6)` | YES if decimals < 6 | Wraps to large u8/u64 → abort | DoS |

**Check**: Move unsigned subtraction aborts on underflow (no wraparound). So `a - b` where `b > a` aborts BEFORE the shift. This is a separate DoS vector (arithmetic underflow). Document both:
1. Underflow abort if `b > a`
2. Shift abort if `a - b >= bit_width`

### 3b. Addition/Multiplication Overflow in Shift Amount

Pattern: `value << (a + b)` or `value << (a * b)`

| Location | Expression | Can Sum/Product >= Bit Width? | Impact |
|----------|-----------|------------------------------|--------|
| {location} | {expression} | YES/NO --- {boundary values} | {DoS / safe} |

### 3c. Shift Result Overflow

Even if the shift amount is safe, the RESULT of the shift may overflow the type:

| Location | Expression | Operand Max Value | Shift Amount | Result Exceeds Type Max? | Impact |
|----------|-----------|-------------------|-------------|-------------------------|--------|
| {location} | `amount << decimals` | {max} | {amount} | YES/NO | {silent truncation / abort} |

**Note**: Move does NOT abort on shift result overflow --- the result is silently truncated (high bits discarded). This is a correctness bug, not a DoS bug, but can cause incorrect calculations (e.g., `1u64 << 63` = 9223372036854775808, but `3u64 << 63` = 9223372036854775808 due to truncation).

Tag: `[BOUNDARY:shift_result=truncated at type_max]`

## 4. DoS Impact Assessment

For each shift operation that can abort:

### 4a. Abort Impact Trace

| Location | Function | Entry Point? | Who Calls This? | Abort Blocks What? | Severity |
|----------|----------|-------------|----------------|--------------------|---------|
| {location} | {function} | YES/NO | {callers} | {blocked operations} | {H/M/L} |

**Trace from the aborting shift outward**:
1. Which function contains the shift?
2. Is that function called by entry functions (user-facing)?
3. Is it called in a critical path (deposit, withdraw, claim, liquidation)?
4. Can an attacker provide input that triggers the abort?
5. Does the abort affect ONLY the attacker's transaction, or does it block other users?

**Severity guide**:
- Shift in view function only -> Low (informational, no state impact)
- Shift in user's own transaction path (self-DoS only) -> Low
- Shift in shared operation (affects all users) -> Medium to High
- Shift in critical path (deposits/withdrawals blocked for all) triggered by attacker input -> High
- Shift in liquidation/price computation path -> High to Critical (can block liquidations, enable insolvency)

### 4b. Attacker-Triggerable Analysis

For shifts that can abort and are in shared/critical paths:

```
1. Attacker calls entry function F with parameter P
2. P flows through {trace} to shift operation at {location}
3. Shift amount becomes {expression} which equals {value} >= {bit_width}
4. Transaction aborts
5. Impact: {what is blocked for other users}
6. Cost to attacker: {gas cost only / requires tokens / requires role}
7. Persistence: {one-time / repeatable / permanent state corruption}
```

Tag: `[TRACE:attacker input P={val} → shift abort → {blocked_operation} DoS]`

## 5. Safe Shift Patterns

Document which shifts in the codebase follow safe patterns (for completeness and to confirm analysis coverage):

| Pattern | Example | Why Safe |
|---------|---------|----------|
| Constant shift < bit width | `1u64 << 32` | 32 < 64, always safe |
| Bounded by min() | `1 << min(amount, 63)` | Capped below bit width |
| Guarded by assert | `assert!(shift < 64, E_INVALID); val << shift` | Explicit pre-check |
| Type-constrained | `(x as u8) << 4` where x comes from a u8 field | u8 max = 255, but shift amount 4 is constant |
| Bounded by protocol invariant | `decimals` is always 6 or 8 (set once, immutable) | Document the invariant and verify immutability |

**RULE**: A shift is only "safe by protocol invariant" if the invariant is ENFORCED on-chain (assert, type constraint, immutable field set in constructor). Documentation-only invariants do NOT qualify.

## Finding Template

When this skill identifies an issue:

```markdown
**ID**: [BS-N]
**Severity**: [based on DoS scope and attacker controllability]
**Step Execution**: check1,2,3,4,5 | X(reasons) | ?(uncertain)
**Rules Applied**: [R2:Y, R4:Y, R10:Y]
**Depth Evidence**: [BOUNDARY:shift_amount={val}], [TRACE:input→abort→impact]
**Location**: module::function (source_file.move:LineN)
**Title**: Unbounded bit shift in [function] enables [DoS/incorrect calculation]
**Description**: [Trace from input to shift operation to abort/truncation to impact]
**Impact**: [What is blocked or miscalculated, who is affected, persistence]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: Shift-by-count overflow in multi-limb integer shift-assign functions causes runtime panic (debug) or silent wrong result (release)
  Where it hit: `Uint<N>` type / `shr_assign` and `shl_assign` functions
  Severity: HIGH
  Source: Solodit (row_id 1253)
  Summary: When `limb_shift` is zero in the `shr_assign`/`shl_assign` functions of a multi-limb unsigned integer type, the internal shift overflows. In debug mode the runtime panics; in release mode the result is silently wrong. The fix replaced the raw shift with `checked_shl` to guard the boundary condition.
  Language context: Rust. In Move the analog is any computed shift amount that reaches the operand's bit width: the VM aborts rather than panicking, but the root trigger is identical — a shift count that hits or exceeds the bit width. The `limb_shift == 0` path maps to the Move case where `shift_amount == bit_width`.
  Map to: shl, shr, shift_count, shift_overflow

- Pattern: Shift count exceeds operand width in range-proof batch function, causing overflow panic
  Where it hit: `BatchedRangeProofU128Data::new` / zk-token-sdk (Solana)
  Severity: HIGH
  Source: Solodit (row_id 10205)
  Summary: The function accepts caller-supplied bit lengths without validating that each value is <= 64. When a bit length exceeds 64 the right-shift operation overflows and the program panics. A patch adds a range check on bit lengths before the shift is executed.
  Language context: Solana/Rust. The pattern maps directly to Move: a user-supplied parameter flows into a shift operation without a bound check, and the shift amount reaches or exceeds the operand's bit width. In Move the outcome is an abort (DoS) rather than a panic, but the attack path is the same.
  Map to: shr, shift_count, shift_overflow, wide_shift

- Pattern: Shift amount computed in bytes instead of bits, producing a shift that is 8x too small
  Where it hit: `modexpGasCost` and `mloadPotentiallyPaddedValue` / era-contracts (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 1548)
  Summary: Both functions compute a shift count in byte units and pass it directly to a bit-shift operator. Because 1 byte = 8 bits the actual shift is only 1/8 of the intended shift, causing incorrect gas cost calculation and wrong memory reads. The fix converts the byte count to a bit count before shifting.
  Language context: Solidity. In Move the same mistake appears when a developer derives a shift count from a decimal or byte-based value (e.g., token decimals) and passes it to `<<` or `>>` without multiplying by 8. The result is a silent wrong value rather than an abort, which is harder to detect.
  Map to: shl, shr, shift_count, bit_shift

- Pattern: Bit-index / byte-index mismatch in paired encode/decode functions produces silent wrong permission bits
  Where it hit: `Uint8CodecLib._updateNthByte` and `_decodeNthByte` (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 4102)
  Summary: `_updateNthByte` treats the position argument as a bit index and shifts accordingly, while `_decodeNthByte` treats the same argument as a byte index. The two functions therefore operate on different bit positions, so permissions stored by one function are read back incorrectly by the other. The fix standardises both functions to the same unit.
  Language context: Solidity. In Move, bitmask-based permission or flag storage is common. If a `<<` shift in a setter uses a different unit than the corresponding `>>` shift in a getter, the stored flags are always wrong. The issue is a shift-count unit error, not an access-control bypass.
  Map to: shl, shr, shift_count, bit_shift

- Pattern: Shift count not masked to the low-order bits mandated by the instruction spec, using the full register value instead
  Where it hit: `SRAV` instruction handler / MIPS-ISA dispute game (Solidity/Optimism)
  Severity: MEDIUM
  Source: Solodit (row_id 5745)
  Summary: The `SRAV` instruction specifies that only the low-order 5 bits of the shift-count register are used. The implementation omits the `& 0x1F` mask and uses the full register value, so any shift count >= 32 produces an incorrect result. This caused the dispute game to mark a valid root claim as false.
  Language context: Solidity emulating a MIPS CPU. The Move equivalent is any computed shift where the count must be constrained to a specific bit range but the code performs no masking or assertion, allowing the count to exceed the operand's bit width and trigger an abort.
  Map to: shr, shift_count, wide_shift, bit_shift

- Pattern: Unchecked left-shift width removes non-zero bytes, producing silent incorrect arithmetic output
  Where it hit: `u256::shlw` usage (Rust)
  Severity: MEDIUM
  Source: Solodit (row_id 13579)
  Summary: The numerator is passed to `shlw` without verifying its value first. A numerator with non-zero high bytes causes those bytes to be discarded by the shift, yielding a truncated result used in subsequent calculations. The fix replaces `shlw` with `checked_shlw`, which returns an error instead of silently dropping bits.
  Language context: Rust. Move does not abort on shift-result overflow; it silently truncates high bits (as documented in the SKILL). This example shows the real-world impact of that silent truncation in arithmetic pipelines and is a direct cross-language precedent for Move's Section 3c (Shift Result Overflow).
  Map to: shl, shift_overflow, bit_shift

- Pattern: Computed shift count uses wrong sub-expression (off-by-offset), causing incorrect subtree midpoint in Merkle proof
  Where it hit: `verifyInner` / `NamespaceMerkleTree.sol` (Solidity)
  Severity: HIGH
  Source: Solodit (row_id 9552)
  Summary: The function computes the subtree midpoint as `1 << (height - 1)` when it should be `1 << (height - heightOffset - 1)`. The extra term `heightOffset` is omitted, so the midpoint is wrong whenever `heightOffset != 0`. The same bug affects the side-node count check. Both errors compromise Merkle proof integrity.
  Language context: Solidity. In Move, shift counts derived from expressions like `(a - b)` are a direct analog: if `b` is omitted or wrong the shift count is wrong. Section 3a of the SKILL covers subtraction underflow in shift-count expressions; this example shows the complementary case where the subtraction is syntactically valid but logically incorrect.
  Map to: shl, shift_count, bit_shift

- Pattern: Left shift applied before division causes overflow and truncation of the denominator, producing incorrect liquidity values
  Where it hit: `PoolLib.getEquivalentLiq` / Ammplify (Solidity)
  Severity: MEDIUM
  Source: Solodit (row_id 471)
  Summary: The function shifts the operand left before dividing, but the shift result exceeds the 256-bit word size and the high bits are silently truncated. The truncated denominator yields a wrong liquidity-equivalent value, enabling unfair value distribution between users. The fix replaces the left shift with 512-bit arithmetic.
  Language context: Solidity. Move has the same silent-truncation behavior on shift results (Section 3c of the SKILL): `amount << decimals` can overflow the declared type without any abort. This example demonstrates the downstream financial impact of shift-result truncation in a liquidity calculation context.
  Map to: shl, shift_overflow, bit_shift

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

> **CRITICAL**: You MUST report completion status for ALL sections. Sections 1-2 are mechanical and must never be skipped.

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Shift Operation Inventory | **YES** | Y/X/? | **MANDATORY** --- grep ALL .move files |
| 2. Shift Amount Bound Verification | YES | Y/X/? | For each non-constant shift |
| 3. Computed Shift Analysis | IF computed shifts found | Y/X(N/A)/? | Subtraction underflow + result overflow |
| 3c. Shift Result Overflow | IF shifts with variable operands | Y/X(N/A)/? | Silent truncation check |
| 4. DoS Impact Assessment | IF any shift can abort | Y/X(N/A)/? | Trace to user impact |
| 4b. Attacker-Triggerable Analysis | IF abort in shared/critical path | Y/X(N/A)/? | Full attack trace |
| 5. Safe Shift Patterns | YES | Y/X/? | Confirm safe shifts for coverage |

### Cross-Reference Markers

**After Section 1** (Shift Operation Inventory):
- IF zero shifts found in codebase -> mark all sections X(N/A), write "No bit shift operations found in audited modules" and STOP
- IF shifts found -> proceed to Section 2, do NOT skip

**After Section 4** (DoS Impact Assessment):
- Cross-reference with access control analysis: can the aborting function be called permissionlessly?
- Cross-reference with oracle/price analysis: are shifts used in price computations? If yes, abort = price oracle DoS -> severity escalation
- IF shift in liquidation path -> severity minimum HIGH

**After Section 5** (Safe Shift Patterns):
- Verify: every shift from Section 1 is accounted for in EITHER Section 2 (unsafe) or Section 5 (safe)
- Any unaccounted shift -> reanalyze before finalizing
