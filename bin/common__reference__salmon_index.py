#!/usr/bin/env python3
"""Contract stub for the SurvOm common.reference.salmon_index atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_REFERENCE_SALMON_INDEX Nextflow process."
        )
    )
    parser.add_argument(
        "--transcript-fasta",
        required=False,
        help="Declared transcript FASTA or FASTA.GZ input for Salmon index creation.",
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
