#!/usr/bin/env python3
"""Contract stub for the SurvOm common.quant.featurecounts atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_QUANT_FEATURECOUNTS Nextflow process."
        )
    )
    parser.add_argument("--sample-id", help="Declared sample ID.")
    parser.add_argument("--paired", action="store_true", help="v0.1.0 uses paired-end counting with -p.")
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
