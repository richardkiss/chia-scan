#!/usr/bin/env python3
"""
Compute and print the SHA256 tree hash of a serialized CLVM object.

Supports both classic (0xfe backref) format and 2026 format.
"""

import argparse
import hashlib
import sys
from io import BytesIO

import clvm.serialize as ser_module
from clvm.CLVMObject import CLVMObject
from clvm.serde_2026 import deserialize
from clvm.serialize import sexp_from_stream


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


def tree_hash(node: CLVMObject) -> bytes:
    """Compute the SHA256 tree hash of a CLVM object.

    For atoms: SHA256(0x01 + atom_bytes)
    For pairs: SHA256(0x02 + left_hash + right_hash)
    """
    if node.pair is None:
        return hashlib.sha256(b"\x01" + node.atom).digest()
    left, right = node.pair
    left_hash = tree_hash(left)
    right_hash = tree_hash(right)
    return hashlib.sha256(b"\x02" + left_hash + right_hash).digest()


def tree_hash_iterative(node: CLVMObject) -> bytes:
    """Iterative version of tree_hash to avoid stack overflow on deep trees."""
    # Stack of (node, state) where state is:
    # 0 = need to process
    # 1 = left done, need right
    # 2 = both done, need to combine
    stack = [(node, 0, None, None)]  # (node, state, left_hash, right_hash)
    result_stack = []

    while stack:
        current, state, left_h, right_h = stack.pop()

        if current.pair is None:
            # Atom - compute hash directly
            result_stack.append(hashlib.sha256(b"\x01" + current.atom).digest())
        elif state == 0:
            # First visit - need to process left child
            left, right = current.pair
            stack.append((current, 1, None, None))  # Come back after left
            stack.append((left, 0, None, None))  # Process left
        elif state == 1:
            # Left is done, need to process right
            left, right = current.pair
            left_hash = result_stack.pop()
            stack.append((current, 2, left_hash, None))  # Come back after right
            stack.append((right, 0, None, None))  # Process right
        elif state == 2:
            # Both done, combine
            right_hash = result_stack.pop()
            combined = hashlib.sha256(b"\x02" + left_h + right_hash).digest()
            result_stack.append(combined)

    return result_stack[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="Path to the .bin file")
    parser.add_argument(
        "--format",
        choices=["auto", "classic", "2026"],
        default="auto",
        help="Serialization format (default: auto-detect)",
    )
    args = parser.parse_args()

    with open(args.file, "rb") as f:
        data = f.read()

    fmt = args.format

    # Auto-detect format
    if fmt == "auto":
        # 2026 format doesn't start with 0xff or 0xfe typically
        # Classic format atoms start with size prefix or 0x80 for nil
        # This is a heuristic - 2026 starts with varint for atom group count
        # For now, try 2026 first, fall back to classic
        try:
            node = deserialize(data)
            fmt = "2026"
        except Exception:
            try:
                node = sexp_from_stream(BytesIO(data), CLVMObject, allow_backrefs=True)
                fmt = "classic"
            except Exception as e:
                print(
                    f"Error: Could not deserialize as either format: {e}",
                    file=sys.stderr,
                )
                return 1
    elif fmt == "2026":
        try:
            node = deserialize(data)
        except Exception as e:
            print(f"Error deserializing as 2026 format: {e}", file=sys.stderr)
            return 1
    else:  # classic
        try:
            node = sexp_from_stream(BytesIO(data), CLVMObject, allow_backrefs=True)
        except Exception as e:
            print(f"Error deserializing as classic format: {e}", file=sys.stderr)
            return 1

    # Compute tree hash (use iterative version for safety)
    try:
        h = tree_hash_iterative(node)
    except RecursionError:
        print(
            "Error: Tree too deep for recursive hash, and iterative failed",
            file=sys.stderr,
        )
        return 1

    print(f"Format: {fmt}")
    print(f"Size: {len(data):,} bytes")
    print(f"Tree hash: {h.hex()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
