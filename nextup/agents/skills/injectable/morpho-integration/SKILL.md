---
name: "morpho-integration"
description: "Protocol Type Trigger morpho_integration (detected when recon finds IMorpho|IMorphoBlue|IMetaMorpho|MarketParams|Id|morpho.supply|morpho.borrow|morpho.liquidate|morpho.createMarket - protocol USES Morpho Blue or MetaMorpho as lending layer)"
---

# Injectable Skill: Morpho Blue / MetaMorpho Integration Security

> **Protocol Type Trigger**: `morpho_integration` (detected when recon finds: `IMorpho`, `IMorphoBlue`, `IMetaMorpho`, `MarketParams`, `Id`, `morpho.supply`, `morpho.borrow`, `morpho.withdraw`, `morpho.repay`, `morpho.liquidate`, `morpho.createMarket`, `morpho.accrueInterest`, `morpho.market`, `supplyShares`, `borrowShares`, `MorphoBalancesLib`, `SharesMathLib` - AND the protocol calls Morpho, not implements it)
> **Inject Into**: Breadth agents, depth-token-flow, depth-edge-case, depth-state-trace
> **Language**: EVM only
> **Finding prefix**: `[MOR-N]`
> **Relationship to LENDING_PROTOCOL_SECURITY**: That skill covers generic lending patterns. This skill covers Morpho-specific integration: singleton architecture, virtual shares, market ID derivation, LLTV bounds, IRM trust, oracle coupling. Both may be active.

## Orchestrator Decomposition Guide
When decomposing this skill into depth agent investigation questions, map sections to domains:
- Section 1: depth-token-flow + depth-edge-case (share accounting, virtual offset, first depositor, rounding)
- Section 2: depth-external (market creation, oracle trust, IRM trust, LLTV)
- Section 3: depth-state-trace (interest accrual, state ordering, market ID)
- Section 4: depth-edge-case (liquidation incentive, bad debt, boundary LLTV)
- Section 5: depth-external + depth-token-flow (MetaMorpho vault, allocation, reallocation)

## When This Skill Activates

Recon detects that the protocol integrates with Morpho Blue (the singleton lending protocol) or MetaMorpho (the vault layer on top). The protocol may supply, borrow, create markets, build vault strategies, or use Morpho as a building block for structured products.

---

## 0. Taxonomy Pre-Search (MANDATORY first step)

Before any code analysis, query the NEXTUP taxonomy for finding types that overlap this skill's domain:

1. Read `{NEXTUP_HOME}/taxonomy/evm.json`.
2. Grep the `types[].markers` arrays for keywords tied to this integration. For this skill, the relevant marker seed list is: `morpho`, `supplyCollateral`, `market`, `oracle`, `IRM`, `position`, `lltv`, `badDebt`, `marketParams`
3. For every match, record the taxonomy `id` (e.g. `EVM-D03`), `name`, `category`, `typical_direction`, and which markers matched.
4. When a finding produced by this skill maps to a taxonomy type, tag it with both IDs: `[MOR-N] (taxonomy: <ID> <NAME>)`.
5. Any taxonomy marker that appears in scope code but produces no finding must be affirmatively dismissed with a one-line reason in your output.

If `taxonomy/evm.json` is missing or unreadable, log to `{SCRATCHPAD}/trace_issues.md` when `TRACE_MODE == true` and continue with marker-free analysis.

---

## 1. Share Accounting and Virtual Offset

Morpho Blue uses a shares-based accounting model with a virtual offset to prevent first-depositor inflation attacks.

### 1a. Virtual Shares and Assets

- Morpho Blue uses `VIRTUAL_SHARES = 1e6` and `VIRTUAL_ASSETS = 1` as offset values in supply and borrow share calculations.
- Share calculation: `shares = assets * (totalSupplyShares + VIRTUAL_SHARES) / (totalSupplyAssets + VIRTUAL_ASSETS)`
- This means the first depositor does NOT get a 1:1 share ratio — the virtual offset prevents the classic ERC4626 inflation attack.
- **Real finding pattern**: Protocol assumes 1:1 share ratio for Morpho markets and computes expected shares as `amount * totalShares / totalAssets`. This is wrong due to the virtual offset — the protocol over/under-estimates its position.

### 1b. Share-to-Asset Conversion Rounding

- Morpho uses `mulDivDown` for supply (round down shares — depositor gets fewer shares) and `mulDivUp` for borrow (round up shares — borrower owes more).
- Does the protocol correctly use the matching rounding direction when converting between shares and assets?
- **Real finding pattern**: Protocol converts its Morpho `supplyShares` to assets using `mulDivUp` (wrong direction — should be `mulDivDown` for supply, overestimating its position). Or converts `borrowShares` to assets using `mulDivDown` (wrong — should be `mulDivUp` for borrow, underestimating its debt).
- Does the protocol use `MorphoBalancesLib` for conversions, or does it roll its own math?

### 1c. Share Precision at Low Amounts

- At very low supply amounts (close to `VIRTUAL_ASSETS`), the virtual offset dominates. Small deposits may receive 0 shares.
- Does the protocol check for zero shares returned from supply operations?
- **Real finding pattern**: Protocol deposits dust amounts into a new Morpho market. Due to virtual offset, it receives 0 shares but the assets are locked. The protocol thinks it has a position but owns nothing.

Tag: `[TRACE:share_conversion={morpho_lib/custom_math} → rounding_direction={correct/inverted} → zero_share_check={YES/NO}]`

---

## 2. Market Creation and Parameter Trust

Morpho Blue markets are permissionless — anyone can create a market with any parameters.

### 2a. Market ID Derivation

- Market ID is `keccak256(abi.encode(MarketParams))` where `MarketParams = {loanToken, collateralToken, oracle, irm, lltv}`.
- **All five parameters define the market identity.** Two markets with the same tokens but different oracles are DIFFERENT markets.
- Does the protocol correctly derive market IDs? If any parameter is wrong, the protocol interacts with the wrong market (or a nonexistent one).
- **Real finding pattern**: Protocol hardcodes a market ID but uses different `MarketParams` when calling `morpho.supply()`. Morpho computes the ID from the params, not the hardcoded value. The protocol supplies to an unintended market.

### 2b. Oracle Trust

- Morpho Blue markets specify an oracle that returns the collateral price relative to the loan token.
- The oracle is set at market creation and CANNOT be changed. But the oracle itself may be manipulable.
- **Real finding pattern**: Protocol creates a market with a spot-price oracle (no TWAP). An attacker manipulates the oracle price via flash loan, then liquidates positions at the manipulated price.
- Does the protocol verify the oracle implementation before creating or entering a market?
- If the protocol enters existing markets: does it validate that the market's oracle is trustworthy?

### 2c. IRM (Interest Rate Model) Trust

- Morpho Blue markets specify an IRM contract. The IRM is immutable per market but the IRM contract itself may have admin functions.
- Does the protocol verify the IRM is a known, audited implementation (e.g., `AdaptiveCurveIrm`)?
- **Real finding pattern**: Attacker creates a market with a malicious IRM that returns extreme interest rates. Protocol enters the market without validating the IRM. Borrow rates spike to 1000% APY, draining the protocol's collateral via interest.
- Can the IRM revert on `borrowRate()` calls? A reverting IRM blocks `accrueInterest()`, freezing the market.

### 2d. LLTV (Liquidation Loan-To-Value)

- LLTV is set at market creation and cannot be changed. It determines the liquidation threshold.
- Morpho Blue enforces that LLTV must be in the `enabledLltv` set (governance-approved values).
- **Real finding pattern**: Protocol assumes all Morpho markets have "reasonable" LLTVs (e.g., 80-90%). A market with LLTV=98% allows positions to be leveraged to extreme levels. If the protocol enters such a market, small price movements cause cascading liquidations.
- Does the protocol validate LLTV bounds before entering a market?

Tag: `[TRACE:market_id_derivation={correct/mismatch} → oracle_validated={YES/NO} → irm_validated={YES/NO} → lltv_range_checked={YES/NO}]`

---

## 3. Interest Accrual and State Ordering

### 3a. Explicit Interest Accrual

- Morpho Blue does NOT auto-accrue interest. Interest accrues ONLY when `accrueInterest()` is called (or as part of supply/withdraw/borrow/repay/liquidate).
- If the protocol reads `morpho.market(id)` to get `totalSupplyAssets` or `totalBorrowAssets` without calling `accrueInterest()` first: the values are stale.
- **Real finding pattern**: Protocol reads `totalSupplyAssets` to compute its share value. No one has interacted with the market for hours. The protocol's valuation is hours behind actual, creating arbitrage: users deposit at stale (lower) valuation, then after accrual, withdraw at updated (higher) valuation.
- Does the protocol use `MorphoBalancesLib.expectedSupplyAssets()` / `expectedBorrowAssets()` which project the accrued value without requiring a state-changing call?

### 3b. State Read vs State Change Ordering

- If the protocol reads market state and then performs an action in the same transaction: the action triggers accrual, changing the state that was just read.
- Does the protocol read state AFTER its action, or does it use the pre-action state?
- **Real finding pattern**: Protocol reads `supplyShares`, supplies more, then reads `supplyShares` again. The second read includes accrued interest from the supply call's implicit `accrueInterest()`. The protocol interprets the difference as "shares received from deposit" but it includes accrued interest on existing shares.

### 3c. Multi-Market Consistency

- If the protocol interacts with multiple Morpho markets in one transaction: each market has independent interest accrual.
- Are cross-market calculations (e.g., total portfolio value) computed after all markets are accrued?
- Can an attacker exploit timing differences between markets in the same transaction?

Tag: `[TRACE:accrue_before_read={YES/NO/expected_lib} → read_after_action={YES/NO} → multi_market_sync={YES/NO/N/A}]`

---

## 4. Liquidation Mechanics

### 4a. Liquidation Incentive Factor (LIF)

- Morpho Blue's liquidation incentive is computed as: `LIF = min(maxLIF, 1 / (1 - cursor * (1 - LLTV)))` where `cursor` is a governance parameter and `maxLIF` caps the incentive.
- The liquidation incentive increases as LLTV increases — high-LLTV markets have high liquidation bonuses.
- Does the protocol account for the liquidation incentive when computing expected losses from liquidation?
- **Real finding pattern**: Protocol borrows from a high-LLTV market (98%). The liquidation incentive is ~15%. On liquidation, the protocol loses 15% of its collateral. The protocol's risk model assumed a 5% liquidation cost (based on Aave-like parameters).

### 4b. Bad Debt Socialization

- In Morpho Blue, if a position is liquidated and the collateral is insufficient to cover the debt (bad debt), the bad debt is socialized across ALL suppliers in that market.
- Each supplier's `supplyShares` are worth less — the exchange rate decreases.
- **Real finding pattern**: Protocol supplies to a Morpho market. Another borrower in the same market gets liquidated with bad debt. The protocol's supply position silently decreases in value. The protocol doesn't detect this because it only tracks shares, not the share-to-asset ratio.
- Does the protocol monitor for bad debt events? Does it adjust its accounting when bad debt occurs?

### 4c. Liquidation as MEV

- Morpho Blue liquidations are permissionless — anyone can liquidate.
- If the protocol holds borrow positions: its positions may be liquidated by MEV bots the moment the health factor drops below 1.0.
- Is there a margin of safety between the protocol's target LTV and the liquidation threshold?
- Can the protocol self-liquidate or deleverage before external liquidators act?

Tag: `[TRACE:lif_accounted={YES/NO} → bad_debt_detected={YES/NO} → deleverage_mechanism={auto/manual/NONE} → safety_margin={value}]`

---

## 5. MetaMorpho Vault Integration

If the protocol integrates with MetaMorpho (the vault layer):

### 5a. Vault Share Accounting

- MetaMorpho is an ERC-4626 vault. Standard ERC-4626 integration concerns apply.
- MetaMorpho uses its own virtual offset (1e6 shares, 1 asset) on top of the underlying Morpho markets.
- Does the protocol handle the double-offset correctly? (MetaMorpho offset on vault shares + Morpho offset on market shares)
- **Real finding pattern**: Protocol computes expected MetaMorpho shares using Morpho market ratios directly, skipping the vault's own share conversion. The result is wrong by a factor related to the vault's virtual offset.

### 5b. Allocation and Supply Queue

- MetaMorpho vaults distribute deposits across multiple Morpho markets via a supply queue (ordered list of markets).
- The vault's `deposit()` fills markets in queue order. The vault's `withdraw()` pulls from markets in withdrawal queue order.
- **Real finding pattern**: Protocol assumes its MetaMorpho deposit goes to a specific market. The supply queue changes (curator reorders). The deposit goes to a different, riskier market. The protocol's risk assumptions are now wrong.
- Does the protocol check which markets the vault is exposed to?

### 5c. Reallocation by Allocator

- MetaMorpho has a `reallocate()` function callable by authorized allocators. This moves funds between markets without vault share changes.
- After reallocation: the vault's exposure changes but depositors' shares don't change.
- **Real finding pattern**: Protocol monitors vault's exposure to a specific market. Allocator reallocates away from that market. Protocol still believes funds are in the original market, making incorrect risk assessments.
- Can reallocation change the vault's overall risk profile? Can an allocator move funds to a market with a malicious oracle or high-risk IRM?

### 5d. Timelock and Guardian

- MetaMorpho has a timelock for configuration changes (market additions, cap changes, fee changes). The guardian can veto pending changes.
- Does the protocol depend on the timelock duration? If the timelock is short (e.g., 0), configuration changes are immediate.
- Can the protocol react to pending vault configuration changes before they take effect?

Tag: `[TRACE:vault_share_conversion={correct/skips_offset} → supply_queue_aware={YES/NO} → reallocation_monitored={YES/NO} → timelock_checked={YES/NO}]`

---

## Common False Positives

- **Direct Morpho Blue with known market**: If the protocol hardcodes a specific market ID for a well-known market (e.g., USDC/WETH with Chainlink oracle and AdaptiveCurveIrm), oracle/IRM trust concerns are reduced
- **Supply-only integration**: If the protocol only supplies (never borrows), liquidation, health factor, and bad debt from own positions don't apply (but bad debt socialization from OTHER borrowers still affects suppliers)
- **MetaMorpho deposit-and-forget**: If the protocol deposits into MetaMorpho and only cares about total value (not per-market exposure), allocation queue and reallocation concerns are reduced
- **Using MorphoBalancesLib consistently**: If the protocol uses the official `MorphoBalancesLib` for all share↔asset conversions, rounding and virtual offset issues are handled correctly
- **Single-transaction interactions**: If the protocol's Morpho interactions are atomic (supply → read → withdraw in one tx), interest accrual staleness between transactions doesn't apply

## Step Execution Checklist (MANDATORY)

| Section | Required | Completed? | Notes |
|---------|----------|------------|-------|
| 1a. Virtual Shares/Assets | YES | | Offset awareness, 1:1 assumption |
| 1b. Rounding Direction | YES | | mulDivDown for supply, mulDivUp for borrow |
| 1c. Share Precision (Low Amounts) | IF dust/small deposits possible | | Zero share check |
| 2a. Market ID Derivation | IF protocol creates/references markets | | Params ↔ ID consistency |
| 2b. Oracle Trust | YES | | Validation, manipulation resistance |
| 2c. IRM Trust | YES | | Known implementation, revert risk |
| 2d. LLTV Bounds | IF protocol enters markets | | Range validation, extreme LLTV |
| 3a. Interest Accrual | YES | | accrueInterest before reads, expectedLib |
| 3b. Read vs Action Ordering | YES | | Stale reads, accrual side effects |
| 3c. Multi-Market Consistency | IF multiple markets | | Cross-market sync |
| 4a. Liquidation Incentive | IF protocol borrows | | LIF computation, LLTV impact |
| 4b. Bad Debt Socialization | IF protocol supplies | | Detection, accounting adjustment |
| 4c. Liquidation MEV | IF protocol borrows | | Safety margin, deleverage |
| 5a. Vault Share Accounting | IF MetaMorpho used | | Double offset, ERC-4626 |
| 5b. Supply/Withdrawal Queue | IF MetaMorpho used | | Queue order, market exposure |
| 5c. Reallocation | IF MetaMorpho used | | Allocator risk, monitoring |
| 5d. Timelock/Guardian | IF MetaMorpho used | | Duration check, veto window |
