"""CLI entry point for vibed-chia-tools."""

import click

from .build_synthetic import build_synthetic
from .extract_blocks import extract_blocks
from .list_blocks import list_blocks
from .mod_hashes import mod_hashes


@click.group()
@click.version_option()
def main() -> None:
    """chia-scan - utilities for Chia blockchain analysis."""
    pass


main.add_command(mod_hashes)
main.add_command(list_blocks)
main.add_command(extract_blocks)
main.add_command(build_synthetic)


if __name__ == "__main__":
    main()
