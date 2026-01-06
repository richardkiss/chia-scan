# Chia Codebase Quick Reference

## chia_rs (Rust + Python bindings)
- **Generator execution**: `chia_rs.run_block_generator()` / `run_block_generator2()` 
  - Returns `(error_code, SpendBundleConditions)` - conditions only, no puzzle reveals
- **Get puzzle for coin**: `chia_rs.get_puzzle_and_solution_for_coin2(generator, block_refs, max_cost, coin, flags)` → `(Program, Program)`
- **Types**: `SpendBundleConditions.spends: list[SpendConditions]`, `CoinSpend` has `puzzle_reveal: Program`
- **Location**: `main/wheel/python/chia_rs/chia_rs.pyi` for type stubs

## clvm_rs (CLVM runtime + Python)
- **Program class**: `clvm_rs.Program` - main CLVM object
- **Uncurrying**: `program.uncurry()` → `(mod: Program, args: Optional[List[Program]])`
- **Tree hash**: `program.tree_hash()` → `bytes`
- **Curry**: `program.curry(*args)` → `Program`
- **Location**: `main/wheel/python/clvm_rs/program.py`

## chia-blockchain
### DB Schema (`main/chia/full_node/block_store.py`)
- Table: `full_blocks` - columns: `header_hash`, `prev_hash`, `height`, `block` (zstd compressed), `in_main_chain`
- Blocks stored as zstd-compressed `FullBlock` bytes
- Generator: `FullBlock.transactions_generator` (can be None for non-tx blocks)
- Query: `SELECT block FROM full_blocks WHERE height >= ? AND height <= ? AND in_main_chain=1`

### Known Puzzle MODs (`main/chia/wallet/`)
| Puzzle | Location |
|--------|----------|
| Standard (p2_delegated) | `puzzles/p2_delegated_puzzle_or_hidden_puzzle.py` → `MOD` |
| CAT | `cat_wallet/cat_utils.py` → `CAT_MOD`, `CAT_MOD_HASH` |
| Singleton | `puzzles/singleton_top_layer_v1_1.py` → `SINGLETON_MOD`, `SINGLETON_MOD_HASH` |
| NFT State Layer | `nft_wallet/nft_puzzles.py` → `NFT_STATE_LAYER_MOD` |
| Offer/Settlement | `trading/offer.py` → `OFFER_MOD`, `OFFER_MOD_HASH` |
| DID | `did_wallet/` |

### Puzzle Binaries
- From `chia_puzzles_py` package (precompiled .hex files)
- Or `main/chia/wallet/puzzles/*.clsp` (source)

## Key Workflow for MOD Analysis
1. Query `full_blocks` by height range, decompress with zstd
2. Parse `FullBlock.from_bytes()`, get `transactions_generator`
3. For each coin in block, call `get_puzzle_and_solution_for_coin2()` to get puzzle_reveal
4. Call `Program(puzzle_reveal).uncurry()` → `(mod, args)`
5. `mod.tree_hash()` → MOD hash
