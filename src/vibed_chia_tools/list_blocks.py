"""List blocks from the blockchain database with size information."""

import sqlite3
import sys

import click

from .utils import DEFAULT_DB_PATH, format_size, open_db, parse_size


@click.command("list-blocks")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    type=click.Path(exists=True),
    help="Path to blockchain database",
    show_default=True,
)
@click.option("--start", "start_height", type=int, help="Start block height (inclusive)")
@click.option("--end", "end_height", type=int, help="End block height (inclusive)")
@click.option("--min-size", help="Minimum compressed block size (e.g., '100k', '1M')")
@click.option("--max-size", help="Maximum compressed block size (e.g., '500k', '2M')")
@click.option("--top", "top_n", type=int, help="Show only top N largest blocks")
@click.option(
    "--sort",
    "sort_by",
    type=click.Choice(["height", "size"]),
    default="height",
    help="Sort by height or size (default: height)",
)
@click.option("--desc", is_flag=True, help="Sort in descending order")
def list_blocks(
    db_path: str,
    start_height: int | None,
    end_height: int | None,
    min_size: str | None,
    max_size: str | None,
    top_n: int | None,
    sort_by: str,
    desc: bool,
) -> None:
    """List blocks with their heights and compressed sizes.

    \b
    Examples:
        chia-scan list-blocks --db blockchain.sqlite --min-size 100k
        chia-scan list-blocks --db blockchain.sqlite --top 20 --sort size --desc
    """
    # Build query with filters
    conditions = ["in_main_chain = 1", "block IS NOT NULL"]
    params: list = []

    if start_height is not None:
        conditions.append("height >= ?")
        params.append(start_height)
    if end_height is not None:
        conditions.append("height <= ?")
        params.append(end_height)
    if min_size:
        conditions.append("length(block) >= ?")
        params.append(parse_size(min_size))
    if max_size:
        conditions.append("length(block) <= ?")
        params.append(parse_size(max_size))

    order_col = "compressed_size" if sort_by == "size" else "height"
    query = f"""
        SELECT height, length(block) as compressed_size FROM full_blocks
        WHERE {" AND ".join(conditions)}
        ORDER BY {order_col} {"DESC" if desc else "ASC"}
    """
    if top_n:
        query += " LIMIT ?"
        params.append(top_n)

    try:
        with open_db(db_path) as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error as e:
        click.echo(f"Database error: {e}", err=True)
        sys.exit(1)

    if not rows:
        click.echo("No blocks found matching criteria.")
        return

    # Print results
    click.echo(f"{'Height':>12}  {'Size (compressed)':>18}")
    click.echo(f"{'-' * 12}  {'-' * 18}")

    total_size = sum(size for _, size in rows)
    for height, size in rows:
        click.echo(f"{height:>12}  {size:>12,} ({format_size(size):>6})")

    click.echo(f"{'-' * 12}  {'-' * 18}")
    click.echo(f"{'Total':>12}  {total_size:>12,} ({format_size(total_size):>6})")
    click.echo(f"Blocks: {len(rows)}")
