# vibed-chia-tools

A collection of tools for analyzing and working with the Chia blockchain.

---

## Tool 1: MOD Hash Analyzer

Analyzes Chia blockchain data to categorize puzzles by their MOD (module template) hashes. Reads directly from `mainnet.db`, extracts and runs generators, then uncurries each puzzle to identify the underlying MOD template.

### Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│ mainnet.db  │────▶│  Block       │────▶│   Puzzle    │────▶│  MOD Hash    │
│  (SQLite)   │     │  Reader      │     │  Extractor  │     │  Counter     │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
```

### Implementation Details (Discovered)

**Database Access:**
- Table: `full_blocks`, column: `block` (zstd compressed)
- Query: `SELECT block FROM full_blocks WHERE height >= ? AND height <= ? AND in_main_chain=1`
- Decompress with `zstd.decompress()`, parse with `FullBlock.from_bytes()`
- Generator is at `full_block.transactions_generator` (None for non-tx blocks)

**Getting Puzzle Reveals:**
- Use `chia_rs.get_puzzle_and_solution_for_coin2(generator, block_refs, max_cost, coin, flags)`
- Returns `(puzzle: Program, solution: Program)`
- Need to iterate over all coins spent in the block

**Uncurrying:**
- Use `clvm_rs.Program` class
- `puzzle.uncurry()` → `(mod: Program, args: Optional[List[Program]])`
- If `args is None`, puzzle is not curried (MOD = puzzle itself)
- `mod.tree_hash()` → 32-byte MOD hash

**Dependencies:**
```toml
dependencies = [
    "chia-rs",       # Generator execution, get_puzzle_and_solution_for_coin2
    "clvm-rs",       # Program.uncurry(), tree_hash()
    "zstd",          # Block decompression
    "click",         # CLI
]
```

### Implementation Plan

- [x] **Phase 1: Database Reader**
  - [x] Connect to mainnet.db (SQLite, read-only)
  - [x] Query blocks by height range (main chain only)
  - [x] Decompress and parse FullBlock
  - [x] Extract generator + generator_ref_list

- [x] **Phase 2: Puzzle Extraction**
  - [x] Get list of spent coins from SpendBundleConditions
  - [x] For each coin, call `get_puzzle_and_solution_for_coin2()`
  - [x] Collect all puzzle reveals

- [x] **Phase 3: MOD Analysis**
  - [x] Uncurry each puzzle
  - [x] Compute tree_hash of MOD
  - [x] Aggregate counts by MOD hash

- [x] **Phase 4: CLI & Output**
  - [x] CLI: `vibed-chia mod-hashes --db PATH --start HEIGHT --end HEIGHT`
  - [x] Table output with counts
  - [x] Label known MODs (p2_delegated, CAT, singleton, NFT, DID, etc.) - 30+ puzzles labeled

### Known MOD Hashes (for labeling)

| Name | Source |
|------|--------|
| p2_delegated_puzzle_or_hidden_puzzle | `chia.wallet.puzzles.p2_delegated_puzzle_or_hidden_puzzle.MOD` |
| CAT2 | `chia.wallet.cat_wallet.cat_utils.CAT_MOD_HASH` |
| Singleton | `chia.wallet.puzzles.singleton_top_layer_v1_1.SINGLETON_MOD_HASH` |
| NFT State Layer | `chia.wallet.nft_wallet.nft_puzzles.NFT_STATE_LAYER_MOD` |
| Offer/Settlement | `chia.wallet.trading.offer.OFFER_MOD_HASH` |

### Example Usage

```bash
# Analyze blocks 1,000,000 to 1,001,000
chia-scan mod-hashes --db ~/.chia/mainnet/db/blockchain_v2_mainnet.db \
                     --start 1000000 --end 1001000

# Output:
# MOD Hash                                                          Count   Label
# ────────────────────────────────────────────────────────────────────────────────
# e9aaa49f45bad5c889b86ee3341550c155cfdd10c3a6757de618d20612fffd52  45231   p2_delegated
# 72dec062874cd4d3aab892a0906688a1ae412b0109982e1797a170add88bdcdc  12453   CAT2
# ...
```

### Open Questions

1. **Block refs**: When calling `get_puzzle_and_solution_for_coin2`, we need `block_refs` (generators from referenced blocks). How do we get `transactions_generator_ref_list` and fetch those generators?

2. **Coin enumeration**: How do we know which coins are spent in a block without running the generator first? May need to:
   - Run `run_block_generator()` first to get `SpendConditions` list (has `coin_id`, `parent_id`, `puzzle_hash`, `amount`)
   - Then call `get_puzzle_and_solution_for_coin2()` for each

---

## Future Tools (Ideas)

- [ ] **Coin Tracer** - Trace coin lineage through the blockchain
- [ ] **Mempool Analyzer** - Analyze pending transactions
- [ ] **Puzzle Decompiler** - Decompile CLVM to readable Chialisp
- [ ] **Block Stats** - Aggregate statistics per block/range
