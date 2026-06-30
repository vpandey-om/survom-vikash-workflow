#!/usr/bin/env python3
"""Implementation-contract stub for common.qc.multiqc.

MultiQC report generation is performed entirely by the Nextflow module with the
pinned MultiQC container. This file exists so metadata and registry tooling can
verify the declared implementation path and checksum for the atomic step.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract stub only. The common.qc.multiqc step emits native MultiQC "
            "HTML and data outputs from modules/local/common/qc/multiqc/main.nf."
        )
    )
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
