"""CLI for MOD hash analysis."""

from __future__ import annotations

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    # Create output directory if saving unknowns
    if save_unknown_dir:
        unknown_dir = Path(save_unknown_dir)
        unknown_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"Saving unknown MODs to: {unknown_dir}")

    def process_block(
        block: BlockData, block_refs: list[bytes]
    ) -> tuple[int, list[tuple[bytes, bytes]], int, int]:
        """Process a single block.

        Returns (height, [(mod_hash, mod_bytes), ...], spend_count, error_count).
        """
        if block.generator is None:
            return (block.height, [], 0, 0)

        # Run the generator
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
            return (block.height, [], 0, 1)  # generator error

        # Parse generator as Program for puzzle extraction
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
                mod_hash = mod.tree_hash()
                mod_bytes = bytes(mod)
                mod_data.append((mod_hash, mod_bytes))
            except Exception:
                local_errors += 1

        return (block.height, mod_data, len(spend_result.spends), local_errors)

    # First pass: read blocks and resolve refs (serial, I/O bound)
    click.echo("Loading blocks from database...")
    blocks_to_process: list[tuple[BlockData, list[bytes]]] = []

    for block in iterate_blocks(db_path, start_height, end_height):
        if block.generator is None:
            continue

        # Resolve generator refs
        block_refs: list[bytes] = []
        if block.generator_ref_list:
            ref_gens = get_generators_for_refs(db_path, block.generator_ref_list)
            block_refs = [ref_gens.get(h, b"") for h in block.generator_ref_list]

        blocks_to_process.append((block, block_refs))

    click.echo(f"Loaded {len(blocks_to_process)} blocks with generators.")
    click.echo()

    # Second pass: process blocks in parallel (CPU bound)
    mod_counts: Counter[bytes] = Counter()
    blocks_processed = 0
    blocks_with_spends = 0
    spends_processed = 0
    errors = 0
    generator_errors = 0

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(process_block, block, refs): block.height
            for block, refs in blocks_to_process
        }

        # Process results as they complete
        for future in as_completed(futures):
            blocks_processed += 1

            if blocks_processed % 100 == 0:
                click.echo(
                    f"\rProcessed {blocks_processed}/{len(blocks_to_process)} blocks, "
                    f"{spends_processed} spends...",
                    nl=False,
                )
                sys.stdout.flush()

            try:
                height, mod_data, spend_count, block_errors = future.result()

                if mod_data:
                    blocks_with_spends += 1
                    spends_processed += len(mod_data)
                    if debug:
                        click.echo(f"  Block {height}: {len(mod_data)} spends")

                    for mod_hash, mod_bytes in mod_data:
                        mod_counts[mod_hash] += 1

                        # Save unknown MODs if requested
                        if (
                            save_unknown_dir
                            and mod_hash not in KNOWN_MODS
                            and mod_hash not in saved_unknown_mods
                        ):
                            saved_unknown_mods.add(mod_hash)
                            filepath = unknown_dir / f"{mod_hash.hex()}.clvm.hex"
                            filepath.write_text(mod_bytes.hex())

                if block_errors > 0:
                    if spend_count == 0:
                        generator_errors += 1
                    else:
                        errors += block_errors

            except Exception as e:
                height = futures[future]
                click.echo(f"\nError at block {height}: {e}", err=True)
                errors += 1

    click.echo(
        f"\rProcessed {blocks_processed}/{len(blocks_to_process)} blocks, "
        f"{spends_processed} spends.    "
    )
    click.echo()

    # Sort by count descending
    sorted_results = sorted(mod_counts.items(), key=lambda x: x[1], reverse=True)

    # Print results
    click.echo(f"{'MOD Hash':<66} {'Count':>10}  Label")
    click.echo("─" * 90)

    for mod_hash, count in sorted_results[:top_n]:
        label = get_mod_label(mod_hash)
        click.echo(f"{mod_hash.hex():<66} {count:>10}  {label}")

    click.echo("─" * 90)
    click.echo(f"Total unique MODs: {len(mod_counts)}")
    click.echo(f"Total spends analyzed: {spends_processed}")
    click.echo(f"Blocks with generators: {blocks_processed}")
    click.echo(f"Blocks with spends: {blocks_with_spends}")
    if generator_errors > 0:
        click.echo(f"Generator errors: {generator_errors}")
    if errors > 0:
        click.echo(f"Spend processing errors: {errors}")
    if save_unknown_dir:
        click.echo(f"Unknown MODs saved: {len(saved_unknown_mods)}")
