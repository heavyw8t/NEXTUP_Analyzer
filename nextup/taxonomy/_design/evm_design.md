# EVM Puzzle-Piece Taxonomy: Design

Language: EVM (Solidity / Vyper / Yul).
ID prefix: `EVM-`.
Source baseline: `nextup/taxonomy/puzzle_taxonomy.json` v1.0.0 (categories A-I).
New native categories start at J.

This document drives JSON authoring. No JSON or Python here.

---

## 1. Inherited A-I types

A01 ROUNDING_FLOOR: INCLUDED. `EVM-A01`. Integer truncation in Solidity division or `mulDiv` floor, favoring the protocol when division yields user-owed amounts. Markers: `["/ (integer division)", "mulDiv(", "mulDivDown(", "Math.mulDiv", "FullMath.mulDiv", "FixedPointMathLib.divWadDown", "rayDiv", "wadDiv"]`.

A02 ROUNDING_CEIL: INCLUDED. `EVM-A02`. Ceiling division typically used when computing user-owed inputs (debt, shares owed). Markers: `["mulDivUp(", "mulDivRoundingUp", "ceilDiv", "(a + b - 1) / b", "FullMath.mulDivRoundingUp", "FixedPointMathLib.divWadUp", "SafeCast.toUint256Up"]`.

A03 MIXED_ROUNDING_DIRECTION: INCLUDED. `EVM-A03`. Same computation path mixes floor and ceil (deposit rounds down but redeem rounds down too, etc.). Markers: `["mulDiv and mulDivUp in same function", "FullMath.mulDiv + FullMath.mulDivRoundingUp pair", "rayDiv and rayDivUp mixed"]`.

A04 PRECISION_TRUNCATION: INCLUDED. `EVM-A04`. Narrowing casts that silently drop high bits. Markers: `["uint256 to uint128 cast", "uint128 to uint64 cast", "SafeCast.toUint128", "SafeCast.toUint96", "SafeCast.toInt128", "int256 to int128", "toUint64", "uint8(x)", "bytes32 truncated to bytes4"]`.

A05 MULT_BEFORE_DIV: INCLUDED. `EVM-A05`. Order-sensitive `a * b / c` that loses precision if divided first or overflows if multiplied first without FullMath. Markers: `["a * b / c (raw)", "no FullMath.mulDiv", "PRBMath missing", "wadMul followed by wadDiv", "amount * rate / PRECISION"]`.

A06 CHECKED_ARITHMETIC_GAP: INCLUDED. `EVM-A06`. `unchecked { }` block wrapping arithmetic that can cross boundary conditions due to caller inputs; also assembly math outside Solidity 0.8 checks. Markers: `["unchecked {", "assembly { add", "assembly { sub", "assembly { mul", "pragma solidity ^0.7", "SafeMath.add without overflow guard above it"]`.

A07 ZERO_AMOUNT_PASSTHROUGH: INCLUDED. `EVM-A07`. Function accepts `amount == 0` without rejecting, allowing dust griefing, event spam, share inflation boundary cases. Markers: `["missing require(amount > 0)", "missing require(shares != 0)", "no zero-guard before _mint", "no zero-guard before _burn", "transfer(..., 0) allowed"]`.

B01 OWNER_ONLY: INCLUDED. `EVM-B01`. Role- or owner-gated state mutator. Markers: `["onlyOwner", "onlyRole(", "hasRole(", "_checkRole", "AccessControl", "Ownable", "Ownable2Step", "msg.sender == owner", "msg.sender == governance", "DEFAULT_ADMIN_ROLE"]`.

B02 SELF_CALLBACK_GATE: INCLUDED. `EVM-B02`. Function only callable when `msg.sender == address(this)` (multicall internals, reentering own context). Markers: `["msg.sender == address(this)", "onlySelf modifier", "require(_msgSender() == address(this))", "Multicall internal callback"]`.

B03 NO_ACCESS_CONTROL: INCLUDED. `EVM-B03`. `external`/`public` state mutator with no sender gate; permissionless entry. Markers: `["external function without modifier", "public function without modifier", "no require(msg.sender)", "anyone-callable state write"]`.

B04 GENESIS_BYPASS: INCLUDED. `EVM-B04`. Initializer, constructor, or first-call-only path that bypasses later restrictions. Markers: `["constructor", "initializer modifier", "reinitializer(", "_disableInitializers", "__X_init", "firstDepositor branch"]`.

B05 PAUSE_GATE: INCLUDED. `EVM-B05`. Pause/circuit-breaker gate. Markers: `["whenNotPaused", "whenPaused", "Pausable", "require(!paused)", "require(!isShutdown)", "ReentrancyGuardPausable"]`.

C01 LOOP_STORAGE_MUTATION: INCLUDED. `EVM-C01`. Storage SSTORE inside a loop body (gas cliff + reordering hazard). Markers: `["SSTORE inside for", "mapping[i] = inside loop", "push inside loop", "balances[x] -= inside loop"]`.

C02 UNBOUNDED_ITERATION: INCLUDED. `EVM-C02`. Loop bound controlled by user-growable array or mapping keyset. Markers: `["for (uint i=0; i<array.length", "while (queue.length)", "enumerable set iteration without cap", "EnumerableSet length as loop bound", "no max iterations constant"]`.

C03 READ_WRITE_GAP: INCLUDED. `EVM-C03`. Read-then-call-then-write on same slot (reentrancy + TOCTOU surface). Markers: `["SLOAD then external call then SSTORE", "cache value, call, write back", "checks-effects-interactions violation"]`.

C04 DELETE_IN_LOOP: INCLUDED. `EVM-C04`. `delete` inside an index-based loop (iteration invariant broken). Markers: `["delete array[i] inside for", "array.pop() inside loop", "EnumerableSet.remove inside iteration", "mapping delete inside for"]`.

C05 COUNTER_INCREMENT: INCLUDED. `EVM-C05`. Monotonic counter (nonce, tokenId, requestId) that may wrap, collide, or leak ordering. Markers: `["nextId++", "nonce++", "_tokenIdTracker.increment()", "Counters.Counter", "unchecked { id++ }"]`.

C06 COLLECT_THEN_ITERATE: INCLUDED. `EVM-C06`. Snapshot a collection to memory then iterate (vs live iteration). Markers: `["copy storage array to memory", "length cached to memory", "address[] memory copy = storageArr"]`.

D01 ORACLE_PRICE_DEP: INCLUDED. `EVM-D01`. Decision depends on price feed. Markers: `["latestRoundData()", "latestAnswer()", "getPrice(", "consult(", "IPyth.getPrice", "getRoundData(", "AggregatorV3Interface"]`.

D02 ORACLE_STALENESS: INCLUDED. `EVM-D02`. Oracle freshness gate with a concrete time window. Markers: `["updatedAt + maxDelay", "block.timestamp - updatedAt", "require(updatedAt >", "HEARTBEAT", "MAX_STALENESS", "publishTime check"]`.

D03 CROSS_CONTRACT_CALL: INCLUDED. `EVM-D03`. Any `.call`, interface call, low-level call, or delegatecall to another contract. Markers: `[".call(", ".staticcall(", ".delegatecall(", "IERC20.transfer(", "safeTransfer(", "Address.functionCall", "interface.method("]`.

D04 QUERY_DEPENDENCY: INCLUDED. `EVM-D04`. Read external contract state whose value may change between read and use. Markers: `["IERC20.balanceOf(", "ICurve.get_virtual_price(", "IVault.totalAssets(", "external view call"]`.

D05 ORACLE_ERROR_SWALLOWED: INCLUDED. `EVM-D05`. Oracle / external call wrapped in try/catch where failure is logged or skipped rather than reverted. Markers: `["try oracle.latestRoundData returns", "try ... catch { continue }", "(bool ok, ) = .call(...); if (!ok)", "catch { emit Error"]`.

E01 FIRST_DEPOSITOR_PATH: INCLUDED. `EVM-E01`. Branch for `totalSupply == 0` (vault inflation vector). Markers: `["if (totalSupply() == 0)", "if (totalAssets() == 0)", "MINIMUM_LIQUIDITY constant", "first deposit mints shares == deposit"]`.

E02 PROPORTIONAL_SHARE: INCLUDED. `EVM-E02`. Share / LP = amount * supply / assets (ERC4626 style). Markers: `["shares = assets * supply / totalAssets", "amount.mulDiv(supply, totalAssets", "_convertToShares", "_convertToAssets"]`.

E03 FEE_COMPUTATION: INCLUDED. `EVM-E03`. Fee as rate * amount with denominator constant. Markers: `["amount * feeBps / 10000", "feeRate * amount / 1e18", "PROTOCOL_FEE_DENOMINATOR", "calcFee("]`.

E04 SLIPPAGE_PROTECTION: INCLUDED. `EVM-E04`. Min out / max in guard supplied by caller. Markers: `["require(amountOut >= minAmountOut)", "amountOutMin", "maxAmountIn", "require(received >= minimum)", "deadline check"]`.

E05 PRICE_FROM_RESERVES: INCLUDED. `EVM-E05`. Price derived from pool reserves (Uni V2 spot). Markers: `["getReserves()", "reserve0 * 1e18 / reserve1", "UniswapV2 quote(", "getAmountOut(reserve0, reserve1)"]`.

E06 PASSIVE_ORDER_GEN: INCLUDED. `EVM-E06`. Protocol-generated (not user-submitted) orders, curves, or auto-rebalance positions. Markers: `["auto-rebalance", "rebalance(", "algorithmic LP placement", "strategy.tend(", "Uniswap V3 auto-LP manager"]`.

E07 CLEARING_PRICE_SELECTION: INCLUDED. `EVM-E07`. Auction or batch-matching price choice. Markers: `["clearingPrice", "settle(", "auctionEnd", "FrankenDAO auction", "batch auction uniform price"]`.

E08 MINIMUM_SIZE_CHECK: INCLUDED. `EVM-E08`. Minimum deposit/withdraw/order size. Markers: `["require(amount >= MIN_DEPOSIT)", "MIN_ORDER_SIZE", "require(shares >= MIN_SHARES)"]`.

F01 CRON_BATCH: INCLUDED. `EVM-F01`. Keeper/upkeep batch-processor. Markers: `["performUpkeep", "checkUpkeep", "keep3r", "Gelato exec", "harvest(", "processQueue(", "rebaseAll("]`.

F02 CANCEL_BEFORE_CREATE: INCLUDED. `EVM-F02`. Same-tx ordering where cancels process before creates (order-book flows). Markers: `["_cancelOrders(...) before _placeOrders(...)", "process cancels then creates in same tx"]`.

F03 MULTI_HOP_CHAIN: INCLUDED. `EVM-F03`. Output of step N feeds step N+1 (swap path, route). Markers: `["path[i] -> path[i+1]", "exactInput(path", "route.length iteration", "multicall(", "Uniswap V3 path encoding"]`.

F04 REPLY_ON_ERROR: INCLUDED. `EVM-F04`. `try/catch` handler that retains partial state on external revert. Markers: `["try ... returns ... catch", "bool success, bytes memory ret = .call", "if (!success) emit Fail"]`.

F05 EARLY_RETURN_BRANCH: INCLUDED. `EVM-F05`. Early `return` that skips later state updates or event emits. Markers: `["if (...) return;", "guard clause before state update", "return 0 before _mint", "short-circuit before accounting"]`.

G01 FUND_VERIFICATION: INCLUDED. `EVM-G01`. Assertion that `msg.value` or received ERC20 equals expected. Markers: `["require(msg.value ==", "balance before/after subtraction", "require(token.balanceOf(this) - before == amount)"]`.

G02 REFUND_CALCULATION: INCLUDED. `EVM-G02`. Excess msg.value or unused input refunded. Markers: `["refund = msg.value - cost", "payable(msg.sender).transfer(excess)", "Address.sendValue(refund)"]`.

G03 MINT_AND_BURN: INCLUDED. `EVM-G03`. Internal `_mint`/`_burn` or totalSupply mutation. Markers: `["_mint(", "_burn(", "totalSupply +=", "ERC20._update", "ERC4626.deposit mints shares"]`.

G04 DUST_ACCUMULATION: INCLUDED. `EVM-G04`. Repeated same-direction rounding inside a batch or per-position loop. Markers: `["per-iteration floor division", "residual dust retained by protocol", "accumulated truncation in fee split"]`.

H01 BLOCK_HEIGHT_DISCRIMINATION: INCLUDED. `EVM-H01`. Same-block vs prior-block distinction. Markers: `["if (createdAt == block.number)", "block.number > lastActionBlock", "sameBlock protection", "flash-sandwich guard on block number"]`.

H02 MAKER_TAKER_SPLIT: INCLUDED. `EVM-H02`. Different fee per order role/timing. Markers: `["makerFee", "takerFee", "isMaker branch", "different fee constant per side"]`.

H03 ORDER_ID_MANIPULATION: INCLUDED. `EVM-H03`. Packed ID encoding for sort key. Markers: `["packed bytes32 ID", "id << bits | data", "abi.encodePacked(price, nonce)", "inverted-priority encoding"]`.

I01 INVARIANT_PRESERVATION: INCLUDED. `EVM-I01`. Explicit invariant check (`x*y>=k`, totalShares tracks totalAssets). Markers: `["require(x * y >= k)", "invariant check", "assert(totalSupply <= cap)", "K invariant"]`.

I02 BALANCE_ACCOUNTING: INCLUDED. `EVM-I02`. Before/after balance reconciliation or `inflows == outflows + fees`. Markers: `["uint256 before = token.balanceOf(this)", "uint256 received = token.balanceOf(this) - before", "balance reconciliation"]`.

All 45 inherited. None excluded, because EVM is the reference baseline for the original taxonomy.

---

## 2. New native categories

Three new categories, each grounded in an EVM-only attack surface that A-I cannot express.

### Category J: Proxy & Upgradeability

Patterns exclusive to EVM's delegatecall-based upgrade model and storage-slot layout.

EVM-J01 DELEGATECALL_TARGET. Category J. Delegatecall to an address whose code or trust boundary is not fully pinned (user-supplied, mutable, or selected from registry). Markers: `["delegatecall(", "Address.functionDelegateCall", "_delegate(implementation)", "proxy fallback delegatecall", "library-as-address delegatecall"]`. typical_direction: favors_user.

EVM-J02 STORAGE_SLOT_COLLISION. Category J. Two layouts (proxy vs implementation, V1 vs V2, parent vs child in multiple-inheritance) write or read the same slot with different semantics. Markers: `["bytes32 private constant _SLOT = keccak256(", "EIP-1967 slot constants", "custom assembly sstore to fixed slot", "struct packed near upgrade boundary", "__gap array sized"]`. typical_direction: favors_protocol.

EVM-J03 INITIALIZER_REENTRY. Category J. `initialize` / `reinitializer(n)` can be re-called, called out of order, or called by unintended actor. Markers: `["initializer modifier", "reinitializer(2)", "_disableInitializers()", "bool initialized flag (not OZ)", "init function without onlyProxy guard"]`. typical_direction: favors_user.

EVM-J04 UUPS_AUTHORIZE_GAP. Category J. `_authorizeUpgrade` missing, empty, or gated by role that lacks timelock. Markers: `["_authorizeUpgrade(address) internal override", "UUPSUpgradeable", "empty _authorizeUpgrade body", "onlyOwner on _authorizeUpgrade"]`. typical_direction: favors_user.

EVM-J05 SELECTOR_CLASH. Category J. Proxy admin function selector collides with implementation function selector, or diamond facet selectors overlap. Markers: `["TransparentUpgradeableProxy admin methods", "diamondCut(", "IDiamondLoupe", "function selector collision"]`. typical_direction: neutral.

EVM-J06 IMPLEMENTATION_SELFDESTRUCT. Category J. Implementation contract has SELFDESTRUCT, arbitrary delegatecall, or ownable state that lets it be bricked, leaving proxy pointing at empty code. Markers: `["selfdestruct(", "assembly { selfdestruct", "delegatecall on implementation without init lock", "unprotected kill() on implementation"]`. typical_direction: favors_user.

### Category K: Low-Level & Assembly

Patterns that live below the Solidity abstraction layer.

EVM-K01 RAW_CALL_RETURN_IGNORED. Category K. Low-level `.call` / `.send` return value discarded (transfer assumed to succeed). Markers: `[".call(", "(bool success, )", "no require(success)", ".send(", ".transfer( on 2300 gas"]`. typical_direction: favors_user.

EVM-K02 ASSEMBLY_MEMORY_UNSAFE. Category K. Inline assembly writes past free memory pointer, reads stale memory, or violates memory safety. Markers: `["assembly {", "mstore(0x40", "free memory pointer not updated", "assembly (\"memory-safe\")", "mload from arbitrary offset"]`. typical_direction: neutral.

EVM-K03 ARBITRARY_CALLDATA_FORWARD. Category K. Function forwards user-supplied target + calldata to `.call` or `.delegatecall` without allowlist. Markers: `["address target, bytes data", "execute(target, data)", "forward low-level call", "multicall with user-controlled targets"]`. typical_direction: favors_user.

EVM-K04 RETURNDATA_BOMB. Category K. External call receives large returndata that is copied unconditionally (gas griefing). Markers: `["returndatacopy(0, 0, returndatasize())", "abi.decode on external return without size guard", "ExcessivelySafeCall missing"]`. typical_direction: favors_user.

EVM-K05 TRANSIENT_STORAGE_LEAK. Category K. `TSTORE` / `TLOAD` (EIP-1153) leaves transient state visible across nested frames within the same tx in a way the caller did not intend. Markers: `["tstore(", "tload(", "transient keyword", "solc >=0.8.24 with transient"]`. typical_direction: neutral.

EVM-K06 CREATE2_ADDRESS_REUSE. Category K. CREATE2 redeployment at same address after SELFDESTRUCT (metamorphic contract), or salted-address predictability used as trust anchor. Markers: `["create2(", "CREATE2_SALT", "precomputeAddress(salt,", "assembly create2(0, ptr,"]`. typical_direction: favors_user.

### Category L: Reentrancy Variants

Patterns that extend the classic reentrancy family beyond a single A-I type would carry.

EVM-L01 CLASSIC_REENTRANCY. Category L. External call in a function that later writes to the same storage the call path can re-read (single-function reentrancy). Markers: `[".call{value:", "ERC20.transfer before state update", "no ReentrancyGuard on payable function", "checks-effects-interactions violated"]`. typical_direction: favors_user.

EVM-L02 CROSS_FUNCTION_REENTRANCY. Category L. Reentrancy into a DIFFERENT function that shares state with the caller; `nonReentrant` on one function only. Markers: `["nonReentrant on withdraw only", "shared balances mapping between guarded/unguarded", "view function returns mid-call stale state"]`. typical_direction: favors_user.

EVM-L03 READ_ONLY_REENTRANCY. Category L. External actor reenters a view/getter of the same protocol (or a dependent consumer) during a callback; consumer trusts the view. Markers: `["get_virtual_price during remove_liquidity callback", "totalAssets() called from callback", "view-only reentrancy on Curve/Balancer pool", "consumer reads pool state mid-call"]`. typical_direction: favors_user.

EVM-L04 ERC777_HOOK_REENTRANCY. Category L. Transfer of ERC777 / ERC1363 / ERC721.safeTransfer / ERC1155 triggers receiver hook that reenters. Markers: `["safeTransfer on ERC721", "_checkOnERC721Received", "tokensReceived hook", "onERC1155Received", "ERC777 send("]`. typical_direction: favors_user.

EVM-L05 CALLBACK_STATE_DIVERGENCE. Category L. Protocol issues a callback (flash loan, swap callback, flash mint) whose body executes while protocol invariants are temporarily broken. Markers: `["uniswapV3SwapCallback", "uniswapV2Call", "flashLoan callback", "onFlashLoan(", "IERC3156FlashBorrower", "executeOperation("]`. typical_direction: favors_user.

EVM-L06 REENTRANCY_GUARD_PROXY_GAP. Category L. `ReentrancyGuard` state sits in implementation storage but proxy pattern or shared diamond facet lets two facets bypass the guard. Markers: `["ReentrancyGuardUpgradeable", "_status slot in facet", "diamond facet without shared guard", "multiple proxies sharing guard slot incorrectly"]`. typical_direction: favors_user.

None of these duplicate A-I. Closest overlaps are:
- J03 vs B04: B04 is the generic "genesis bypass" marker at the entry point; J03 covers the EVM-specific initializer vulnerability surface (reinitializer, re-entry, cross-contract init). Kept separate.
- L01 vs C03: C03 is the structural read-call-write gap; L01 is the exploit primitive (callable re-entry). Keep both so chain analysis sees structural+exploit pair.
- K03 vs D03: D03 is "any external call"; K03 is "external call with user-controlled target AND data". K03 is always a bridge even when D03 is not.

---

## 3. Actor vocabulary

Enumerated values for `actor` field on EVM pieces. Extraction assigns one.

- `any_user`: function is `external`/`public` with no sender gate. Fires on B03 and any J/K/L piece in an unguarded function.
- `owner`: function gated by `Ownable.onlyOwner` or `owner()` equality. Fires on B01 where the role string is owner/admin.
- `non_owner`: precondition specifically excludes owner (e.g., user-side withdraw in a split owner/user flow). Rare; fires when the code branches `if (msg.sender != owner)`.
- `role`: AccessControl / custom role other than owner. Payload may carry the role name. Fires on `onlyRole(...)`.
- `keeper`: automated bot role (KEEPER_ROLE, OPERATOR_ROLE, BOT_ROLE, Chainlink Automation, Gelato). Fires on F01 and on any function behind such a modifier.
- `multisig`: role pinned to a Gnosis Safe or equivalent multi-sig address. Orthogonal to `owner`/`role`; extraction tags `multisig` when the address points to a known Safe.
- `governance`: role controlled by a DAO / Governor contract / timelock. Implies delayed execution.
- `self_callback`: `msg.sender == address(this)`. Fires on B02.
- `delegate`: call frame entered via `delegatecall`; `msg.sender` is the outer caller but execution is in this contract's context. Fires on J01/J04 code paths and on diamond facets.
- `flash_borrower`: call arrives inside a flash-loan callback frame (onFlashLoan, uniswapV3SwapCallback, etc.). Fires on L05 and on any piece whose function is the callback target.
- `bridge_endpoint`: call arrives from a cross-chain messenger (LayerZero endpoint, CCIP router, Wormhole core). Fires on CMI-flagged entry points.
- `initializer`: call is the first-time initialization path (constructor / `initialize` / `reinitializer(n)`). Fires on B04 and J03.
- `protocol_internal`: piece is inside an `internal`/`private` function; not reachable directly, only by composition from another piece.

Extraction rule: when multiple actors could apply, prefer the most restrictive one that the code enforces. `any_user` is the default fallback.

---

## 4. Bridge types

Bridge pieces are connectors in the combinator's graph: they are the types that most commonly chain otherwise-disconnected pieces into an attack path. Rationale per entry.

- EVM-D03 CROSS_CONTRACT_CALL: every external call is a potential hop. Connects state-change pieces in this contract to side effects in another.
- EVM-J01 DELEGATECALL_TARGET: delegatecall re-enters this contract's storage from another code unit; bridges storage pieces to external logic.
- EVM-K03 ARBITRARY_CALLDATA_FORWARD: user-controlled forwarding makes any downstream function reachable from any entry point that holds this piece.
- EVM-L05 CALLBACK_STATE_DIVERGENCE: flash/swap callback frame bridges attacker-controlled logic INTO a transiently inconsistent protocol state.
- EVM-L04 ERC777_HOOK_REENTRANCY: transfer hook bridges a token-movement piece to an attacker-controlled contract mid-function.
- EVM-F01 CRON_BATCH: keeper entry points bridge keeper-only logic to user state; attack chains frequently cross this boundary.
- EVM-F03 MULTI_HOP_CHAIN: path iteration bridges per-hop pieces into a composite flow where rounding / slippage / reserve pieces compound.
- EVM-C03 READ_WRITE_GAP: structural slot that any reentrancy (L01/L02/L03) can latch onto.
- EVM-D01 ORACLE_PRICE_DEP: oracle consumption bridges manipulation pieces (E05, L05) to downstream pricing pieces.
- EVM-B04 GENESIS_BYPASS: initializer bridges a one-time-privileged state write to any later read.

Bridges get a `+0.5` priority in the combinator; non-bridge pieces on their own rarely form chains >2.

---

## 5. Conflicting actor pairs

Pairs that cannot both fire in the same attack path; the combinator prunes combos containing both.

- `owner` + `any_user`: the same call cannot be both owner-only and unpermissioned. (Exception: two separate calls composed in a chain; the combinator still permits the chain if the pieces live in different pieces, but not when the actor is being used to describe a single fired piece.)
- `owner` + `non_owner`: contradictory by definition.
- `owner` + `multisig` (when attributed to the SAME piece): a piece is one or the other, not both. Cross-piece is fine.
- `keeper` + `any_user`: same piece cannot be both permissionless and keeper-only.
- `initializer` + `any_user`: initializer is by construction one-shot; cannot also be general permissionless. (Exception: genuinely unprotected init is covered by B04 with actor `any_user` AND J03 with actor `initializer`; the pair exists across two pieces, not one.)
- `self_callback` + `any_user`: mutually exclusive guards on the same call.
- `bridge_endpoint` + `any_user`: if the function correctly checks endpoint, it is not open to any_user. If it does not check, it is `any_user` with a J/L implication, not `bridge_endpoint`.
- `governance` + `keeper`: governance decisions are not made by bots in the same action; the combinator should not treat a keeper action as governance-delayed.
- `flash_borrower` + `initializer`: init happens once in constructor/initialize, never inside a flash callback frame.
- `protocol_internal` + any external actor: `protocol_internal` means not directly reachable; external actor on the same piece is a contradiction unless composed via another bridge piece.

Cross-piece chains may legitimately contain an owner piece and an any_user piece (setter + consumer). The rule applies to a SINGLE piece's actor tag.

---

## 6. Extra elimination rules

Rules beyond the shared set, specific to EVM.

- EVM-R1: eliminate if every piece in the combo lives in a `view` or `pure` function AND no piece is a bridge that can reach a non-view callee. Reason: view-only combos cannot alter state; worst they do is return wrong data to an off-chain consumer, which if real would be encoded as a separate EVT-style finding.
- EVM-R2: eliminate if the combo's only D01/E05 piece is priced off a `TWAP` / `observe` / `consult` window > 1 block AND the combo does not include L05 or an external flash bridge. Reason: short-window manipulation requires an atomic bridge.
- EVM-R3: eliminate if the combo requires `initializer` actor AND the target has `_disableInitializers()` in its constructor AND there is no J04 (authorize gap) in the same combo. Reason: initializer is provably one-shot and locked.
- EVM-R4: eliminate if the combo chains through delegatecall (J01) but every piece in the target lives behind `onlyOwner` or `onlyProxy` AND no J05 selector clash is in the combo. Reason: delegatecall gadget has no reachable sink.
- EVM-R5: eliminate if the combo contains L01/L02/L03 reentrancy AND every function in the chain carries `nonReentrant` AND the guard slot is not in a J06/J02 (collision) piece. Reason: guard intact.
- EVM-R6: eliminate if the combo's rounding piece (A01/A02/A03/A04/A05/G04) produces a per-call delta below 1 wei of the smallest-decimal token in the flow AND no C01/C02 loop amplifier is in the combo. Reason: sub-wei rounding cannot be extracted without amplification.
- EVM-R7: eliminate if the combo requires `flash_borrower` actor AND the protocol's flash-loan source has a non-zero fee AND the combo's profit trace is empty or negative. Reason: unprofitable flash attack, not a finding.
- EVM-R8: eliminate if the combo's only cross-chain piece is a CMI/CCT marker AND the receiving function checks BOTH `srcEid` and `sender` AND the combo contains no J03 initializer or B03 unchecked entry. Reason: peer auth intact.
- EVM-R9: eliminate if the combo includes E05 spot-reserve pricing but the consuming function's only state write is gated by a slippage piece (E04) with `minAmountOut >= expected - maxSlippageBps` AND the slippage parameter is user-supplied in the same tx. Reason: user's own slippage bound absorbs the manipulation.
- EVM-R10: eliminate if the combo's owner piece (B01) is behind a Timelock with `minDelay` >= 24h AND the combo's user-impact chain relies on a parameter set within that delay window. Reason: users can exit before the change takes effect. Do NOT apply when the combo describes fund theft or when the owner action is a pause/emergency that bypasses timelock.

These fire AFTER the shared elimination set, only to prune false positives that are specifically EVM-shaped.

---

## 7. Scoring weight recommendations

Weights feed the combinator's priority score. Values are integer-safe multipliers on base 100.

| Weight key | EVM value | Shared default | Override? | Note |
|---|---:|---:|---|---|
| `w_bridge` | 150 | 100 | OVERRIDE | Bridges matter more on EVM because delegatecall + callbacks build long chains. |
| `w_favors_user_direction` | 130 | 100 | OVERRIDE | User-profitable direction is the typical exploit shape. |
| `w_favors_protocol_direction` | 90 | 100 | OVERRIDE | Protocol-favoring pieces are usually griefing or sub-wei; lower priority unless amplified. |
| `w_neutral_direction` | 100 | 100 | default | Direction unclear without other pieces. |
| `w_actor_any_user` | 140 | 100 | OVERRIDE | Permissionless entry is the most common attack precondition. |
| `w_actor_flash_borrower` | 135 | 100 | OVERRIDE | Flash context compresses attack window to 1 tx. |
| `w_actor_keeper` | 110 | 100 | OVERRIDE | Keepers add MEV surface but are rate-limited. |
| `w_actor_owner` | 70 | 100 | OVERRIDE | Owner-only rarely produces user-exploitable findings; downweight. |
| `w_actor_governance` | 80 | 100 | OVERRIDE | Timelock softens. |
| `w_actor_initializer` | 120 | 100 | OVERRIDE | Init bugs are one-shot but catastrophic. |
| `w_category_J` | 140 | 100 | NEW | Proxy / upgrade issues score higher due to blast radius. |
| `w_category_K` | 125 | 100 | NEW | Low-level / assembly issues often slip past reviewers. |
| `w_category_L` | 150 | 100 | NEW | Reentrancy remains the highest-yield class; weight highest. |
| `w_chain_length_bonus_per_piece` | 15 | 10 | OVERRIDE | Longer composed chains reward on EVM because of delegatecall/callback composability. |
| `w_dup_piece_penalty` | -30 | -20 | OVERRIDE | Penalize combos with two copies of the same piece harder on EVM. |
| `w_has_oracle_piece` | 115 | 100 | NEW | Oracle piece raises severity ceiling. |
| `w_has_external_call_piece` | 110 | 100 | NEW | Crossing a call boundary broadens blast radius. |

---

## 8. Cross-check notes

`nextup/prompts/evm/generic-security-rules.md`: 17 rules mined. R1 (return type mismatch) feeds EVM-D03/D04 markers and suggests a later type-mismatch refinement. R2 (griefable preconditions) is expressible with B03 + E04/E05 chains already; no new type needed. R3 (transfer side effects) is exactly EVM-L04. R7 (donation DoS) is covered by I02 + G01 + E05 chains; no new type. R8 (cached parameters in multi-step ops) is covered by C03 + C05 composed. R14 (cross-variable invariant) is covered by I01. R15 (flash-loan precondition) is exactly L05 + E05 chains plus the `flash_borrower` actor. R16 (oracle integrity) is covered by D01/D02/D05 and the EVM-R2 elimination rule. R17 (state transition completeness) is covered by C03 + G03 + I01 composed. The rules file validated that no new TYPE is needed for R1/R2/R7/R8/R14/R16/R17; new types were only added where the primitive is EVM-exclusive (delegatecall, assembly, reentrancy variants).

`storage-layout-safety`: mined directly into category J. Memory-vs-storage confusion (SKILL Step 2) maps to J02 STORAGE_SLOT_COLLISION when the confusion crosses a proxy boundary, and otherwise to C03 READ_WRITE_GAP when it is a plain lost-write. Proxy slot overlap (Step 3) is pure J02. Upgrade continuity (Step 3b) is J02 plus J03 INITIALIZER_REENTRY when reinitializer is involved. Assembly slot safety produces J02 or K02 depending on whether the bug is layout or memory.

`event-correctness`: mined. Event bugs (wrong parameter, wrong ordering, missing emit on a branch) are a LOW/INFO-tier surface that the existing C03 + F05 pair already expresses structurally (state write without matching emit is a read-write or early-return pattern). No new type added; event correctness stays a skill-layer concern rather than a taxonomy type.

`cross-chain-message-integrity`: mined. Endpoint authentication gap is B03 + `bridge_endpoint` actor. Peer registry issues are B01 + C03. Replay protection is C05 COUNTER_INCREMENT with a missing-check flavor. Ordering/nonce gaps are C05 + H01. No new type required because the CMI skill's primitives are all expressible; the NEW contribution is the `bridge_endpoint` actor so the combinator can recognize the entry-frame difference.

`oracle-analysis`: mined. Staleness, decimal, zero-return, negative-price, sequencer, TWAP-window, config-bounds are all expressible with D01/D02/D05 + A04 PRECISION_TRUNCATION + I01 INVARIANT_PRESERVATION. No new type. The SKILL's contribution to this design is elimination rule EVM-R2 (TWAP guards atomic manipulation).

`staking-receipt-tokens`: mined. Donation-inflation attacks are the combination E01 FIRST_DEPOSITOR_PATH + I02 BALANCE_ACCOUNTING + L04 hook + the `unsolicited transfer` semantics captured in the EVM-L04 markers. Receipt-token specific side-effects (Rule 3) are L04. No new type; the extraction path is a combo.

`flash-loan-interaction`: mined. Atomic sequence modeling is exactly EVM-L05 CALLBACK_STATE_DIVERGENCE plus the `flash_borrower` actor plus the elimination rule EVM-R7 (profitability gate). Third-party flash manipulation is E05 + D04 composed.

`centralization-risk`: mined. Privilege inventory maps onto B01 + the actor vocabulary (`owner`, `role`, `multisig`, `governance`). Fund-control vs parameter-control distinction is severity-matrix concern, not a taxonomy type. Elimination rule EVM-R10 (timelock) came from this skill.

`migration-analysis`: mined. Token-type transitions (old -> new) are expressible with D03 + D04 + I02 composed. Stranded-asset severity floor is a severity rule (Rule 9 in generic-security-rules), not a taxonomy type. No new type.

`semi-trusted-roles`: mined. Keeper abuse is B01 + F01 + actor `keeper`. No new type; the actor vocabulary carries the semantics.

`fork-ancestry`: mined. Fork detection does not produce pieces directly; it enriches the recon buffer with known-bad patterns from the parent codebase. No type impact. Taxonomy is codebase-agnostic.

`token-flow-tracing`: mined. Entry/exit tracking is G01/G02/G03 + I02. Self-transfer accounting is a specific combo (G03 + I02 + C03). No new type.

`cross-chain-timing`: mined. Stale-state arbitrage across sync windows is D04 QUERY_DEPENDENCY + H01 BLOCK_HEIGHT_DISCRIMINATION + the `bridge_endpoint` actor. No new type.

`external-precondition-audit`, `economic-design-audit`, `share-allocation-fairness`, `temporal-parameter-staleness`, `verification-protocol`, `zero-state-return`: all covered by existing A-I primitives composed via the combinator; none motivate a new type.

Coverage gap audit: the only skill families that demanded NEW taxonomy types were (1) proxy / upgradeability primitives (J category), (2) low-level and assembly primitives (K category), and (3) reentrancy variants beyond the single "read-write gap" abstraction (L category). Every other skill's threat surface decomposes cleanly into A-I + the new actor vocabulary + the elimination/scoring overrides.
