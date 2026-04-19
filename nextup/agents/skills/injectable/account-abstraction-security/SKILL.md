---
name: "account-abstraction-security"
description: "Protocol Type Trigger account_abstraction (detected when ERC-4337 interfaces, EntryPoint, UserOperation, or Paymaster patterns found) - Inject Into Breadth agents, depth-external"
---

# Injectable Skill: Account Abstraction Security

> **Protocol Type Trigger**: `account_abstraction` (detected when ERC-4337 interfaces, EntryPoint, UserOperation, or Paymaster patterns found)
> **Inject Into**: Breadth agents, depth-external
> **Language**: EVM only (other VMs handle account abstraction natively without smart contract validation stacks)
> **Finding prefix**: `[AA-N]`

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (validation flow, external calls to EntryPoint)
- Section 2: depth-edge-case (paymaster edge cases, gas bounds)
- Section 3: depth-state-trace (signature validation state, module registry)
- Section 4: depth-token-flow (fee payment flows, token approvals)

## When This Skill Activates

Recon detects ERC-4337 patterns: `UserOperation`, `IAccount`, `IPaymaster`, `EntryPoint`, `validateUserOp`, `validatePaymasterUserOp`, `postOp`, `isValidSignature` (ERC-1271), or smart account/wallet factory patterns.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `UserOperation`, `EntryPoint`, `validateUserOp`, `validatePaymasterUserOp`, `paymaster`, `bundler`, `executeUserOp`, `ERC-4337`, `EIP-7702`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[AA-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. UserOperation Validation Flow

For each `validateUserOp` implementation:

### 1a. Signature Verification
- What signature scheme is used? (ECDSA, multi-sig, passkey/WebAuthn, session keys)
- Is the signature verified against the CORRECT signer(s)?
- Is the `userOpHash` computed correctly (includes `chainId`, `entryPoint`, `nonce`)?
- Can a valid signature for one operation be replayed for a different operation? (nonce management)

### 1b. Nonce Management
- Is the nonce scheme sequential, 2D (key + sequence), or custom?
- Can nonce be skipped or reused?
- For 2D nonces: can different keys interfere with each other?
- Does the nonce validation happen BEFORE or AFTER signature verification?

### 1c. Return Value Correctness
- `validateUserOp` must return `validationData` encoding `(authorizer, validUntil, validAfter)`.
- Does the return value correctly encode time bounds?
- Does returning `0` (success) vs `1` (failure) vs packed data follow the spec?
- Can the function return success for an INVALID operation?

Tag: `[TRACE:validateUserOp → sig_scheme={scheme} → hash_includes_chainId={YES/NO} → nonce_check={method}]`

---

## 2. Paymaster Validation

For each `validatePaymasterUserOp` implementation:

### 2a. Pre-Validation vs Post-Execution
- What validation occurs in `validatePaymasterUserOp` (pre-execution)?
- What validation occurs in `postOp` (post-execution)?
- If payment validation is DEFERRED to `postOp`: what happens if `postOp` reverts? Does the paymaster eat the cost?
- Can a user consume gas without ever paying? (trigger `validatePaymasterUserOp` success → execute expensive operation → `postOp` fails to collect payment)

### 2b. Payment Token Handling
If paymaster accepts ERC-20 for gas payment:
- Is the token approval checked in `validatePaymasterUserOp` or `postOp`?
- Can the user revoke approval BETWEEN validation and `postOp`? (inner execution context)
- Is the exchange rate (token/gas) manipulable? (oracle dependency → cross-reference ORACLE_ANALYSIS)
- Is there a maximum gas sponsor amount to prevent griefing?

### 2c. Paymaster Context Integrity
- Data passed via `context` from `validatePaymasterUserOp` to `postOp`: can it be tampered with?
- Is the context length bounded? (unbounded context → gas griefing)
- Does `postOp` handle all three modes? (`opSucceeded`, `opReverted`, `postOpReverted`)

Tag: `[TRACE:paymaster_validate → deferred_checks={list} → postOp_can_fail={YES/NO} → payment_collected={guaranteed/conditional}]`

---

## 3. Signature Validation Modules (ERC-1271)

For each `isValidSignature` implementation:

### 3a. Delegation Security
- Is signature validation delegated to external modules/plugins?
- If yes: is the module registry access-controlled? (who can add/remove modules)
- Can a malicious module return `0x1626ba7e` (valid) for ANY hash? (always-true validator)
- Is there a timelock/guardian approval for module changes?

### 3b. Module Interaction Safety
- Can modules call back into the account contract? (reentrancy via validation)
- Can modules access account funds during validation?
- Is there a gas limit on module `isValidSignature` calls?

### 3c. Session Key Constraints
If session keys or scoped permissions are supported:
- Are permissions correctly scoped? (target contract, function selector, value limit, time window)
- Can a session key exceed its permission scope through calldata manipulation?
- Are session key permissions checked BEFORE or AFTER signature verification?

Tag: `[TRACE:isValidSignature → delegated_to={module} → registry_access={control} → always_valid={YES/NO}]`

---

## 4. Factory and Initialization

### 4a. Counterfactual Address Binding
- Is the wallet's initialization data (owner, modules, config) committed to the CREATE2 salt/address?
- Can an attacker deploy a wallet at the expected address with DIFFERENT initialization parameters?
- Pattern: `CREATE2(salt=hash(owner))` is safe. `CREATE2(salt=nonce)` without binding owner → attacker deploys with their own owner at the victim's expected address.

### 4b. Pre-Deployment Fund Safety
- Can funds be sent to a counterfactual address before deployment?
- If yes: can anyone deploy the wallet at that address and drain the funds?
- Is there a race condition between fund deposit and wallet deployment?

### 4c. Re-Initialization Protection
- After deployment: can `initialize()` be called again?
- Is the initializer modifier (`initializer`/`reinitializer`) correctly applied?
- For proxy-based accounts: can the implementation be initialized separately from the proxy?

Tag: `[TRACE:factory_deploy → salt_binds_owner={YES/NO} → pre_deploy_funds={safe/vulnerable}]`

---

## Key Questions (must answer all)
1. Does `validateUserOp` correctly verify signatures against the operation hash including chain ID?
2. Can the paymaster be drained by operations that validate but fail to pay in `postOp`?
3. Are signature validation modules restricted to a trusted registry with access control?
4. Is the wallet's CREATE2 address bound to its initialization parameters (owner, config)?
5. Can session keys or scoped permissions be exceeded through calldata manipulation?

## Common False Positives
- **EntryPoint-enforced nonce**: If using standard EntryPoint nonce management → protocol-level nonce check may be redundant
- **Trusted module whitelist with timelock**: Module registry behind multisig + timelock → low risk of malicious module
- **Paymaster with prepaid deposits**: If paymaster requires pre-deposited balance (not deferred payment) → `postOp` failure doesn't lose funds
- **Standard factory with owner-bound salt**: `CREATE2` salt includes `keccak256(owner)` → counterfactual address is owner-specific

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: EntryPoint address omitted from CREATE2 salt lets attacker deploy wallet at victim's counterfactual address
  Where it hit: SmartAccount factory / wallet factory deploy function
  Severity: HIGH
  Source: Solodit (row_id 13685)
  Summary: The entrypoint address was excluded from address generation, so an attacker could deploy the counterfactual wallet using an arbitrary entrypoint while producing the same address. The attacker gains full control of the wallet and can steal pre-existing funds or change the owner. Fix: include the entrypoint in the CREATE2 salt.
  Map to: EntryPoint, ERC4337

- Pattern: EntryPoint address excluded from userOpHash enables cross-entrypoint replay attacks
  Where it hit: DeleGatorCore / EIP7702DeleGatorCore hash computation
  Severity: HIGH
  Source: Solodit (row_id 2035)
  Summary: The userOpHash did not include the EntryPoint address, so a valid signed operation could be replayed against a different EntryPoint contract. A proof of concept was provided showing successful cross-entrypoint replay. Fix: include the EntryPoint address in the hashing logic inside validateUserOp.
  Map to: UserOperation, validateUserOp, EntryPoint, ERC4337

- Pattern: Paymaster signature replayable across multiple UserOperations drains paymaster deposits
  Where it hit: VerifyingSingletonPaymaster.sol / validatePaymasterUserOp
  Severity: HIGH
  Source: Solodit (row_id 13683)
  Summary: The paymaster's off-chain signature was not invalidated after first use, allowing an attacker to replay it across multiple operations and drain the paymaster's deposited balance. A proof of concept using a MaliciousAccount was provided and verified. Fix: track used hashes with a boolean mapping inside validatePaymasterUserOp.
  Map to: Paymaster, validateUserOp, ERC4337

- Pattern: Paymaster does not account for gas cost of current transaction, users can withdraw before paying
  Where it hit: Paymaster / GasTank balance accounting
  Severity: HIGH
  Source: Solodit (row_id 405)
  Summary: The paymaster did not lock or account for gas owed by an in-flight user transaction, letting users withdraw their GasTank balance immediately after submitting an operation and before gas was settled. Users could consume gas without paying for it. Fix: block withdrawals for accounts with unpaid in-flight transactions.
  Map to: Paymaster, postOp, ERC4337

- Pattern: Zero-padded paymasterAndData field bypasses module guard checks
  Where it hit: NativeTokenLimitModule / PaymasterGuardModule
  Severity: HIGH
  Source: Solodit (row_id 2557)
  Summary: Passing a 52-byte all-zero paymasterAndData field caused the decoded paymaster address to be zero, and the modules' conditions failed to reject it because they lacked a non-zero address check. An attacker could submit such a UserOperation to bypass the paymaster guard and drain the account. Fix: add an explicit non-zero check on the decoded paymaster address in each module's if-condition.
  Map to: Paymaster, UserOperation, validateUserOp, ERC4337

- Pattern: Non-allowlisted paymaster passes validation phase and drains account's pre-approved balance
  Where it hit: Smart Wallet Permissions / permission contracts
  Severity: HIGH
  Source: Solodit (row_id 4328)
  Summary: The allowlist check for paymasters was performed during execution rather than during the validation phase, so a non-allowlisted paymaster could pass validatePaymasterUserOp and consume the account's pre-approved balance before the check ran and failed. Fix: move the paymaster allowlist check into the validation phase.
  Map to: Paymaster, validateUserOp, ERC4337

- Pattern: chainId missing from UserOperation hash enables cross-chain signature replay
  Where it hit: SmartAccount / UserOperation hash computation
  Severity: MEDIUM
  Source: Solodit (row_id 13678)
  Summary: The chainId was not included in the UserOperation hash, so a signed operation valid on one chain could be replayed on any other chain where the same smart contract account exists and the same verifyingSigner is configured. Fix: include the chainId in the UserOperation hash calculation.
  Map to: UserOperation, validateUserOp, ERC4337

- Pattern: 2D nonce batchId #0 shared between EntryPoint path and direct execTransaction causes collision
  Where it hit: SmartAccount.sol / execTransaction and validateUserOp
  Severity: MEDIUM
  Source: Solodit (row_id 13673)
  Summary: The protocol locked batchId #0 for EntryPoint use, but execTransaction imposed no such restriction. A direct call to execTransaction using batchId 0 would increment the same nonce counter, causing concurrent UserOperations routed through the EntryPoint to fail unexpectedly. Fix: require batchId != 0 inside execTransaction.
  Map to: UserOperation, validateUserOp, EntryPoint, ERC4337

- Pattern: ERC4337Factory salt does not bind owner address, enabling frontrun to steal funds
  Where it hit: ERC4337Factory.createAccount
  Severity: MEDIUM
  Source: Solodit (row_id 2928)
  Summary: When a salt smaller than 2^96 was provided, the factory did not validate that the owner address was encoded in the salt. An attacker could frontrun account creation with a different owner, deploying at the same deterministic address and gaining control of any funds already sent to that counterfactual address. Fix: strictly require the owner address in the first 160 bits of all salts.
  Map to: ERC4337, EntryPoint

- Pattern: postOp fee bypass via intentional revert allows user to execute operations without paying paymaster
  Where it hit: VersaVerifyingPaymaster / _postOp
  Severity: MEDIUM
  Source: Solodit (row_id 10318)
  Summary: When _postOp failed, the EntryPoint called it again in postOpReverted mode, but this second call also failed to charge the user. A user could intentionally trigger the revert path to complete execution while avoiding the gas fee, effectively draining the paymaster. Fix: enforce fee collection in all three postOp modes, including the postOpReverted path.
  Map to: Paymaster, postOp, ERC4337


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. UserOperation Validation | IF `validateUserOp` present | | Signature, nonce, return value |
| 2. Paymaster Validation | IF paymaster present | | Pre/post validation, payment token |
| 3. Signature Validation Modules | IF ERC-1271 / modules | | Delegation, session keys |
| 4. Factory and Initialization | IF wallet factory present | | Address binding, re-init |
