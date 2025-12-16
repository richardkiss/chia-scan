# chia-scan

Tools for Chia blockchain analysis.

## Installation

```bash
# Using uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Tools

### mod-hashes

Analyze puzzle MOD hashes in a block range. This tool reads blocks from the blockchain database, extracts puzzle reveals, uncurries them, and counts occurrences of each MOD template hash.

```bash
chia-scan mod-hashes --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                     --start 5000000 --end 5010000
```

Options:
- `--db PATH` - Path to blockchain database (required)
- `--start HEIGHT` - Start block height, inclusive (required)
- `--end HEIGHT` - End block height, inclusive (required)
- `--top N` - Show top N MOD hashes (default: 50)
- `--workers N` - Number of parallel workers (default: 4)
- `--save-unknown PATH` - Directory to save unknown MOD puzzles as `.clvm.hex` files
- `--debug` - Show debug information about blocks and spends

Example output:
```
MOD Hash                                                            Count  Label
──────────────────────────────────────────────────────────────────────────────────────────
e9aaa49f45bad5c889b86ee3341550c155cfdd10c3a6757de618d20612fffd52    71708  p2_delegated_puzzle_or_hidden_puzzle
37bef360ee858133b69d595a906dc45d01af50379dad515eb9518abb7c1d2a7a      860  cat_puzzle
24e044101e57b3d8c908b8a38ad57848afd29d3eecc439dba45f4412df4954fd      385  singleton_top_layer
adb656e0211e2ab4f42069a4c5efc80dc907e7062be08bf1628c8e5b6d94d25b      366  p2_singleton_or_delayed_puzhash
7faa3253bfddd1e0decb0906b2dc6247bbc4cf608f58345d173adb63e8b47c9f      288  singleton_top_layer_v1_1
9a6c5ff6689b900c6c5d2dddd84b0ff5492e9ca92228beca280832e438c273df       65
...
──────────────────────────────────────────────────────────────────────────────────────────
Total unique MODs: 29
Total spends analyzed: 73823
```

#### Saving Unknown MODs

Use `--save-unknown` to save unrecognized puzzle MODs for later analysis:

```bash
chia-scan mod-hashes --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                     --start 5000000 --end 5010000 \
                     --save-unknown ./unknown_mods
```

Each unknown MOD is saved as `{hash}.clvm.hex` containing hex-encoded serialized CLVM. You can disassemble them with:

```bash
# Using brun
brun -d $(cat unknown_mods/9a6c5ff6689b900c6c5d2dddd84b0ff5492e9ca92228beca280832e438c273df.clvm.hex)
```

---

### list-blocks

List blocks with their heights and compressed sizes. Useful for finding large or interesting blocks to analyze.

```bash
# List all blocks with size >= 100KB
chia-scan list-blocks --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                      --min-size 100k

# List top 20 largest blocks
chia-scan list-blocks --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                      --top 20 --sort size --desc

# List blocks in a height range
chia-scan list-blocks --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                      --start 5000000 --end 5001000
```

Options:
- `--db PATH` - Path to blockchain database (required)
- `--start HEIGHT` - Start block height (inclusive)
- `--end HEIGHT` - End block height (inclusive)
- `--min-size SIZE` - Minimum compressed block size (e.g., '100k', '1M')
- `--max-size SIZE` - Maximum compressed block size
- `--top N` - Show only top N blocks
- `--sort [height|size]` - Sort by height or size (default: height)
- `--desc` - Sort in descending order

---

### extract-blocks

Extract blocks or generators from the blockchain database to binary files.

```bash
# Extract generators for a height range
chia-scan extract-blocks --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                         -o ./generators --height 5000000-5001000 --generator-only

# Extract large blocks (compressed size >= 100KB)
chia-scan extract-blocks --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                         -o ./large_blocks --size 100k- --generator-only

# Extract specific heights from a file
chia-scan extract-blocks --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
                         -o ./blocks --heights-file heights.txt
```

Options:
- `--db PATH` - Path to blockchain database (required)
- `-o, --output PATH` - Directory to write extracted files (required)
- `--height RANGE` - Block height range (e.g., '1000-2000', '1000-', '-2000')
- `--heights-file PATH` - File with list of heights, or '-' for stdin
- `--size RANGE` - Block size range (e.g., '100k-1M'). Supports k, M, G suffixes.
- `--generator-only` - Extract only the generator portion (not full blocks)
- `--decompress/--no-decompress` - Decompress blocks before writing (default: decompress)

Output files are named:
- Generators: `generator_{height}_{hash}.bin`
- Blocks: `block_{height}_{hash}.bin` or `.bin.zstd` if compressed

---

### build-synthetic

Build a synthetic generator from real spends for compression testing. This extracts spends from multiple block generators, filters out spends with abnormally large atoms (NFTs, JPEGs, etc.), and combines them into a single generator.

```bash
# Build with 1000 spends (default)
chia-scan build-synthetic -i ./generators -o synthetic.bin

# Build targeting ~1MB serialized size
chia-scan build-synthetic -i ./generators -o synthetic.bin --target-size 1M

# Filter out spends with atoms > 500 bytes (stricter NFT filtering)
chia-scan build-synthetic -i ./generators -o synthetic.bin --max-atom-size 500

# Just show statistics without writing
chia-scan build-synthetic -i ./generators --stats-only
```

Options:
- `-i, --input PATH` - Directory containing generator `.bin` files (required)
- `-o, --output PATH` - Output file path (default: synthetic_generator.bin)
- `--max-atom-size N` - Maximum atom size to allow (default: 1000 bytes)
- `--target-spends N` - Target number of spends to include
- `--target-size SIZE` - Target serialized size (e.g., '1M', '500K')
- `--stats-only` - Only print statistics, don't write output

---

## Typical Workflow

1. **Find interesting blocks** using `list-blocks`:
   ```bash
   chia-scan list-blocks --db blockchain.sqlite --min-size 50k --top 100 --sort size --desc
   ```

2. **Extract generators** from those blocks:
   ```bash
   chia-scan extract-blocks --db blockchain.sqlite -o ./generators \
                            --size 50k- --generator-only
   ```

3. **Analyze MOD usage** in a block range:
   ```bash
   chia-scan mod-hashes --db blockchain.sqlite --start 5000000 --end 5010000
   ```

4. **Build synthetic generators** for testing:
   ```bash
   chia-scan build-synthetic -i ./generators -o synthetic.bin --target-size 1M
   ```

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src
```

## License

MIT
