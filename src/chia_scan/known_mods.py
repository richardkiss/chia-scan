"""Known MOD hashes for common Chia puzzles.

These hashes are extracted from chia_puzzles_py.programs.
"""

# Map from MOD hash (bytes) to human-readable name
KNOWN_MODS: dict[bytes, str] = {
    # Standard transaction puzzle (most common)
    bytes.fromhex(
        "e9aaa49f45bad5c889b86ee3341550c155cfdd10c3a6757de618d20612fffd52"
    ): "p2_delegated_puzzle_or_hidden_puzzle",
    # CAT (Chia Asset Token) v2
    bytes.fromhex("37bef360ee858133b69d595a906dc45d01af50379dad515eb9518abb7c1d2a7a"): "cat_puzzle",
    # Singletons
    bytes.fromhex(
        "7faa3253bfddd1e0decb0906b2dc6247bbc4cf608f58345d173adb63e8b47c9f"
    ): "singleton_top_layer_v1_1",
    bytes.fromhex(
        "24e044101e57b3d8c908b8a38ad57848afd29d3eecc439dba45f4412df4954fd"
    ): "singleton_top_layer",
    bytes.fromhex(
        "eff07522495060c066f66f32acc2a77e3a3e737aca8baea4d1a64ea4cdc13da9"
    ): "singleton_launcher",
    # NFT puzzles
    bytes.fromhex(
        "a04d9f57764f54a43e4030befb4d80026e870519aaa66334aef8304f5d0393c2"
    ): "nft_state_layer",
    bytes.fromhex(
        "c5abea79afaa001b5427dfa0c8cf42ca6f38f5841b78f9b3c252733eb2de2726"
    ): "nft_ownership_layer",
    bytes.fromhex(
        "fe8a4b4e27a2e29a4d3fc7ce9d527adbcaccbab6ada3903ccf3ba9a769d2d78b"
    ): "nft_metadata_updater_default",
    bytes.fromhex(
        "0b1ffba1601777c06b78ab38636e9624f2f8da73be9b36e0ce17c8d8ef3bad9f"
    ): "nft_metadata_updater_updateable",
    bytes.fromhex(
        "7a32d2d9571d3436791c0ad3d7fcfdb9c43ace2b0f0ff13f98d29f0cc093f445"
    ): "nft_intermediate_launcher",
    # DID (Decentralized Identity)
    bytes.fromhex(
        "33143d2bef64f14036742673afd158126b94284b4530a28c354fac202b0c910e"
    ): "did_innerpuz",
    # Offer/Trading
    bytes.fromhex(
        "cfbfdeed5c4ca2de3d0bf520b9cb4bb7743a359bd2e6a188d19ce7dffc21d3e7"
    ): "settlement_payment",
    # CAT Tails (minting)
    bytes.fromhex(
        "493afb89eed93ab86741b2aa61b8f5de495d33ff9b781dfc8919e602b2afa150"
    ): "genesis_by_coin_id",
    bytes.fromhex(
        "de5a6e06d41518be97ff6365694f4f89475dda773dede267caa33da63b434e36"
    ): "genesis_by_puzzle_hash",
    bytes.fromhex(
        "1720d13250a7c16988eaf530331cefa9dd57a76b2c82236bec8bbbff91499b89"
    ): "everything_with_signature",
    bytes.fromhex(
        "999c3696e167f8a79d938adc11feba3a3dcb39ccff69a426d570706e7b8ec399"
    ): "delegated_tail",
    bytes.fromhex(
        "40170305e3a71c3e7523f37fbcfc3188f9f949da0818a6331f28251e76e8c56f"
    ): "genesis_by_coin_id_or_singleton",
    bytes.fromhex(
        "0876da2005fe6262d4504c27a1b6379227aba8adbbad3758cb0e329a4e74c6cc"
    ): "everything_with_singleton",
    # DAO puzzles
    bytes.fromhex(
        "488f55bedaca5a599544dfd5ab341e2e5c7e6fca67d9b98a3d856f876c52f53e"
    ): "dao_cat_eve",
    bytes.fromhex(
        "a01a838d18d4e031e937c79fa3f80f213fa00a3e64af6c16a1f137770cd3a567"
    ): "dao_cat_launcher",
    bytes.fromhex(
        "694c99e1fb07671771bbca3d110880693a9ecc37a6529891ec979d0f3e760eba"
    ): "dao_finished_state",
    bytes.fromhex("d6215f0916715a69fbbf2d1a679f437fde81787adeb90c666642fb9c2deff7ce"): "dao_lockup",
    bytes.fromhex(
        "1acd912fca662d1474f7a6c762280fc1430875bef518883387086c1125027526"
    ): "dao_proposal_timer",
    bytes.fromhex(
        "92209b0f7efb2dbaaaa3aab94dcadcafa9d008d39661763841c7d92065b3fd34"
    ): "dao_proposal_validator",
    bytes.fromhex(
        "fe6d5c0373c1750598d137ce50b5b025a203655ccab4ab3329315abad49c3586"
    ): "dao_proposal",
    bytes.fromhex(
        "637d78acd395b6bb03211bcfc5f5f2e878cba2d62b2f53871d49a8b928411b19"
    ): "dao_treasury",
    bytes.fromhex(
        "fc032384cfece9b542c3e1ea77ba119fb1013a3d74b622302c0b670447e4343d"
    ): "dao_update_proposal",
    bytes.fromhex(
        "7bc8942159e600f56a87e1d9c059c8705307ec2fb996a949503298dedfed00be"
    ): "dao_spend_p2_singleton",
    # Verifiable Credentials (VC) puzzles
    bytes.fromhex(
        "1a169582dc619f2542f8eb79f02823e1595ba0aca53820f503eda5ff20b47856"
    ): "conditions_w_fee_announce",
    # P2 puzzles (pay-to)
    bytes.fromhex(
        "542cde70d1102cd1b763220990873efc8ab15625ded7eae22cc11e21ef2e2f7c"
    ): "p2_delegated_puzzle",
    bytes.fromhex(
        "0ff94726f1a8dea5c3f70d3121945190778d3b2b3fcda3735a1f290977e98341"
    ): "p2_delegated_conditions",
    bytes.fromhex(
        "adb656e0211e2ab4f42069a4c5efc80dc907e7062be08bf1628c8e5b6d94d25b"
    ): "p2_singleton_or_delayed_puzhash",
    bytes.fromhex(
        "9590eaa169e45b655a31d3c06bbd355a3e2b2e3e410d3829748ce08ab249c39e"
    ): "p2_singleton_via_delegated_puzzle",
    bytes.fromhex(
        "40f828d8dd55603f4ff9fbf6b73271e904e69406982f4fbefae2c8dcceaf9834"
    ): "p2_singleton",
    bytes.fromhex("b10ce2d0b18dcf8c21ddfaf55d9b9f0adcbf1e0beb55b1a8b9cad9bbff4e5f22"): "p2_parent",
    # DataLayer
    bytes.fromhex(
        "0893e36a88c064fddfa6f8abdb42c044584a98cb4273b80cccc83b4867b701a1"
    ): "graftroot_dl_offers",
    # Third-party / unidentified (but commonly seen)
    bytes.fromhex(
        "28bc631093d2f8aaaed9d132f085b931dc2f90f742797e20f0438ac5e2e124ee"
    ): "unknown_delegated_wrapper",
}


def get_mod_label(mod_hash: bytes) -> str:
    """Return a human-readable label for a MOD hash, or empty string if unknown."""
    return KNOWN_MODS.get(mod_hash, "")
