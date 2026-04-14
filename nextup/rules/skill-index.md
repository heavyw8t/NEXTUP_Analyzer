# Skill Index

> Skills are methodology files read by agents via `Read {NEXTUP_HOME}/agents/skills/{LANGUAGE}/{name}/SKILL.md`.
> The orchestrator resolves `{LANGUAGE}` to `evm`, `solana`, `aptos`, `sui`, or `c_cpp` based on Step 0 detection.
> EVM has 18 skills, Solana has 20 skills, Aptos has 21 skills, Sui has 21 skills, C/C++ has 12 skills - no shared skills directory exists.

## EVM Skills (`{NEXTUP_HOME}/agents/skills/evm/`)

> Load these when `LANGUAGE=evm`. All 18 skills use EVM/Solidity concepts.

| Skill | Trigger Pattern | Used By |
|-------|-----------------|---------|
| FLASH_LOAN_INTERACTION | FLASH_LOAN or FLASH_LOAN_EXTERNAL flag | breadth agents, depth-token-flow, depth-edge-case |
| ORACLE_ANALYSIS | ORACLE flag | breadth agents, depth-external, depth-edge-case |
| TOKEN_FLOW_TRACING | BALANCE_DEPENDENT flag | depth-token-flow, breadth agents |
| ZERO_STATE_RETURN | ERC4626/first-depositor | depth-edge-case |
| STAKING_RECEIPT_TOKENS | Receipt token detected | breadth agents, depth-token-flow |
| EVENT_CORRECTNESS | >15 events detected (optional) | breadth agents |
| SEMI_TRUSTED_ROLES | SEMI_TRUSTED_ROLE flag | breadth agents, depth-state-trace |
| MIGRATION_ANALYSIS | MIGRATION flag | breadth agents |
| CROSS_CHAIN_TIMING | CROSS_CHAIN flag | depth-external |
| TEMPORAL_PARAMETER_STALENESS | TEMPORAL flag | breadth agents, depth-state-trace |
| CENTRALIZATION_RISK | 3+ privileged roles (optional) | breadth agents |
| SHARE_ALLOCATION_FAIRNESS | SHARE_ALLOCATION flag | breadth agents, depth-edge-case |
| FORK_ANCESTRY | Always (recon TASK 0) | recon agent |
| ECONOMIC_DESIGN_AUDIT | MONETARY_PARAMETER flag | breadth agents |
| EXTERNAL_PRECONDITION_AUDIT | External interactions | breadth agents |
| VERIFICATION_PROTOCOL | Always (verifiers) | security-verifier |
| STORAGE_LAYOUT_SAFETY | STORAGE_LAYOUT flag (proxy/upgradeable/diamond/delegatecall/sstore/sload/assembly) | depth-state-trace, depth-edge-case |
| CROSS_CHAIN_MESSAGE_INTEGRITY | CROSS_CHAIN_MSG flag (lzReceive/ccipReceive/receiveWormholeMessages/setPeer/setTrustedRemote) | breadth agents, depth-external |

## Solana Skills (`{NEXTUP_HOME}/agents/skills/solana/`)

> Load these when `LANGUAGE=solana`. All 20 skills use Solana/Anchor concepts.

| Skill | Trigger Pattern | Used By |
|-------|-----------------|---------|
| ACCOUNT_VALIDATION | Always (Solana) | breadth agents, depth agents |
| CPI_SECURITY | CPI flag | breadth agents, depth-external |
| PDA_SECURITY | PDA flag | breadth agents, depth-state-trace |
| ACCOUNT_LIFECYCLE | ACCOUNT_CLOSING flag | breadth agents, depth-edge-case |
| TOKEN_2022_EXTENSIONS | TOKEN_2022 flag | breadth agents, depth-token-flow |
| INSTRUCTION_INTROSPECTION | INSTRUCTION_INTROSPECTION flag | breadth agents, depth-external |
| SEMI_TRUSTED_ROLES | SEMI_TRUSTED_ROLE flag | breadth agents, depth-state-trace |
| MIGRATION_ANALYSIS | MIGRATION flag | breadth agents |
| CROSS_CHAIN_TIMING | CROSS_CHAIN flag | depth-external |
| TEMPORAL_PARAMETER_STALENESS | TEMPORAL flag | breadth agents, depth-state-trace |
| CENTRALIZATION_RISK | 3+ privileged roles (optional) | breadth agents |
| SHARE_ALLOCATION_FAIRNESS | SHARE_ALLOCATION flag | breadth agents, depth-edge-case |
| FORK_ANCESTRY | Always (recon TASK 0) | recon agent |
| ECONOMIC_DESIGN_AUDIT | MONETARY_PARAMETER flag | breadth agents |
| EXTERNAL_PRECONDITION_AUDIT | External interactions (CPI targets) | breadth agents |
| VERIFICATION_PROTOCOL | Always (verifiers) | security-verifier |
| TOKEN_FLOW_TRACING | BALANCE_DEPENDENT flag | depth-token-flow, breadth agents |
| ZERO_STATE_RETURN | Vault/first-depositor | depth-edge-case |
| FLASH_LOAN_INTERACTION | FLASH_LOAN flag | breadth agents, depth-token-flow, depth-edge-case |
| TRIDENT_API_REFERENCE | `trident_available: true` in build_status.md | invariant fuzz generator (Phase 4b), security-verifier Template 6 |

## Aptos Skills (`{NEXTUP_HOME}/agents/skills/aptos/`)

> Load these when `LANGUAGE=aptos`. All 21 skills use Aptos Move concepts.

| Skill | Trigger Pattern | Used By |
|-------|-----------------|---------|
| ABILITY_ANALYSIS | Always (Aptos) | breadth agents, depth agents |
| BIT_SHIFT_SAFETY | Always (Aptos) | breadth agents, depth-edge-case |
| TYPE_SAFETY | Always (Aptos) | breadth agents, depth-state-trace |
| REF_LIFECYCLE | Always (Aptos) | breadth agents, depth-state-trace, depth-token-flow |
| FORK_ANCESTRY | Always (recon TASK 0) | recon agent |
| VERIFICATION_PROTOCOL | Always (verifiers) | security-verifier |
| ORACLE_ANALYSIS | ORACLE flag | breadth agents, depth-external, depth-edge-case |
| FLASH_LOAN_INTERACTION | FLASH_LOAN flag | breadth agents, depth-token-flow, depth-edge-case |
| TOKEN_FLOW_TRACING | BALANCE_DEPENDENT flag | depth-token-flow, breadth agents |
| ZERO_STATE_RETURN | Vault/first-depositor | depth-edge-case |
| SEMI_TRUSTED_ROLES | SEMI_TRUSTED_ROLE flag | breadth agents, depth-state-trace |
| TEMPORAL_PARAMETER_STALENESS | TEMPORAL flag | breadth agents, depth-state-trace |
| ECONOMIC_DESIGN_AUDIT | MONETARY_PARAMETER flag | breadth agents |
| EXTERNAL_PRECONDITION_AUDIT | External module interactions | breadth agents |
| MIGRATION_ANALYSIS | MIGRATION flag | breadth agents |
| CROSS_CHAIN_TIMING | CROSS_CHAIN flag | depth-external |
| FUNGIBLE_ASSET_SECURITY | FA_STANDARD flag | breadth agents, depth-token-flow |
| REENTRANCY_ANALYSIS | REENTRANCY flag | breadth agents, depth-state-trace |
| DEPENDENCY_AUDIT | EXTERNAL_LIB flag | breadth agents, depth-external |
| CENTRALIZATION_RISK | 3+ privileged roles (optional) | breadth agents |
| SHARE_ALLOCATION_FAIRNESS | SHARE_ALLOCATION flag | breadth agents, depth-edge-case |

## Sui Skills (`{NEXTUP_HOME}/agents/skills/sui/`)

> Load these when `LANGUAGE=sui`. All 21 skills use Sui Move concepts.

| Skill | Trigger Pattern | Used By |
|-------|-----------------|---------|
| ABILITY_ANALYSIS | Always (Sui) | breadth agents, depth agents |
| BIT_SHIFT_SAFETY | Always (Sui) | breadth agents, depth-edge-case |
| TYPE_SAFETY | Always (Sui) | breadth agents, depth-state-trace |
| OBJECT_OWNERSHIP | Always (Sui) | breadth agents, depth-state-trace, depth-token-flow |
| FORK_ANCESTRY | Always (recon TASK 0) | recon agent |
| VERIFICATION_PROTOCOL | Always (verifiers) | security-verifier |
| ORACLE_ANALYSIS | ORACLE flag | breadth agents, depth-external, depth-edge-case |
| FLASH_LOAN_INTERACTION | FLASH_LOAN flag | breadth agents, depth-token-flow, depth-edge-case |
| TOKEN_FLOW_TRACING | BALANCE_DEPENDENT flag | depth-token-flow, breadth agents |
| ZERO_STATE_RETURN | Vault/first-depositor | depth-edge-case |
| SEMI_TRUSTED_ROLES | SEMI_TRUSTED_ROLE flag | breadth agents, depth-state-trace |
| TEMPORAL_PARAMETER_STALENESS | TEMPORAL flag | breadth agents, depth-state-trace |
| ECONOMIC_DESIGN_AUDIT | MONETARY_PARAMETER flag | breadth agents |
| EXTERNAL_PRECONDITION_AUDIT | External package interactions | breadth agents |
| MIGRATION_ANALYSIS | MIGRATION flag | breadth agents |
| CROSS_CHAIN_TIMING | CROSS_CHAIN flag | depth-external |
| PTB_COMPOSABILITY | PTB flag | breadth agents, depth-external, depth-state-trace |
| PACKAGE_VERSION_SAFETY | PACKAGE_UPGRADE flag | breadth agents, depth-external |
| DEPENDENCY_AUDIT | EXTERNAL_LIB flag | breadth agents, depth-external |
| CENTRALIZATION_RISK | 3+ privileged roles (optional) | breadth agents |
| SHARE_ALLOCATION_FAIRNESS | SHARE_ALLOCATION flag | breadth agents, depth-edge-case |

## C/C++ Skills (`{NEXTUP_HOME}/agents/skills/c_cpp/`)

> Load these when `LANGUAGE=c_cpp`. All 12 skills use C/C++ concepts (memory safety, concurrency, crypto, systems programming).

| Skill | Trigger Pattern | Used By |
|-------|-----------------|---------|
| MEMORY_SAFETY_AUDIT | Always (C/C++) | breadth agents, depth agents |
| BUFFER_OPERATIONS | BUFFER_OPS flag (memcpy/strcpy/strncpy) | breadth agents, depth-data-flow, depth-edge-case |
| INTEGER_SAFETY | Arithmetic on user input | breadth agents, depth-edge-case |
| CRYPTO_CONSTANT_TIME | CRYPTO_OPS flag (secp256k1_*/EVP_*) | breadth agents, depth-external, depth-edge-case |
| CONCURRENCY_SAFETY | THREADING flag (mutex/pthread/std::thread) | breadth agents, depth-state-trace |
| NETWORK_PROTOCOL_SECURITY | NETWORK_IO flag (socket/recv/send) | breadth agents, depth-external |
| VERIFICATION_PROTOCOL | Always (verifiers) | security-verifier |
| RAII_RESOURCE_MANAGEMENT | RAII_PATTERN flag (new/malloc/fopen) | breadth agents, depth-state-trace |
| CENTRALIZATION_RISK | Admin/config patterns (optional) | breadth agents |
| FORK_ANCESTRY | Always (recon TASK 0) | recon agent |
| PREPROCESSOR_SAFETY | COMPLEX_MACROS flag (>10 non-trivial macros) | breadth agents |
| ECONOMIC_DESIGN_AUDIT | MONETARY_PARAMETER flag | breadth agents |

## Injectable Skills (`{NEXTUP_HOME}/agents/skills/injectable/`)

> Injectable skills are protocol-type-specific. They load ONLY when recon classifies the protocol as the matching type.
> They are NOT counted in the per-tree standard skill set.
> They merge into existing agents via the standard merge hierarchy - they do NOT spawn new agents.

| Skill | Protocol Type Trigger | Inject Into |
|-------|----------------------|-------------|
| VAULT_ACCOUNTING | `vault` | Core state or economic design agent (M4) |
| ACCOUNT_ABSTRACTION_SECURITY | `account_abstraction` (ERC-4337, EntryPoint, UserOperation, Paymaster) | Breadth agents, depth-external |
| NFT_PROTOCOL_SECURITY | `nft` (ERC721/ERC1155 with marketplace, staking, or collateral logic) | Breadth agents, depth-token-flow, depth-edge-case |
| GOVERNANCE_ATTACK_VECTORS | `governance` (Governor, Timelock, voting, proposal, quorum, delegate) | Breadth agents, depth-external, depth-edge-case |
| OUTCOME_DETERMINISM | `outcome_determinism` (finite-pool selection with depletion fallback + time-gated actions with observable default/fallback outcomes). NOTE: callback selective revert and RNG consumption enumeration are now ALWAYS-ON in depth templates, not in this injectable. | Breadth agents, depth-edge-case |
| LENDING_PROTOCOL_SECURITY | `lending` (liquidate/borrow/repay/collateral/lend/loan/LTV/healthFactor/interestRate/debtToken) | Breadth agents, depth-token-flow, depth-edge-case, depth-state-trace |
| DEX_INTEGRATION_SECURITY | `dex_integration` (swap/addLiquidity/removeLiquidity/IUniswapV2Router/ISwapRouter/amountOutMin - AND protocol is NOT itself a DEX) | Breadth agents, depth-external, depth-edge-case |
| V4_HOOK_SECURITY | `v4_hook` (IHooks/BaseHook/beforeSwap/afterSwap/PoolManager/PoolKey/Currency.unwrap - AND protocol IS the hook implementation) | Breadth agents, depth-external, depth-token-flow, depth-edge-case |
| LIQUID_STAKING_INTEGRATION | `lst_integration` (stETH/wstETH/rETH/frxETH/sfrxETH/cbETH/mETH - AND protocol ACCEPTS or HOLDS these tokens, not issues them) | Breadth agents, depth-token-flow, depth-edge-case, depth-external |
| PERMIT2_SECURITY | `permit2_integration` (IPermit2/IAllowanceTransfer/ISignatureTransfer/PermitTransferFrom - AND protocol USES Permit2, not implements it) | Breadth agents, depth-external, depth-state-trace |
| EIGENLAYER_INTEGRATION | `eigenlayer_integration` (IStrategy/IDelegationManager/ISlasher/IEigenPod/AVS/operator.*register - AND protocol integrates with EigenLayer, not implements core contracts) | Breadth agents, depth-external, depth-state-trace, depth-edge-case |
| LAYERZERO_INTEGRATION | `layerzero_integration` (OFT/ONFT/OApp/ILayerZeroEndpointV2/lzReceive/_lzSend/setPeer/SendParam - AND protocol USES LayerZero, not implements the endpoint) | Breadth agents, depth-external, depth-state-trace, depth-edge-case |
| AAVE_INTEGRATION | `aave_integration` (IPool/IAToken/IVariableDebtToken/getReserveData/getUserAccountData/flashLoan - AND protocol USES Aave, not implements it) | Breadth agents, depth-token-flow, depth-edge-case, depth-external |
| MORPHO_INTEGRATION | `morpho_integration` (IMorpho/IMorphoBlue/IMetaMorpho/MarketParams/supplyShares/borrowShares/MorphoBalancesLib - AND protocol USES Morpho, not implements it) | Breadth agents, depth-token-flow, depth-edge-case, depth-state-trace |
| VAULT_SECURITY | `vault_builder` (ERC4626/deposit/withdraw/totalAssets/totalShares/convertToShares/convertToAssets/previewDeposit/previewRedeem AND the protocol IS the vault implementation) | Breadth agents, depth-token-flow, depth-edge-case, depth-state-trace |
| VAULT_INTEGRATION_SECURITY | `vault_integration` (ERC4626/IERC4626/deposit/withdraw/convertToAssets/convertToShares/previewRedeem/previewDeposit/maxDeposit AND the protocol CALLS external vaults, not implements them) | Breadth agents, depth-external, depth-token-flow, depth-edge-case |

### How Injectable Skills Work
1. Recon Agent classifies protocol type in TASK 0 Step 1
2. Recon Agent adds injectable skill recommendations to `template_recommendations.md` under `## Injectable Skills`
3. Orchestrator reads injectable recommendations during Phase 2 instantiation
4. Injectable skill methodology is APPENDED to the relevant agent's prompt (not a separate agent)
5. No new agents spawned - injectable skills increase depth of existing agents

## Niche Agents (`{NEXTUP_HOME}/agents/skills/niche/`)

> Niche agents are flag-triggered STANDALONE agents. Unlike injectable skills (which append methodology to existing agents), niche agents spawn as independent agents in Phase 4b iteration 1. Each costs 1 depth budget slot.
> They are NOT counted in the per-tree standard skill set.
> Use niche agents instead of bloating scanner templates when a concern area needs focused depth.

| Niche Agent | Trigger Flag | Budget | Description |
|-------------|-------------|--------|-------------|
| EVENT_COMPLETENESS | `MISSING_EVENT` | 1 slot | Event emission coverage, parameter accuracy, cross-component event gaps |
| SEMANTIC_GAP_INVESTIGATOR | `sync_gaps >= 1` OR `accumulation_exposures >= 1` OR `conditional_writes >= 1` OR `cluster_gaps >= 1` (from Phase 4a.5) | 1 slot | Investigates SYNC_GAP, ACCUMULATION_EXPOSURE, CONDITIONAL, and CLUSTER_GAP flags from semantic invariants to conclusion |
| SPEC_COMPLIANCE_AUDIT | `HAS_DOCS` flag (non-empty DOCS_PATH with testable claims) | 1 slot | Spec-to-code compliance: extracts doc claims, verifies against code, reports mismatches |
| SIGNATURE_VERIFICATION_AUDIT | `HAS_SIGNATURES` flag (ecrecover/ECDSA.recover/permit/EIP712/domainSeparator/nonces/isValidSignature) | 1 slot | Signature replay, malleability, EIP-712 domain, permit front-run, nonce management, cross-chain replay |
| SEMANTIC_CONSISTENCY_AUDIT | `HAS_MULTI_CONTRACT` flag (2+ in-scope contracts sharing parameters or formulas) | 1 slot | Config variable unit mismatches, formula semantic drift, magic number consistency across contracts |

### How Niche Agents Work
1. Recon Agent 3 detects trigger flag (e.g., `MISSING_EVENT` from setter_list.md/emit_list.md)
2. Recon adds niche agent to `template_recommendations.md` → `## Niche Agents` in BINDING MANIFEST
3. Orchestrator reads niche agent definition from `{NEXTUP_HOME}/agents/skills/niche/{name}/SKILL.md`
4. Orchestrator spawns niche agent in Phase 4b iteration 1 alongside standard depth agents
5. Niche agent writes to `{SCRATCHPAD}/niche_{name}_findings.md`
6. Chain analysis reads niche agent output alongside depth/scanner findings

### When to Use Niche Agents vs Injectable Skills vs Scanner Sub-Checks
| Criteria | Scanner Sub-Check | Injectable Skill | Niche Agent |
|----------|------------------|-----------------|-------------|
| Lines of methodology | ≤5 | 10-100 | 50-150 |
| Applies universally? | Yes | No (protocol-type) | No (flag-triggered) |
| Spawns new agent? | No | No | **Yes** (1 budget slot) |
| Depth of analysis | Surface scan | Medium (enriches existing agent) | **Deep** (entire agent focused on one concern) |
| Use when | Quick check, low FP risk | Protocol-type-specific methodology | Concern needs dedicated focus, scanner sub-check is insufficient |
