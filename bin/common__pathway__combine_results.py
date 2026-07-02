#!/usr/bin/env python3
"""Validate and combine standardized pathway enrichment result tables."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "database_id",
    "database_version",
    "gene_set_id",
    "gene_set_name",
    "test_method",
    "direction",
    "background_count",
    "selected_count",
    "gene_set_size",
    "overlap_count",
    "overlap_resolved_identifiers",
    "p_value",
    "p_adjust_method",
    "adjusted_p_value",
]
NUMERIC_COLUMNS = [
    "background_count",
    "selected_count",
    "gene_set_size",
    "overlap_count",
    "p_value",
    "adjusted_p_value",
]


class CombineError(Exception):
    """Raised for expected user-facing pathway combine failures."""


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
        raise CombineError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise CombineError(f"{label} must contain a JSON object.")
    return parsed


def require_bool(params: dict[str, Any], key: str) -> bool:
    value = params.get(key)
    if not isinstance(value, bool):
        raise CombineError(f"combine_params.{key} must be an explicit boolean.")
    return value


def read_results(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise CombineError(f"Missing enrichment result table: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise CombineError(f"Enrichment result table is empty or missing a header: {path}")
        header = [name if name is not None else "" for name in reader.fieldnames]
        if any(not column for column in header):
            raise CombineError(f"Enrichment result table contains an empty column name: {path}")
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise CombineError(f"Enrichment result table {path} is missing required column(s): {', '.join(missing)}.")
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    if not rows:
        raise CombineError(f"Enrichment result table must contain at least one data row: {path}")
    return header, rows


def validate_numeric(row: dict[str, str], path: Path, row_number: int) -> None:
    for column in NUMERIC_COLUMNS:
        raw = row.get(column, "").strip()
        if raw == "":
            raise CombineError(f"Column {column!r} must not be empty in {path} row {row_number}.")
        try:
            value = float(raw)
        except ValueError as exc:
            raise CombineError(f"Column {column!r} must be numeric in {path} row {row_number}: {raw!r}.") from exc
        if column in {"background_count", "selected_count", "gene_set_size", "overlap_count"} and not value.is_integer():
            raise CombineError(f"Column {column!r} must contain integer counts in {path} row {row_number}.")


def validate_rows(path: Path, rows: list[dict[str, str]]) -> None:
    for row_number, row in enumerate(rows, start=2):
        empty_required = [column for column in REQUIRED_COLUMNS if not row.get(column, "").strip()]
        if empty_required:
            raise CombineError(
                f"Enrichment result table {path} row {row_number} has empty required column(s): "
                f"{', '.join(empty_required)}."
            )
        validate_numeric(row, path, row_number)


def duplicate_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row.get("contrast_id", ""),
        row["database_id"],
        row["database_version"],
        row["gene_set_id"],
        row["test_method"],
        row["direction"],
    )


def combine(result_paths: list[Path], params: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    allow_mixed_versions = require_bool(params, "allow_mixed_database_versions")
    combined_header: list[str] = []
    combined_rows: list[dict[str, str]] = []
    input_summaries: list[dict[str, Any]] = []

    for path in result_paths:
        header, rows = read_results(path)
        validate_rows(path, rows)
        for column in header:
            if column not in combined_header:
                combined_header.append(column)
        combined_rows.extend(rows)
        input_summaries.append(
            {
                "path": str(path),
                "n_rows": len(rows),
                "database_ids": sorted({row["database_id"] for row in rows}),
                "database_versions": sorted({row["database_version"] for row in rows}),
                "test_methods": sorted({row["test_method"] for row in rows}),
                "directions": sorted({row["direction"] for row in rows}),
            }
        )

    versions_by_database: dict[str, set[str]] = defaultdict(set)
    for row in combined_rows:
        versions_by_database[row["database_id"]].add(row["database_version"])
    mixed_versions = {
        database_id: sorted(versions)
        for database_id, versions in sorted(versions_by_database.items())
        if len(versions) > 1
    }
    if mixed_versions and not allow_mixed_versions:
        formatted = "; ".join(f"{database_id}: {', '.join(versions)}" for database_id, versions in mixed_versions.items())
        raise CombineError(
            "Multiple database_version values were observed for the same database_id and "
            "combine_params.allow_mixed_database_versions is false: "
            f"{formatted}."
        )

    key_counts = Counter(duplicate_key(row) for row in combined_rows)
    duplicate_keys = sorted(key for key, count in key_counts.items() if count > 1)
    if duplicate_keys:
        formatted = [
            "/".join(value if value else "<no_contrast>" for value in key)
            for key in duplicate_keys
        ]
        raise CombineError(
            "Combined enrichment rows must be unique by contrast_id + database_id + database_version + "
            f"gene_set_id + test_method + direction. Duplicates: {', '.join(formatted)}."
        )

    ordered_header = REQUIRED_COLUMNS + [column for column in combined_header if column not in REQUIRED_COLUMNS]
    diagnostics = {
        "schema_version": 1,
        "step_id": "common.pathway.combine_results",
        "version": "0.1.0",
        "status": "passed",
        "parameters": {
            "allow_mixed_database_versions": allow_mixed_versions,
        },
        "n_input_result_files": len(result_paths),
        "n_total_result_rows": len(combined_rows),
        "database_versions_by_database_id": {key: sorted(value) for key, value in sorted(versions_by_database.items())},
        "mixed_database_versions": mixed_versions,
        "test_methods": sorted({row["test_method"] for row in combined_rows}),
        "directions": sorted({row["direction"] for row in combined_rows}),
        "input_summaries": input_summaries,
        "warnings": [],
        "errors": [],
    }
    return ordered_header, combined_rows, diagnostics


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(args: argparse.Namespace, message: str) -> None:
    payload = {
        "schema_version": 1,
        "step_id": "common.pathway.combine_results",
        "version": "0.1.0",
        "status": "failed",
        "parameters": {},
        "n_input_result_files": 0,
        "n_total_result_rows": 0,
        "database_versions_by_database_id": {},
        "mixed_database_versions": {},
        "warnings": [],
        "errors": [message],
    }
    write_json(args.out_combined_diagnostics, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and combine pathway enrichment result tables.")
    parser.add_argument("--enrichment-results", required=True, help="Comma-separated pathway enrichment result TSV paths.")
    parser.add_argument("--combine-params", required=True, type=Path)
    parser.add_argument("--out-combined-results", required=True, type=Path)
    parser.add_argument("--out-combined-diagnostics", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        result_paths = split_paths(args.enrichment_results, "enrichment result table")
        params = read_json(args.combine_params, "combine params")
        header, rows, diagnostics = combine(result_paths, params)
    except CombineError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_tsv(args.out_combined_results, header, rows)
    write_json(args.out_combined_diagnostics, diagnostics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
