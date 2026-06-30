#!/usr/bin/env python3
"""Normalize SeqKit stats TSV output into deterministic JSON and TSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = ["file", "format", "type", "num_seqs", "sum_len", "min_len", "avg_len", "max_len"]
OPTIONAL_NUMERIC_COLUMNS = {
    "Q1": "q1_len",
    "Q2": "q2_len",
    "Q3": "q3_len",
    "sum_gap": "sum_gap",
    "N50": "n50",
    "Q20(%)": "q20_percent",
    "Q30(%)": "q30_percent",
    "GC(%)": "gc_percent",
    "AvgQual": "avg_qual",
    "avg_qual": "avg_qual",
}
TSV_COLUMNS = [
    "source_file",
    "format",
    "type",
    "num_seqs",
    "sum_len",
    "min_len",
    "avg_len",
    "max_len",
    "gc_percent",
    "q20_percent",
    "q30_percent",
    "avg_qual",
]


class NormalizeError(Exception):
    """Raised for invalid SeqKit TSV input."""


def parse_number(raw: str, column: str, row_number: int) -> int | float:
    value = raw.strip().replace(",", "")
    if value == "":
        raise NormalizeError(f"row {row_number}: column '{column}' is empty")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise NormalizeError(f"row {row_number}: column '{column}' is not numeric: {raw!r}") from exc
    if not math.isfinite(parsed):
        raise NormalizeError(f"row {row_number}: column '{column}' must be finite")
    if parsed.is_integer():
        return int(parsed)
    return round(parsed, 6)


def parse_int(raw: str, column: str, row_number: int) -> int:
    parsed = parse_number(raw, column, row_number)
    if isinstance(parsed, float):
        raise NormalizeError(f"row {row_number}: column '{column}' must be an integer")
    return parsed


def normalize_rows(seqkit_tsv: Path) -> list[dict[str, Any]]:
    with seqkit_tsv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise NormalizeError("SeqKit TSV is empty and missing a header")
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise NormalizeError(f"SeqKit TSV is missing required column(s): {', '.join(missing)}")

        rows = []
        for row_number, row in enumerate(reader, start=2):
            normalized = {
                "source_file": row["file"],
                "format": row["format"],
                "type": row["type"],
                "num_seqs": parse_int(row["num_seqs"], "num_seqs", row_number),
                "sum_len": parse_int(row["sum_len"], "sum_len", row_number),
                "min_len": parse_int(row["min_len"], "min_len", row_number),
                "avg_len": parse_number(row["avg_len"], "avg_len", row_number),
                "max_len": parse_int(row["max_len"], "max_len", row_number),
            }
            for seqkit_column, output_key in OPTIONAL_NUMERIC_COLUMNS.items():
                if seqkit_column in row and row[seqkit_column] not in {None, ""}:
                    normalized[output_key] = parse_number(row[seqkit_column], seqkit_column, row_number)
            rows.append(normalized)
        return rows


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": 1,
        "generated_by": "bin/common__qc__seqkit_fastq_stats.py",
        "files": rows,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_tsv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TSV_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_tsv_value(row.get(column)) for column in TSV_COLUMNS})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize SeqKit stats TSV output.")
    parser.add_argument("--seqkit-tsv", required=True, help="Input from seqkit stats --all --tabular.")
    parser.add_argument("--json-out", required=True, help="Deterministic normalized JSON output.")
    parser.add_argument("--tsv-out", required=True, help="Deterministic normalized TSV output.")
    args = parser.parse_args(argv)

    try:
        rows = normalize_rows(Path(args.seqkit_tsv))
        write_json(Path(args.json_out), rows)
        write_tsv(Path(args.tsv_out), rows)
    except NormalizeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
