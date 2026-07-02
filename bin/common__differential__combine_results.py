#!/usr/bin/env python3
"""Validate and combine standardized differential-analysis result tables."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "feature_id",
    "contrast_id",
    "effect_estimate",
    "effect_type",
    "p_value",
    "adjusted_p_value",
    "status",
    "method",
    "positive_effect_definition",
]


class CombineError(Exception):
    """Raised for expected user-facing combine failures."""


def split_paths(raw: str, label: str) -> list[Path]:
    paths = [Path(item) for item in raw.split(",") if item]
    if not paths:
        raise CombineError(f"At least one {label} path is required.")
    return paths


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise CombineError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CombineError(f"{label} is not valid JSON: {path} line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise CombineError(f"{label} must contain a JSON object: {path}")
    return parsed


def read_results(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise CombineError(f"Missing result table: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise CombineError(f"Result table is empty or missing a header: {path}")
        header = list(reader.fieldnames)
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise CombineError(f"Result table {path} is missing required column(s): {', '.join(missing)}.")
        rows = [dict(row) for row in reader]
    return header, rows


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def method_summary(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    by_method: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_method[row["method"]].append(row)
    return {
        method: {
            "n_rows": len(method_rows),
            "contrasts": sorted({row["contrast_id"] for row in method_rows}),
            "statuses": dict(Counter(row["status"] for row in method_rows)),
        }
        for method, method_rows in sorted(by_method.items())
    }


def combine(result_paths: list[Path], diagnostics_paths: list[Path]) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    if len(result_paths) != len(diagnostics_paths):
        raise CombineError("The number of result tables must match the number of diagnostics files.")

    combined_header: list[str] = []
    combined_rows: list[dict[str, str]] = []
    diagnostics_by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    warnings: list[str] = []

    for index, result_path in enumerate(result_paths):
        header, rows = read_results(result_path)
        for column in header:
            if column not in combined_header:
                combined_header.append(column)
        combined_rows.extend(rows)

        diagnostics = read_json(diagnostics_paths[index], "diagnostics JSON")
        method = str(diagnostics.get("method", rows[0]["method"] if rows else f"input_{index + 1}"))
        diagnostics_by_method[method].append(diagnostics)
        if diagnostics.get("status") not in (None, "passed"):
            warnings.append(f"Diagnostics file {diagnostics_paths[index]} has status {diagnostics.get('status')!r}.")

    key_counts = Counter((row["feature_id"], row["contrast_id"], row["method"]) for row in combined_rows)
    duplicate_keys = sorted(key for key, count in key_counts.items() if count > 1)
    if duplicate_keys:
        formatted = [f"{feature_id}/{contrast_id}/{method}" for feature_id, contrast_id, method in duplicate_keys]
        raise CombineError(
            "Result rows must be unique by feature_id + contrast_id + method. "
            f"Duplicates: {', '.join(formatted)}."
        )

    methods = sorted({row["method"] for row in combined_rows})
    diagnostics = {
        "schema_version": 1,
        "status": "passed",
        "methods": methods,
        "n_input_result_files": len(result_paths),
        "n_total_result_rows": len(combined_rows),
        "contrasts": sorted({row["contrast_id"] for row in combined_rows}),
        "per_method_summary": method_summary(combined_rows),
        "method_diagnostics": diagnostics_by_method,
        "warnings": warnings,
        "errors": [],
    }
    ordered_header = REQUIRED_COLUMNS + [column for column in combined_header if column not in REQUIRED_COLUMNS]
    return ordered_header, combined_rows, diagnostics


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(args: argparse.Namespace, message: str) -> None:
    payload = {
        "schema_version": 1,
        "status": "failed",
        "methods": [],
        "n_input_result_files": 0,
        "n_total_result_rows": 0,
        "contrasts": [],
        "per_method_summary": {},
        "warnings": [],
        "errors": [message],
    }
    write_json(args.out_combined_diagnostics, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and combine standardized differential-analysis result tables."
    )
    parser.add_argument("--result-tables", required=True, help="Comma-separated standardized result TSV paths.")
    parser.add_argument("--diagnostics", required=True, help="Comma-separated diagnostics JSON paths.")
    parser.add_argument("--out-combined-results", required=True, type=Path)
    parser.add_argument("--out-combined-diagnostics", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        result_paths = split_paths(args.result_tables, "result table")
        diagnostics_paths = split_paths(args.diagnostics, "diagnostics")
        header, rows, diagnostics = combine(result_paths, diagnostics_paths)
    except CombineError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_tsv(args.out_combined_results, header, rows)
    write_json(args.out_combined_diagnostics, diagnostics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
