"""Core analysis logic for MOD hash extraction.

This module provides programmatic access to MOD hash analysis.
For CLI usage, see the `mod_hashes` command.
"""

from __future__ import annotations

import multiprocessing as mp
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from typing import TYPE_CHECKING

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
from .db_reader import BlockData, BlockReader, get_generators_for_refs, iterate_blocks

if TYPE_CHECKING:
    from collections.abc import Callable

# Max cost for running generators
MAX_COST = 0xFFFFFFFFFFFFFFFF


def _analyze_block_worker(
    generator: bytes,
    block_refs: list[bytes],
    height: int,
) -> tuple[int, list[bytes]]:
    """Worker function for parallel block analysis."""
    # Import here to work in subprocess
    from chia_rs import (
        DONT_VALIDATE_SIGNATURE,
        Coin,
        G2Element,
        Program,
        get_puzzle_and_solution_for_coin2,
        run_block_generator2,
    )
    from chia_rs.sized_ints import uint64
    from clvm_rs import Program as CLVMProgram

    from ..constants import MAINNET_CONSTANTS

    max_cost = 0xFFFFFFFFFFFFFFFF

    err, spend_result = run_block_generator2(
        generator,
        block_refs,
        max_cost,
        DONT_VALIDATE_SIGNATURE,
        G2Element(),
        None,
        MAINNET_CONSTANTS,
    )

    if err is not None or spend_result is None:
        return (height, [])

    generator_program = Program.from_bytes(generator)
    mod_hashes: list[bytes] = []

    for spend in spend_result.spends:
        try:
            coin = Coin(spend.parent_id, spend.puzzle_hash, uint64(spend.coin_amount))
            puzzle, _ = get_puzzle_and_solution_for_coin2(
                generator_program, block_refs, max_cost, coin, 0
            )
            clvm_puzzle = CLVMProgram.from_bytes(bytes(puzzle))
            mod, _ = clvm_puzzle.uncurry()
            mod_hashes.append(mod.tree_hash())
        except Exception:
            continue

    return (height, mod_hashes)


def analyze_block_range(
    db_path: str,
    start_height: int,
    end_height: int,
    progress_callback: Callable[[int, int], None] | None = None,
    num_workers: int | None = None,
    batch_size: int = 500,
    cache_size: int = 2000,
) -> dict[bytes, int]:
    """Analyze MOD hashes for all spends in a block range.

    Uses multiprocessing for parallel CLVM execution.

    Args:
        db_path: Path to the blockchain database
        start_height: Start height (inclusive)
        end_height: End height (inclusive)
        progress_callback: Optional callback(blocks_processed, spends_processed)
        num_workers: Number of worker processes (default: CPU count)
        batch_size: Blocks to prefetch at a time
        cache_size: Generator ref cache size

    Returns:
        Dict mapping MOD hash to occurrence count
    """
    if num_workers is None:
        num_workers = mp.cpu_count()

    mod_counts: Counter[bytes] = Counter()
    blocks_processed = 0
    spends_processed = 0

    buffer_size = num_workers * 4

    with (
        BlockReader(db_path, cache_size=cache_size) as reader,
        ProcessPoolExecutor(max_workers=num_workers) as executor,
    ):
        pending: set[Future[tuple[int, list[bytes]]]] = set()

        for block, block_refs in reader.iterate_blocks_with_refs(
            start_height, end_height, batch_size=batch_size
        ):
            future = executor.submit(
                _analyze_block_worker,
                block.generator,
                block_refs,
                block.height,
            )
            pending.add(future)

            while len(pending) >= buffer_size:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    height, block_mods = future.result()
                    mod_counts.update(block_mods)
                    blocks_processed += 1
                    spends_processed += len(block_mods)

                    if progress_callback and blocks_processed % 100 == 0:
                        progress_callback(blocks_processed, spends_processed)

        # Drain remaining
        for future in pending:
            height, block_mods = future.result()
            mod_counts.update(block_mods)
            blocks_processed += 1
            spends_processed += len(block_mods)

    return dict(mod_counts)


def analyze_block(db_path: str, block: BlockData) -> list[bytes]:
    """Analyze a single block and return list of MOD hashes.

    Args:
        db_path: Path to database (for fetching ref generators)
        block: Block data to analyze

    Returns:
        List of MOD hashes for all spends in the block
    """
    if block.generator is None:
        return []

    # Fetch referenced generators if needed
    block_refs: list[bytes] = []
    if block.generator_ref_list:
        ref_gens = get_generators_for_refs(db_path, block.generator_ref_list)
        block_refs = [ref_gens.get(h, b"") for h in block.generator_ref_list]

    # Parse generator as Program
    generator_program = Program.from_bytes(block.generator)

    # Run the generator to get spend conditions
    # Use DONT_VALIDATE_SIGNATURE since we don't have the actual aggregated signature
    err, spend_result = run_block_generator2(
        block.generator,
        block_refs,
        MAX_COST,
        DONT_VALIDATE_SIGNATURE,
        G2Element(),
        None,
        MAINNET_CONSTANTS,
    )

    if err is not None or spend_result is None:
        return []

    # For each spend, get the puzzle reveal and uncurry it
    mod_hashes: list[bytes] = []

    for spend in spend_result.spends:
        try:
            coin = Coin(spend.parent_id, spend.puzzle_hash, uint64(spend.coin_amount))

            puzzle, _ = get_puzzle_and_solution_for_coin2(
                generator_program,
                block_refs,
                MAX_COST,
                coin,
                0,
            )

            clvm_puzzle = CLVMProgram.from_bytes(bytes(puzzle))
            mod, _ = clvm_puzzle.uncurry()
            mod_hashes.append(mod.tree_hash())

        except Exception:
            continue

    return mod_hashes
