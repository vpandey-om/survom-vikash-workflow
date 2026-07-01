#!/usr/bin/env python3
"""Contract stub for the SurvOm common.reference.hisat2_index atomic step."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. Runtime execution is provided by the "
            "SURVOM_COMMON_REFERENCE_HISAT2_INDEX Nextflow process."
        )
    )
    parser.add_argument("--genome-fasta", help="Declared genome FASTA input.")
    parser.add_argument("--annotation-gtf", help="Declared GTF annotation input.")
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
