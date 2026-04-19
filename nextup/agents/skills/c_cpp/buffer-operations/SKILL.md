---
name: "buffer-operations"
description: "Trigger memcpy/strcpy/strncpy/snprintf detected - Buffer boundary and bounds checking audit"
---

# Skill: BUFFER_OPERATIONS

> **Trigger**: memcpy/memmove/strcpy/strncpy/snprintf/sprintf usage detected
> **Covers**: Buffer overflows, off-by-one errors, null termination, format string issues
> **Required**: YES when buffer operation patterns detected

## Trigger Patterns

```
memcpy|memmove|strcpy|strncpy|strcat|strncat|sprintf|snprintf|gets|fgets|scanf|sscanf|vsprintf
```

## Reasoning Template

### Step 1: Dangerous Function Inventory

Enumerate ALL buffer operation call sites:

| # | Function | Source | Destination | Size | Bounds Verified? | File:Line |
|---|----------|--------|-------------|------|-----------------|-----------|

**Danger levels**:
- **CRITICAL**: gets(), sprintf(), strcpy() — unbounded by design
- **HIGH**: scanf("%s"), strcat() — commonly misused
- **MEDIUM**: memcpy(), strncpy(), snprintf() — safe IF size is correct
- **LOW**: fgets(), strncat() with verified bounds

### Step 2: Size Validation Trace

For each CRITICAL/HIGH function call:

| Call Site | Size/Bound Parameter | Source of Size | User-Controlled? | Overflow Possible? |
|----------|---------------------|---------------|-----------------|-------------------|

**Check**:
- [ ] Is the size parameter derived from the source buffer or destination buffer?
- [ ] Can an attacker control the size parameter?
- [ ] Is there an integer overflow in the size calculation? (e.g., `len1 + len2` wrapping)
- [ ] For strncpy: is null termination guaranteed? (strncpy does NOT null-terminate if src >= n)

### Step 3: Off-by-One Analysis

For each bounded operation:
- [ ] Does the bound include or exclude the null terminator?
- [ ] Is the comparison `<` or `<=`? (fencepost error)
- [ ] For loops: is the index 0-based with `< size` or 1-based with `<= size`?

### Step 4: Format String Audit

For every printf-family call:
- [ ] Is the format string a compile-time constant? (SAFE)
- [ ] Is user input passed as the format string? (CRITICAL: format string vulnerability)
- [ ] Do format specifiers match argument types? (type confusion)
- [ ] Is `%n` used anywhere? (write primitive)

### Step 5: Safe Alternative Recommendations

For each finding, recommend the safe alternative:
| Dangerous | Safe Alternative | Notes |
|-----------|-----------------|-------|
| strcpy | strlcpy or snprintf | strlcpy not in C standard but widely available |
| sprintf | snprintf | Always use snprintf with explicit size |
| strcat | strlcat or snprintf | Track remaining buffer space |
| gets | fgets | Always specify max length |
| scanf("%s") | scanf("%Ns") or fgets | Specify field width |

### Output Format
Use [BUFOP-N] finding IDs. Severity: buffer overflow with attacker-controlled input → HIGH/CRITICAL.
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Sourced from CVE databases, Bitcoin Core security advisories, and Trail of Bits research.
> Mapped to SKILL.md patterns: `buffer_overflow`, `memcpy`, `strcpy`, `snprintf`, `bounds_check`.

---

## [BUFOP-W1] CVE-2017-18350: Bitcoin Core SOCKS5 Stack Buffer Overflow via Signed-Char Signedness Error

**Severity**: HIGH
**Pattern**: `buffer_overflow`, `bounds_check`
**Source**: https://bitcoincore.org/en/2019/11/08/CVE-2017-18350/

*Root cause*: In the SOCKS5 proxy handshake handler, the server-returned domain name length was stored in a `char` (signed on x86). When the server returned a length of 255, the value was interpreted as -1. That negative value was then passed to `recv()`, which accepted it as a `size_t` (implicit conversion to a large positive value), causing an effectively unbounded read into a 256-byte stack buffer.

*Exploit scenario*: Any attacker who can intercept or serve a SOCKS5 proxy connection (e.g., a malicious proxy configured by the user) can overwrite the stack, redirect execution, and achieve remote code execution in the bitcoind/Bitcoin-Qt process.

*Fix*: Change the length variable from `char` to `unsigned char` before passing it to `recv()`. Released in Bitcoin Core 0.15.1.

*Audit checklist items triggered*:
- Step 2: Size/bound parameter is signed, user-controlled via network input.
- Step 2: Integer signedness error in size calculation.

---

## [BUFOP-W2] CVE-2015-6031 / CVE-2015-20111: miniupnpc XML Parser snprintf Return Value Not Checked (Bitcoin Core)

**Severity**: HIGH
**Pattern**: `snprintf`, `bounds_check`, `buffer_overflow`
**Source**: https://bitcoincore.org/en/2024/07/03/disclose_upnp_rce/

*Root cause*: The miniupnpc library's XML element name parser used `snprintf` to copy element names into a fixed-size buffer but did not check the return value. If `snprintf` returns a value >= the buffer size, the write truncates without null-termination and subsequent pointer arithmetic produces writes past the buffer end.

*Exploit scenario*: A malicious UPnP server on the local network sends an XML response with an oversized element name. Bitcoin Core with UPnP enabled (the default in some builds) processes this at startup, triggering heap or stack corruption and potentially remote code execution.

*Fix*: miniupnpc 1.9.20151008 added the missing return-value check. Bitcoin Core 0.12 adopted the patched version.

*Audit checklist items triggered*:
- Step 1: `snprintf` classified MEDIUM; escalates to HIGH when return value is discarded.
- Step 3: Off-by-one in buffer boundary when truncated output is used for further pointer arithmetic.

---

## [BUFOP-W3] CVE-2014-0160 (Heartbleed): OpenSSL Missing Bounds Check Before memcpy

**Severity**: CRITICAL
**Pattern**: `memcpy`, `bounds_check`
**Source**: https://www.invicti.com/blog/web-security/the-heartbleed-bug

*Root cause*: The TLS heartbeat handler accepted a user-supplied `payload_length` field without validating it against the actual received message length. It then called `memcpy(bp, pl, payload)` where `payload` came from the attacker. If the attacker claimed a 64 KB payload but sent 1 byte, `memcpy` read 64 KB starting from the source pointer, leaking up to 64 KB of process memory per request.

*Exploit scenario*: Any remote client sends a crafted heartbeat request. No authentication required. Repeated requests can leak private keys, session tokens, and passwords from the server's heap.

*Fix*: OpenSSL 1.0.1g added the bounds check: `if (1 + 2 + payload + 16 > s3->rrec.length) return 0;` before `memcpy`.

*Audit checklist items triggered*:
- Step 2: Size parameter (`payload_length`) is fully attacker-controlled, never validated against source buffer.
- Step 2: `memcpy` with user-controlled length is CRITICAL when source bounds are not verified.

---

## [BUFOP-W4] CVE-2020-26800: cpp-ethereum (aleth) Stack Buffer Overflow in JSON Config Parser

**Severity**: HIGH
**Pattern**: `buffer_overflow`, `bounds_check`
**Source**: https://github.com/ethereum/aleth/issues/5917

*Root cause*: The JSON configuration file parser in cpp-ethereum (aleth) used a recursive descent approach without limiting recursion depth or input nesting. Supplying a config.json with 3764 or more consecutive `[` characters exhausted the stack, causing a segmentation fault.

*Exploit scenario*: An attacker who can influence the config.json read at node startup (e.g., a supply-chain substitution, a crafted file dropped via another vulnerability) can trigger immediate denial of service. With more advanced stack-smashing techniques the overflow could be leveraged for code execution.

*Fix*: Add a nesting-depth counter; abort parsing when depth exceeds a safe limit.

*Audit checklist items triggered*:
- Step 1: Parser consumes unbounded user-supplied input into a fixed stack frame.
- Step 2: No depth/size bound on recursive calls; input size is the sole bound.

---

## [BUFOP-W5] Arbitrum Stylus C SDK strncpy Off-by-One: Destination Overwrite (CSV finding, row 6431)

**Severity**: MEDIUM
**Pattern**: `strcpy`, `bounds_check`
**Source**: Local CSV row 6431 (Stylus C SDK audit)

*Root cause*: The Stylus C SDK wrapper around `strncpy` wrote one byte past the declared destination size. `strncpy` does not null-terminate when `src_len >= n`; the SDK code treated the buffer as already terminated and performed a write at `dest[n]`, overwriting an adjacent memory region.

*Exploit scenario*: Any contract compiled with the affected SDK that calls the wrapped `strncpy` with a source string exactly filling the destination buffer will corrupt adjacent stack or heap data. Depending on what lies adjacent, this can produce incorrect computation results or exploitable memory corruption.

*Fix (short-term)*: Change the write index from `n` to `n-1`, or use `strlcpy`. Long-term: add ASan-driven edge-case tests for all SDK string functions.

*Audit checklist items triggered*:
- Step 2: Destination buffer bound is off by one.
- Step 3: Classic fencepost error: `<= size` instead of `< size`.

---

## [BUFOP-W6] Bitcoin Core Heap Buffer Overflow via PV60Sync::changeSyncer (cpp-ethereum pattern, AddressSanitizer)

**Severity**: HIGH
**Pattern**: `memcpy`, `buffer_overflow`, `bounds_check`
**Source**: https://github.com/ethereum/cpp-ethereum/issues/2279

*Root cause*: In the `PV60Sync::changeSyncer` function (BlockChainSync.cpp:576), a peer-supplied block count was used as a direct index into a heap-allocated array without a range check. AddressSanitizer detected an out-of-bounds heap write when a crafted peer message contained a block count larger than the allocated array size.

*Exploit scenario*: A remote peer on the P2P network sends a crafted sync message with an oversized block count. The node writes past the end of its internal sync-state array, corrupting heap metadata. This can produce a crash (DoS) or, with heap-grooming, arbitrary write primitives.

*Fix*: Bounds-check the peer-supplied count against the array allocation size before indexing.

*Audit checklist items triggered*:
- Step 1: Network-supplied integer used as array index without bounds check.
- Step 2: Size parameter is remote-peer-controlled.

---

## [BUFOP-W7] CVE-2018-17144: Bitcoin Core Missing Duplicate-Input Check Enabling Inflation (Logic Bound Failure)

**Severity**: CRITICAL
**Pattern**: `bounds_check`
**Source**: https://bitcoinops.org/en/topics/cve-2018-17144/

*Root cause*: Bitcoin Core 0.14 removed a check that detected duplicate inputs within a single transaction, treating it as redundant. In 0.15 the `assert` that would have caught this was rewritten in a way that allowed the node to continue processing a transaction with duplicate inputs instead of aborting. The effective invariant `inputs are unique within a transaction` was no longer enforced.

*Exploit scenario*: A miner could construct a block containing a transaction that spends the same UTXO twice. Nodes running 0.14.x-0.16.x before the patch would accept the block, crediting the miner twice the value of the spent output and inflating the supply.

*Fix*: Re-add the uniqueness check in `CheckTransaction`. Released in 0.14.3, 0.15.2, 0.16.3.

*Audit checklist items triggered*:
- Step 2: Invariant (loop bound / set uniqueness) removed as "optimization" without proof of redundancy.
- Step 3: Assertion rewrite introduced a logic off-by-one in the duplicate-detection branch.

---

## [BUFOP-W8] Parity libsecp256k1 (Rust FFI): R/S Parameter Not Reduced Modulo Curve Order (Overflow in Signature Verification)

**Severity**: HIGH
**Pattern**: `bounds_check`, `buffer_overflow`
**Source**: https://vulners.com/osv/OSV:GHSA-G4VJ-X7V9-H82M

*Root cause*: The Parity Rust wrapper around the C libsecp256k1 library did not enforce that the R and S scalar values in an ECDSA signature were reduced modulo the curve order n before use. Values equal to or larger than n should be rejected as invalid. Because the check was absent, a signature with R or S == n (which should be invalid) passed verification.

*Exploit scenario*: A transaction or message authentication relying on this library could be made to accept a signature that is cryptographically invalid. In a blockchain context this can enable signature malleability or bypass authentication checks.

*Fix*: Versions >= 0.5.0 of the parity libsecp256k1 crate add the range check before scalar use.

*Audit checklist items triggered*:
- Step 2: Integer value derived from external input used without range validation against a known upper bound (curve order).
- Step 2: Integer overflow possible when arithmetic on unchecked scalar wraps modulo field size.

---

## Pattern Coverage Summary

| SKILL.md Pattern | Findings |
|-----------------|---------|
| buffer_overflow | W1, W2, W4, W6 |
| memcpy | W2, W3, W6 |
| strcpy / strncpy | W5 |
| snprintf | W2 |
| bounds_check | W1, W2, W3, W4, W5, W6, W7, W8 |


