"""CLI for MOD hash analysis."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

import click

from ..known_mods import KNOWN_MODS, get_mod_label
from ..utils import DEFAULT_DB_PATH
from .db_reader import BlockData, get_generators_for_refs, iterate_blocks


@click.command()
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    type=click.Path(exists=True),
    show_default=True,
    help="Path to blockchain database",
)
@click.option(
    "--start",
    "start_height",
    required=True,
    type=int,
    help="Start block height (inclusive)",
)
@click.option(
    "--end",
    "end_height",
    required=True,
    type=int,
    help="End block height (inclusive)",
)
@click.option(
    "--top",
    "top_n",
    default=50,
    type=int,
    help="Show top N MOD hashes (default: 50)",
)
@click.option(
    "--workers",
    "num_workers",
    default=4,
    type=int,
    help="Number of parallel workers (default: 4)",
)
@click.option(
    "--save-unknown",
    "save_unknown_dir",
    type=click.Path(),
    help="Directory to save unknown MOD puzzles as .clvm.hex files",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Show debug information about blocks and spends",
)
def mod_hashes(
    db_path: str,
    start_height: int,
    end_height: int,
    top_n: int,
    num_workers: int,
    save_unknown_dir: str | None,
    debug: bool,
) -> None:
    """Analyze puzzle MOD hashes in a block range.

    Reads blocks from the database, extracts puzzle reveals, uncurries them,
    and counts occurrences of each MOD template hash.
    """
    # Defer heavy imports until command runs
    from chia_rs.sized_ints import uint64

    from chia_rs import (
        DONT_VALIDATE_SIGNATURE,
        Coin,
        G2Element,
        Program,
        get_puzzle_and_solution_for_coin2,
        run_block_generator2,
    )
    from clvm_rs import Program as CLVMProgram

    from ..constants import MAINNET_CONSTANTS

    click.echo(f"Analyzing blocks {start_height} to {end_height}...")
    click.echo(f"Database: {db_path}")
    click.echo(f"Workers: {num_workers}")
    click.echo()

    max_cost = 0xFFFFFFFFFFFFFFFF

    # Track unknown MODs we've already saved (to avoid duplicates)
    saved_unknown_mods: set[bytes] = set()
    unknown_dir: Path | None = None

    if save_unknown_dir:
        unknown_dir = Path(save_unknown_dir)
        unknown_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"Saving unknown MODs to: {unknown_dir}")

    # Result type from process_block
    BlockResult = tuple[int, list[tuple[bytes, bytes]], int, int]

    def process_block(item: tuple[BlockData, list[bytes]]) -> BlockResult:
        """Process a single block. Returns (height, mod_data, spend_count, errors)."""
        block, block_refs = item

        if block.generator is None:
            return (block.height, [], 0, 0)

        err, spend_result = run_block_generator2(
            block.generator,
            block_refs,
            max_cost,
            DONT_VALIDATE_SIGNATURE,
            G2Element(),
            None,
            MAINNET_CONSTANTS,
        )

        if err is not None or spend_result is None:
            return (block.height, [], 0, 1)

        generator_program = Program.from_bytes(block.generator)
        mod_data: list[tuple[bytes, bytes]] = []
        local_errors = 0

        for spend in spend_result.spends:
            try:
                coin = Coin(spend.parent_id, spend.puzzle_hash, uint64(spend.coin_amount))
                puzzle, _ = get_puzzle_and_solution_for_coin2(
                    generator_program, block_refs, max_cost, coin, 0
                )
                clvm_puzzle = CLVMProgram.from_bytes(bytes(puzzle))
                mod, _ = clvm_puzzle.uncurry()
                mod_data.append((mod.tree_hash(), bytes(mod)))
            except Exception:
                local_errors += 1

        return (block.height, mod_data, len(spend_result.spends), local_errors)

    # Accumulators
    mod_counts: Counter[bytes] = Counter()
    stats = {"blocks": 0, "blocks_with_spends": 0, "spends": 0, "errors": 0, "gen_errors": 0}

    def handle_result(result: BlockResult) -> None:
        """Handle result from a processed block."""
        height, mod_data, spend_count, block_errors = result
        stats["blocks"] += 1

        if mod_data:
            stats["blocks_with_spends"] += 1
            stats["spends"] += len(mod_data)
            if debug:
                click.echo(f"  Block {height}: {len(mod_data)} spends")

            for mod_hash, mod_bytes in mod_data:
                mod_counts[mod_hash] += 1

                is_unknown = mod_hash not in KNOWN_MODS and mod_hash not in saved_unknown_mods
                if unknown_dir and is_unknown:
                    saved_unknown_mods.add(mod_hash)
                    (unknown_dir / f"{mod_hash.hex()}.clvm.hex").write_text(mod_bytes.hex())

        if block_errors > 0:
            if spend_count == 0:
                stats["gen_errors"] += 1
            else:
                stats["errors"] += block_errors

    def block_items():
        """Yield (block, refs) tuples for blocks with generators."""
        for block in iterate_blocks(db_path, start_height, end_height):
            if block.generator is None:
                continue
            block_refs: list[bytes] = []
            if block.generator_ref_list:
                ref_gens = get_generators_for_refs(db_path, block.generator_ref_list)
                block_refs = [ref_gens.get(h, b"") for h in block.generator_ref_list]
            yield (block, block_refs)

    click.echo("Processing blocks...")
    buffersize = num_workers * 2

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        pending: set[Future] = set()

        for item in block_items():
            pending.add(executor.submit(process_block, item))

            while len(pending) >= buffersize:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    result = future.result()
                    click.echo(f"\rBlock {result[0]}...", nl=False)
                    handle_result(result)

        # Drain remaining
        for future in pending:
            result = future.result()
            click.echo(f"\rBlock {result[0]}...", nl=False)
            handle_result(result)

    click.echo(f"\rProcessed {stats['blocks']} blocks, {stats['spends']} spends.          ")
    click.echo()

    # Print results
    sorted_results = sorted(mod_counts.items(), key=lambda x: x[1], reverse=True)

    click.echo(f"{'MOD Hash':<66} {'Count':>10}  Label")
    click.echo("─" * 90)

    for mod_hash, count in sorted_results[:top_n]:
        label = get_mod_label(mod_hash)
        click.echo(f"{mod_hash.hex():<66} {count:>10}  {label}")

    click.echo("─" * 90)
    click.echo(f"Total unique MODs: {len(mod_counts)}")
    click.echo(f"Total spends analyzed: {stats['spends']}")
    click.echo(f"Blocks with generators: {stats['blocks']}")
    click.echo(f"Blocks with spends: {stats['blocks_with_spends']}")
    if stats["gen_errors"] > 0:
        click.echo(f"Generator errors: {stats['gen_errors']}")
    if stats["errors"] > 0:
        click.echo(f"Spend processing errors: {stats['errors']}")
    if save_unknown_dir:
        click.echo(f"Unknown MODs saved: {len(saved_unknown_mods)}")
