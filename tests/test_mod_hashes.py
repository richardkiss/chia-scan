"""Tests for mod_hashes module."""


def test_import_cli() -> None:
    """Test that CLI can be imported."""
    from chia_scan.cli import main

    assert main is not None


def test_import_constants() -> None:
    """Test that constants can be imported."""
    from chia_scan.constants import MAINNET_CONSTANTS

    assert MAINNET_CONSTANTS is not None
    assert MAINNET_CONSTANTS.MAX_BLOCK_COST_CLVM == 11000000000


def test_import_db_reader() -> None:
    """Test that db_reader can be imported."""
    from chia_scan.mod_hashes.db_reader import get_generators_for_refs, iterate_blocks

    assert iterate_blocks is not None
    assert get_generators_for_refs is not None


def test_import_analyzer() -> None:
    """Test that analyzer can be imported."""
    from chia_scan.mod_hashes.analyzer import analyze_block, analyze_block_range

    assert analyze_block_range is not None
    assert analyze_block is not None
