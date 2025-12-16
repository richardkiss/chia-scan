"""Extract blocks or generators from the blockchain database to files."""

import sqlite3
import sys
from pathlib import Path

import click
import zstd

from chia_rs import FullBlock

from .utils import DEFAULT_DB_PATH, open_db, parse_range


def read_heights(source) -> list[int]:
    """Read heights from file or stdin, one per line."""
    import contextlib

    heights = []
    for line in source:
        line = line.strip()
        if line and not line.startswith("#"):
            with contextlib.suppress(ValueError, IndexError):
                heights.append(int(line.split()[0]))
    return heights


@click.command("extract-blocks")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    type=click.Path(exists=True),
    help="Path to blockchain database",
    show_default=True,
)
@click.option(
    "-o",
    "--output",
    "output_dir",
    required=True,
    type=click.Path(),
    help="Directory to write extracted files",
)
@click.option(
    "--height", "height_range", help="Block height range (e.g., '1000-2000', '1000-', '-2000')"
)
@click.option(
    "--heights-file",
    type=click.Path(),
    help="File with list of heights (one per line), or '-' for stdin",
)
@click.option(
    "--size", "size_range", help="Block size range (e.g., '100k-1M'). Supports k, M, G suffixes."
)
@click.option(
    "--generator-only", is_flag=True, help="Extract only the generator portion (not full blocks)"
)
@click.option(
    "--decompress/--no-decompress",
    default=True,
    help="Decompress blocks before writing (default: decompress)",
)
def extract_blocks(
    db_path: str,
    output_dir: str,
    height_range: str | None,
    heights_file: str | None,
    size_range: str | None,
    generator_only: bool,
    decompress: bool,
) -> None:
    """Extract blocks or generators from the blockchain database to files.

    \b
    Examples:
        chia-scan extract-blocks --db blockchain.sqlite -o ./generators \\
            --height 5000000-5001000 --generator-only
        chia-scan extract-blocks --db blockchain.sqlite -o ./blocks --size 100k-
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Parse heights from file if provided
    specific_heights: list[int] | None = None
    if heights_file:
        try:
            if heights_file == "-":
                specific_heights = read_heights(sys.stdin)
            else:
                with open(heights_file) as f:
                    specific_heights = read_heights(f)
            if not specific_heights:
                click.echo("Error: No valid heights found in input", err=True)
                sys.exit(1)
            click.echo(f"Read {len(specific_heights)} heights")
        except OSError as e:
            click.echo(f"Error reading heights file: {e}", err=True)
            sys.exit(1)

    # Parse ranges
    min_height, max_height = (None, None)
    min_size, max_size = (None, None)
    if height_range and not specific_heights:
        min_height, max_height = parse_range(height_range)
    if size_range:
        min_size, max_size = parse_range(size_range, is_size=True)

    # Build query
    conditions = ["in_main_chain = 1"]
    params: list = []

    if specific_heights:
        conditions.append(f"height IN ({','.join('?' * len(specific_heights))})")
        params.extend(specific_heights)
    else:
        if min_height is not None:
            conditions.append("height >= ?")
            params.append(min_height)
        if max_height is not None:
            conditions.append("height <= ?")
            params.append(max_height)

    query = f"""
        SELECT header_hash, height, block FROM full_blocks
        WHERE {" AND ".join(conditions)} ORDER BY height
    """

    try:
        with open_db(db_path) as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error as e:
        click.echo(f"Database error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(rows)} blocks matching criteria")
    if generator_only:
        mode = "generators"
    else:
        mode = "decompressed blocks" if decompress else "compressed blocks"
    click.echo(f"Mode: Extracting {mode}")

    extracted, skipped, total_size = 0, 0, 0

    for header_hash, height, block_data in rows:
        if not block_data:
            skipped += 1
            continue

        # Check size filter on compressed data
        if min_size and len(block_data) < min_size:
            skipped += 1
            continue
        if max_size and len(block_data) > max_size:
            skipped += 1
            continue

        # Decompress if needed
        if decompress or generator_only:
            try:
                block_bytes = zstd.decompress(block_data)
            except Exception as e:
                click.echo(f"Error decompressing block {height}: {e}", err=True)
                skipped += 1
                continue
        else:
            block_bytes = block_data

        # Extract generator if requested
        if generator_only:
            try:
                full_block = FullBlock.from_bytes(block_bytes)
                if full_block.transactions_generator is None:
                    skipped += 1
                    continue
                output_data = bytes(full_block.transactions_generator)
            except Exception as e:
                click.echo(f"Error parsing block {height}: {e}", err=True)
                skipped += 1
                continue
        else:
            output_data = block_bytes

        # Write file
        prefix = "generator" if generator_only else "block"
        ext = ".bin" if (decompress or generator_only) else ".bin.zstd"
        filename = f"{prefix}_{height:010d}_{header_hash.hex()[:16]}{ext}"

        try:
            (output_path / filename).write_bytes(output_data)
            extracted += 1
            total_size += len(output_data)
            if extracted % 100 == 0:
                click.echo(f"  Extracted {extracted} files...")
        except OSError as e:
            click.echo(f"Error writing {filename}: {e}", err=True)
            skipped += 1

    click.echo()
    click.echo(f"Extraction complete: {extracted} files, {skipped} skipped")
    click.echo(f"Total size: {total_size:,} bytes ({total_size / 1024**2:.2f} MB)")
