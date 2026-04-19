---
name: "memory-safety-audit"
description: "Trigger Always (C/C++) - Systematic audit of memory allocation, deallocation, and pointer safety"
---

# Skill: MEMORY_SAFETY_AUDIT

> **Trigger**: Always required for C/C++ audits
> **Covers**: Use-after-free, double-free, memory leaks, dangling pointers, uninitialized memory
> **Required**: YES (foundational C/C++ security check)

## Trigger Patterns

```
malloc|calloc|realloc|free|new |new\[|delete |delete\[|unique_ptr|shared_ptr|make_unique|make_shared
```

## Reasoning Template

### Step 1: Allocation Inventory

Enumerate ALL dynamic allocations using grep:

| # | Allocation Site | Type | Size Source | Allocation Function | File:Line |
|---|----------------|------|-------------|--------------------:|-----------|
| 1 | {variable} | {type} | {how size is determined} | malloc/new/etc | {file:line} |

**Categorize each**:
- **HEAP_RAW**: malloc/calloc/realloc (C-style, manual free required)
- **HEAP_CPP**: new/new[] (C++-style, manual delete required)
- **SMART_PTR**: unique_ptr/shared_ptr (RAII-managed)
- **STACK**: VLA or alloca (stack-allocated, auto-freed but overflow risk)

### Step 2: Deallocation Tracing

For each HEAP_RAW and HEAP_CPP allocation, trace ALL paths to deallocation:

| Allocation | Dealloc Function | Dealloc Site | All Paths Covered? | Missing Paths |
|-----------|-----------------|-------------|-------------------:|--------------|
| {var} | free/delete | {file:line} | YES/NO | {error path, early return, exception} |

**Check for each**:
- [ ] Is pointer set to NULL after free? (prevents use-after-free)
- [ ] Are there multiple code paths that could free the same pointer? (double-free)
- [ ] Is the correct deallocator used? (malloc→free, new→delete, new[]→delete[])
- [ ] On error/exception paths, is the allocation freed?

### Step 3: Use-After-Free Detection

For each free/delete call, trace ALL subsequent uses of the pointer:

| Free Site | Pointer | Subsequent Uses | Use-After-Free? | File:Line |
|----------|---------|-----------------|----------------:|-----------|

**Patterns to check**:
- free(ptr) followed by ptr->field access
- delete obj followed by obj->method() call
- Iterator invalidation: container.erase() followed by iterator use
- Vector reallocation: push_back() invalidating previously stored references/pointers

### Step 4: Uninitialized Memory Detection

For each allocation WITHOUT immediate initialization:

| Allocation | Initialized Before Use? | First Read Site | Risk |
|-----------|------------------------|----------------|------|
| malloc(n) | memset/explicit init? | {file:line} | Information leak / undefined behavior |
| stack var | assigned before read? | {file:line} | Undefined behavior |

**Note**: calloc zero-initializes. malloc does NOT. new with constructor initializes. Placement new may not.

### Step 5: Smart Pointer Correctness

For SMART_PTR allocations:
- [ ] Is shared_ptr used where unique_ptr suffices? (unnecessary overhead)
- [ ] Are there raw pointer escapes from smart pointers (.get() stored separately)?
- [ ] Are there circular references with shared_ptr? (memory leak)
- [ ] Is make_shared/make_unique used? (exception safety)

### Step 6: Buffer Overflow Proximity

For each allocation, check if the allocated buffer is used in:
- memcpy/memmove (is copy size ≤ buffer size?)
- strcpy/strncpy (is source length ≤ destination size?)
- Array indexing (is index < allocated count?)

### Output Format

For each finding, use standard format with [MEMSAFE-N] IDs.
Severity guide:
- Use-after-free with attacker-controlled data → HIGH/CRITICAL
- Double-free → MEDIUM/HIGH (heap corruption)
- Memory leak in hot path → MEDIUM (DoS via resource exhaustion)
- Memory leak in one-time path → LOW/INFO
- Missing NULL check after malloc → MEDIUM (null deref → crash)
- Uninitialized read of sensitive data → MEDIUM/HIGH (information disclosure)
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

Source: CVE databases, bitcoincore.org security advisories, xrpl.org disclosure reports,
openssl.org vulnerability pages. Local CSV returned 0 hits; all entries sourced via WebSearch.

---

## MEMSAFE-1

*Project*: Bitcoin Core (C++)
*CVE*: CVE-2017-18350
*Category*: heap_overflow / stack_overflow
*Severity*: HIGH

*Description*: The SOCKS5 proxy handshake code passed the result of `recv()` into a stack
buffer indexed by a variable declared as `char` (signed on x86). When the hostname length
byte came back as 0xFF the signed conversion produced -1, which was then passed as the
`count` argument to `recv()`. The C runtime promotes that to a large unsigned value,
causing an effectively unbounded read that overwrites the 256-byte dummy stack buffer and
adjacent stack frames.

*Root cause*: `char` used for a length field that drives a `recv()` call. Signed-to-unsigned
implicit conversion turns a malicious 0xFF byte into SIZE_MAX.

*Pattern*: `char len = recv(...); recv(buf, len, ...)` where `buf` is a fixed-size stack array.

*Fix*: Changed the length variable to `unsigned char`, eliminating the negative conversion.

*Affected versions*: Bitcoin Core 0.7.0 - 0.15.0
*References*: https://bitcoincore.org/en/2019/11/08/CVE-2017-18350/

---

## MEMSAFE-2

*Project*: Bitcoin Core (C++)
*CVE*: CVE-2024-35202
*Category*: null_pointer / assert_crash
*Severity*: HIGH

*Description*: The compact block reconstruction path (`PartiallyDownloadedBlock::FillBlock`)
contained an `assert` that the function is called at most once per block request. An attacker
could craft a sequence where a short-ID collision forced a full block re-download while the
partial block state was left alive. A second `blocktxn` message for the same block then
triggered the assert, crashing the node process remotely with no authentication required.

*Root cause*: Missing guard on double-call to `FillBlock`; state not reset after collision
branch. The `assert` acted as an unintentional remote crash gadget.

*Pattern*: Stateful object re-entered after an internal invariant is partially broken by
an attacker-controlled message sequence.

*Fix*: PR #26898 cleared the partial block state on the collision path so a second call
could not reach the assert.

*Affected versions*: Bitcoin Core < 25.0
*References*: https://bitcoincore.org/en/2024/10/08/disclose-blocktxn-crash/

---

## MEMSAFE-3

*Project*: Bitcoin Core / miniupnpc (C)
*CVE*: CVE-2015-20111
*Category*: heap_overflow / stack_overflow
*Severity*: MEDIUM

*Description*: The bundled `miniupnpc` library called `snprintf()` without checking its
return value. When the UPnP discovery response contained a URL longer than the destination
buffer, the unchecked truncation left the caller believing the full string was written.
Combined with a second stack overflow in CVE-2015-6031, an attacker on the local network
(or controlling the UPnP-announcing router) could achieve remote code execution on nodes
with UPnP enabled.

*Root cause*: Missing `snprintf` return-value check; buffer overflow from UPnP response
data controlled by the network.

*Pattern*: `snprintf(buf, sizeof(buf), fmt, attacker_data)` with no length validation of
the resulting string before use.

*Fix*: Fixed in miniupnpc commit 4c90b87; Bitcoin Core 0.12 shipped the patched version.

*Affected versions*: Bitcoin Core < 0.12 (UPnP enabled by default on some builds)
*References*: https://bitcoincore.org/en/2024/07/03/disclose_upnp_rce/

---

## MEMSAFE-4

*Project*: OpenSSL (C) - used by rippled, Bitcoin Core pre-0.12, Monero, LND
*CVE*: CVE-2014-0160 ("Heartbleed")
*Category*: heap_overflow (over-read) / information_disclosure
*Severity*: CRITICAL

*Description*: The TLS heartbeat extension handler copied `payload_length` bytes from a
heap buffer back to the peer without first checking that `payload_length` did not exceed
the actual received payload. An attacker sent a heartbeat with a 1-byte payload claiming
a length of 65535 bytes, causing `memcpy` to read 64 KB of adjacent heap memory, which
could contain private keys, session tokens, and plaintext.

*Root cause*: Missing bounds check before `memcpy(bp, pl, payload)` where `payload` is
attacker-controlled. The allocation was sized to the *claimed* length, not the actual
received data length.

*Pattern*:
```c
// Vulnerable: no check that payload <= actual received length
memcpy(bp, pl, payload);
```

*Fix*: Added `if (1 + 2 + payload + 16 > s->s3->rrec.length) return 0;` before the copy.

*Affected versions*: OpenSSL 1.0.1 - 1.0.1f, 1.0.2-beta
*References*: https://www.cvedetails.com/cve/CVE-2014-0160/

---

## MEMSAFE-5

*Project*: OpenSSL (C) - used by crypto node software broadly
*CVE*: CVE-2016-0705
*Category*: double_free
*Severity*: HIGH

*Description*: `dsa_priv_decode()` in `crypto/dsa/dsa_ameth.c` called `DSA_free()` on a
partially constructed DSA key on one error path, then returned through a code path that
also called `DSA_free()` on the same pointer. A remote attacker supplying a malformed DSA
private key in a TLS client certificate could trigger heap corruption, potentially enabling
code execution or a reliable crash.

*Root cause*: Dual ownership of a pointer on an error path: the allocating function and
its caller both held a reference and both freed it without coordination.

*Pattern*:
```c
DSA_free(dsa);   // first free on error
return 0;
// ... caller also calls DSA_free(dsa) on the same error return
```

*Fix*: Removed the redundant `DSA_free` call on the inner error path.

*Affected versions*: OpenSSL 1.0.1 before 1.0.1s; 1.0.2 before 1.0.2g
*References*: https://www.cvedetails.com/cve/CVE-2016-0705/

---

## MEMSAFE-6

*Project*: OpenSSL (C)
*CVE*: CVE-2021-3449
*Category*: null_pointer
*Severity*: HIGH

*Description*: During TLS 1.2 renegotiation, if the client's renegotiation `ClientHello`
omitted the `signature_algorithms` extension but included `signature_algorithms_cert`, the
server code dereferenced a pointer that was only initialised on the original handshake path.
The result was a NULL pointer dereference, crashing the TLS server process. Any TLS server
using OpenSSL with renegotiation enabled (the default) was exposed.

*Root cause*: `s->s3->tmp.peer_sigalgs` set to NULL on renegotiation; subsequent dereference
assumed non-NULL based on original handshake invariant that no longer held.

*Pattern*: Pointer valid at construction time but becomes NULL on a specific re-entry path;
code unconditionally dereferences without a NULL guard.

*Fix*: Added a NULL check for `s->s3->tmp.peer_sigalgs` before dereferencing.

*Affected versions*: OpenSSL 1.1.1a - 1.1.1j (fixed in 1.1.1k)
*References*: https://nvd.nist.gov/vuln/detail/cve-2021-3449

---

## MEMSAFE-7

*Project*: rippled / XRP Ledger (C++)
*CVE*: none assigned (internal disclosure)
*Category*: dangling_pointer / use_after_free (cache invalidation)
*Severity*: HIGH

*Description*: The `PaymentChannelClaim` and similar transaction handlers accepted an
object ID parameter, looked up the object in the ledger cache, then assumed the cached
pointer remained valid through the transaction's processing window. An attacker submitted
a `TrustSet` for a `RippleState` object (causing a cache refresh) immediately before
submitting a `PaymentChannelClaim` referencing the same object ID. Nodes that had the
`RippleState` in cache accessed the stale pointer after the cache update, triggering a
crash. The attack halted XRP Ledger transaction processing for approximately 10 minutes
on 25 November 2024.

*Root cause*: Object type not validated against the expected type for the transaction before
the cache lookup result was used. Cache entry remained live but referred to an object of the
wrong type, causing an invalid downcast or field access.

*Pattern*: `auto obj = cache.lookup(id); obj->checkSpecificField()` with no prior type
assertion that `obj` is the expected ledger object type.

*Fix*: rippled 2.3.0 adds object-type validation before the cached pointer is used.

*Affected versions*: rippled < 2.3.0
*References*: https://xrpl.org/blog/2025/vulnerabilitydisclosurereport-bug-nov2024

---

## MEMSAFE-8

*Project*: go-ethereum (C interop via CGO / EVM interpreter)
*CVE*: GO-2022-0254 (GitHub Advisory GHSA-xw37-57qp-9mm4)
*Category*: heap_overflow / memory_corruption
*Severity*: CRITICAL (consensus-breaking)

*Description*: A memory-corruption bug in the EVM execution layer caused vulnerable nodes
to compute a different `stateRoot` when processing a maliciously crafted transaction. Because
the EVM interpreter contains hot paths written against C-style buffer semantics (fixed-size
byte arrays, manual slice management), an out-of-bounds write in the interpreter state
produced a divergent post-state. Nodes running the vulnerable version would reject valid
blocks or accept invalid ones, resulting in a consensus split.

*Root cause*: Buffer length accounting error in the EVM interpreter byte-array operations;
a write index was not clamped to the allocated slice length.

*Pattern*: EVM MSTORE/MLOAD operations that extend memory by rounding up to the next 32-byte
word boundary; off-by-one in the extension calculation left one byte written outside the
allocated region.

*Fix*: Fixed in geth 1.10.x; bounds check added before the memory extension write.

*Affected versions*: go-ethereum before the patch commit (2022)
*References*: https://pkg.go.dev/vuln/GO-2022-0254

---

## Summary Table

| ID | Project | CVE | Category | Severity |
|----|---------|-----|----------|----------|
| MEMSAFE-1 | Bitcoin Core | CVE-2017-18350 | heap_overflow | HIGH |
| MEMSAFE-2 | Bitcoin Core | CVE-2024-35202 | null_pointer / assert_crash | HIGH |
| MEMSAFE-3 | Bitcoin Core / miniupnpc | CVE-2015-20111 | heap_overflow | MEDIUM |
| MEMSAFE-4 | OpenSSL | CVE-2014-0160 | heap_overflow (over-read) | CRITICAL |
| MEMSAFE-5 | OpenSSL | CVE-2016-0705 | double_free | HIGH |
| MEMSAFE-6 | OpenSSL | CVE-2021-3449 | null_pointer | HIGH |
| MEMSAFE-7 | rippled / XRPL | (none) | dangling_pointer / UAF | HIGH |
| MEMSAFE-8 | go-ethereum | GO-2022-0254 | heap_overflow | CRITICAL |


