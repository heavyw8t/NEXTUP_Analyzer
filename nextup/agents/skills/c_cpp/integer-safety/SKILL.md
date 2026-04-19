---
name: "integer-safety"
description: "Trigger Arithmetic on user-influenced values detected - Integer overflow, underflow, and type confusion audit"
---

# Skill: INTEGER_SAFETY

> **Trigger**: Arithmetic on user input or size calculations detected
> **Covers**: Integer overflow/underflow, signed/unsigned confusion, truncation, undefined behavior
> **Required**: YES when arithmetic on external input detected

## Trigger Patterns

```
size_t|uint32_t|uint64_t|int32_t|int64_t|__builtin_.*_overflow|numeric_limits|INT_MAX|UINT_MAX|SIZE_MAX
```

## Reasoning Template

### Step 1: Arithmetic Operation Inventory

Enumerate arithmetic on user-influenced or size-related values:

| # | Operation | Operand Types | User-Influenced? | Overflow Check? | File:Line |
|---|-----------|--------------|-----------------|----------------|-----------|

### Step 2: Signed/Unsigned Confusion

For every comparison or assignment between signed and unsigned:

| # | Expression | Signed Type | Unsigned Type | Implicit Conversion | Risk | File:Line |
|---|-----------|-------------|--------------|--------------------:|------|-----------|

**Critical patterns**:
- `if (signed_val < unsigned_val)` — signed silently converts to unsigned, negative becomes huge
- `unsigned x = negative_value` — wraps to large number
- `int len = unsigned_size` — truncation if size > INT_MAX
- Array indexing with signed index: `arr[signed_idx]` where signed_idx could be negative

### Step 3: Overflow/Underflow Paths

For each arithmetic operation on user-influenced values:
- **Signed overflow**: UNDEFINED BEHAVIOR in C/C++. Compiler can assume it never happens and optimize accordingly.
- **Unsigned overflow**: Wraps modulo 2^N. Not UB but often a logic bug.
- **size_t arithmetic**: `size_a + size_b` can wrap, leading to undersized allocation then buffer overflow

| Operation | Can Overflow? | Consequence | Safe Alternative |
|-----------|-------------|-------------|-----------------|
| a + b | YES/NO | {what happens} | __builtin_add_overflow / SafeInt<> |
| a * b | YES/NO | {what happens} | __builtin_mul_overflow |
| a - b | YES/NO | {unsigned underflow wraps} | check a >= b first |

### Step 4: Truncation Analysis

For every narrowing conversion (explicit or implicit):

| # | From Type | To Type | Can Lose Data? | Checked? | File:Line |
|---|-----------|---------|---------------|---------|-----------|

Common dangerous patterns:
- uint64_t → uint32_t (silent truncation)
- size_t → int (size_t is unsigned, int is signed — double danger)
- double → int (fractional loss + overflow if > INT_MAX)

### Step 5: Allocation Size Calculations

Special focus on size calculations used for memory allocation:

| Allocation | Size Expression | Can Overflow? | Result if Overflow |
|-----------|----------------|-------------|-------------------|
| malloc(n * sizeof(T)) | n * sizeof(T) | YES if n is large | Undersized buffer → heap overflow |

**Rule**: Any `malloc(a * b)` without overflow check is a potential heap overflow.

### Output Format
Use [INTSAFE-N] finding IDs. Severity: integer overflow in allocation size → HIGH/CRITICAL.
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Sourced from CVE databases, Bitcoin Core security advisories, and public blockchain security disclosures.
Use these as pattern precedents when investigating this skill. For each finding, check whether the
described mechanism is present in scope code. If a match is found, tag the finding with
`Example precedent: <row_id or URL>`.

---

## [INTSAFE-W01] Bitcoin Value Overflow — 184 Billion BTC Minted
- *Severity*: CRITICAL
- *CVE*: CVE-2010-5139
- *Source*: https://en.bitcoin.it/wiki/Value_overflow_incident
- *Affected*: Bitcoin Core < 0.3.10 (C++), `src/main.cpp` `ConnectInputs()`
- *Type*: integer_overflow (unsigned wraparound), missing bounds check
- *Root cause*: `ConnectInputs()` accumulated output values into `nValueIn` (int64_t) without checking
  that any individual output value stayed within `MAX_MONEY`. Two outputs each set to ~92.2 billion
  satoshi caused the sum to overflow int64_t, wrapping to a small positive number. The output-sum
  check passed, and block 74638 created 184,467,440,737 BTC across three addresses.
- *Exploit path*: Craft a transaction with two outputs whose individual amounts each exceed
  `INT64_MAX / 2`. The addition overflows to a value that satisfies `nValueIn >= nValueOut`, bypassing
  monetary integrity validation. Node accepts and relays the block.
- *Fix*: Added `MoneyRange()` guards on each individual output value before accumulating into the total.
  Hard fork required; all nodes upgraded to 0.3.10 within 19 hours.
- *Map to*: integer_overflow, INT_MAX, signed_overflow, missing_bounds_check

---

## [INTSAFE-W02] Bitcoin Core Timestamp Signed Overflow — Network Split
- *Severity*: HIGH (Medium per Bitcoin Core rating)
- *CVE*: CVE-2024-52912 (fix shipped in Bitcoin Core 0.21.0, January 2021)
- *Source*: https://bitcoincore.org/en/2024/07/03/disclose-timestamp-overflow/
- *Affected*: Bitcoin Core < 0.21.0 (C++), peer-to-peer version message processing
- *Type*: signed_overflow, undefined_behavior, abs64 logic bug
- *Root cause*: Two cooperating bugs. (1) A signed int64_t overflow when accumulating time-offset values
  from the first 200 connecting peers — if the sum overflows `INT64_MAX` the result is undefined
  behavior and in practice wraps to a large negative offset. (2) `abs64(INT64_MIN) == INT64_MIN`
  (two's-complement minimum has no positive counterpart), so the maximum-adjustment clamp was bypassed.
  An attacker in the first-200-peers window could skew the victim node's adjusted time arbitrarily far
  forward, causing all new blocks to be rejected as timestamped too far in the future.
- *Exploit path*: Connect to a victim as one of its first 200 peers and send crafted version messages
  with extreme timestamp values. The cumulative offset overflows and the node's adjusted time is
  pushed far ahead, isolating it from the honest chain.
- *Fix*: Use saturating arithmetic for time-offset accumulation; fix abs64 edge case.
- *Map to*: signed_overflow, INT_MAX, undefined_behavior, wraparound

---

## [INTSAFE-W03] Bitcoin Core CVE-2018-17144 — Duplicate Input Inflation
- *Severity*: CRITICAL (inflation; DoS in older branch)
- *CVE*: CVE-2018-17144
- *Source*: https://bitcoincore.org/en/2018/09/20/notice/
- *Affected*: Bitcoin Core 0.14.0–0.16.2 (C++), `src/validation.cpp`
- *Type*: missing_overflow_check, integer_accumulation, logic removal
- *Root cause*: An optimization added in 0.14.0 removed a deduplication check on transaction inputs
  that was considered redundant. In 0.15.0 the assertion that caught the duplicate-input case was
  rewritten, and the duplicate path no longer caused a crash — instead the node continued processing
  and counted the same input twice toward `nValueIn`. A miner could craft a block where one input
  UTXO was referenced twice; the node would accept the block and credit the miner for double the
  UTXO value, creating coins from nothing.
- *Exploit path*: Miner constructs a coinbase transaction (or any transaction) that lists the same
  UTXO outpoint twice. Pre-0.15 nodes crash (DoS). Post-0.15 nodes accept the block and the miner
  receives double the input value, inflating supply without triggering the `nValueIn >= nValueOut` check.
- *Fix*: Restored the explicit deduplication check before accumulating input values.
- *Map to*: integer_overflow, missing_bounds_check, accumulation_without_check

---

## [INTSAFE-W04] Bitcoin Core CAddrMan nIdCount Integer Overflow — Daemon Crash
- *Severity*: HIGH (remote DoS)
- *CVE*: listed in Bitcoin Core CVE list; fixed in Bitcoin Core 22.0
- *Source*: https://www.cvedetails.com/vulnerability-list/vendor_id-12094/product_id-59195/opov-1/Bitcoin-Bitcoin-Core.html
- *Affected*: Bitcoin Core < 22.0 (C++), `src/addrman.cpp`
- *Type*: integer_overflow, assertion_failure, wraparound
- *Root cause*: `CAddrMan::nIdCount` is a counter incremented each time a new peer address is added.
  The counter type overflows when a flood of addr messages forces it past its maximum value, triggering
  an internal assertion failure and causing the daemon to exit (crash). The overflow requires no
  authentication; any peer can send addr messages.
- *Exploit path*: Send a sustained flood of addr P2P messages containing novel addresses. Each message
  can carry up to 1000 addresses. After enough messages `nIdCount` overflows and the assert fires,
  taking the node offline.
- *Fix*: Guard the counter increment with a bounds check; use a wider type or cap enrollment rate.
- *Map to*: integer_overflow, wraparound, missing_bounds_check

---

## [INTSAFE-W05] EOSIO asset.hpp Multiplication Overflow — Compiler Eliminates Safety Check
- *Severity*: HIGH (asset amount forgery in smart contracts)
- *CVE*: no public CVE; disclosed 2018-07-26, fixed 2018-08-07
- *Source*: https://blogs.360.cn/post/eos-asset-multiplication-integer-overflow-vulnerability.html
- *Affected*: EOSIO contracts/eosiolib/asset.hpp `asset& operator*=(int64_t a)` (C++)
- *Type*: signed_overflow, undefined_behavior, compiler_optimization_removes_check
- *Root cause*: The `operator*=` function contained the overflow check
  `(amount * a) / a == amount` — a classic "verify by dividing back" pattern. In C/C++, signed integer
  overflow is undefined behavior. When compiled with clang at `-O3` (EOSIO's default), the compiler
  proved the expression is always true under the no-UB assumption and eliminated it entirely. Two
  additional checks were also misplaced (executed before the multiplication result existed). The net
  effect: all three overflow guards were dead code in the compiled WebAssembly, allowing `amount` to
  wrap to any value the attacker chose.
- *Exploit path*: Call a contract that uses `asset operator*=` with inputs that overflow int64_t. The
  overflow check passes vacuously; the resulting asset holds a wrapped (possibly negative or zero) value
  that is then used in token-transfer logic, allowing forged balances.
- *Fix*: Replace the division-based check with `__builtin_mul_overflow` or equivalent safe-math
  intrinsics that survive optimization; restructure check to execute after the multiplication.
- *Map to*: signed_overflow, undefined_behavior, INT_MAX, compiler_removes_check

---

## [INTSAFE-W06] Monero / CryptoNote Key-Image Overflow — Unlimited Coin Minting
- *Severity*: CRITICAL (supply inflation, undetectable without explicit check)
- *CVE*: no CVE; disclosed 2017-05-17 after coordinated patch
- *Source*: https://www.getmonero.org/2017/05/17/disclosure-of-a-major-bug-in-cryptonote-based-currencies.html
- *Affected*: Monero (C++), all CryptoNote-based currencies using ed25519 ring signatures
- *Type*: elliptic-curve integer arithmetic, point not on prime-order subgroup (analogous to
  unsigned wraparound in modular arithmetic)
- *Root cause*: The key-image value used to detect double-spends can be constructed from a point on
  the full elliptic curve group rather than the prime-order subgroup. When the verification code
  computes `l * key_image` (where l is the curve order), a malformed key image that is a multiple
  of a small cofactor produces the identity element — passing the check — while being reusable across
  distinct transactions. This is equivalent to arithmetic wraparound: the attacker exploits the fact
  that the integer check does not constrain the input to the valid subgroup.
- *Exploit path*: Construct transactions whose key images are low-order points. Each transaction
  passes the double-spend check independently, but together they spend the same output multiple times,
  minting coins ex nihilo. The inflation is invisible unless a node explicitly scans for low-order
  key images.
- *Fix*: Multiply every incoming key image by the curve order l and verify the result is the identity
  element before accepting the transaction.
- *Map to*: integer_overflow, wraparound, modular_arithmetic_bounds, missing_subgroup_check

---

## [INTSAFE-W07] OpenSSL EVP_EncryptUpdate Output Length Integer Overflow
- *Severity*: HIGH (incorrect output length, downstream buffer overflow)
- *CVE*: CVE-2021-23840
- *Source*: https://security.snyk.io/vuln/SNYK-ALPINE320-OPENSSL-7010749
- *Affected*: OpenSSL < 1.0.2x / < 1.1.1l (C), `crypto/evp/evp_enc.c`
- *Type*: integer_overflow, signed_to_unsigned_truncation, output_length_wrap
- *Root cause*: Calls to `EVP_CipherUpdate`, `EVP_EncryptUpdate`, and `EVP_DecryptUpdate` write the
  output byte count into an `int*` out-parameter. When the input length is close to `INT_MAX`, the
  internal size arithmetic overflows, causing the written output length to become negative. Callers
  that check only for a non-negative return value (1 = success) see a valid return code but receive
  a negative length, leading to incorrect buffer management or subsequent heap overflows.
- *Exploit path*: Pass input buffers whose length exceeds `INT_MAX - block_size` to an encrypt or
  decrypt call. The function returns 1 (success) but stores a negative length in `*outl`. Downstream
  code that uses `*outl` to advance a write pointer or size a subsequent allocation operates on a
  garbage or negative size, causing memory corruption.
- *Fix*: Add an input-length bound check before the internal size arithmetic; use size_t consistently
  throughout the length computation path.
- *Map to*: integer_overflow, signed_overflow, truncation, size_t_vs_int

---

## [INTSAFE-W08] EOSIO eosio.token Fake-Transfer Notification — Auth Check Bypass
- *Severity*: HIGH (token balance forgery, dapp fund drain)
- *CVE*: no CVE; exploited September–October 2018; 187,000+ EOS lost
- *Source*: https://blog.peckshield.com/2018/10/26/eos/
- *Affected*: EOSIO smart contract ecosystem (C++), `apply()` dispatcher in dapp contracts
- *Type*: missing_origin_check (integer/type confusion in action dispatch table)
- *Root cause*: EOSIO's action notification system passes `(code, action)` pairs to `apply()`. Many
  gambling contracts checked only `action == "transfer"` without also checking `code == "eosio.token"`.
  An attacker deployed a copycat token contract and transferred fake EOS (same symbol, different
  issuer) to the victim dapp. The `apply()` dispatch treated the notification identically to a genuine
  eosio.token transfer and credited real prizes. The dispatcher's integer-equality check on the action
  name hash was correct but the second dimension (code origin) was absent.
- *Exploit path*: Deploy `fakeeostoken` contract with identical `EOS` symbol. Call `fakeeostoken::transfer`
  to victim dapp. Dapp receives `on_transfer` notification with `action == N(transfer)`, credits the bet,
  pays out real EOS. Repeat at zero cost.
- *Fix*: Add `require(code == N(eosio.token))` in the `apply()` guard before handling transfer actions.
- *Map to*: missing_bounds_check, integer_comparison, type_confusion, dispatch_origin_not_validated


