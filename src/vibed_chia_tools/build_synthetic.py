"""Build synthetic generators from real spends for compression testing."""

import glob
import sys
from io import BytesIO
from pathlib import Path

import click
import clvm.serialize as ser_module
from clvm.CLVMObject import CLVMObject
from clvm.serialize import sexp_to_stream

import chia_rs

from .utils import parse_size


def _atom_from_stream_no_limit(f, b):
    """Patched atom reader that allows large atoms."""
    if b == 0x80:
        return b""
    if b <= 0x7F:
        return bytes([b])
    bit_count, bit_mask = 0, 0x80
    while b & bit_mask:
        bit_count += 1
        b &= 0xFF ^ bit_mask
        bit_mask >>= 1
    size_blob = bytes([b])
    if bit_count > 1:
        size_blob += f.read(bit_count - 1)
    return f.read(int.from_bytes(size_blob, "big"))


ser_module._atom_from_stream = _atom_from_stream_no_limit


def lazy_node_to_clvm(node) -> CLVMObject:
    """Convert a chia_rs LazyNode to a CLVMObject."""
    if node.pair is None:
        return CLVMObject(node.atom if node.atom is not None else b"")
    return CLVMObject((lazy_node_to_clvm(node.pair[0]), lazy_node_to_clvm(node.pair[1])))


def max_atom_size(node: CLVMObject) -> int:
    """Find the largest atom in a CLVM tree."""
    if node.pair is None:
        return len(node.atom)
    return max(max_atom_size(node.pair[0]), max_atom_size(node.pair[1]))


def count_atoms_and_pairs(node: CLVMObject) -> tuple[int, int]:
    """Count atoms and pairs in a CLVM tree."""
    if node.pair is None:
        return 1, 0
    la, lp = count_atoms_and_pairs(node.pair[0])
    ra, rp = count_atoms_and_pairs(node.pair[1])
    return la + ra, lp + rp + 1


def extract_spends(gen_path: str) -> list[CLVMObject]:
    """Extract individual spends from a generator file."""
    with open(gen_path, "rb") as f:
        gen_data = f.read()

    _, result = chia_rs.run_chia_program(gen_data, b"\x80", 100_000_000_000, 0)
    if result.pair is None:
        return []

    spends_list, _ = result.pair
    spends = []
    while spends_list.pair is not None:
        spend, spends_list = spends_list.pair
        spends.append(lazy_node_to_clvm(spend))
    return spends


def build_generator(spends: list[CLVMObject]) -> CLVMObject:
    """Build a generator: (q . (spends_list . ())) where q=1 (quote)."""
    nil = CLVMObject(b"")
    spends_list = nil
    for spend in reversed(spends):
        spends_list = CLVMObject((spend, spends_list))
    return CLVMObject((CLVMObject(b"\x01"), CLVMObject((spends_list, nil))))


def serialize_generator(gen: CLVMObject) -> bytes | None:
    """Serialize a generator, returning None if too large."""
    try:
        buf = BytesIO()
        sexp_to_stream(gen, buf, max_size=10_000_000_000)
        return buf.getvalue()
    except ValueError:
        return None


@click.command("build-synthetic")
@click.option(
    "-i",
    "--input",
    "input_dir",
    required=True,
    type=click.Path(exists=True),
    help="Directory containing generator .bin files",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    default="synthetic_generator.bin",
    help="Output file path (default: synthetic_generator.bin)",
)
@click.option(
    "--max-atom-size",
    "max_atom",
    type=int,
    default=1000,
    help="Maximum atom size to allow (default: 1000 bytes)",
)
@click.option("--target-spends", type=int, help="Target number of spends to include")
@click.option("--target-size", help="Target serialized size (e.g., '1M', '500K')")
@click.option("--stats-only", is_flag=True, help="Only print statistics, don't write output")
def build_synthetic(
    input_dir: str,
    output_file: str,
    max_atom: int,
    target_spends: int | None,
    target_size: str | None,
    stats_only: bool,
) -> None:
    """Build a synthetic generator from real spends.

    Extracts spends from generators, filters out large atoms (NFTs, etc.),
    and combines them for compression testing.

    \b
    Examples:
        chia-scan build-synthetic -i ./generators -o synthetic.bin
        chia-scan build-synthetic -i ./generators --target-size 1M
    """
    target_size_bytes = parse_size(target_size) if target_size else None
    if target_size_bytes is None and target_spends is None:
        target_spends = 1000

    gen_files = sorted(glob.glob(f"{input_dir}/*.bin"))
    if not gen_files:
        click.echo(f"No .bin files found in {input_dir}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(gen_files)} generator files, max atom size: {max_atom} bytes")

    all_spends: list[CLVMObject] = []
    blocks_scanned, spends_rejected = 0, 0

    for path in gen_files:
        try:
            for spend in extract_spends(path):
                if max_atom_size(spend) <= max_atom:
                    all_spends.append(spend)
                else:
                    spends_rejected += 1
            blocks_scanned += 1

            # Check termination
            if target_spends and len(all_spends) >= target_spends:
                break
            if target_size_bytes and len(all_spends) % 50 == 0:
                gen_bytes = serialize_generator(build_generator(all_spends))
                if gen_bytes and len(gen_bytes) >= target_size_bytes:
                    break
        except Exception as e:
            click.echo(f"  Error processing {path}: {e}", err=True)

    click.echo(f"Scanned {blocks_scanned} blocks")
    click.echo(f"Collected {len(all_spends)} spends ({spends_rejected} rejected for large atoms)")

    if not all_spends:
        click.echo("No spends found!", err=True)
        sys.exit(1)

    # Determine final spends to use
    if target_size_bytes:
        # Binary search for target size
        lo, hi, best = 1, len(all_spends), 1
        while lo <= hi:
            mid = (lo + hi) // 2
            gen_bytes = serialize_generator(build_generator(all_spends[:mid]))
            if gen_bytes and len(gen_bytes) <= target_size_bytes:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        spends_to_use = all_spends[:best]
    else:
        spends_to_use = all_spends[:target_spends] if target_spends else all_spends

    generator = build_generator(spends_to_use)
    gen_bytes = serialize_generator(generator)

    # Stats
    total_atoms, total_pairs = 0, 0
    for spend in spends_to_use:
        a, p = count_atoms_and_pairs(spend)
        total_atoms += a
        total_pairs += p

    click.echo(f"\nUsing {len(spends_to_use)} spends")
    click.echo(f"  ~{total_atoms:,} atoms, ~{total_pairs:,} pairs")
    if gen_bytes:
        click.echo(f"Serialized size: {len(gen_bytes):,} bytes")

    if not stats_only and gen_bytes:
        Path(output_file).write_bytes(gen_bytes)
        click.echo(f"Wrote {output_file}")
