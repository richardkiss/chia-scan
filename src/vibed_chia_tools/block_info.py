"""Deep-dive info on specific blocks."""

import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

import click
import zstd

from chia_rs import FullBlock

from .known_mods import get_mod_label
from .utils import DEFAULT_DB_PATH, format_size, open_db


def get_block_data(conn: sqlite3.Connection, height: int) -> tuple | None:
    """Fetch block data for a specific height."""
    row = conn.execute(
        """SELECT header_hash, height, block FROM full_blocks
           WHERE height = ? AND in_main_chain = 1""",
        (height,),
    ).fetchone()
    return row


def analyze_block(block_bytes: bytes, db_path: str, show_mods: bool) -> dict:
    """Analyze a decompressed block and return metrics."""
    full_block = FullBlock.from_bytes(block_bytes)

    info: dict = {
        "timestamp": None,
        "has_generator": full_block.transactions_generator is not None,
        "generator_size": 0,
        "generator_ref_count": len(full_block.transactions_generator_ref_list),
        "generator_refs": list(full_block.transactions_generator_ref_list),
    }

    # Get timestamp from reward chain block
    if full_block.reward_chain_block:
        ts = full_block.reward_chain_block.timestamp
        if ts:
            info["timestamp"] = datetime.fromtimestamp(ts, tz=timezone.utc)

    if not full_block.transactions_generator:
        return info

    gen_bytes = bytes(full_block.transactions_generator)
    info["generator_size"] = len(gen_bytes)

    if not show_mods:
        return info

    # Run generator to get spend details
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

    from .constants import MAINNET_CONSTANTS
    from .mod_hashes.db_reader import get_generators_for_refs

    # Resolve generator refs
    block_refs: list[bytes] = []
    if full_block.transactions_generator_ref_list:
        ref_gens = get_generators_for_refs(
            db_path, list(full_block.transactions_generator_ref_list)
        )
        block_refs = [ref_gens.get(h, b"") for h in full_block.transactions_generator_ref_list]

    max_cost = 0xFFFFFFFFFFFFFFFF
    err, spend_result = run_block_generator2(
        gen_bytes,
        block_refs,
        max_cost,
        DONT_VALIDATE_SIGNATURE,
        G2Element(),
        None,
        MAINNET_CONSTANTS,
    )

    if err is not None or spend_result is None:
        info["generator_error"] = err
        return info

    info["spend_count"] = len(spend_result.spends)
    info["cost"] = spend_result.cost

    # Analyze spends
    generator_program = Program.from_bytes(gen_bytes)
    mod_counts: Counter[bytes] = Counter()
    total_amount = 0
    amounts: list[int] = []
    puzzle_hashes: set[bytes] = set()

    for spend in spend_result.spends:
        total_amount += spend.coin_amount
        amounts.append(spend.coin_amount)
        puzzle_hashes.add(spend.puzzle_hash)

        try:
            coin = Coin(spend.parent_id, spend.puzzle_hash, uint64(spend.coin_amount))
            puzzle, _ = get_puzzle_and_solution_for_coin2(
                generator_program, block_refs, max_cost, coin, 0
            )
            clvm_puzzle = CLVMProgram.from_bytes(bytes(puzzle))
            mod, _ = clvm_puzzle.uncurry()
            mod_counts[mod.tree_hash()] += 1
        except Exception:
            mod_counts[b"<error>"] += 1

    info["total_amount"] = total_amount
    info["unique_puzzle_hashes"] = len(puzzle_hashes)
    info["mod_counts"] = mod_counts
    if amounts:
        info["min_amount"] = min(amounts)
        info["max_amount"] = max(amounts)

    return info


def format_xch(mojos: int) -> str:
    """Format mojos as XCH."""
    xch = mojos / 1_000_000_000_000
    if xch >= 1:
        return f"{xch:,.6f} XCH"
    return f"{mojos:,} mojos"


@click.command("block-info")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    type=click.Path(exists=True),
    help="Path to blockchain database",
    show_default=True,
)
@click.option(
    "--mods",
    is_flag=True,
    help="Show MOD hash breakdown (slower, runs generator)",
)
@click.argument("heights", nargs=-1, type=int, required=True)
def block_info(db_path: str, mods: bool, heights: tuple[int, ...]) -> None:
    """Show detailed information about specific blocks.

    \b
    Examples:
        chia-scan block-info 5000000 5000001 5000002
        chia-scan block-info --mods 5000000
    """
    try:
        with open_db(db_path) as conn:
            for i, height in enumerate(heights):
                if i > 0:
                    click.echo()  # Separator between blocks

                row = get_block_data(conn, height)
                if not row:
                    click.echo(f"Block {height}: NOT FOUND")
                    continue

                header_hash, _, block_data = row
                compressed_size = len(block_data)

                try:
                    block_bytes = zstd.decompress(block_data)
                    decompressed_size = len(block_bytes)
                except Exception as e:
                    click.echo(f"Block {height}: DECOMPRESSION ERROR: {e}")
                    continue

                info = analyze_block(block_bytes, db_path, mods)

                # Print block info
                click.echo(f"Block {height}")
                click.echo(f"  Header hash: {header_hash.hex()}")
                if info["timestamp"]:
                    click.echo(f"  Timestamp: {info['timestamp'].isoformat()}")
                click.echo(
                    f"  Size: {format_size(compressed_size)} compressed, "
                    f"{format_size(decompressed_size)} decompressed "
                    f"({compressed_size / decompressed_size:.1%} ratio)"
                )

                if not info["has_generator"]:
                    click.echo("  Type: Non-transaction block (no generator)")
                    continue

                click.echo(f"  Generator: {format_size(info['generator_size'])}")
                if info["generator_ref_count"] > 0:
                    refs_str = ", ".join(str(h) for h in info["generator_refs"][:5])
                    if info["generator_ref_count"] > 5:
                        refs_str += f" ... ({info['generator_ref_count']} total)"
                    click.echo(f"  Generator refs: {refs_str}")

                if "generator_error" in info:
                    click.echo(f"  Generator error: {info['generator_error']}")
                    continue

                if not mods:
                    click.echo("  (use --mods to see spend details)")
                    continue

                # Spend details
                click.echo(f"  Spends: {info['spend_count']}")
                click.echo(f"  Cost: {info['cost']:,}")
                click.echo(f"  Total value: {format_xch(info['total_amount'])}")
                if "min_amount" in info:
                    click.echo(
                        f"  Coin range: {format_xch(info['min_amount'])} - "
                        f"{format_xch(info['max_amount'])}"
                    )
                click.echo(f"  Unique puzzle hashes: {info['unique_puzzle_hashes']}")

                # MOD breakdown
                click.echo("  MOD breakdown:")
                for mod_hash, count in info["mod_counts"].most_common():
                    if mod_hash == b"<error>":
                        click.echo(f"    {count:>6}  <parse error>")
                    else:
                        label = get_mod_label(mod_hash)
                        if label:
                            click.echo(f"    {count:>6}  {label}")
                        else:
                            click.echo(f"    {count:>6}  {mod_hash.hex()[:16]}...")

    except sqlite3.Error as e:
        click.echo(f"Database error: {e}", err=True)
        sys.exit(1)
