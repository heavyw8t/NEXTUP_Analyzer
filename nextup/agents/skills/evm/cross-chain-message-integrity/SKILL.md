---
name: "cross-chain-message-integrity"
description: "Type Thought-template (instantiate before use) - Trigger Pattern CROSS_CHAIN_MSG flag detected (protocol RECEIVES cross-chain messages)"
---

# Skill: Cross-Chain Message Integrity

> **Type**: Thought-template (instantiate before use)
> **Trigger Pattern**: CROSS_CHAIN_MSG flag detected (protocol RECEIVES cross-chain messages)
> **Inject Into**: Breadth agents, depth-external
> **Finding prefix**: `[CMI-N]`
> **Rules referenced**: R1, R2, R4, R8, R10

Covers: message endpoint authentication, peer/remote verification, replay protection, payload validation, and message ordering for bridge-receiving protocols.

This skill is SEPARATE from CROSS_CHAIN_TIMING (which covers stale state and latency arbitrage for L2 interactions). Use this skill when the protocol RECEIVES and PROCESSES inbound cross-chain messages. Use CROSS_CHAIN_TIMING when the protocol READS state synced across chains.

---

## Trigger Patterns
```
lzReceive|_ccipReceive|receiveWormholeMessages|onOFTReceived|
setPeer|setTrustedRemote|_nonblockingLzReceive|executeMessage|
_processMessageFrom|ILayerZeroReceiver|IAny2EVMMessageReceiver|
endpoint.*receive|bridge.*receive|relayer.*deliver|_lzReceive
```

---

## Step 1: Message Receiving Surface Inventory

For each function that processes inbound cross-chain messages:

| # | Function | Bridge Protocol | Source Auth? | Payload Validated? | State Modified | Access Control |
|---|----------|----------------|-------------|-------------------|----------------|---------------|

For each entry:
- What bridge/messaging protocol delivers the message?
- Can the function be called DIRECTLY by anyone, or only via the bridge endpoint?
- What state does the function modify based on message content? (mint, unlock, update, execute)

---

## Step 2: Endpoint Authentication Audit

For EACH message-receiving function:

### 2a. Caller Verification
| # | Check | Status | Location |
|---|-------|--------|----------|
| 1 | `msg.sender == endpoint/router` verified | YES/NO | {line} |
| 2 | Endpoint address immutable or admin-protected | YES/NO | {line} |
| 3 | Modifier checks the CORRECT address variable | YES/NO | {line} |

**Missing caller check → CRITICAL**: Anyone can fabricate message data and trigger mints/unlocks.

### 2b. Source Origin Verification
| # | Check | Status | Location |
|---|-------|--------|----------|
| 1 | Source chain ID validated against allowed set | YES/NO | {line} |
| 2 | Source sender validated against registered peer | YES/NO | {line} |
| 3 | BOTH checks present (chain AND sender) | YES/NO | {line} |

**Pattern**: Checks `_origin.srcEid` (chain) but not `_origin.sender` (peer) → accepts messages from ANY contract on allowed chains.

---

## Step 3: Peer Registry Security

For each function that configures trusted peers/remotes:

### 3a. Setter Access Control
| # | Check | Status | Location |
|---|-------|--------|----------|
| 1 | Access-controlled (onlyOwner/multisig/timelock) | YES/NO | {line} |
| 2 | Validates new peer is non-zero | YES/NO | {line} |
| 3 | Emits event for off-chain monitoring | YES/NO | {line} |
| 4 | Timelock/delay on peer changes | YES/NO | {line} |

### 3b. Peer Binding Completeness
- Peer mapping keyed by chain ID? One peer per chain, or multiple?
- Can in-flight messages from OLD peer be processed after peer change?
- Default state for unregistered chain: does `_origin.sender == peers[chainId]` pass when BOTH are zero?

### 3c. Cross-Chain Address Assumptions
- Does the protocol assume `address(X) on Chain A == address(X) on Chain B` means same owner?
- For CREATE-deployed contracts: different deployer nonce across chains → same address, different owner.
- For EOAs: private key owner is the same across chains (safe). For contracts: NOT guaranteed.

Tag: `[TRACE:setPeer(chain={X}) → access={check} → zero_check={YES/NO} → default_peer={value}]`

---

## Step 4: Replay Protection

### 4a. Message Uniqueness
| # | Check | Status | Location |
|---|-------|--------|----------|
| 1 | Each message processed exactly once | YES/NO | {line} |
| 2 | Replay check BEFORE state changes | YES/NO | {line} |
| 3 | Out-of-order messages handled | YES/NO | {line} |
| 4 | Sequence gaps handled gracefully | YES/NO | {line} |

### 4b. Cross-Chain Replay
- Message valid on chain A replayable on chain B?
- Payload includes destination chain ID AND destination address?
- Same contract deployed on N chains: message for chain A processable on chain B?

### 4c. Re-org Safety
- Source chain re-org: can previously-processed message be re-delivered with different nonce?
- Protocol responsibility vs bridge responsibility for re-org handling?

Tag: `[TRACE:message_nonce={N} → replay_check={method} → before_state_change={YES/NO}]`

---

## Step 5: Payload Validation

### 5a. Format Enforcement
- Payload decoded with explicit type checks? (`abi.decode` with expected types)
- Malformed payload handling: revert, silent skip, or partial decode?
- Payload length mismatch: can it cause incorrect ABI decoding of dynamic types?

### 5b. Value Bounds
For each decoded value:
- Bounds checks present? (amount ≤ supply cap, address ≠ zero, deadline not expired)
- Can source chain send payload causing overflow/underflow when processed?
- Addresses decoded from payload: treated as address on THIS chain or source chain?

### 5c. Arbitrary Execution
If message triggers execution of decoded calldata:
- Target restricted to known contracts?
- Function selector restricted to safe set?
- Can decoded calldata invoke `transferFrom`/`approve` on tokens the contract holds or has approvals for?

Tag: `[BOUNDARY:payload_amount={MAX} → decoded → processed_as={result}]`

---

## Step 6: Message Ordering and Delivery

### 6a. Ordering Dependencies
- Any messages depend on previous messages being processed first?
- Out-of-order arrival: state corruption or graceful handling?
- Queue/retry mechanism for failed deliveries?

### 6b. Blocked Message Recovery
- Failed message: retryable? By whom? With what gas limit?
- Permanently blocked message prevents subsequent messages? (head-of-line blocking)
- Admin mechanism to skip/clear blocked messages?
- Can attacker intentionally cause failure to block the queue?

Tag: `[TRACE:message_N_fails → message_N+1={blocked/processed} → recovery={mechanism}]`

---

## Key Questions (must answer all)
1. Can any receiving function be called directly without going through the bridge endpoint?
2. Are BOTH source chain AND source address validated against registered peers?
3. What is the default behavior for messages from an UNREGISTERED chain/peer?
4. Is each message processed exactly once with replay check BEFORE state changes?
5. Can decoded payload values cause overflow, underflow, or arbitrary execution?
6. What happens when delivery fails or messages arrive out of order?

## Common False Positives
- **Bridge-level replay**: Bridge protocol itself prevents replay AND protocol correctly verifies bridge auth → protocol-level replay may be unnecessary
- **Idempotent operations**: Protocol allows re-delivery by design (same result regardless of count) → not a replay vulnerability
- **Admin peer with timelock**: `setPeer` behind multisig + timelock → low unauthorized change risk
- **View-only consumption**: Message updates state also validated by other mechanisms (oracle bounds, rate limits) → bounded impact

## Instantiation Parameters
```
{CONTRACTS}           -- Contracts with message receiving functions
{BRIDGE_PROTOCOL}     -- Bridge/messaging protocol (LayerZero, CCIP, Wormhole, Axelar, Hyperlane)
{RECEIVE_FUNCTIONS}   -- Functions that process inbound messages
{PEER_SETTERS}        -- Functions that configure trusted peers/remotes
{STATE_MODIFIED}      -- State modified by message processing
```

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

> Source: candidates.jsonl (46 rows). Selected 8 findings across 5 distinct bug categories.
> Categories: chainId, sourceChain, cross_chain_replay, message_format, bridge_trust.

---

## Example 1 — chainId

*Severity*: HIGH
*Row*: 9167

*Summary*: Linea prover can set a forked chain's `chainId` as a constant in the circuit. The L1 verifier contract has no `chainId` public input, so it cannot distinguish canonical Linea block data from a forked chain's data. A malicious prover submits forked-chain data that passes ZK verification and manipulates L1 state.

*Why selected*: Clean example of a missing chain-identity check at the verification layer, not the message layer. Distinct from EIP-155 signature replay — the vector is ZK circuit parameterization.

---

## Example 2 — chainId

*Severity*: MEDIUM
*Row*: 2452

*Summary*: Strategy contract hard-codes `chainid = 80000` for Berachain. The correct mainnet chain ID is `80094`. Chain-specific logic (rate limits, fee tiers, reserve configs) silently uses the wrong branch for every Berachain transaction.

*Why selected*: Illustrates incorrect constant rather than missing check. Impact is logic misbranching rather than replay. Pairs with Example 1 to show both missing and wrong chain-ID handling.

---

## Example 3 — chainId

*Severity*: MEDIUM
*Row*: 14636

*Summary*: WormholeFacet uses `block.chainid` (EVM chain ID) for a Wormhole chain-ID check. Wormhole maintains its own chain-ID namespace. On non-EVM or Wormhole-specific chains the values do not match, causing the check to reject valid messages or accept messages destined for a different chain, risking funds sent to wrong-chain addresses.

*Why selected*: Cross-namespace chain-ID confusion — distinct from both wrong-constant and missing-check patterns. Relevant when protocols bridge between EVM and non-EVM chains via a protocol with its own chain registry.

---

## Example 4 — sourceChain

*Severity*: HIGH
*Row*: 7852

*Summary*: `_toeComposeReceiver` in Tapioca accepts `_srcChainSender` as a caller-supplied parameter. Modules handling `MSG_MARKET_REMOVE_ASSET` do not verify that `_srcChainSender` matches the actual LayerZero origin address. An attacker passes any victim address as `_srcChainSender` and executes `UsdoMarketReceiverModule` functions on behalf of that victim.

*Why selected*: Source-address spoofing via parameter, not via the bridge path. The bridge endpoint is called correctly; the vulnerability is in how the protocol forwards and validates the claimed origin within its own compose layer.

---

## Example 5 — sourceChain

*Severity*: HIGH
*Row*: 12843

*Summary*: XProvider's `onlySource` modifier validates that the cross-chain message sender is a trusted remote. However Connext's fast-path sets `msg.sender` to the zero address, and `trustedRemoteConnext[domain]` also returns zero for unregistered domains. Zero equals zero — so an attacker sending from an arbitrary chain passes the modifier and can corrupt vault allocations and XChainController state.

*Why selected*: Default-zero peer binding bypass. The modifier logic is structurally correct but the zero-address default collapses the security invariant. Canonical illustration of SKILL.md Step 3b "default state for unregistered chain."

---

## Example 6 — cross_chain_replay

*Severity*: HIGH
*Row*: 2961

*Summary*: Borrow signatures do not include `block.chainid` in the signed hash. A user signs a borrow on chain A; the same signature is valid on chain B where the same contract is deployed. An attacker replays the signature on chain B to borrow on behalf of the victim without new authorization.

*Why selected*: Direct cross-chain signature replay with clear fix (add chainId to hash). Textbook instance of SKILL.md Step 4b.

---

## Example 7 — cross_chain_replay

*Severity*: HIGH
*Row*: 16467

*Summary*: `postIncomingMessages` in `MessageProxyForSchain` calls `_callReceiverContract` — which hands control to a potentially attacker-controlled contract — before incrementing `incomingMessageCounter`. An attacker's receiver re-enters `postIncomingMessages` with the same message batch, causing the same cross-chain messages (e.g. a 1000 USDC transfer) to execute multiple times.

*Why selected*: Replay via reentrancy rather than signature. The bridge does not deduplicate delivery; the receiving contract's counter ordering is the sole guard. Illustrates that replay protection must precede all external calls.

---

## Example 8 — message_format

*Severity*: HIGH
*Row*: 1423

*Summary*: In a cross-chain liquidation flow, the LayerZero message payload reuses the `amount` field for both the seize amount (collateral transferred to liquidator) and the repay amount (debt cleared on the source chain). The destination chain decodes `amount` as the repay amount but the source chain encoded it as the seize amount, causing under- or over-repayment of the borrower's debt.

*Why selected*: Field-reuse encoding error — the message reaches the right endpoint with valid auth, but the payload semantics diverge across chains. Directly illustrates SKILL.md Step 5a format enforcement and Step 5b value bounds.

---

## Example 9 — bridge_trust

*Severity*: HIGH
*Row*: 8633

*Summary*: `AxiomV2GnosisHashiAmbHeaderVerifier._checkL1Broadcaster()` verifies that the Hashi `yaru` contract relayed the message but omits a check on `yaru.adapters()`. An attacker deploys a malicious contract that mimics the Hashi interface, calls `updateLatestPmmr()` through it, and stores arbitrary PMMRs. Any downstream proof verification that trusts stored PMMRs is compromised.

*Why selected*: Bridge trust-model bypass at the adapter-verification layer — the caller-is-endpoint check passes because the attacker supplies a conforming interface; the missing check is one level deeper (which adapters signed off). Illustrates that endpoint auth alone is insufficient when the bridge is multi-adapter.

---

## Coverage Matrix

| Category | Examples | Rows |
|---|---|---|
| chainId | 1, 2, 3 | 9167, 2452, 14636 |
| sourceChain | 4, 5 | 7852, 12843 |
| cross_chain_replay | 6, 7 | 2961, 16467 |
| message_format | 8 | 1423 |
| bridge_trust | 9 | 8633 |


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Message Receiving Surface Inventory | YES | | All receiving functions |
| 2. Endpoint Authentication Audit | YES | | Caller + source origin |
| 3. Peer Registry Security | IF configurable peers | | Setter access, binding, defaults |
| 4. Replay Protection | YES | | Uniqueness, cross-chain, re-org |
| 5. Payload Validation | YES | | Format, bounds, arbitrary execution |
| 6. Message Ordering and Delivery | IF ordered messages | | Dependencies, blocked recovery |
