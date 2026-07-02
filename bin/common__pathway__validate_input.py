#!/usr/bin/env python3
"""Validate pathway enrichment input before identifier resolution."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


THRESHOLD_KEYS = ("adjusted_p_value_max", "effect_abs_min")
TRUE_VALUES = {"1", "true", "t", "yes", "y", "selected"}
FALSE_VALUES = {"0", "false", "f", "no", "n", ""}
ALLOWED_DIRECTIONS = {"both", "up", "down"}
RESERVED_OUTPUT_COLUMNS = {"survom_pathway_selected"}


class ValidationError(Exception):
    """Raised for expected user-facing validation failures."""


def read_json(path: Path, label: str) -> dict[str, Any]:
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
            raise ValidationError(f"{label} is empty or missing a header row.")
        header = [name if name is not None else "" for name in reader.fieldnames]
        if any(not column for column in header):
            raise ValidationError(f"{label} contains an empty column name.")
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    if not rows:
        raise ValidationError(f"{label} must contain at least one data row.")
    return header, rows


def require_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"validation_params.{key} must be an explicit non-empty string.")
    return value


def optional_number(params: dict[str, Any], key: str) -> float | None:
    if key not in params:
        return None
    value = params[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"validation_params.{key} must be numeric when supplied.")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValidationError(f"validation_params.{key} must be finite.")
    return parsed


def parse_number(raw: str, column: str, feature_id: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValidationError(f"Column {column!r} for feature {feature_id!r} is not numeric: {raw!r}.") from exc
    if not math.isfinite(value):
        raise ValidationError(f"Column {column!r} for feature {feature_id!r} is not finite: {raw!r}.")
    return value


def parse_selected(raw: str, column: str, feature_id: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValidationError(
        f"Selection column {column!r} for feature {feature_id!r} must contain boolean-like values."
    )


def check_required_columns(header: list[str], required: list[str], label: str) -> None:
    missing = [column for column in required if column not in header]
    if missing:
        raise ValidationError(f"{label} is missing required column(s): {', '.join(missing)}.")


def duplicate_values(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def resolve_policy(params: dict[str, Any]) -> tuple[str, str | None, float | None, float | None]:
    selection_column = params.get("selection_column")
    if selection_column is not None and (not isinstance(selection_column, str) or not selection_column):
        raise ValidationError("validation_params.selection_column must be a non-empty string when supplied.")
    adjusted_p_value_max = optional_number(params, "adjusted_p_value_max")
    effect_abs_min = optional_number(params, "effect_abs_min")
    has_selection = selection_column is not None
    has_threshold = adjusted_p_value_max is not None or effect_abs_min is not None
    if has_selection == has_threshold:
        raise ValidationError(
            "validation_params must supply exactly one selection policy: selection_column or threshold field(s)."
        )
    policy = "selection_column" if has_selection else "threshold"
    return policy, selection_column, adjusted_p_value_max, effect_abs_min


def selected_by_threshold(
    row: dict[str, str],
    feature_id: str,
    adjusted_p_value_max: float | None,
    effect_abs_min: float | None,
) -> bool:
    selected = True
    if adjusted_p_value_max is not None:
        selected = selected and parse_number(row.get("adjusted_p_value", ""), "adjusted_p_value", feature_id) <= adjusted_p_value_max
    if effect_abs_min is not None:
        selected = selected and abs(parse_number(row.get("effect", ""), "effect", feature_id)) >= effect_abs_min
    return selected


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "step_id": "common.pathway.validate_input",
        "version": "0.1.0",
        "status": "failed",
        "selection_policy": None,
        "direction": None,
        "feature_id_column": None,
        "background_id_column": None,
        "n_input_rows": 0,
        "n_background_rows": 0,
        "n_unique_background_ids": 0,
        "n_selected_features": 0,
        "selected_feature_ids": [],
        "warnings": [],
        "errors": [],
    }


def validate_inputs(
    enrichment_input: Path,
    background_universe: Path,
    params: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]], list[str], list[dict[str, str]], dict[str, Any]]:
    feature_id_column = require_string(params, "feature_id_column")
    raw_background_id_column = params.get("background_id_column", feature_id_column)
    if not isinstance(raw_background_id_column, str) or not raw_background_id_column:
        raise ValidationError("validation_params.background_id_column must be an explicit non-empty string when supplied.")
    background_id_column = raw_background_id_column
    direction = require_string(params, "direction").lower()
    if direction not in ALLOWED_DIRECTIONS:
        raise ValidationError("validation_params.direction must be one of: both, up, down.")

    policy, selection_column, adjusted_p_value_max, effect_abs_min = resolve_policy(params)
    input_header, input_rows = read_tsv(enrichment_input, "enrichment input")
    background_header, background_rows = read_tsv(background_universe, "background universe")
    reserved_collisions = sorted(RESERVED_OUTPUT_COLUMNS.intersection(input_header))
    if reserved_collisions:
        raise ValidationError(
            "enrichment input uses reserved output column(s): "
            f"{', '.join(reserved_collisions)}."
        )

    required_input_columns = [feature_id_column]
    if selection_column:
        required_input_columns.append(selection_column)
    if adjusted_p_value_max is not None:
        required_input_columns.append("adjusted_p_value")
    if effect_abs_min is not None:
        required_input_columns.append("effect")
    if direction != "both":
        required_input_columns.append("direction")
    check_required_columns(input_header, required_input_columns, "enrichment input")
    check_required_columns(background_header, [background_id_column], "background universe")

    feature_ids = [row.get(feature_id_column, "").strip() for row in input_rows]
    if any(not feature_id for feature_id in feature_ids):
        raise ValidationError(f"Column {feature_id_column!r} must not contain empty feature IDs.")
    duplicated_features = duplicate_values(feature_ids)
    if duplicated_features:
        raise ValidationError(f"Input feature IDs must be unique before pathway validation. Duplicates: {', '.join(duplicated_features)}.")
    if direction != "both":
        invalid_directions = sorted(
            {
                row.get("direction", "").strip().lower()
                for row in input_rows
                if row.get("direction", "").strip().lower() not in {"up", "down"}
            }
        )
        if invalid_directions:
            formatted = ", ".join(repr(value) for value in invalid_directions)
            raise ValidationError(
                "Column 'direction' must contain only 'up' or 'down' when validation_params.direction "
                f"is not 'both'. Invalid values: {formatted}."
            )

    background_ids = [row.get(background_id_column, "").strip() for row in background_rows]
    if any(not feature_id for feature_id in background_ids):
        raise ValidationError(f"Column {background_id_column!r} must not contain empty background IDs.")
    unique_background = sorted(set(background_ids))

    selected_rows: list[dict[str, str]] = []
    validated_rows: list[dict[str, str]] = []
    for row in input_rows:
        feature_id = row[feature_id_column].strip()
        if selection_column:
            selected = parse_selected(row.get(selection_column, ""), selection_column, feature_id)
        else:
            selected = selected_by_threshold(row, feature_id, adjusted_p_value_max, effect_abs_min)
        out_row = dict(row)
        out_row["survom_pathway_selected"] = "true" if selected else "false"
        validated_rows.append(out_row)
        if selected:
            selected_rows.append(out_row)

    if not selected_rows:
        raise ValidationError("Pathway input validation selected zero features.")
    selected_ids = sorted({row[feature_id_column].strip() for row in selected_rows})
    missing_from_background = sorted(set(selected_ids) - set(unique_background))
    if missing_from_background:
        raise ValidationError(
            "Selected features must be a subset of the background universe. "
            f"Missing from background: {', '.join(missing_from_background)}."
        )

    validated_background_rows = [{feature_id_column: feature_id} for feature_id in unique_background]
    report = base_report()
    report.update(
        {
            "status": "passed",
            "selection_policy": policy,
            "direction": direction,
            "feature_id_column": feature_id_column,
            "background_id_column": background_id_column,
            "n_input_rows": len(input_rows),
            "n_background_rows": len(background_rows),
            "n_unique_background_ids": len(unique_background),
            "n_selected_features": len(selected_ids),
            "selected_feature_ids": selected_ids,
            "thresholds": {
                "adjusted_p_value_max": adjusted_p_value_max,
                "effect_abs_min": effect_abs_min,
            },
            "warnings": [],
            "errors": [],
        }
    )
    return input_header + ["survom_pathway_selected"], validated_rows, [feature_id_column], validated_background_rows, report


def write_failure(args: argparse.Namespace, message: str) -> None:
    report = base_report()
    report["errors"] = [message]
    write_json(args.out_validation_report, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pathway enrichment input before identifier resolution.")
    parser.add_argument("--enrichment-input", required=True, type=Path)
    parser.add_argument("--background-universe", required=True, type=Path)
    parser.add_argument("--validation-params", required=True, type=Path)
    parser.add_argument("--out-validated-enrichment-input", required=True, type=Path)
    parser.add_argument("--out-validated-background-universe", required=True, type=Path)
    parser.add_argument("--out-validation-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        params = read_json(args.validation_params, "validation params")
        input_header, input_rows, background_header, background_rows, report = validate_inputs(
            args.enrichment_input,
            args.background_universe,
            params,
        )
    except ValidationError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_tsv(args.out_validated_enrichment_input, input_header, input_rows)
    write_tsv(args.out_validated_background_universe, background_header, background_rows)
    write_json(args.out_validation_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
