#!/usr/bin/env python3
"""Validate feature matrix, metadata, and design specification before modeling."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class ValidationError(Exception):
    """Raised for expected user-facing validation failures."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValidationError(f"{label} must contain a JSON object.")
    return parsed


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise ValidationError(f"Missing {label}: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValidationError(f"{label} is empty or missing a header row: {path}")
        header = [name if name is not None else "" for name in reader.fieldnames]
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    return header, rows


def duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def matrix_rank(matrix: list[list[float]], tolerance: float = 1e-10) -> int:
    if not matrix:
        return 0
    work = [row[:] for row in matrix]
    n_rows = len(work)
    n_cols = len(work[0])
    rank = 0
    for col in range(n_cols):
        pivot = None
        for row in range(rank, n_rows):
            if abs(work[row][col]) > tolerance:
                pivot = row
                break
        if pivot is None:
            continue
        work[rank], work[pivot] = work[pivot], work[rank]
        pivot_value = work[rank][col]
        work[rank] = [value / pivot_value for value in work[rank]]
        for row in range(n_rows):
            if row == rank:
                continue
            factor = work[row][col]
            if abs(factor) <= tolerance:
                continue
            work[row] = [value - factor * work[rank][idx] for idx, value in enumerate(work[row])]
        rank += 1
        if rank == n_rows:
            break
    return rank


def require_string(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{context} requires non-empty string field {key!r}.")
    return value


def observed_levels(metadata_rows: list[dict[str, str]], variable: str) -> list[str]:
    return sorted({row.get(variable, "") for row in metadata_rows if row.get(variable, "") != ""})


def build_design_matrix(metadata_rows: list[dict[str, str]], variables: list[dict[str, Any]]) -> tuple[list[list[float]], list[str]]:
    columns = ["Intercept"]
    matrix = [[1.0] for _ in metadata_rows]
    for variable in variables:
        name = str(variable["name"])
        reference = str(variable["reference_level"])
        levels = [level for level in observed_levels(metadata_rows, name) if level != reference]
        for level in levels:
            columns.append(f"{name}[{level}]")
            for row_index, row in enumerate(metadata_rows):
                matrix[row_index].append(1.0 if row.get(name, "") == level else 0.0)
    return matrix, columns


def confounding_message(primary_name: str, variables: list[dict[str, Any]], metadata_rows: list[dict[str, str]]) -> str:
    primary_levels = observed_levels(metadata_rows, primary_name)
    for variable in variables:
        name = str(variable["name"])
        if name == primary_name:
            continue
        mapping: dict[str, set[str]] = defaultdict(set)
        for row in metadata_rows:
            mapping[row.get(primary_name, "")].add(row.get(name, ""))
        if len(primary_levels) >= 2 and all(len(mapping[level]) == 1 for level in primary_levels):
            pairs = [f"{primary_name}={level} only appears with {name}={next(iter(mapping[level]))}" for level in primary_levels]
            return (
                f"{primary_name} and {name} cannot be evaluated separately because "
                f"{'; '.join(pairs)}."
            )
    return "The design matrix is rank deficient; one or more design variables are perfectly confounded."


def validate(
    feature_matrix: Path,
    feature_matrix_meta: dict[str, Any],
    sample_metadata: Path,
    design_spec: dict[str, Any],
    minimum_group_size: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if minimum_group_size < 1:
        raise ValidationError("--minimum-group-size must be at least 1.")

    matrix_header, matrix_rows = read_tsv(feature_matrix, "feature matrix")
    metadata_header, metadata_rows = read_tsv(sample_metadata, "sample metadata")
    feature_id_column = require_string(feature_matrix_meta, "feature_id_column", "feature_matrix_meta")
    sample_id_column = require_string(feature_matrix_meta, "sample_id_column", "feature_matrix_meta")
    if feature_id_column not in matrix_header:
        raise ValidationError(f"Feature ID column {feature_id_column!r} is missing from the feature matrix.")
    if sample_id_column not in metadata_header:
        raise ValidationError(f"Sample ID column {sample_id_column!r} is missing from the sample metadata.")

    matrix_sample_ids = [column for column in matrix_header if column != feature_id_column]
    metadata_sample_ids = [row.get(sample_id_column, "") for row in metadata_rows]
    feature_ids = [row.get(feature_id_column, "") for row in matrix_rows]

    duplicate_feature_ids = duplicates(feature_ids)
    duplicate_metadata_sample_ids = duplicates(metadata_sample_ids)
    if duplicate_feature_ids:
        raise ValidationError(f"Feature IDs must be unique. Duplicates: {', '.join(duplicate_feature_ids)}.")
    if duplicate_metadata_sample_ids:
        raise ValidationError(f"Metadata sample IDs must be unique. Duplicates: {', '.join(duplicate_metadata_sample_ids)}.")
    matrix_only = sorted(set(matrix_sample_ids) - set(metadata_sample_ids))
    metadata_only = sorted(set(metadata_sample_ids) - set(matrix_sample_ids))
    if matrix_only or metadata_only:
        raise ValidationError(
            "Matrix and metadata sample IDs must match exactly. "
            f"Matrix-only sample IDs: {matrix_only}; metadata-only sample IDs: {metadata_only}."
        )

    metadata_by_sample = {row[sample_id_column]: row for row in metadata_rows}
    ordered_metadata = [metadata_by_sample[sample_id] for sample_id in matrix_sample_ids]

    primary = design_spec.get("primary_factor")
    if not isinstance(primary, dict):
        raise ValidationError("design_spec.primary_factor must be an object.")
    primary_name = require_string(primary, "name", "primary_factor")
    primary_reference = require_string(primary, "reference_level", "primary_factor")
    covariates = design_spec.get("covariates", [])
    if not isinstance(covariates, list):
        raise ValidationError("design_spec.covariates must be a list.")

    variables = [{"name": primary_name, "reference_level": primary_reference}]
    for covariate in covariates:
        if not isinstance(covariate, dict):
            raise ValidationError("Each covariate must be an object.")
        variables.append(
            {
                "name": require_string(covariate, "name", "covariate"),
                "reference_level": require_string(covariate, "reference_level", "covariate"),
            }
        )

    for variable in variables:
        name = str(variable["name"])
        reference = str(variable["reference_level"])
        if name not in metadata_header:
            raise ValidationError(f"Design variable {name!r} is missing from sample metadata.")
        levels = observed_levels(ordered_metadata, name)
        if reference not in levels:
            raise ValidationError(f"Reference level {reference!r} for {name!r} is not present in observed metadata values.")

    primary_levels = observed_levels(ordered_metadata, primary_name)
    if len(primary_levels) < 2:
        raise ValidationError(f"Primary factor {primary_name!r} must have at least two observed levels.")
    group_sizes = {level: sum(1 for row in ordered_metadata if row.get(primary_name, "") == level) for level in primary_levels}
    too_small = {level: size for level, size in group_sizes.items() if size < minimum_group_size}
    if too_small:
        raise ValidationError(
            f"Minimum group size is {minimum_group_size}, but these groups are too small: {too_small}."
        )

    matrix, columns = build_design_matrix(ordered_metadata, variables)
    rank = matrix_rank(matrix)
    full_rank = rank == len(columns)
    formula = "~ " + " + ".join(str(variable["name"]) for variable in variables)
    if not full_rank:
        raise ValidationError(confounding_message(primary_name, variables, ordered_metadata))

    validated_design = {
        "schema_version": 1,
        "status": "passed",
        "sample_id_column": sample_id_column,
        "sample_ids": matrix_sample_ids,
        "primary_factor": {
            "name": primary_name,
            "reference_level": primary_reference,
            "observed_levels": primary_levels,
            "group_sizes": group_sizes,
        },
        "covariates": [
            {
                "name": str(variable["name"]),
                "reference_level": str(variable["reference_level"]),
                "observed_levels": observed_levels(ordered_metadata, str(variable["name"])),
            }
            for variable in variables[1:]
        ],
        "minimum_group_size": minimum_group_size,
        "resolved_formula": formula,
        "design_matrix": {
            "columns": columns,
            "n_rows": len(matrix),
            "n_columns": len(columns),
            "rank": rank,
            "full_rank": full_rank,
        },
    }
    report = {
        "schema_version": 1,
        "status": "passed",
        "errors": [],
        "warnings": [],
        "sample_matching": {
            "status": "matched",
            "matrix_only_sample_ids": [],
            "metadata_only_sample_ids": [],
        },
        "group_sizes": group_sizes,
        "resolved_formula": formula,
        "design_matrix_rank": rank,
        "design_matrix_columns": columns,
    }
    return validated_design, report


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(args: argparse.Namespace, message: str) -> None:
    payload = {"schema_version": 1, "status": "failed", "errors": [message], "warnings": []}
    write_json(args.out_validated_design, payload)
    write_json(args.out_design_validation_report, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a generic differential-analysis design before modeling.")
    parser.add_argument("--feature-matrix", required=True, type=Path)
    parser.add_argument("--feature-matrix-meta", required=True, type=Path)
    parser.add_argument("--sample-metadata", required=True, type=Path)
    parser.add_argument("--design-spec", required=True, type=Path)
    parser.add_argument("--minimum-group-size", required=True, type=int)
    parser.add_argument("--out-validated-design", required=True, type=Path)
    parser.add_argument("--out-design-validation-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        feature_matrix_meta = load_json(args.feature_matrix_meta, "feature matrix metadata")
        design_spec = load_json(args.design_spec, "design spec")
        validated_design, report = validate(
            args.feature_matrix,
            feature_matrix_meta,
            args.sample_metadata,
            design_spec,
            args.minimum_group_size,
        )
    except ValidationError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_json(args.out_validated_design, validated_design)
    write_json(args.out_design_validation_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
