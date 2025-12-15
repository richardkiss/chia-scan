"""CLI entry point for vibed-chia-tools."""

import click

from .mod_hashes import mod_hashes


@click.group()
@click.version_option()
def main() -> None:
    """chia-scan - utilities for Chia blockchain analysis."""
    pass


main.add_command(mod_hashes)


if __name__ == "__main__":
    main()
