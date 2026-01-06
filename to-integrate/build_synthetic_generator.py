#!/usr/bin/env python3
"""
Build a synthetic generator from real spends, excluding large-blob spends.

This extracts spends from multiple block generators, filters out any with
abnormally large atoms (NFTs, JPEGs, etc.), and combines them into a single
synthetic generator for realistic compression testing.
"""

import glob
import sys
from collections import Counter
from io import BytesIO

import chia_rs
import clvm.serialize as ser_module
from clvm.CLVMObject import CLVMObject
from clvm.serde_2026 import serialize
from clvm.serialize import sexp_to_stream


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
        bb = f.read(bit_count - 1)
        size_blob += bb
    size = int.from_bytes(size_blob, "big")
    return f.read(size)


ser_module._atom_from_stream = _atom_from_stream_no_limit


def lazy_node_to_clvm(node) -> CLVMObject:
    """Convert a chia_rs LazyNode to a CLVMObject."""
    if node.pair is None:
        atom = node.atom
        return CLVMObject(atom if atom is not None else b"")
    left, right = node.pair
    return CLVMObject((lazy_node_to_clvm(left), lazy_node_to_clvm(right)))


def max_atom_size(node: CLVMObject) -> int:
    """Find the largest atom in a CLVM tree."""
    if node.pair is None:
        return len(node.atom)
    left, right = node.pair
    return max(max_atom_size(left), max_atom_size(right))


def count_atoms_and_pairs(node: CLVMObject) -> tuple[int, int]:
    """Count atoms and pairs in a CLVM tree."""
    if node.pair is None:
        return 1, 0
    left, right = node.pair
    la, lp = count_atoms_and_pairs(left)
    ra, rp = count_atoms_and_pairs(right)
    return la + ra, lp + rp + 1


def extract_spends(gen_path: str) -> list[CLVMObject]:
    """Extract individual spends from a generator file."""
    with open(gen_path, "rb") as f:
        gen_data = f.read()

    cost, result = chia_rs.run_chia_program(gen_data, b"\x80", 100_000_000_000, 0)

    if result.pair is None:
        return []

    spends_list, rest = result.pair
    spends = []

    while spends_list.pair is not None:
        spend, spends_list = spends_list.pair
        spends.append(lazy_node_to_clvm(spend))

    return spends


def build_generator(spends: list[CLVMObject]) -> CLVMObject:
    """Build a generator that returns the given spends.

    Generator format: (q . (spends_list . ()))
    where q = opcode 1 (quote)
    """
    # Build spends list (proper list ending in nil)
    spends_list = CLVMObject(b"")  # nil
    for spend in reversed(spends):
        spends_list = CLVMObject((spend, spends_list))

    # Build result: (spends_list . ())
    result = CLVMObject((spends_list, CLVMObject(b"")))

    # Build generator: (q . result) where q = 1
    generator = CLVMObject((CLVMObject(b"\x01"), result))

    return generator


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--blocks-dir",
        default="BLOCKS",
        help="Directory containing generator .bin files",
    )
    parser.add_argument(
        "--max-atom-size",
        type=int,
        default=1000,
        help="Maximum atom size to allow in spends (default: 1000 bytes)",
    )
    parser.add_argument(
        "--target-spends",
        type=int,
        default=None,
        help="Target number of spends to include",
    )
    parser.add_argument(
        "--target-size",
        type=str,
        default=None,
        help="Target 2026 serialized size, e.g. '1M', '500K', '1000000'",
    )
    parser.add_argument(
        "--output",
        default="synthetic_generator.bin",
        help="Output file path",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only print statistics, don't write output",
    )
    args = parser.parse_args()

    # Parse target size
    def parse_size(s):
        if s is None:
            return None
        s = s.strip().upper()
        if s.endswith("K"):
            return int(float(s[:-1]) * 1024)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1024 * 1024)
        if s.endswith("G"):
            return int(float(s[:-1]) * 1024 * 1024 * 1024)
        return int(s)

    target_size = parse_size(args.target_size)
    target_spends = args.target_spends

    if target_size is None and target_spends is None:
        target_spends = 1000  # default

    print(f"Scanning {args.blocks_dir}/*.bin for spends...")
    print(f"Max atom size filter: {args.max_atom_size} bytes")
    if target_size:
        print(f"Target 2026 size: {target_size:,} bytes")
    if target_spends:
        print(f"Target spends: {target_spends}")
    print()

    all_spends = []
    blocks_scanned = 0
    spends_rejected = 0
    current_size = 0

    for path in sorted(glob.glob(f"{args.blocks_dir}/*.bin")):
        try:
            spends = extract_spends(path)
            blocks_scanned += 1

            for spend in spends:
                max_size = max_atom_size(spend)
                if max_size <= args.max_atom_size:
                    all_spends.append(spend)

                    # Check size periodically when targeting size
                    if target_size and len(all_spends) % 50 == 0:
                        test_gen = build_generator(all_spends)
                        current_size = len(serialize(test_gen))
                        if current_size >= target_size:
                            break
                else:
                    spends_rejected += 1

            if blocks_scanned % 20 == 0:
                size_info = f", current 2026 size ~{current_size:,}" if target_size else ""
                print(
                    f"  Scanned {blocks_scanned} blocks, "
                    f"collected {len(all_spends)} spends, "
                    f"rejected {spends_rejected}{size_info}"
                )

            # Check termination conditions
            if target_spends and len(all_spends) >= target_spends:
                break
            if target_size and current_size >= target_size:
                break

        except Exception as e:
            print(f"  Error processing {path}: {e}")

    print()
    print(f"Scanned {blocks_scanned} blocks")
    print(f"Collected {len(all_spends)} spends (rejected {spends_rejected} with large atoms)")

    if not all_spends:
        print("No spends found!")
        return 1

    # If targeting size, trim to just under target
    if target_size:
        # Binary search to find right number of spends
        lo, hi = 1, len(all_spends)
        best = lo
        while lo <= hi:
            mid = (lo + hi) // 2
            test_gen = build_generator(all_spends[:mid])
            size = len(serialize(test_gen))
            if size <= target_size:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        spends_to_use = all_spends[:best]
        print(f"Using {len(spends_to_use)} spends to hit ~{target_size:,} byte target")
    elif target_spends:
        spends_to_use = all_spends[:target_spends]
        print(f"Using {len(spends_to_use)} spends")

    # Build generator
    generator = build_generator(spends_to_use)

    # Serialize (original format may exceed limits for large generators)
    try:
        buf = BytesIO()
        sexp_to_stream(generator, buf, max_size=10_000_000_000)
        gen_bytes = buf.getvalue()
    except ValueError:
        gen_bytes = None
        print("(Original serialization too large, skipping)")

    # Stats
    from clvm.intern_clvm import InternCLVMStorage

    storage = InternCLVMStorage()
    storage.intern(generator)

    ser_2026 = serialize(generator)

    print()
    print("Synthetic generator stats:")
    print(f"  Unique atoms: {len(storage._atoms)}")
    print(f"  Unique pairs: {len(storage._pairs)}")
    if gen_bytes:
        print(f"  Original serialization: {len(gen_bytes):,} bytes")
        print(f"  2026 serialization: {len(ser_2026):,} bytes")
        print(f"  Compression ratio: {len(ser_2026) / len(gen_bytes):.2%}")
    else:
        print(f"  2026 serialization: {len(ser_2026):,} bytes")

    # Atom size distribution
    sizes = [len(a) for a in storage._atoms]
    print()
    print("Atom size distribution:")
    print(f"  Max: {max(sizes)} bytes")
    print(f"  Total atom data: {sum(sizes):,} bytes")
    size_counts = Counter(sizes)
    print("  Top sizes:", size_counts.most_common(10))

    if not args.stats_only:
        if gen_bytes:
            with open(args.output, "wb") as f:
                f.write(gen_bytes)
            print()
            print(f"Wrote {args.output} ({len(gen_bytes):,} bytes)")

        # Also write 2026 version
        output_2026 = args.output.replace(".bin", "_2026.bin")
        with open(output_2026, "wb") as f:
            f.write(ser_2026)
        if gen_bytes:
            print(f"Wrote {output_2026} ({len(ser_2026):,} bytes)")
        else:
            print()
            print(f"Wrote {output_2026} ({len(ser_2026):,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
