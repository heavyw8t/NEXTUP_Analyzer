---
name: "network-protocol-security"
description: "Trigger Socket/network operations detected - Network message parsing, protocol handling, and DoS resistance audit"
---

# Skill: NETWORK_PROTOCOL_SECURITY

> **Trigger**: Socket operations, message parsing, serialization/deserialization detected
> **Covers**: Message parsing vulnerabilities, DoS vectors, protocol confusion, TLS handling
> **Required**: YES when network I/O operations detected

## Trigger Patterns

```
socket|connect|bind|listen|accept|recv|send|read\(|write\(|SSL_|TLS_|htons|ntohs|serialize|deserialize|parse.*message|message.*handler
```

## Reasoning Template

### Step 1: Message Handler Inventory

Enumerate ALL network message types and their handlers:

| # | Message Type | Handler Function | Input Validation | Max Size Check | File:Line |
|---|-------------|-----------------|-----------------|---------------|-----------|

### Step 2: Input Validation Audit

For each message handler:
- [ ] Is message length validated before processing?
- [ ] Are all length fields bounds-checked? (attacker can send length=0xFFFFFFFF)
- [ ] Are nested structures validated recursively?
- [ ] Is there a maximum nesting depth to prevent stack overflow?
- [ ] Are string fields null-terminated or length-prefixed with validation?

### Step 3: Parsing Vulnerability Analysis

For each deserialization/parsing function:

| # | Parser | Input Type | Overflow Risk | OOB Read Risk | Format Confusion | File:Line |
|---|--------|-----------|-------------|--------------|-----------------|-----------|

**Check**:
- Integer overflow in length calculation (e.g., `count * sizeof(Element)` overflow → undersized buffer)
- Out-of-bounds read when parsing (reading past message boundary)
- Type confusion (message type field says X but content is Y)
- Unterminated loop in recursive parsing

### Step 4: DoS Resistance

For each network-facing function:

| # | Function | Can Slow Client Block? | Max Processing Time | Resource Limit | Amplification? |
|---|----------|----------------------|--------------------:|----------------|---------------|

**Vectors**:
- **Slowloris**: Slow sending, holding connections open
- **Large message**: Single huge message consuming memory
- **Many small messages**: Flooding with valid but useless messages
- **CPU exhaustion**: Messages triggering expensive computation (crypto operations, complex parsing)
- **Memory exhaustion**: Messages causing allocation without limit

### Step 5: TLS/Authentication Handling

If TLS is used:
- [ ] Is certificate validation enabled? (not SSL_CTX_set_verify with callback that returns 1)
- [ ] Is hostname verification performed?
- [ ] Are deprecated protocols disabled? (SSLv3, TLS 1.0, TLS 1.1)
- [ ] Are weak cipher suites disabled?
- [ ] Is certificate pinning used where appropriate?

### Step 6: Protocol State Machine

Map the connection state machine:
- [ ] Can messages be sent out of order? (e.g., data before handshake)
- [ ] Are all state transitions validated?
- [ ] Can a malformed message leave the state machine in an inconsistent state?

### Output Format
Use [NETPROTO-N] finding IDs. Severity: RCE via parsing → CRITICAL. DoS → MEDIUM/HIGH. Missing cert validation → HIGH.
