---
name: "layerzero-integration"
description: "Protocol Type Trigger layerzero_integration (detected when recon finds OFT|ONFT|OApp|ILayerZeroEndpointV2|lzReceive|_lzSend|setPeer|setTrustedRemoteAddress|SendParam|MessagingFee - protocol USES LayerZero for cross-chain messaging)"
---

# Injectable Skill: LayerZero Integration Security

> **Protocol Type Trigger**: `layerzero_integration` (detected when recon finds: `OFT`, `ONFT`, `OApp`, `ILayerZeroEndpointV2`, `ILayerZeroEndpoint`, `lzReceive`, `_lzSend`, `setPeer`, `setTrustedRemoteAddress`, `SendParam`, `MessagingFee`, `Origin`, `MessagingReceipt`, `OFTCore`, `IOFT` - AND the protocol sends/receives cross-chain messages via LayerZero, not implements the endpoint itself)
> **Inject Into**: Breadth agents, depth-external, depth-state-trace, depth-edge-case
> **Language**: EVM only
> **Finding prefix**: `[LZ-N]`
> **Relationship to CROSS_CHAIN_MESSAGE_INTEGRITY**: That skill covers generic cross-chain message receive patterns. This skill covers LayerZero-specific integration patterns (OFT, OApp, DVN, Executor, gas, peer config). Both may be active.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-external (peer configuration, endpoint trust, chain identity)
- Section 2: depth-state-trace (message ordering, nonce handling, retry/revert)
- Section 3: depth-token-flow + depth-edge-case (OFT supply, shared/local decimals, dust)
- Section 4: depth-external (gas estimation, executor trust, DVN configuration)
- Section 5: depth-edge-case (compose messages, airdrop abuse, message size)

## When This Skill Activates

Recon detects that the protocol integrates with LayerZero for cross-chain messaging — either as an OFT/ONFT (Omnichain Fungible/Non-Fungible Token), an OApp (Omnichain Application), or a contract that sends/receives arbitrary cross-chain messages via LayerZero endpoints.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `layerzero`, `OApp`, `OFT`, `lzSend`, `lzReceive`, `peer`, `nonce`, `endpoint`, `composer`, `options`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[LZ-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Peer Configuration and Chain Identity

LayerZero V2 uses a peer mapping (`eid → bytes32 address`) to authenticate cross-chain messages. Misconfiguration is the #1 source of LayerZero integration bugs in audit contests.

### 1a. Peer Validation on Receive

- Does `_lzReceive()` validate that the message originates from a configured peer? OApp base handles this, but custom overrides may skip it.
- If the contract overrides `_lzReceive()` directly: does it check `_origin.sender == peers[_origin.srcEid]`?
- Can an attacker send messages from an unconfigured chain (where no peer is set)? Does `peers[eid] == bytes32(0)` pass or fail the check?
- **Real finding pattern**: Protocols that check `peers[eid] != address(0)` but don't verify the sender matches the peer — any address on the source chain can send messages.

### 1b. Peer Setting and Admin Control

- Who can call `setPeer()` / `setTrustedRemoteAddress()`? Is it owner-only or governed?
- Can a compromised admin redirect peers to malicious contracts, enabling unlimited minting or state corruption on the receiving chain?
- Is there a timelock or multi-sig on peer changes? A peer change takes effect immediately — no pending period.
- **Real finding pattern**: Protocol sets peer on chain A but forgets chain B. Attacker deploys a contract at the expected address on chain B (or uses CREATE2 to precompute the address).

### 1c. Chain ID (EID) Validation

- Does the protocol hardcode expected endpoint IDs (eids), or does it accept messages from any chain?
- If messages from unknown chains are processed: can an attacker deploy on a new chain and send malicious messages?
- For OFTs: is the token supply assumption valid across all configured chains? (Total supply = sum of all chain supplies)

### 1d. Gas Griefing / Channel Blocking

- Can a user control the gas limit forwarded to the destination `_lzReceive()`? If gas is user-supplied and no minimum is enforced, an attacker can pass 1 wei of gas, causing `_lzReceive()` to revert.
- **Real finding pattern (C4: Tapioca #1207, Maia #333)**: `callOutAndBridge()` encodes user-supplied `GasParams` into adapter params without validation. Attacker sends with `GasParams(0,0)`. `_lzReceive()` runs out of gas before `NonblockingLzApp`'s try/catch can store the failure (EIP-150 63/64 rule). Channel permanently blocked.
- **Real finding pattern (LZ V2 Checklist: Critical)**: Protocol doesn't set `enforcedOptions`. Anyone can execute a delivered message with `options=(gasLimit=1)`. Nonce consumed but logic never executes — permanent state divergence.
- Does the protocol use `setMinDstGas()` (V1) or `enforcedOptions` (V2) to enforce minimum gas per message type?

Tag: `[TRACE:peer_validation={OApp_base/custom/NONE} → peer_admin={owner/governance/timelock} → eid_restricted={YES/NO} → min_gas_enforced={YES/NO}]`

---

## 2. Message Ordering, Nonces, and Failure Handling

### 2a. Message Ordering Guarantees

- LayerZero V2 provides ordered delivery per (srcEid, sender) channel by default, but protocols can opt into unordered delivery.
- Does the protocol depend on message ordering? If yes: is ordered delivery enforced (default in OApp)?
- If the protocol uses `OAppOptionsType3` or custom options: can message ordering be overridden?
- **Real finding pattern**: Protocol assumes A arrives before B, but with unordered channels or executor retries, B can arrive first, breaking state machine transitions.

### 2b. Failed Message Handling (lzReceive Revert)

- If `_lzReceive()` reverts: LayerZero V2 stores the message hash in a `failedMessages` mapping. Anyone can retry via `lzReceive()` or clear via `nilify()`.
- Does the protocol handle retried messages correctly? A retried message executes with CURRENT state, not the state at original send time.
- Can state changes between initial failure and retry cause unexpected behavior? (e.g., price moved, positions liquidated, admin changed parameters)
- **Real finding pattern**: Protocol processes partial state in `_lzReceive`, reverts mid-way. On retry, the partial state is already applied, leading to double-processing.
- Does the protocol implement `_blockingLzReceive()` or similar? Blocking mode prevents subsequent messages until the failed one is resolved — can this be exploited to permanently block the channel?
- **Real finding pattern (LZ V2 Checklist: Critical)**: In ordered delivery mode, if any message in sequence reverts, ALL subsequent messages with higher nonces are permanently blocked. Only `skip()` (admin action) can unblock, losing the skipped message. Attacker crafts a message that triggers revert in `_lzReceive()` — entire ordered channel halts indefinitely.

### 2c. Nonce Management

- LayerZero V2 manages nonces internally. Does the protocol maintain its own nonce tracking on top?
- If yes: can desynchronization between LZ nonces and protocol nonces block messages or allow replay?
- For V1 integrations: `ILayerZeroEndpoint.retryPayload()` uses stored payloads — can an attacker front-run retry with a malicious payload?

Tag: `[TRACE:ordering={ordered/unordered} → revert_handling={retry_safe/double_process_risk/blocking} → nonce_sync={LZ_only/protocol_tracked}]`

---

## 3. OFT Token Supply and Decimal Handling

If the protocol uses OFT (Omnichain Fungible Token) or wraps tokens cross-chain:

### 3a. Supply Conservation

- OFT uses a burn-on-source/mint-on-destination model. Is total supply conserved across chains?
- On the source chain: are tokens burned or locked? If locked: does the lock contract hold sufficient tokens for all outstanding cross-chain balances?
- Can an attacker mint tokens on chain B without burning on chain A? (Requires peer misconfiguration or missing validation in `_lzReceive`)
- **Real finding pattern**: Protocol mints on receive but doesn't verify the `amountLD` against what was burned on the source. A malicious peer can inflate the amount.

### 3b. Shared vs Local Decimals

- OFT uses `sharedDecimals` (typically 6) for cross-chain transfers, while `localDecimals` matches the token's actual decimals on each chain.
- Conversion: `amountSD = amountLD / (10 ** (localDecimals - sharedDecimals))` — this TRUNCATES. The dust (remainder) stays on the source chain.
- **Real finding pattern**: Protocol hardcodes `sharedDecimals = 6` but deploys a token with 8 decimals on one chain and 18 on another. Users lose up to `10^(localDecimals - sharedDecimals) - 1` wei per transfer.
- Does the protocol handle the dust correctly? Is it returned to the sender, burned, or silently lost?
- Does `_debitView()` correctly compute the amount after dust removal? Overriding `_debit()` without matching `_debitView()` causes quote mismatches.

### 3c. Credit and Debit Overrides

- If the protocol overrides `_debit()` or `_credit()`: do the overrides maintain the burn/mint invariant?
- Can a fee-on-transfer token break the OFT accounting? (Source debits X, destination credits X, but actual tokens transferred = X - fee)
- If the protocol adds transfer fees in `_debit()`: is the fee-adjusted amount correctly encoded in the cross-chain message?
- **Real finding pattern (Ackee H-1)**: `_debitFrom(address _from, ...)` does not verify `msg.sender` is authorized to spend tokens on behalf of `_from`. Attacker calls the OFT bridge specifying a victim's address as `_from` — victim's tokens are burned and minted to attacker on destination.
- **Real finding pattern (LZ V2 Checklist: Critical)**: When `sharedDecimals == localDecimals`, `_toSD()` casts to `uint64` without magnitude reduction. Any amount exceeding `uint64.max` (~18.4e18) silently truncates. Source burns the full amount, destination mints the truncated value — permanent token loss.
- **Real finding pattern (OpenZeppelin Across H-01)**: `OFTAdapter._debit()` assumes lossless transfers. For fee-on-transfer tokens, the adapter receives fewer tokens than recorded. Cross-chain message claims original amount. Destination mints more than the adapter holds — protocol insolvency over time.

Tag: `[TRACE:supply_model={burn_mint/lock_mint} → shared_decimals={value} → dust_handling={return/burn/lost} → debit_credit_overridden={YES/NO}]`

---

## 4. Gas Estimation, Executor, and DVN Configuration

### 4a. Gas Estimation for lzReceive

- Does the protocol use `_estimateFees()` / `MessagingFee` to estimate destination gas?
- Is the gas estimate sufficient for the `_lzReceive()` execution? If underestimated: the message will revert on destination, entering the failed messages queue.
- **Real finding pattern**: Protocol estimates gas for a simple token mint, but `_lzReceive()` also updates state, emits events, and makes external calls. The gas estimate is too low, causing all cross-chain transfers to fail.
- Does the gas estimate account for varying gas costs across chains? (L2s have different gas models)
- Can an attacker force high gas consumption in `_lzReceive()` to make the message undeliverable? (Gas griefing via large payloads or state-dependent loops)

### 4b. Executor and DVN Trust

- Which executor and DVN (Decentralized Verifier Network) configuration does the protocol use?
- If using default LZ executor: the protocol trusts LayerZero's default infrastructure. Is this acceptable for the protocol's security model?
- If using custom DVN: who controls the DVN? Can a compromised DVN forge message verification?
- **Real finding pattern**: Protocol uses a single required DVN with no optional DVNs. If that DVN is compromised or goes offline, all cross-chain messaging stops or becomes forgeable.

### 4c. Extra Options and Airdrop

- Does the protocol use `_addExecutorLzReceiveOption()` or `_addExecutorAirdropOption()`?
- If airdrop (native gas on destination): can an attacker specify excessive airdrop amounts to drain the executor's balance?
- Are extra options validated? Can a user inject malicious options that alter execution behavior?

Tag: `[TRACE:gas_estimation={static/dynamic/user_provided} → executor={default/custom} → dvn_count={required_N/optional_N} → airdrop_used={YES/NO}]`

---

## 5. Composed Messages and Advanced Patterns

### 5a. Compose Messages (lzCompose)

- LayerZero V2 supports composed messages: `_lzReceive()` stores a compose message, then the endpoint calls `lzCompose()` on the target.
- If the protocol uses compose: is the compose handler authenticated? (`msg.sender` must be the endpoint, `_from` must be the OApp)
- Can the compose message be replayed? (Endpoint prevents this, but custom compose handlers may not)
- **Real finding pattern**: Protocol stores compose data in `_lzReceive()` but doesn't clear it after `lzCompose()` executes. A retry of the failed receive message re-stores the compose, triggering double execution.

### 5b. Rate Limiting and Throttling

- Does the protocol implement rate limiting on cross-chain transfers? (`RateLimiter` is an OFT extension)
- If rate-limited: can an attacker fill the rate limit from a cheap chain, blocking legitimate transfers on an expensive chain?
- Is the rate limit per-chain or global? Per-chain limits can be bypassed by spreading across chains.

### 5c. Message Size and Payload Validation

- Is the `_lzReceive()` payload validated for expected length and format?
- Can an oversized or malformed payload cause unexpected behavior (out-of-bounds reads, revert, gas griefing)?
- For OFT: does the protocol validate the `SendParam` struct fields? (e.g., `minAmountLD` should be <= `amountLD`)

Tag: `[TRACE:compose_used={YES/NO} → compose_replay_safe={YES/NO} → rate_limited={YES/NO/per_chain/global} → payload_validated={YES/NO}]`

---

## Common False Positives

- **Vanilla OApp/OFT with no overrides**: If the protocol uses LayerZero's OApp/OFT base contracts without overriding `_lzReceive`, `_debit`, `_credit`, or `setPeer`, most integration bugs don't apply — the base contracts handle peer validation, nonce management, and decimal conversion correctly
- **Single-chain deployment with bridge**: If the protocol only deploys on one chain and uses LZ only for bridging a token (not for state sync), message ordering and compose concerns are minimal
- **Read-only cross-chain queries**: If the protocol only reads cross-chain state (via LZ Read or similar) without executing state changes, receive-side vulnerabilities don't apply
- **Admin-controlled peer with timelock**: If setPeer is behind a timelock + multi-sig, peer manipulation attacks require governance compromise (centralization risk, not integration bug)

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Peer Validation on Receive | YES | | _lzReceive checks, sender match |
| 1b. Peer Setting Admin | YES | | setPeer access control, timelock |
| 1c. Chain ID Restriction | YES | | EID whitelist, unknown chains |
| 2a. Message Ordering | IF state-dependent | | Ordered vs unordered, assumptions |
| 2b. Failed Message Handling | YES | | Retry safety, blocking, state drift |
| 2c. Nonce Management | IF protocol tracks nonces | | Sync with LZ nonces |
| 3a. Supply Conservation | IF OFT/token bridge | | Burn/lock invariant, amount validation |
| 3b. Shared vs Local Decimals | IF OFT | | Truncation, dust, sharedDecimals value |
| 3c. Credit/Debit Overrides | IF overridden | | Fee-on-transfer, invariant maintenance |
| 4a. Gas Estimation | YES | | Sufficient for _lzReceive, cross-chain variance |
| 4b. Executor/DVN Trust | YES | | Default vs custom, single DVN risk |
| 4c. Extra Options/Airdrop | IF used | | Airdrop drain, option injection |
| 5a. Compose Messages | IF lzCompose used | | Auth, replay, clear-after-use |
| 5b. Rate Limiting | IF RateLimiter used | | Per-chain vs global, cross-chain grief |
| 5c. Payload Validation | YES | | Length, format, malformed handling |
