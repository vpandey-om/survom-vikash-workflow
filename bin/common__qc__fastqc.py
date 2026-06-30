#!/usr/bin/env python3
"""Implementation-contract stub for common.qc.fastqc.

FastQC report generation is performed entirely by the Nextflow module with the
pinned FastQC container. This file exists so metadata and registry tooling can
verify the declared implementation path and checksum for the atomic step.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. The common.qc.fastqc step emits native FastQC "
            "HTML and ZIP reports from modules/local/common/qc/fastqc/main.nf."
        )
    )
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
