#!/usr/bin/env python3
"""Inspect a feature-by-sample matrix and sample metadata TSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


MISSING_VALUES = {"", "na", "n/a", "nan", "null", "none"}
INTEGER_TOLERANCE = 1e-9


class InspectError(Exception):
    """Raised for expected user-facing inspection failures."""


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise InspectError(f"Missing {label}: {path}")
    if not path.is_file():
        raise InspectError(f"{label} is not a file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise InspectError(f"{label} is empty or missing a header row: {path}")
        fieldnames = [name if name is not None else "" for name in reader.fieldnames]
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    return fieldnames, rows


def duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_VALUES


def parse_number(value: str) -> float | None:
    if is_missing(value):
        return None
    try:
        parsed = float(value)
    except ValueError:
        raise InspectError(f"Non-numeric matrix value detected: {value!r}")
    if not math.isfinite(parsed):
        raise InspectError(f"Non-numeric matrix value detected: {value!r}")
    return parsed


def classify_metadata_column(values: list[str], sample_id_column: str, column: str) -> str:
    non_missing = [value for value in values if not is_missing(value)]
    if column == sample_id_column:
        return "identifier_candidate"
    if not non_missing:
        return "categorical"
    numeric_count = 0
    for value in non_missing:
        try:
            parsed = float(value)
        except ValueError:
            parsed = None
        if parsed is not None and math.isfinite(parsed):
            numeric_count += 1
    if numeric_count == len(non_missing):
        return "numeric"
    if len(set(non_missing)) == len(non_missing) and len(non_missing) > 1:
        return "identifier_candidate"
    return "categorical"


def base_report(feature_id_column: str, sample_id_column: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "failed",
        "feature_id_column": feature_id_column,
        "sample_id_column": sample_id_column,
        "n_features": 0,
        "n_samples": 0,
        "matrix_sample_ids": [],
        "duplicate_feature_ids": [],
        "duplicate_matrix_sample_ids": [],
        "duplicate_metadata_sample_ids": [],
        "numeric_validity": {
            "is_numeric": False,
            "non_numeric_values": [],
            "numeric_value_count": 0,
            "missing_value_count": 0,
            "total_value_count": 0,
        },
        "integer_fraction": 0.0,
        "zero_fraction": 0.0,
        "missing_fraction": 0.0,
        "suggested_value_scale": "unknown",
        "metadata_columns": [],
        "metadata_column_types": {},
        "sample_matching": {
            "status": "not_evaluated",
            "matrix_only_sample_ids": [],
            "metadata_only_sample_ids": [],
        },
        "warnings": [],
        "errors": [],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inspect_inputs(
    feature_matrix: Path,
    sample_metadata: Path,
    feature_id_column: str,
    sample_id_column: str,
) -> dict[str, Any]:
    report = base_report(feature_id_column, sample_id_column)
    errors: list[str] = []
    warnings: list[str] = []

    matrix_header, matrix_rows = read_tsv(feature_matrix, "feature matrix")
    metadata_header, metadata_rows = read_tsv(sample_metadata, "sample metadata")

    if feature_id_column not in matrix_header:
        errors.append(f"Missing declared feature-ID column {feature_id_column!r} in feature matrix.")
    if sample_id_column not in metadata_header:
        errors.append(f"Missing declared sample-ID column {sample_id_column!r} in sample metadata.")
    if errors:
        report["errors"] = errors
        return report

    matrix_sample_ids = [column for column in matrix_header if column != feature_id_column]
    feature_ids = [row.get(feature_id_column, "") for row in matrix_rows]
    metadata_sample_ids = [row.get(sample_id_column, "") for row in metadata_rows]

    duplicate_feature_ids = duplicates(feature_ids)
    duplicate_matrix_sample_ids = duplicates(matrix_sample_ids)
    duplicate_metadata_sample_ids = duplicates(metadata_sample_ids)

    report.update(
        {
            "n_features": len(matrix_rows),
            "n_samples": len(matrix_sample_ids),
            "matrix_sample_ids": matrix_sample_ids,
            "duplicate_feature_ids": duplicate_feature_ids,
            "duplicate_matrix_sample_ids": duplicate_matrix_sample_ids,
            "duplicate_metadata_sample_ids": duplicate_metadata_sample_ids,
            "metadata_columns": metadata_header,
        }
    )

    if duplicate_feature_ids:
        errors.append(f"Duplicate feature IDs detected: {', '.join(duplicate_feature_ids)}")
    if duplicate_matrix_sample_ids:
        errors.append(f"Duplicate matrix sample IDs detected: {', '.join(duplicate_matrix_sample_ids)}")
    if duplicate_metadata_sample_ids:
        errors.append(f"Duplicate metadata sample IDs detected: {', '.join(duplicate_metadata_sample_ids)}")

    matrix_set = set(matrix_sample_ids)
    metadata_set = set(metadata_sample_ids)
    matrix_only = sorted(matrix_set - metadata_set)
    metadata_only = sorted(metadata_set - matrix_set)
    sample_match_status = "matched" if not matrix_only and not metadata_only else "mismatched"
    report["sample_matching"] = {
        "status": sample_match_status,
        "matrix_only_sample_ids": matrix_only,
        "metadata_only_sample_ids": metadata_only,
    }
    if sample_match_status != "matched":
        errors.append(
            "Matrix and metadata sample IDs do not match. "
            f"Matrix-only sample IDs: {matrix_only}; metadata-only sample IDs: {metadata_only}."
        )

    total_values = len(matrix_rows) * len(matrix_sample_ids)
    numeric_values: list[float] = []
    missing_count = 0
    non_numeric_values: list[dict[str, Any]] = []
    for row_index, row in enumerate(matrix_rows, start=2):
        feature_id = row.get(feature_id_column, "")
        for sample_id in matrix_sample_ids:
            raw_value = row.get(sample_id, "")
            if is_missing(raw_value):
                missing_count += 1
                continue
            try:
                parsed = parse_number(raw_value)
            except InspectError:
                non_numeric_values.append(
                    {
                        "row": row_index,
                        "feature_id": feature_id,
                        "sample_id": sample_id,
                        "value": raw_value,
                    }
                )
                continue
            if parsed is not None:
                numeric_values.append(parsed)

    if non_numeric_values:
        preview = non_numeric_values[0]
        errors.append(
            "Non-numeric matrix value detected at "
            f"feature {preview['feature_id']!r}, sample {preview['sample_id']!r}: {preview['value']!r}."
        )

    integer_count = sum(1 for value in numeric_values if abs(value - round(value)) <= INTEGER_TOLERANCE)
    zero_count = sum(1 for value in numeric_values if value == 0)
    non_negative = all(value >= 0 for value in numeric_values)
    numeric_count = len(numeric_values)

    integer_fraction = integer_count / numeric_count if numeric_count else 0.0
    zero_fraction = zero_count / numeric_count if numeric_count else 0.0
    missing_fraction = missing_count / total_values if total_values else 0.0

    suggested_value_scale = "unknown"
    if not non_numeric_values:
        if numeric_count and non_negative and integer_fraction == 1.0:
            suggested_value_scale = "raw_count"
        elif numeric_count:
            suggested_value_scale = "continuous"

    if missing_count:
        warnings.append(f"Missing matrix values detected: {missing_count} of {total_values}.")
    if numeric_values and any(value < 0 for value in numeric_values):
        warnings.append("Negative matrix values detected; raw count scale is unlikely.")

    report["numeric_validity"] = {
        "is_numeric": not non_numeric_values,
        "non_numeric_values": non_numeric_values,
        "numeric_value_count": numeric_count,
        "missing_value_count": missing_count,
        "total_value_count": total_values,
    }
    report["integer_fraction"] = round(integer_fraction, 10)
    report["zero_fraction"] = round(zero_fraction, 10)
    report["missing_fraction"] = round(missing_fraction, 10)
    report["suggested_value_scale"] = suggested_value_scale

    report["metadata_column_types"] = {
        column: classify_metadata_column([row.get(column, "") for row in metadata_rows], sample_id_column, column)
        for column in metadata_header
    }

    report["warnings"] = warnings
    report["errors"] = errors
    report["status"] = "failed" if errors else "passed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a feature matrix TSV and sample metadata TSV without modifying the inputs."
    )
    parser.add_argument("--feature-matrix", required=True, type=Path, help="Feature-by-sample TSV matrix.")
    parser.add_argument("--sample-metadata", required=True, type=Path, help="Sample metadata TSV.")
    parser.add_argument("--feature-id-column", required=True, help="Feature ID column in the matrix.")
    parser.add_argument("--sample-id-column", required=True, help="Sample ID column in metadata.")
    parser.add_argument("--out-inspection", required=True, type=Path, help="Inspection report JSON output.")
    args = parser.parse_args(argv)

    try:
        report = inspect_inputs(
            args.feature_matrix,
            args.sample_metadata,
            args.feature_id_column,
            args.sample_id_column,
        )
    except InspectError as exc:
        report = base_report(args.feature_id_column, args.sample_id_column)
        report["errors"] = [str(exc)]
        write_report(args.out_inspection, report)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_report(args.out_inspection, report)
    if report["status"] != "passed":
        for error in report["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
