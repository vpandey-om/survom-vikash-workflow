#!/usr/bin/env python3
"""Contract stub for the SurvOm common.preprocess.fastp atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_PREPROCESS_FASTP Nextflow process."
        )
    )
    parser.add_argument(
        "--trimming-profile",
        choices=["default", "illumina_pe_q20"],
        help="Declared fastp trimming profile supported by v0.1.0.",
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
