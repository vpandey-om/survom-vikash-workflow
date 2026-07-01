#!/usr/bin/env python3
"""Contract stub for the SurvOm common.align.hisat2 atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_ALIGN_HISAT2 Nextflow process."
        )
    )
    parser.add_argument("--sample-id", help="Declared sample ID.")
    parser.add_argument("--paired", action="store_true", help="v0.1.0 supports paired-end FASTQ input only.")
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
