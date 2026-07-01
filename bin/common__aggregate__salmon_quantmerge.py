#!/usr/bin/env python3
"""Contract stub for the SurvOm common.aggregate.salmon_quantmerge atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_AGGREGATE_SALMON_QUANTMERGE Nextflow process."
        )
    )
    parser.add_argument(
        "--column",
        choices=["NumReads"],
        default="NumReads",
        help="Fixed Salmon quantmerge column supported by v0.1.0.",
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
