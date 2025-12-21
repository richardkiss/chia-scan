"""CLI for MOD hash analysis."""

from __future__ import annotations

import multiprocessing as mp
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click

from ..known_mods import KNOWN_MODS, get_mod_label
from ..utils import DEFAULT_DB_PATH


# Type alias for chunk processing result
# (rowid_start, rowid_end, mod_counts dict, stats dict)
ChunkResult = tuple[int, int, dict[bytes, int], dict[str, int]]


def _process_chunk(
    db_path: str,
    rowid_start: int,
    rowid_end: int,
    ref_cache: dict[int, bytes],
) -> ChunkResult:
    """Process a chunk of blocks by rowid range. Runs entirely in worker process.

    Each worker has its own DB connection and does all I/O + CPU work.
    ref_cache is a shared Manager dict for lazy caching of generator refs.
    """
    # All imports inside worker to avoid pickling issues
    import sqlite3
    from collections import Counter

    import zstd
    from chia_rs import (
        DONT_VALIDATE_SIGNATURE,
        Coin,
        FullBlock,
        G2Element,
        Program,
        get_puzzle_and_solution_for_coin2,
        run_block_generator2,
    )
    from chia_rs.sized_ints import uint64
    from clvm_rs import Program as CLVMProgram

    from ..constants import MAINNET_CONSTANTS

    max_cost = 0xFFFFFFFFFFFFFFFF

    # Local stats for this chunk
    stats = {"blocks": 0, "blocks_with_spends": 0, "spends": 0, "errors": 0, "gen_errors": 0}
    mod_counts: Counter[bytes] = Counter()

    # Open DB connection for this worker
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    def get_ref(height: int) -> bytes:
        """Get generator ref, fetching from DB if not in shared cache."""
        # Check shared cache first
        cached = ref_cache.get(height)
        if cached is not None:
            return cached

        cursor = conn.execute(
            "SELECT block FROM full_blocks WHERE height = ? AND in_main_chain = 1",
            (height,),
        )
        row = cursor.fetchone()
        if row is None:
            ref_cache[height] = b""
            return b""

        block_bytes = zstd.decompress(row[0])
        full_block = FullBlock.from_bytes(block_bytes)
        if full_block.transactions_generator is None:
            ref_cache[height] = b""
            return b""

        gen_bytes = bytes(full_block.transactions_generator)
        ref_cache[height] = gen_bytes
        return gen_bytes

    try:
        # Query by rowid range for contiguous physical reads
        cursor = conn.execute(
            """
            SELECT height, block
            FROM full_blocks
            WHERE rowid >= ? AND rowid <= ? AND in_main_chain = 1
            """,
            (rowid_start, rowid_end),
        )

        for row in cursor:
            height = row[0]
            block_bytes = zstd.decompress(row[1])
            full_block = FullBlock.from_bytes(block_bytes)

            if full_block.transactions_generator is None:
                continue

            stats["blocks"] += 1
            generator = bytes(full_block.transactions_generator)

            # Get refs lazily from shared cache
            ref_list = list(full_block.transactions_generator_ref_list)
            block_refs = [get_ref(h) for h in ref_list]

            # Run the generator
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
                stats["gen_errors"] += 1
                continue

            if not spend_result.spends:
                continue

            stats["blocks_with_spends"] += 1
            generator_program = Program.from_bytes(generator)

            for spend in spend_result.spends:
                try:
                    coin = Coin(spend.parent_id, spend.puzzle_hash, uint64(spend.coin_amount))
                    puzzle, _ = get_puzzle_and_solution_for_coin2(
                        generator_program, block_refs, max_cost, coin, 0
                    )
                    clvm_puzzle = CLVMProgram.from_bytes(bytes(puzzle))
                    mod, _ = clvm_puzzle.uncurry()
                    mod_counts[mod.tree_hash()] += 1
                    stats["spends"] += 1
                except Exception:
                    stats["errors"] += 1

    finally:
        conn.close()

    return (rowid_start, rowid_end, dict(mod_counts), stats)


def _process_chunk_with_mods(
    db_path: str,
    rowid_start: int,
    rowid_end: int,
    ref_cache: dict[int, bytes],
) -> tuple[int, int, dict[bytes, int], dict[str, int], dict[bytes, bytes]]:
    """Process chunk by rowid range and also return MOD bytes for unknown MODs.

    Returns: (rowid_start, rowid_end, mod_counts, stats, mod_bytes_map)
    ref_cache is a shared Manager dict for lazy caching of generator refs.
    """
    # All imports inside worker
    import sqlite3
    from collections import Counter

    import zstd
    from chia_rs import (
        DONT_VALIDATE_SIGNATURE,
        Coin,
        FullBlock,
        G2Element,
        Program,
        get_puzzle_and_solution_for_coin2,
        run_block_generator2,
    )
    from chia_rs.sized_ints import uint64
    from clvm_rs import Program as CLVMProgram

    from ..constants import MAINNET_CONSTANTS

    max_cost = 0xFFFFFFFFFFFFFFFF

    stats = {"blocks": 0, "blocks_with_spends": 0, "spends": 0, "errors": 0, "gen_errors": 0}
    mod_counts: Counter[bytes] = Counter()
    mod_bytes_map: dict[bytes, bytes] = {}  # hash -> bytes (for saving unknowns)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    def get_ref(height: int) -> bytes:
        """Get generator ref, fetching from DB if not in shared cache."""
        cached = ref_cache.get(height)
        if cached is not None:
            return cached

        cursor = conn.execute(
            "SELECT block FROM full_blocks WHERE height = ? AND in_main_chain = 1",
            (height,),
        )
        row = cursor.fetchone()
        if row is None:
            ref_cache[height] = b""
            return b""

        block_bytes = zstd.decompress(row[0])
        full_block = FullBlock.from_bytes(block_bytes)
        if full_block.transactions_generator is None:
            ref_cache[height] = b""
            return b""

        gen_bytes = bytes(full_block.transactions_generator)
        ref_cache[height] = gen_bytes
        return gen_bytes

    try:
        cursor = conn.execute(
            """
            SELECT height, block
            FROM full_blocks
            WHERE rowid >= ? AND rowid <= ? AND in_main_chain = 1
            """,
            (rowid_start, rowid_end),
        )

        for row in cursor:
            height = row[0]
            block_bytes = zstd.decompress(row[1])
            full_block = FullBlock.from_bytes(block_bytes)

            if full_block.transactions_generator is None:
                continue

            stats["blocks"] += 1
            generator = bytes(full_block.transactions_generator)

            # Get refs lazily from shared cache
            ref_list = list(full_block.transactions_generator_ref_list)
            block_refs = [get_ref(h) for h in ref_list]

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
                stats["gen_errors"] += 1
                continue

            if not spend_result.spends:
                continue

            stats["blocks_with_spends"] += 1
            generator_program = Program.from_bytes(generator)

            for spend in spend_result.spends:
                try:
                    coin = Coin(spend.parent_id, spend.puzzle_hash, uint64(spend.coin_amount))
                    puzzle, _ = get_puzzle_and_solution_for_coin2(
                        generator_program, block_refs, max_cost, coin, 0
                    )
                    clvm_puzzle = CLVMProgram.from_bytes(bytes(puzzle))
                    mod, _ = clvm_puzzle.uncurry()
                    mod_hash = mod.tree_hash()
                    mod_counts[mod_hash] += 1
                    stats["spends"] += 1

                    # Store mod bytes if we haven't seen it
                    if mod_hash not in mod_bytes_map:
                        mod_bytes_map[mod_hash] = bytes(mod)
                except Exception:
                    stats["errors"] += 1

    finally:
        conn.close()

    return (rowid_start, rowid_end, dict(mod_counts), stats, mod_bytes_map)


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
    default=None,
    type=int,
    help="Number of parallel workers (default: CPU count)",
)
@click.option(
    "--chunk-size",
    "chunk_size",
    default=500,
    type=int,
    help="Blocks per worker chunk (default: 500)",
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
    num_workers: int | None,
    chunk_size: int,
    save_unknown_dir: str | None,
    debug: bool,
) -> None:
    """Analyze puzzle MOD hashes in a block range.

    Reads blocks from the database, extracts puzzle reveals, uncurries them,
    and counts occurrences of each MOD template hash.

    Uses multiprocessing with each worker processing independent block ranges.
    """
    import sqlite3

    if num_workers is None:
        num_workers = mp.cpu_count()

    # Quick DB query to get rowid range for our height range
    click.echo(f"Database: {db_path}")
    click.echo("Querying database...")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # Get rowid range and block count for our height range
        row = conn.execute(
            """
            SELECT MIN(rowid), MAX(rowid), COUNT(*), MIN(height), MAX(height)
            FROM full_blocks
            WHERE height >= ? AND height <= ? AND in_main_chain = 1
            """,
            (start_height, end_height),
        ).fetchone()
        min_rowid, max_rowid, actual_blocks, actual_min, actual_max = row

        if min_rowid is None or actual_blocks == 0:
            click.echo("No blocks found in range.")
            return

    finally:
        conn.close()

    click.echo(f"Found {actual_blocks:,} blocks in range {actual_min:,} to {actual_max:,}")
    click.echo(f"Rowid range: {min_rowid:,} to {max_rowid:,}")
    click.echo(f"Workers: {num_workers} (processes)")
    click.echo(f"Chunk size: {chunk_size:,} rows per worker")
    click.echo()

    # Create chunks by rowid for contiguous physical reads
    chunks: list[tuple[int, int]] = []  # (rowid_start, rowid_end)
    total_rowids = max_rowid - min_rowid + 1
    for chunk_idx in range(0, total_rowids, chunk_size):
        rowid_start = min_rowid + chunk_idx
        rowid_end = min(rowid_start + chunk_size - 1, max_rowid)
        chunks.append((rowid_start, rowid_end))

    click.echo(f"Split into {len(chunks)} chunks")

    # Track unknown MODs
    unknown_dir: Path | None = None
    if save_unknown_dir:
        unknown_dir = Path(save_unknown_dir)
        unknown_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"Saving unknown MODs to: {unknown_dir}")

    # Aggregated results
    mod_counts: Counter[bytes] = Counter()
    all_mod_bytes: dict[bytes, bytes] = {}
    total_stats = {"blocks": 0, "blocks_with_spends": 0, "spends": 0, "errors": 0, "gen_errors": 0}

    click.echo()
    click.echo("Processing chunks...")

    chunks_done = 0
    start_time = time.time()

    def format_duration(seconds: float) -> str:
        """Format seconds as human-readable duration."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            mins, secs = divmod(int(seconds), 60)
            return f"{mins}m {secs}s"
        else:
            hours, remainder = divmod(int(seconds), 3600)
            mins, secs = divmod(remainder, 60)
            return f"{hours}h {mins}m {secs}s"

    # Choose worker function based on whether we need mod bytes
    worker_fn = _process_chunk_with_mods if save_unknown_dir else _process_chunk

    # Create a shared cache for generator refs (lazily populated by workers)
    manager = mp.Manager()
    ref_cache = manager.dict()

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit all chunks (by rowid range) with shared ref_cache
        futures = {
            executor.submit(worker_fn, db_path, rowid_start, rowid_end, ref_cache): (
                rowid_start,
                rowid_end,
            )
            for rowid_start, rowid_end in chunks
        }

        for future in as_completed(futures):
            rowid_start, rowid_end = futures[future]
            chunks_done += 1

            try:
                result = future.result()

                if save_unknown_dir:
                    _, _, chunk_mods, chunk_stats, chunk_mod_bytes = result
                    # Collect mod bytes for saving
                    for mod_hash, mod_bytes in chunk_mod_bytes.items():
                        if mod_hash not in all_mod_bytes:
                            all_mod_bytes[mod_hash] = mod_bytes
                else:
                    _, _, chunk_mods, chunk_stats = result

                # Aggregate counts
                mod_counts.update(chunk_mods)

                # Aggregate stats
                for key in total_stats:
                    total_stats[key] += chunk_stats[key]

                # Calculate progress and ETA
                elapsed = time.time() - start_time
                progress = chunks_done / len(chunks)
                progress_pct = progress * 100

                if chunks_done > 0 and progress > 0:
                    eta_seconds = (elapsed / progress) * (1 - progress)
                    eta_str = format_duration(eta_seconds)
                    elapsed_str = format_duration(elapsed)
                    blocks_per_sec = total_stats["blocks"] / elapsed if elapsed > 0 else 0

                    click.echo(
                        f"\r[{chunks_done}/{len(chunks)}] {progress_pct:.1f}% - "
                        f"Blocks: {total_stats['blocks']:,}, Spends: {total_stats['spends']:,} | "
                        f"{blocks_per_sec:.0f} blk/s | "
                        f"Elapsed: {elapsed_str}, ETA: {eta_str}   ",
                        nl=False,
                    )
                else:
                    click.echo(
                        f"\r[{chunks_done}/{len(chunks)}] {progress_pct:.1f}% - Starting...   ",
                        nl=False,
                    )

                if debug:
                    click.echo(f"\n  Chunk rowid {rowid_start}-{rowid_end}: {chunk_stats}")

            except Exception as e:
                click.echo(f"\nError processing chunk rowid {rowid_start}-{rowid_end}: {e}")

    total_elapsed = time.time() - start_time
    click.echo()
    click.echo()
    click.echo(f"Completed in {format_duration(total_elapsed)}")
    click.echo()

    # Save unknown MODs if requested
    saved_count = 0
    if unknown_dir:
        for mod_hash, mod_bytes in all_mod_bytes.items():
            if mod_hash not in KNOWN_MODS:
                (unknown_dir / f"{mod_hash.hex()}.clvm.hex").write_text(mod_bytes.hex())
                saved_count += 1

    # Print results
    sorted_results = sorted(mod_counts.items(), key=lambda x: x[1], reverse=True)

    click.echo(f"{'MOD Hash':<66} {'Count':>10}  Label")
    click.echo("─" * 90)

    for mod_hash, count in sorted_results[:top_n]:
        label = get_mod_label(mod_hash)
        click.echo(f"{mod_hash.hex():<66} {count:>10}  {label}")

    click.echo("─" * 90)
    click.echo(f"Total unique MODs: {len(mod_counts)}")
    click.echo(f"Total spends analyzed: {total_stats['spends']:,}")
    click.echo(f"Blocks with generators: {total_stats['blocks']:,}")
    click.echo(f"Blocks with spends: {total_stats['blocks_with_spends']:,}")
    if total_stats["gen_errors"] > 0:
        click.echo(f"Generator errors: {total_stats['gen_errors']}")
    if total_stats["errors"] > 0:
        click.echo(f"Spend processing errors: {total_stats['errors']}")
    if save_unknown_dir:
        click.echo(f"Unknown MODs saved: {saved_count}")
    if ref_cache:
        click.echo(f"Generator refs cached: {len(ref_cache)}")
