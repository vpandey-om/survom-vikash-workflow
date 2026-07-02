#!/usr/bin/env python3
"""Filter low-information features before differential modeling."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


RAW_COUNT_ASSAYS = {"bulk_rnaseq_counts"}
MISSING_VALUES = {"", "na", "n/a", "nan", "null", "none"}


class FilterError(Exception):
    """Raised for expected user-facing filter failures."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FilterError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FilterError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise FilterError(f"{label} must contain a JSON object.")
    return parsed


def read_matrix(path: Path, feature_id_column: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FilterError(f"Missing feature matrix: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise FilterError("Feature matrix is empty or missing a header row.")
        header = [name if name is not None else "" for name in reader.fieldnames]
        if feature_id_column not in header:
            raise FilterError(f"Feature ID column {feature_id_column!r} is missing from feature matrix.")
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    sample_ids = [column for column in header if column != feature_id_column]
    return header, rows, sample_ids


def write_matrix(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_VALUES


def parse_number(value: str, feature_id: str, sample_id: str) -> float | None:
    if is_missing(value):
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise FilterError(
            f"Matrix value for feature {feature_id!r}, sample {sample_id!r} is not numeric: {value!r}."
        ) from exc
    if not math.isfinite(parsed):
        raise FilterError(
            f"Matrix value for feature {feature_id!r}, sample {sample_id!r} is not finite: {value!r}."
        )
    return parsed


def unique_feature_ids(rows: list[dict[str, str]], feature_id_column: str) -> None:
    feature_ids = [row.get(feature_id_column, "") for row in rows]
    duplicates = sorted(feature_id for feature_id, count in Counter(feature_ids).items() if count > 1)
    if duplicates:
        raise FilterError(f"Feature IDs must be unique. Duplicates: {', '.join(duplicates)}.")


def require_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FilterError(f"filter_spec.{key} must be an explicit number.")
    return float(value)


def require_positive_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise FilterError(f"filter_spec.{key} must be an explicit integer greater than or equal to 1.")
    return value


def base_report(assay_type: str, value_scale: str, n_before: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "failed",
        "n_features_before": n_before,
        "n_features_after": 0,
        "assay_type": assay_type,
        "value_scale": value_scale,
        "filter_rules": {},
        "min_count": None,
        "min_samples_count": None,
        "min_samples_fraction": None,
        "resolved_min_samples": None,
        "dropped_feature_ids": [],
        "warnings": [],
        "errors": [],
    }


def resolve_raw_count_filter(filter_spec: dict[str, Any], n_samples: int) -> tuple[int, int | None, float | None, int]:
    if "min_count" not in filter_spec:
        raise FilterError("filter_spec.min_count is required for raw-count matrices.")
    min_count = require_positive_int(filter_spec, "min_count")
    has_count = "min_samples_count" in filter_spec
    has_fraction = "min_samples_fraction" in filter_spec
    if has_count == has_fraction:
        raise FilterError("filter_spec must supply exactly one of min_samples_count or min_samples_fraction.")
    if has_count:
        min_samples_count = require_positive_int(filter_spec, "min_samples_count")
        if min_samples_count > n_samples:
            raise FilterError("filter_spec.min_samples_count cannot exceed the number of matrix samples.")
        return min_count, min_samples_count, None, min_samples_count
    min_samples_fraction = require_number(filter_spec, "min_samples_fraction")
    if min_samples_fraction <= 0 or min_samples_fraction > 1:
        raise FilterError("filter_spec.min_samples_fraction must be greater than 0 and less than or equal to 1.")
    resolved_min_samples = math.ceil(n_samples * min_samples_fraction)
    return min_count, None, min_samples_fraction, resolved_min_samples


def filter_raw_counts(
    rows: list[dict[str, str]],
    sample_ids: list[str],
    feature_id_column: str,
    filter_spec: dict[str, Any],
    report: dict[str, Any],
) -> list[dict[str, str]]:
    min_count, min_samples_count, min_samples_fraction, resolved_min_samples = resolve_raw_count_filter(
        filter_spec,
        len(sample_ids),
    )
    kept = []
    dropped = []
    for row in rows:
        feature_id = row.get(feature_id_column, "")
        values = [parse_number(row.get(sample_id, ""), feature_id, sample_id) for sample_id in sample_ids]
        present_values = [value for value in values if value is not None]
        if any(value < 0 or abs(value - round(value)) > 1e-9 for value in present_values):
            raise FilterError("Raw-count filtering requires non-negative integer-like matrix values.")
        passing_samples = sum(1 for value in present_values if value >= min_count)
        if passing_samples >= resolved_min_samples:
            kept.append(row)
        else:
            dropped.append(feature_id)

    report.update(
        {
            "filter_rules": {
                "mode": "raw_count_prevalence",
                "rule": "count >= min_count in at least resolved_min_samples samples",
            },
            "min_count": min_count,
            "min_samples_count": min_samples_count,
            "min_samples_fraction": min_samples_fraction,
            "resolved_min_samples": resolved_min_samples,
            "dropped_feature_ids": dropped,
        }
    )
    return kept


def filter_continuous(
    rows: list[dict[str, str]],
    sample_ids: list[str],
    feature_id_column: str,
    filter_spec: dict[str, Any],
    report: dict[str, Any],
) -> list[dict[str, str]]:
    unsupported = {"min_count", "min_samples_count", "min_samples_fraction"} & set(filter_spec)
    if unsupported:
        raise FilterError(
            "Continuous matrices support only max_missing_fraction and drop_zero_variance; "
            f"unsupported setting(s): {sorted(unsupported)}."
        )
    if "max_missing_fraction" not in filter_spec and "drop_zero_variance" not in filter_spec:
        raise FilterError("Continuous filtering requires max_missing_fraction and/or drop_zero_variance.")
    max_missing_fraction = filter_spec.get("max_missing_fraction")
    if max_missing_fraction is not None:
        if not isinstance(max_missing_fraction, (int, float)) or isinstance(max_missing_fraction, bool):
            raise FilterError("filter_spec.max_missing_fraction must be numeric when supplied.")
        if max_missing_fraction < 0 or max_missing_fraction > 1:
            raise FilterError("filter_spec.max_missing_fraction must be between 0 and 1.")
    drop_zero_variance = filter_spec.get("drop_zero_variance", False)
    if not isinstance(drop_zero_variance, bool):
        raise FilterError("filter_spec.drop_zero_variance must be true or false when supplied.")

    kept = []
    dropped = []
    for row in rows:
        feature_id = row.get(feature_id_column, "")
        values = [parse_number(row.get(sample_id, ""), feature_id, sample_id) for sample_id in sample_ids]
        missing_count = sum(1 for value in values if value is None)
        present_values = [value for value in values if value is not None]
        missing_fraction = missing_count / len(sample_ids) if sample_ids else 0.0
        drop = False
        if max_missing_fraction is not None and missing_fraction > max_missing_fraction:
            drop = True
        if drop_zero_variance and present_values and len(set(present_values)) == 1:
            drop = True
        if drop:
            dropped.append(feature_id)
        else:
            kept.append(row)

    report.update(
        {
            "filter_rules": {
                "mode": "continuous_missingness_variance",
                "max_missing_fraction": max_missing_fraction,
                "drop_zero_variance": drop_zero_variance,
            },
            "dropped_feature_ids": dropped,
        }
    )
    return kept


def filter_features(feature_matrix: Path, feature_matrix_meta: dict[str, Any], filter_spec: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    feature_id_column = feature_matrix_meta.get("feature_id_column")
    if not isinstance(feature_id_column, str) or not feature_id_column:
        raise FilterError("feature_matrix_meta.feature_id_column is required.")
    assay_type = str(feature_matrix_meta.get("assay_type", "unknown"))
    value_profile = feature_matrix_meta.get("value_profile", {})
    value_scale = str(value_profile.get("suggested_value_scale", feature_matrix_meta.get("suggested_value_scale", "unknown")))
    header, rows, sample_ids = read_matrix(feature_matrix, feature_id_column)
    unique_feature_ids(rows, feature_id_column)
    report = base_report(assay_type, value_scale, len(rows))

    if assay_type in RAW_COUNT_ASSAYS or value_scale == "raw_count":
        kept = filter_raw_counts(rows, sample_ids, feature_id_column, filter_spec, report)
    elif value_scale == "continuous":
        kept = filter_continuous(rows, sample_ids, feature_id_column, filter_spec, report)
    else:
        raise FilterError(f"Unsupported assay/value scale for filtering: assay_type={assay_type!r}, value_scale={value_scale!r}.")

    if not kept:
        report["dropped_feature_ids"] = [row.get(feature_id_column, "") for row in rows]
        raise FilterError("All features were removed by filtering; choose less restrictive filter settings.")
    report["status"] = "passed"
    report["n_features_after"] = len(kept)
    return header, kept, report


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(args: argparse.Namespace, message: str, feature_matrix_meta: dict[str, Any] | None = None) -> None:
    assay_type = str((feature_matrix_meta or {}).get("assay_type", "unknown"))
    value_profile = (feature_matrix_meta or {}).get("value_profile", {})
    value_scale = str(value_profile.get("suggested_value_scale", (feature_matrix_meta or {}).get("suggested_value_scale", "unknown")))
    report = base_report(assay_type, value_scale, 0)
    report["errors"] = [message]
    write_json(args.out_filter_report, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Filter low-information features before differential modeling.")
    parser.add_argument("--feature-matrix", required=True, type=Path)
    parser.add_argument("--feature-matrix-meta", required=True, type=Path)
    parser.add_argument("--filter-spec", required=True, type=Path)
    parser.add_argument("--out-filtered-feature-matrix", required=True, type=Path)
    parser.add_argument("--out-filter-report", required=True, type=Path)
    args = parser.parse_args(argv)

    feature_matrix_meta: dict[str, Any] | None = None
    try:
        feature_matrix_meta = load_json(args.feature_matrix_meta, "feature matrix metadata")
        filter_spec = load_json(args.filter_spec, "filter spec")
        header, kept, report = filter_features(args.feature_matrix, feature_matrix_meta, filter_spec)
    except FilterError as exc:
        write_failure(args, str(exc), feature_matrix_meta)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_matrix(args.out_filtered_feature_matrix, header, kept)
    write_json(args.out_filter_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
