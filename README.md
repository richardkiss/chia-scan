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
