---
name: "event-correctness"
description: "Trigger 15 events detected in recon event_definitions.md (optional skill) - Used By breadth agents (assigned to core state or dedicated agent)"
---

# Skill: EVENT_CORRECTNESS

> **Trigger**: >15 events detected in recon event_definitions.md (optional skill)
> **Used By**: breadth agents (assigned to core state or dedicated agent)
> **Purpose**: Verify emitted event parameters match actual state changes

## Methodology

### Step 1: Inventory All Emit Statements
From `{SCRATCHPAD}/emit_list.md`, extract every `emit` statement with:
- Event name, parameter values passed, source location
- The state-changing operation(s) that precede the emit

### Step 2: Parameter Semantic Check
For EACH emit statement, verify:

| # | Check | Question |
|---|-------|----------|
| 1 | **Value accuracy** | Does each parameter reflect the ACTUAL post-operation state? (not a stale pre-operation value, not an input parameter that was modified before use) |
| 2 | **Index correctness** | If the event indexes an entity (ID, address, index), is the index the CORRECT entity? (not off-by-one, not a different entity's ID, not a loop variable after increment) |
| 3 | **Ordering** | Is the emit placed AFTER all state changes it describes? (not before a conditional that could change the values) |
| 4 | **Conditional coverage** | If the function has branching logic, does EVERY branch that modifies state emit the appropriate event? (no silent state changes) |
| 5 | **Parameter count** | Do the emitted parameters match the event definition? (Solidity allows emitting fewer params - missing params default to zero) |
| 6 | **Semantic correctness** | Does each emitted variable match the SEMANTIC INTENT of the parameter name? If the event parameter is named `tokensReceived`, is the emitted value the actual tokens received (output), or is it the input amount (e.g., DAI spent)? Compare the parameter name against the variable being emitted - a mismatch between name semantics and actual value is a finding even if types match. |

### Step 3: Off-Chain Impact Assessment
For events consumed by off-chain systems (indexers, frontends, monitoring):
- If event parameters are wrong → off-chain state diverges from on-chain state
- Severity: typically LOW-MEDIUM unless financial decisions depend on indexed events

## Output
Findings use IDs `[EVT-N]`. Include the emit location, the incorrect parameter, and the correct value it should emit.
## Real-world examples

Use these as pattern precedents when investigating this skill. For each example, check whether the described mechanism is present in the scope code. If a match is found, tag the finding with `Example precedent: <row_id or URL>` (see `rules/finding-output-format.md`).

### From web-sourced audit reports

> Source mix: 4 CSV hits (solodit_findings.dedup.csv) + 6 web research findings.
> Tags map to SKILL.md checks: missing_event, wrong_event_args, unindexed, event_arg_order.

---

## WEB-EVT-001 — Missing event on SystemConfig initialization parameters

- Tag: `missing_event`
- Severity: MEDIUM
- Protocol: Optimism / SystemConfig
- Source: Spearbit / Sherlock (sherlock-audit/2023-01-optimism-judging)
- Summary: The `initialize()` function of `SystemConfig` sets gas cost parameters without emitting the corresponding configuration event. Off-chain indexers that rely on events to reconstruct system state have no record of the initial parameter values, causing divergence between on-chain storage and indexed state from block 0.
- Pattern: Admin/initializer function modifies critical storage; `emit` is absent or conditional on a path that is skipped during initialization.
- Check maps to: SKILL.md Step 2, check #4 (Conditional coverage — every branch that modifies state must emit).

---

## WEB-EVT-002 — Ribbon-v2: unindexed parameters across vault events

- Tag: `unindexed`
- Severity: MEDIUM
- Protocol: Ribbon Finance v2 (RibbonVault, RibbonThetaVault, GnosisAuction, StrikeSelection)
- Source: CSV row 17471 (Code4rena / Spearbit)
- Summary: `InitiateWithdraw`, `CapSet`, and `Withdraw` in `RibbonVault`, and most events in `RibbonThetaVault`, `GnosisAuction`, and `StrikeSelection` have zero indexed parameters. Off-chain clients cannot filter events by user address, round, or vault without scanning the full log.
- Additional sub-finding: `Deposit`, `InitiateWithdraw`, `Redeem`, and `CollectVaultFees` use inconsistent types for the `round` parameter (mixing `uint16` and `uint256`), breaking ABI-level event parsing in some tooling.
- Check maps to: SKILL.md Step 2, check #2 (Index correctness) and check #5 (Parameter count / consistency).

---

## WEB-EVT-003 — Fei Protocol: PCVDripController emits stale pre-operation amount

- Tag: `wrong_event_args`
- Severity: MEDIUM
- Protocol: Fei Protocol (PCVDripController)
- Source: CSV row 17680 (Fei Protocol Spearbit audit)
- Summary: The constructor of `PCVDripController` emits `DripAmountUpdate` with `_incentiveAmount` instead of `_dripAmount`. In the `drip()` function the `Dripped` event emits the *requested* withdraw amount rather than the *actual* amount returned by the Uniswap pool, which can differ due to slippage. Indexers tracking drip volume over-count or under-count the actual tokens moved.
- Check maps to: SKILL.md Step 2, check #1 (Value accuracy — post-operation actual, not input parameter) and check #6 (Semantic correctness — `dripAmount` field should hold actual output, not input).

---

## WEB-EVT-004 — BeamNetwork: all event parameters unindexed in EcoBalanceStore

- Tag: `unindexed`
- Severity: MEDIUM
- Protocol: BeamNetwork / EcoBalanceStore
- Source: CSV row 18903
- Summary: Every event defined in `BeamBalanceStore` (later renamed `EcoBalanceStore`) emits parameters with no `indexed` qualifier. The contract tracks per-user balance changes; without indexed user-address fields, block explorers and subgraphs must decode every log to find events for a given account, making targeted queries O(n) over all events rather than O(1) via Bloom filter.
- Check maps to: SKILL.md Step 2, check #2 (Index correctness — key entity identifiers should be indexed).

---

## WEB-EVT-005 — Missing events on sensitive admin setters (setFeeRecipient, setStrikePrice, initialize)

- Tag: `missing_event`
- Severity: MEDIUM
- Protocol: Ribbon Finance v2 (RibbonVault, RibbonThetaVault, RibbonDeltaVault)
- Source: CSV row 17471 (same audit, distinct sub-finding)
- Summary: `setFeeRecipient` in `RibbonVault`, `setStrikePrice` in `RibbonThetaVault`, `baseInitialize` in `RibbonVault`, and `initialize` in `RibbonThetaVault` / `RibbonDeltaVault` execute privileged state changes with no event emission. Monitoring systems and multisig watchers receive no signal when the fee recipient or strike price is changed by an admin.
- Check maps to: SKILL.md Step 2, check #4 (Conditional coverage — all branches that modify state must emit).

---

## WEB-EVT-006 — Fei Protocol: UpdateReceivingAddress and PCVSwapperUniswap events omit previous value

- Tag: `wrong_event_args`
- Severity: MEDIUM
- Protocol: Fei Protocol (PCVSwapperUniswap, PCVDripController, Timed)
- Source: CSV row 17680 (Fei Protocol Spearbit audit, distinct sub-finding)
- Summary: `UpdateReceivingAddress` emits only the new address; the previous value is not included. The four events in `PCVSwapperUniswap` and `TimerReset` in `Timed` similarly omit the before-state. Off-chain systems cannot determine whether a change was expected or reconstruct the state transition timeline without querying historical storage.
- Pattern: Setter events emit only `newValue`; `oldValue` is discarded. This is distinct from wrong_event_args (the new value is correct) but constitutes incomplete event data that prevents state reconstruction.
- Check maps to: SKILL.md Step 2, check #6 (Semantic correctness — parameter name implies a transition; only half the transition is logged).

---

## WEB-EVT-007 — Event emitted before state change completes (pre-operation emit)

- Tag: `event_arg_order`
- Severity: LOW-MEDIUM
- Protocol: General pattern (documented at detectors.auditbase.com and vibraniumaudits.com)
- Source: AuditBase detector "Events may be emitted out of order due to reentrancy"; Vibranium Audits post on incorrect event emission
- Summary: An `emit` placed before the state-modifying line (or before an external call that can alter state) logs the pre-operation value. Example: a balance event emitted before `transfer()` records the sender's balance before the deduction. If the external call re-enters and modifies state, the emitted value is stale.
- Pattern: `emit Transfer(sender, recipient, amount)` appears on the line *before* `balances[sender] -= amount`, or before an external call that may itself modify `balances`.
- Check maps to: SKILL.md Step 2, check #3 (Ordering — emit must be placed after all state changes it describes).

---

## WEB-EVT-008 — Wrong semantic variable emitted: input token amount instead of output token amount

- Tag: `wrong_event_args`
- Severity: MEDIUM
- Protocol: General DeFi swap / vault pattern
- Source: Vibranium Audits "Incorrect Event Emission in Solidity" (vibraniumaudits.com/post/incorrect-event-emission-in-solidity-risks-and-best-practices); corroborated by Fei Protocol Dripped event (CSV row 17680)
- Summary: A swap or deposit event named `Swapped(uint256 tokensReceived)` emits the input token amount (`amountIn`) rather than the actual output (`amountOut`) returned by the pool. The parameter name `tokensReceived` semantically implies the output; using `amountIn` causes off-chain accounting (subgraphs, portfolio trackers) to overstate or understate received amounts by the fee spread.
- Pattern: The function receives `amountIn`, calls an external AMM that returns `amountOut`, but `emit Swapped(amountIn)` uses the input variable rather than the local variable holding the return value.
- Check maps to: SKILL.md Step 2, check #6 (Semantic correctness — compare parameter name semantics against the actual variable emitted).

---

## WEB-EVT-009 — Missing event when ReweightIncentiveUpdate is defined but never used

- Tag: `missing_event`
- Severity: LOW
- Protocol: Fei Protocol (IUniswapPCVController)
- Source: CSV row 17680 (Fei Protocol Spearbit audit, sub-finding)
- Summary: `ReweightIncentiveUpdate` is declared in the interface and presumably covers state changes to the reweight incentive parameter, but no `emit` statement in the implementation triggers it. The incentive parameter changes silently. This is a distinct sub-pattern of missing_event: the event definition exists but the emit call is absent.
- Check maps to: SKILL.md Step 2, check #4 (Conditional coverage — defined event never emitted = dead event definition + silent state change).

---

## WEB-EVT-010 — Duplicate event names across contracts cause indexer collisions

- Tag: `wrong_event_args`
- Severity: LOW
- Protocol: Fei Protocol (RatioPCVController vs IPCVDeposit; Timed vs IUniswapOracle)
- Source: CSV row 17680 (Fei Protocol Spearbit audit, sub-finding)
- Summary: `WithdrawERC20` is defined in both `RatioPCVController` and `IPCVDeposit` with different parameter sets. `DurationUpdate` is defined in both `Timed` and `IUniswapOracle`. ABI-level decoders that match on event topic hash alone will misparse one of the two when logs from both contracts appear in the same transaction receipt or subgraph query.
- Pattern: Two contracts emit events with the same name but different parameter types or order; the keccak256 topic will differ only if the signature differs, but semantically identical names with different ABIs confuse off-chain tooling.
- Check maps to: SKILL.md Step 2, check #5 (Parameter count — emit signature must match the event definition in scope, not a homonymous definition from another contract).


