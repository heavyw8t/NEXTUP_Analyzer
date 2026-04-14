# Solidity / EVM Pattern Hints

Language-specific markers for puzzle piece extraction in Solidity smart contracts.

## Arithmetic & Precision (Category A)

- **Floor rounding**: Integer division `a / b` (always floors in Solidity), `mulDiv(a, b, c)`, `FullMath.mulDiv`
- **Ceil rounding**: `mulDivUp`, `ceilDiv`, `(a + b - 1) / b`, `Math.ceilDiv`
- **Precision loss**: Downcasting `uint256` to `uint128/uint96/uint64`, `SafeCast`, decimal scaling `/ 1e18`
- **Unchecked ops**: `unchecked { }` blocks, inline assembly math, pre-0.8.0 arithmetic
- **Zero checks**: Missing `require(amount > 0)`, no zero-address check `require(addr != address(0))`

## Access Control (Category B)

- **Owner check**: `onlyOwner`, `onlyAdmin`, `onlyRole(ROLE)`, `msg.sender == owner()`, `Ownable`, `AccessControl`
- **Self-callback**: `msg.sender == address(this)`, `onlySelf` modifier
- **No check**: `external`/`public` functions without access modifiers that modify state
- **Pause**: `whenNotPaused`, `Pausable`, `require(!paused())`

## State & Storage (Category C)

- **Storage in loop**: `storage[i] = value` inside `for`/`while`, `mapping` write in loop
- **Unbounded iteration**: `for(i=0; i<array.length; i++)` on dynamic array, `while(queue.length > 0)`
- **Read-write gap**: State read → external call → state write (classic reentrancy pattern)
- **Delete in loop**: `delete array[i]` or `mapping` removal inside iteration
- **Counter**: `_tokenIds++`, `nonce++`, `Counters.increment`

## External Dependencies (Category D)

- **Oracle**: `latestRoundData()`, `getPrice()`, `consult()`, Chainlink/Pyth/UMA
- **Staleness**: `updatedAt + MAX_DELAY > block.timestamp`, `require(answeredInRound >= roundId)`
- **External call**: `.call()`, `.transfer()`, `.send()`, `IERC20.safeTransfer`, interface calls
- **Balance check**: `IERC20.balanceOf(address(this))` (manipulable via donation)

## Economic Logic (Category E)

- **First depositor**: `totalSupply() == 0`, `if(_totalSupply == 0)`
- **Share calculation**: `amount * totalSupply / totalAssets()`, `convertToShares`, `convertToAssets`
- **Fee**: `amount * feeRate / FEE_DENOMINATOR`, `fee = amount.mulDiv(rate, PRECISION)`
- **Slippage**: `require(amountOut >= minAmountOut)`, `amountOutMin`, `deadline`
- **Price from reserves**: `reserve0 * 1e18 / reserve1`, `getAmountOut`, `quote`

## Control Flow (Category F)

- **Keeper/bot**: `performUpkeep`, `checkUpkeep`, keeper pattern, relayer
- **Callback**: `uniswapV3SwapCallback`, `flashCallback`, `onFlashLoan`
- **Multi-hop**: `exactInput(path)`, `swapExactTokensForTokens(path)`
- **Try/catch**: `try external.call() { } catch { }` -- partial state commit risk

## Token Handling (Category G)

- **Fund check**: `require(msg.value == amount)`, balance-of before/after
- **Refund**: `msg.value - cost` sent back, `safeTransfer(msg.sender, excess)`
- **Mint/Burn**: `_mint()`, `_burn()`, `totalSupply` modification
- **Approval**: `approve`, `permit`, `increaseAllowance` (front-runnable)
