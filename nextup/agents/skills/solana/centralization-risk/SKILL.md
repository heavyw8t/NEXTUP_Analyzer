---
name: "centralization-risk"
description: "Trigger Pattern Protocol has privileged authorities (upgrade authority, admin, operator, governance, multisig) - Inject Into Breadth agents (optional), depth-state-trace"
---

# CENTRALIZATION_RISK Skill (Solana)

> **Trigger Pattern**: Protocol has privileged authorities (upgrade authority, admin, operator, governance, multisig)
> **Inject Into**: Breadth agents (optional), depth-state-trace
> **Finding prefix**: `[CR-N]`
> **Rules referenced**: R2, R6, R9, R10, R13
> **Required**: NO (recommended when protocol has 3+ distinct privileged roles)

Covers: single points of failure, privilege escalation, program upgrade risk, external governance dependencies, emergency powers. On Solana, centralization risk has unique dimensions: BPFLoaderUpgradeable allows full program replacement, freeze authority can lock user token accounts, close authority can destroy accounts and their lamports, and PDA self-authority patterns can create hidden centralization.

---

## Step 1: Privilege Inventory

Enumerate ALL privileged instructions by scanning for signer checks against stored authority pubkeys:

| # | Instruction | Program | Authority/Signer | What It Controls | Impact If Abused |
|---|-------------|---------|------------------|------------------|-----------------|
| 1 | {ix_name} | {program} | {authority pubkey field} | {parameter/state} | {worst case} |

**Solana authority patterns to scan for**:
- `has_one = authority` / `has_one = admin` / `has_one = owner` in Anchor account constraints
- `require!(ctx.accounts.authority.key() == config.authority)` manual checks
- Signer constraints: `#[account(signer)]` or `Signer<'info>` combined with stored pubkey comparison
- `upgrade_authority` in program deploy config (BPFLoaderUpgradeable)
- `mint_authority` / `freeze_authority` / `close_authority` on SPL Token mints
- PDA-based authorities: programs that use their own PDA as authority for token mints or other programs

**Categorize each by impact**:
- **FUND_CONTROL**: Can move, lock, freeze, or close user token accounts/SOL
- **PARAMETER_CONTROL**: Can change fees, rates, thresholds, delays
- **OPERATIONAL_CONTROL**: Can pause, unpause, add/remove validators/pools/markets
- **UPGRADE_CONTROL**: Can replace program logic entirely via BPFLoaderUpgradeable
- **MINT_CONTROL**: Can mint new tokens (SPL Token mint authority)

---

## Step 2: Role Hierarchy and Separation

Map the role hierarchy:

| Role | Stored In (Account) | Granted By | Can Grant Others? | Revocable? | Timelock? |
|------|---------------------|-----------|-------------------|-----------|-----------|
| {role} | {config PDA / mint} | {grantor instruction} | YES/NO | YES/NO | YES/NO ({mechanism}) |

### Solana-Specific Hierarchy Checks

- [ ] Are FUND_CONTROL and UPGRADE_CONTROL held by different keys?
- [ ] Does any single keypair have both PARAMETER_CONTROL and FUND_CONTROL?
- [ ] Is the upgrade authority a multisig (Squads) or DAO (Realms), not a single EOA?
- [ ] Are authority transfers behind timelocks (Clockwork scheduler, Squads time-lock vault)?
- [ ] Can roles be revoked? Does revocation require the role-holder's cooperation?
- [ ] Is there a two-step authority transfer pattern? (propose new authority -> accept authority)

### Program Upgrade Authority Analysis (CRITICAL)

| Program | Upgrade Authority | Type | Immutable? | Risk Level |
|---------|------------------|------|-----------|------------|
| {program_id} | {authority pubkey} | EOA / Squads / Realms / Revoked | YES/NO | {assessment} |

**Check via**: `solana program show <program_id>` or read BPFLoaderUpgradeable programdata account.

**Risk levels**:
- **Revoked (immutable)**: No upgrade risk. Verify: `upgrade_authority: None`
- **Realms DAO**: Low risk if DAO has sufficient voter distribution and timelock
- **Squads multisig (3/5+)**: Low-Medium risk. Check: threshold, signer count, timelock
- **Squads multisig (2/3 or lower)**: Medium risk. Collusion of 2 signers can replace program
- **Single EOA**: **CRITICAL** risk. One compromised key replaces entire program

---

## Step 3: Single Points of Failure

For each privileged role:

| Role | Key Compromise Impact | Mitigation | Residual Risk |
|------|----------------------|------------|---------------|
| {role} | {what attacker can do} | {multisig? timelock? immutable?} | {what remains} |

### Solana-Specific SPOF Analysis

| Risk | Description | Severity |
|------|-------------|----------|
| **Upgrade authority compromise** | Attacker replaces program with malicious version. ALL user funds at risk. | CRITICAL if single EOA, HIGH if multisig without timelock |
| **Freeze authority active** | Authority can freeze any user's token account. Users cannot transfer, sell, or withdraw. | HIGH if single key, MEDIUM if multisig |
| **Close authority on user accounts** | Authority can close user PDAs, reclaiming lamports and destroying state. | HIGH - user data and rent-exempt lamports lost |
| **Mint authority active** | Authority can mint unlimited tokens, diluting all holders. | HIGH if supply-sensitive protocol |
| **PDA self-authority** | Program uses its own PDA as authority - program upgrade changes PDA behavior. Upgrade authority effectively controls all PDA-authorized actions. | Severity inherits from upgrade authority risk |

**Severity assessment**:
- Single EOA with FUND_CONTROL or UPGRADE_CONTROL -> **HIGH** centralization risk (minimum)
- Multisig with FUND_CONTROL but no timelock -> **MEDIUM**
- Multisig + timelock with FUND_CONTROL -> **LOW** (but document)
- Immutable program + no freeze/close/mint authority -> **INFO**

---

## Step 4: External Governance Dependencies

Identify parameters or behaviors controlled by EXTERNAL governance:

| Dependency | External Entity | What They Control | Protocol Impact If Changed | Notification? |
|------------|----------------|-------------------|---------------------------|---------------|
| {dep} | {entity} | {parameter/behavior} | {impact on this protocol} | YES/NO |

**Solana-specific external governance**:
- **Pyth/Switchboard oracle governance**: Can change feed configurations, add/remove publishers
- **SPL Governance (Realms)**: External DAO decisions affecting shared infrastructure
- **Liquid staking governance**: Protocol parameter changes affecting staked assets
- **DEX aggregator routing changes**: If protocol depends on external routing for swaps, routing/fee changes
- **Wormhole guardian set rotation**: Can affect cross-chain message validation

**Check**:
- Can external governance changes break protocol invariants?
- Does the protocol have circuit breakers or fallback paths for external changes?
- Are external governance timelines aligned with this protocol's operational timelines?
- **Does the protocol verify external program IDs at CPI call sites?** (If not, external program upgrade = arbitrary code execution within protocol context)

---

## Step 5: Emergency Powers

Document emergency/pause capabilities:

| Emergency Function | Who Can Call | What It Affects | Recovery Path | Time to Recover |
|-------------------|-------------|-----------------|---------------|-----------------|
| {instruction} | {authority} | {scope} | {how to resume} | {estimate} |

### Solana Emergency Patterns

| Pattern | Description | Risk |
|---------|-------------|------|
| **Global pause flag** | Config account has `paused: bool`. All user instructions check it. | Standard - check: can users emergency-withdraw when paused? |
| **Account freeze via SPL Token** | Freeze authority freezes user token accounts. | HIGH if no thaw path independent of authority |
| **Program close** | BPFLoaderUpgradeable allows closing the program entirely. All CPI calls to it fail. | CRITICAL if user funds locked in PDAs |
| **Account close cascade** | Authority closes critical config/state accounts. Program instructions fail due to missing accounts. | HIGH - effectively a permanent pause |

**Check**:
- [ ] Can pausing strand user funds permanently? (Rule 9 - stranded asset severity floor)
- [ ] Is there a maximum pause duration enforced on-chain?
- [ ] Can users exit during pause (emergency withdraw instruction)?
- [ ] If program is closed: can PDAs still be accessed? (No - PDA authority is gone)
- [ ] If no exit during pause -> apply Rule 9 (stranded asset severity floor: minimum MEDIUM)

---

## Step 6: Authority Revocation Assessment

For each authority type, assess revocation status and path:

| Authority | Current State | Revocation Path | Should Be Revoked? | Risk If Not Revoked |
|-----------|--------------|-----------------|-------------------|-------------------|
| Upgrade authority | {active/revoked} | `solana program set-upgrade-authority --final` | {assessment} | {risk level} |
| Mint authority | {active/revoked} | `spl-token authorize <mint> mint --disable` | {assessment} | {risk level} |
| Freeze authority | {active/revoked} | `spl-token authorize <mint> freeze --disable` | {assessment} | {risk level} |
| Close authority (per account type) | {active/none} | {code change required} | {assessment} | {risk level} |

**Rule 13 check**: Is the authority retention documented? If the protocol claims to be "decentralized" or "trustless" but retains upgrade/freeze/mint authority, apply the 5-question test:
1. Who is harmed by this authority retention?
2. Can affected users avoid the harm?
3. Is the authority retention documented in protocol docs?
4. Could the protocol achieve the same goal without this authority?
5. Does the program fulfill its stated trustlessness completely?

---

## Output Schema

```markdown
## Finding [CR-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: check1,2,3,4,5,6 | skip(reason) | uncertain
**Severity**: Critical/High/Medium/Low/Info
**Location**: program_id or instruction name

**Centralization Type**: FUND_CONTROL / PARAMETER_CONTROL / OPERATIONAL_CONTROL / UPGRADE_CONTROL / MINT_CONTROL
**Affected Role**: {authority_name}
**Mitigation Present**: {Squads multisig / Realms DAO / Clockwork timelock / Immutable / NONE}

**Description**: What is wrong
**Impact**: What can happen if authority is compromised or acts maliciously
**Recommendation**: How to mitigate (add timelock, revoke authority, use multisig, separate roles)
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

---

- Pattern: Multisig creation uses an unauthenticated `create_key` PDA seed, allowing an attacker to front-run the victim's `create_multisig` transaction and substitute their own members list, gaining threshold control over the multisig vault.
  Where it hit: Squads protocol, `create_multisig` instruction
  Severity: HIGH
  Source: Solodit (row_id 9973)
  Summary: The `create_multisig` instruction derives the multisig PDA from a `create_key` that any signer can supply without proof of ownership. An attacker watches the mempool, front-runs with the victim's `create_key` and a modified members list containing attacker-controlled keys, then drains vault funds once accumulation reaches critical mass. Fix: require the `create_key` account to be a signer of the `create_multisig` instruction so only the key-owner can create the corresponding multisig.
  Map to: multisig, authority_rotation

---

- Pattern: Init instruction accepts any arbitrary signer as `super_admin` with no validation against the mint authority, so any caller can seize super-admin rights and disable the whitelist.
  Where it hit: Unnamed SPL token protocol, initialization instruction
  Severity: MEDIUM
  Source: Solodit (row_id 286)
  Summary: The init instruction stores the transaction signer directly as `super_admin` without checking whether that signer is the mint authority. An attacker can invoke init before the legitimate deployer and claim super-admin, then disable whitelist controls at zero cost. Fix: constrain `super_admin` to the mint authority during initialization.
  Map to: admin_authority, upgrade_authority

---

- Pattern: `InitializeGlobalState` allows any user to set `super_admin` and `admin` to arbitrary values; `admin` is not required to sign, enabling fake global state accounts that steal tokens or DoS legitimate admins.
  Where it hit: Unnamed Solana program, `InitializeGlobalState` instruction
  Severity: MEDIUM
  Source: Solodit (row_id 287)
  Summary: There are no constraints preventing a malicious actor from calling `InitializeGlobalState` with attacker-controlled pubkeys for `super_admin` and `admin`. The instruction also does not require `admin` to sign, so fake oracle and global state accounts can be created with adversarial parameters. Fix: restrict `super_admin` to a hardcoded trusted address, require `admin` to sign, and tighten `global_state` PDA derivation.
  Map to: admin_authority, upgrade_authority

---

- Pattern: TSS authority update resets the authorized signer key but does not reset the nonce counter, so previously authorized signatures remain valid and can be replayed after a key rotation.
  Where it hit: ZetaChain Solana bridge, TSS address update function
  Severity: MEDIUM
  Source: Solodit (row_id 1584)
  Summary: When the authority rotates the TSS address from key A to key B, the nonce is not reset to zero. Any old signature from key A that was authorized under a prior nonce is still accepted, enabling replay of unauthorized transactions. Fix: atomically reset the nonce to 0 whenever the TSS address is updated. The protocol team resolved this in their patch.
  Map to: authority_rotation, set_authority

---

- Pattern: Protocol `lp_wallet` address is settable without validation or timelock, allowing the admin to redirect lamport withdrawals to an arbitrary account.
  Where it hit: Entangle protocol, wallet initialization / round management
  Severity: MEDIUM
  Source: Solodit (row_id 5951)
  Summary: The `lp_wallet` field is written without constraining it to a multisig or trusted address. An admin (or a compromised key) can point `lp_wallet` at any account before the next withdrawal, diverting all outgoing SOL. Additionally, new rounds do not enforce `sol_deposited = 0`, producing inconsistent accounting. Fix: enforce a trusted multisig constant for `lp_wallet` and initialize `sol_deposited` to zero on every new round.
  Map to: set_authority, admin_authority

---

- Pattern: `create_oracle` and `create_pool` instructions carry no permission control, so any caller can create oracle or pool accounts with attacker-set parameters and manipulate prices or steal funds.
  Where it hit: WOOFi Solana, `create_oracle` / `create_pool` instructions
  Severity: MEDIUM
  Source: Solodit (row_id 4398)
  Summary: Both instructions accept arbitrary callers because the `admin` field in the context is not constrained to `wooconfig.authority`. Attackers can insert malicious oracles or pools before the legitimate admin, poisoning price feeds. Fix: add a `has_one = authority` constraint (or equivalent check) binding oracle/pool creation to `wooconfig.authority`.
  Map to: admin_authority, set_authority

---

- Pattern: Token mint accepted at initialization without checking for an active `freeze_authority`, so a freeze-authority holder can later freeze the protocol's escrow accounts, causing a permanent denial of service and fund lock.
  Where it hit: ONFT protocol (`init_ONft`), lending collateral validation
  Severity: HIGH / MEDIUM
  Source: Solodit (row_id 2980, corroborated by row_id 3941 and row_id 7405)
  Summary: The `init_ONft` instruction stores a `token_mint` without asserting `freeze_authority == None`. If the freeze authority is later exercised on `token_escrow`, all token transfers to that account fail, rendering the ONFT unusable (DoS) or permanently locking collateral in lending pools. Fix: during initialization, reject any mint whose `freeze_authority` is not `None`; alternatively, log a warning and let the admin allowlist only verified mints.
  Map to: set_authority, admin_authority, authority_rotation


## Step Execution Checklist (MANDATORY)

| Step | Required | Completed? | Notes |
|------|----------|------------|-------|
| 1. Privilege Inventory (all instructions with authority checks) | YES | | |
| 2. Role Hierarchy and Separation | YES | | |
| 3. Single Points of Failure (per role) | YES | | |
| 4. External Governance Dependencies | YES | | |
| 5. Emergency Powers and Recovery Paths | YES | | |
| 6. Authority Revocation Assessment | YES | | |

### Cross-Reference Markers

**After Step 1**: Cross-reference with ACCOUNT_VALIDATION skill - are all authority checks properly validated (not just signer, but signer == stored authority)?

**After Step 2**: If upgrade authority is single EOA -> immediate finding (minimum HIGH).

**After Step 3**: If PDA self-authority pattern detected, severity inherits from upgrade authority assessment.

**After Step 5**: If no emergency withdraw exists AND pause is possible -> Rule 9 stranded asset finding.

**After Step 6**: If protocol claims trustlessness but retains mutable authorities -> Rule 13 anti-normalization finding.
