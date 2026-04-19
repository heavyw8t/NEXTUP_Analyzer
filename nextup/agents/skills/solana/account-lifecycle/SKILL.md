---
name: "account-lifecycle"
description: "Trigger Pattern ACCOUNT_CLOSING flag detected (close/CloseAccount usage) - Inject Into Breadth agents, depth agents"
---

# ACCOUNT_LIFECYCLE Skill

> **Trigger Pattern**: ACCOUNT_CLOSING flag detected (close/CloseAccount usage)
> **Inject Into**: Breadth agents, depth agents
> **Finding prefix**: `[AL-N]`
> **Rules referenced**: S4, R9

For every account close operation in the Solana program:

## 1. Close Operation Inventory

List all account closing operations:

| # | Instruction | Account Closed | Close Method | Lamport Recipient | Location |
|---|------------|---------------|-------------|-------------------|----------|
| 1 | {ix} | {account} | Anchor `close` / manual | {recipient} | {file:line} |

## 2. Close Completeness

For each close operation, verify ALL steps:

| Close Op | Data Zeroed? | Lamports Transferred? | Discriminator Set to CLOSED? | Owner Transferred to System? |
|----------|-------------|----------------------|-----------------------------|-----------------------------|
| {op} | YES/NO | YES/NO | YES/NO | YES/NO |

**Anchor `close`**: Handles all 4 steps automatically. Manual closing MUST do all 4.
**Missing step impact**:
- Data not zeroed → residual data readable by other programs
- Lamports not fully transferred → rent-exempt lamports stranded (Rule 9)
- Discriminator not set → account can be "reopened" with stale type
- Owner not transferred → program still has authority over closed account

## 3. Revival Attack Analysis (S4 - CRITICAL)

For each close operation:

| Close Op | Same-Tx Refund Possible? | Revival Guard? | Attack Sequence |
|----------|------------------------|---------------|-----------------|
| {op} | YES/NO | YES/NO | {if YES: describe} |

**Attack (S4)**: Within the SAME transaction, after an account is closed (lamports drained, data zeroed):
1. Close account (lamports go to attacker)
2. In same tx, re-fund account with lamports (becomes rent-exempt again)
3. Account data is all zeros but account exists again
4. Next instruction that checks `account.data_len() > 0` or assumes "closed accounts don't exist" fails

**Defense**: Set discriminator to a CLOSED sentinel value. Check discriminator on every access, not just data length.

## 4. Rent Recovery

For each close operation:

| Account | Rent-Exempt Lamports | Fully Recovered? | Recipient Correct? |
|---------|--------------------:|-----------------|-------------------|
| {account} | {amount} | YES/NO | {who gets the lamports} |

**Check**: Are ALL lamports transferred? Partial transfer leaves lamports stranded.

## 5. Token Account Closure

For each SPL Token account closure:

| Token Account | Balance Checked Zero? | Withheld Fees Harvested? (Token-2022) | Close Authority Correct? |
|--------------|----------------------|--------------------------------------|------------------------|
| {account} | YES/NO | YES/NO/N/A | {who can close it} |

**SPL Token rule**: Token accounts can only be closed when balance == 0.
**Token-2022**: Accounts with TransferFeeConfig may have withheld fees. Must harvest before close.

## 6. Reinitialization Prevention

For each account type that can be initialized:

| Account Type | Init Method | Can Be Re-Initialized? | Guard |
|-------------|------------|----------------------|-------|
| {type} | `init` / `init_if_needed` / manual | YES/NO | {what prevents it} |

**`init_if_needed` WARNING**: This attribute allows reinitialization if the account already exists. It is a known footgun.
**Safe pattern**: Use `init` (fails if account exists) + manual `is_initialized` flag for manual programs.
**Attack**: Re-initialize an account to reset its state (e.g., reset reward counter, change authority).

## Finding Template

```markdown
**ID**: [AL-N]
**Severity**: [revival = High, stranded rent = Medium, reinit = High]
**Step Execution**: ✓1,2,3,4,5,6 | ✗(reasons) | ?(uncertain)
**Rules Applied**: [S4:✓, R9:✓/✗]
**Location**: program/src/{file}.rs:LineN
**Title**: [Lifecycle issue] in [instruction] enables [attack]
**Description**: [Specific lifecycle vulnerability with code trace]
**Impact**: [Fund theft via revival / stranded assets / state reset]
```

---

## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From the local Solodit-derived corpus

- Pattern: `init_if_needed` on staking config allows anyone to re-initialize parameters after first deployment
  Where it hit: Staking program / `Initialize` instruction
  Severity: HIGH
  Source: Solodit (row_id 7319)
  Summary: The `Initialize` instruction uses `init_if_needed`, which succeeds even when the account already exists and is populated. Any caller can invoke it again to overwrite staking parameters (rates, authorities, caps) at will. The fix is to replace `init_if_needed` with `init`, which fails if the account already exists.
  Map to: init_if_needed, account_reinit

- Pattern: `init_if_needed` on staking parameters allows repeated re-initialization by any caller
  Where it hit: Staking program / staking parameters account
  Severity: HIGH
  Source: Solodit (row_id 8967)
  Summary: Identical root cause to row 7319 — `init_if_needed` permits the staking parameter account to be re-initialized after it was already populated, letting an attacker reset protocol configuration. The fix switches to `init` so the first initialization is the only one.
  Map to: init_if_needed, account_reinit

- Pattern: `close_account` sends refund to wrong recipient; closed account data allows ghost orders after purge
  Where it hit: Dex user account / `close_account` instruction
  Severity: HIGH
  Source: Solodit (row_id 15890)
  Summary: After an account is closed the program does not reset the account's tag/discriminator field, leaving the close incomplete. During the grace period before the runtime purges the account, a new order can be filed referencing the closed account. If that order is matched after purge the program cannot find the necessary state, causing a loss of funds and a frozen event queue. The fix adds a step to reset the account tag inside `close_account`.
  Map to: close_account, account_reinit

- Pattern: `ClosePosition` passes token mint key instead of token account key, making rent reclaim impossible
  Where it hit: Jet v2 / `ClosePosition` instruction
  Severity: HIGH
  Source: Solodit (row_id 15276)
  Summary: The `ClosePosition` handler passes the token mint's public key in the field that should hold the token account to close. The SPL token close call targets the wrong account, so the position is never actually closed and rent-exempt lamports are permanently stranded. The fix corrects the key passed to the instruction.
  Map to: close_account, rent_exempt

- Pattern: Non-rent-exempt market accounts can be purged by the runtime, enabling account address reuse for a new exchange
  Where it hit: Agnostic orderbook / `create_market` instruction
  Severity: HIGH
  Source: Solodit (row_id 15892)
  Summary: `create_market` assumes that the caller pre-created market accounts (event queue, bids, asks) with sufficient lamports, but does not verify rent-exempt status. If any account falls below the rent-exempt threshold it will be purged. An attacker can recreate the account at the same address and use it in a new, attacker-controlled exchange, draining user funds. The fix adds an explicit rent-exempt balance check inside `create_market`.
  Map to: rent_exempt, account_reinit

- Pattern: Hardcoded `Rent::default()` instead of `Rent::get()` underfunds new accounts, enabling DoS via purge
  Where it hit: Deriverse program / account creation logic
  Severity: MEDIUM
  Source: Solodit (row_id 87)
  Summary: Account creation uses a hardcoded default rent amount rather than fetching the current value from the on-chain `Rent` sysvar. If the sysvar value differs (e.g., after a network upgrade), funded accounts may fall below the rent-exempt threshold and be purged by the runtime, causing a denial of service. The fix replaces `Rent::default()` with `Rent::get()`.
  Map to: rent_exempt

- Pattern: `init` on ATA fails when account pre-exists, allowing DoS via front-running account creation
  Where it hit: Pump Science / `CreateBondingCurve` instruction
  Severity: MEDIUM
  Source: Solodit (row_id 2971)
  Summary: `CreateBondingCurve` opens a `bonding_curve_token_account` with Anchor's `init` constraint. Because ATAs are deterministic, an attacker can create the ATA in advance, causing every legitimate `CreateBondingCurve` call to fail with `AccountAlreadyInitialized`. The fix changes the constraint to `init_if_needed`, which succeeds whether or not the account already exists.
  Map to: init_if_needed

- Pattern: `init` on ATA allows permanent DoS of NFT deposit by front-running ATA creation
  Where it hit: Liquidity lockbox / `deposit` instruction
  Severity: MEDIUM
  Source: Solodit (row_id 8774)
  Summary: The `deposit` function uses Anchor's `init` constraint for the NFT's ATA. An attacker creates the ATA for a target NFT before a victim's deposit, causing the victim's transaction to fail with `AccountAlreadyInitialized`. This permanently blocks deposits for that specific NFT position. The fix uses `init_if_needed` or a different ATA handling strategy.
  Map to: init_if_needed

- Pattern: Rent-exempt check in bonding curve invariant includes rent lamports in the SOL balance comparison, corrupting the invariant
  Where it hit: Pump Science / bonding curve invariant check
  Severity: MEDIUM
  Source: Solodit (row_id 2249)
  Summary: The invariant check compares `sol_escrow_lamports` (which includes rent) against `real_sol_reserves` (which excludes rent). The check can pass when it should fail because the rent portion inflates the left-hand side. The fix subtracts the rent-exempt amount from `sol_escrow_lamports` before the comparison so both sides represent actual reserves.
  Map to: rent_exempt

- Pattern: `cancel_auction` fails with `UnbalancedInstruction` when a bid exists because lamport transfer precedes CPI completion
  Where it hit: Auction program / `cancel_auction` instruction
  Severity: MEDIUM
  Source: Solodit (row_id 8889)
  Summary: The close/transfer sequence in `cancel_auction` moves lamports before all CPIs finish, triggering a runtime `UnbalancedInstruction` error. Sellers cannot cancel auctions where a bid has already been placed, locking auction state. The fix restructures the instruction so the lamport transfer happens after all CPI calls complete.
  Map to: close_account


## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1. Close Operation Inventory | YES | ✓/✗/? | For every close |
| 2. Close Completeness | YES | ✓/✗/? | All 4 steps verified |
| 3. Revival Attack Analysis | YES | ✓/✗/? | **CRITICAL** - same-tx refund |
| 4. Rent Recovery | YES | ✓/✗/? | Full lamport transfer |
| 5. Token Account Closure | IF token accounts closed | ✓/✗(N/A)/? | Balance + withheld fees |
| 6. Reinitialization Prevention | YES | ✓/✗/? | init_if_needed is dangerous |
