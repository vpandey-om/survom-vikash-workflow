#!/usr/bin/env python3
"""Contract stub for the SurvOm common.quant.salmon_quant atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_QUANT_SALMON_QUANT Nextflow process."
        )
    )
    parser.add_argument(
        "--read-layout",
        choices=["single", "paired"],
        help="Declared FASTQ layout supported by v0.1.0.",
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
