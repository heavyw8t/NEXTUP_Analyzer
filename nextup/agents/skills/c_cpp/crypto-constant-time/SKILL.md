---
name: "crypto-constant-time"
description: "Trigger secp256k1_*/EVP_*/comparison functions detected - Constant-time operations and cryptographic correctness audit"
---

# Skill: CRYPTO_CONSTANT_TIME

> **Trigger**: Cryptographic function usage detected (secp256k1, OpenSSL, libsodium, custom crypto)
> **Covers**: Timing side channels, secret data leakage, RNG misuse, improper secret clearing
> **Required**: YES when cryptographic operations detected

## Trigger Patterns

```
secp256k1_|EVP_|HMAC_|SHA256|SHA512|AES_|RAND_bytes|RAND_seed|EC_POINT|BN_|memcmp.*secret|memcmp.*key|explicit_bzero|OPENSSL_cleanse
```

## Reasoning Template

### Step 1: Secret Data Inventory

Identify ALL variables that hold secret/sensitive data:

| # | Variable | Type | Contains | Lifetime | Cleared? | Clear Method | File:Line |
|---|----------|------|----------|----------|---------|--------------|-----------|

**Secret categories**:
- Private keys, secret keys, signing keys
- Nonces, blinding factors, random scalars
- Passwords, tokens, session keys
- Intermediate cryptographic values (partial computations)

### Step 2: Constant-Time Comparison Audit

For EVERY comparison involving secret data:

| # | Comparison | Method | Constant-Time? | Fix | File:Line |
|---|-----------|--------|---------------|-----|-----------|

**DANGEROUS** (NOT constant-time):
- `memcmp(secret, input, len)` — early exit on first mismatch
- `strcmp(secret, input)` — early exit
- `if (secret[i] != input[i]) return` — byte-by-byte with early exit
- `secret == value` for multi-byte types — compiler may optimize

**SAFE** (constant-time):
- `CRYPTO_memcmp()` (OpenSSL)
- `sodium_memcmp()` (libsodium)
- `timingsafe_bcmp()` (BSD)
- XOR-and-OR accumulator pattern: `diff |= a[i] ^ b[i]`

### Step 3: Secret-Dependent Branching

For EVERY conditional branch, check if the condition depends on secret data:

| # | Branch Condition | Depends on Secret? | Can Leak via Timing? | File:Line |
|---|-----------------|-------------------|---------------------:|-----------|

**Patterns that leak**:
- `if (secret_bit) { expensive_op(); }` — timing difference
- `secret ? path_A : path_B` — if paths have different execution time
- Table lookups with secret index: `table[secret_byte]` — cache timing attack

**Safe patterns**:
- Constant-time conditional select: `result = mask & a | ~mask & b`
- Branchless min/max using bit manipulation

### Step 4: Secret Clearing Audit

For EVERY secret variable, verify proper clearing at end of lifetime:

| # | Secret | Cleared? | Method | Safe? | File:Line |
|---|--------|---------|--------|------|-----------|

**DANGEROUS**: `memset(buf, 0, len)` — compiler can optimize this out (dead store elimination)
**SAFE**: `explicit_bzero(buf, len)`, `OPENSSL_cleanse(buf, len)`, `SecureZeroMemory(buf, len)` (Win), volatile function pointer pattern

### Step 5: RNG Audit

For EVERY random number generation:

| # | RNG Function | Seed Source | Cryptographically Secure? | Usage | File:Line |
|---|-------------|-------------|--------------------------|-------|-----------|

**DANGEROUS**: rand(), random(), srand(time(NULL)), /dev/urandom without checking
**SAFE**: RAND_bytes() (OpenSSL), getrandom() (Linux), arc4random() (BSD), sodium_randombytes()

### Step 6: Elliptic Curve Operation Safety (if applicable)

For EC operations (secp256k1, Ed25519, etc.):
- [ ] Point validation: Is every input point checked to be on the curve?
- [ ] Scalar range: Is every scalar checked to be in [1, order-1]?
- [ ] Point at infinity: Is identity element handled correctly?
- [ ] Projective coordinates: Is coordinate blinding used? (prevents cache attacks)
- [ ] Scalar blinding: Is scalar split into random shares? (prevents power analysis)

### Output Format
Use [CRYPTO-N] finding IDs. Severity:
- Secret comparison via memcmp → HIGH (timing oracle)
- Secret not cleared → MEDIUM (memory forensics)
- Weak RNG for crypto → CRITICAL
- Missing point validation → HIGH (invalid curve attack)
