#!/usr/bin/env python3
"""Build explicit assay-agnostic differential-analysis planning files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


RAW_COUNT_ASSAYS = {"bulk_rnaseq_counts"}
SUPPORTED_ENGINES = {
    "bulk_rnaseq_counts": ["transcriptomics.stats.deseq2"],
}


class PlanError(Exception):
    """Raised for expected user-facing planning failures."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise PlanError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise PlanError(f"{label} must contain a JSON object.")
    return parsed


def require_string(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PlanError(f"{label} requires non-empty string field {key!r}.")
    return value


def as_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key, False)
    if not isinstance(value, bool):
        raise PlanError(f"Field {key!r} must be true or false.")
    return value


def sorted_levels(levels_by_variable: dict[str, Any], variable: str) -> list[str]:
    raw_levels = levels_by_variable.get(variable)
    if not isinstance(raw_levels, list) or not raw_levels:
        raise PlanError(
            f"Metadata levels for {variable!r} are required to build the plan. "
            "Provide an explicit non-empty list in analysis_request.metadata_levels."
        )
    levels = []
    for level in raw_levels:
        if not isinstance(level, str) or not level:
            raise PlanError(f"Metadata levels for {variable!r} must be non-empty strings.")
        levels.append(level)
    return sorted(set(levels))


def normalize_covariates(raw_covariates: Any) -> list[dict[str, str | None]]:
    if raw_covariates is None:
        return []
    if not isinstance(raw_covariates, list):
        raise PlanError("analysis_request.covariates must be a list when supplied.")
    normalized = []
    for item in raw_covariates:
        if isinstance(item, str):
            normalized.append({"name": item, "reference_level": None})
            continue
        if isinstance(item, dict):
            name = require_string(item, "name", "covariate")
            reference = item.get("reference_level")
            if reference is not None and (not isinstance(reference, str) or not reference):
                raise PlanError(f"Covariate {name!r} reference_level must be a non-empty string when supplied.")
            normalized.append({"name": name, "reference_level": reference})
            continue
        raise PlanError("Each covariate must be a string or an object with name/reference_level.")
    return normalized


def validate_inspection(inspection: dict[str, Any]) -> None:
    if inspection.get("status") != "passed":
        errors = inspection.get("errors", [])
        detail = "; ".join(str(error) for error in errors) if errors else "input inspection did not pass"
        raise PlanError(f"Input inspection must pass before planning. Inspection error(s): {detail}")
    if inspection.get("sample_matching", {}).get("status") != "matched":
        raise PlanError("Input inspection reports that matrix and metadata sample IDs do not match.")
    if not inspection.get("numeric_validity", {}).get("is_numeric", False):
        raise PlanError("Input inspection reports non-numeric matrix values; planning cannot continue.")


def validate_raw_count_compatibility(inspection: dict[str, Any], assay_type: str) -> None:
    if assay_type not in RAW_COUNT_ASSAYS:
        return
    integer_fraction = inspection.get("integer_fraction")
    suggested_scale = inspection.get("suggested_value_scale")
    if integer_fraction != 1.0 or suggested_scale != "raw_count":
        raise PlanError(
            "Your data does not look like raw non-negative integer counts, but the request selected "
            f"{assay_type!r}. DESeq2-style raw-count analysis requires raw integer counts. "
            "Check the uploaded matrix or choose an assay type compatible with continuous values."
        )


def choose_engine(assay_type: str, requested_engine: Any) -> str | None:
    compatible = SUPPORTED_ENGINES.get(assay_type, [])
    if requested_engine is not None:
        if not isinstance(requested_engine, str) or not requested_engine:
            raise PlanError("requested_engine must be a non-empty string when supplied.")
        if requested_engine not in compatible:
            raise PlanError(
                f"Requested engine {requested_engine!r} is not compatible with assay type {assay_type!r}. "
                f"Compatible engine(s): {compatible}."
            )
        return requested_engine
    if len(compatible) == 1:
        # If a second engine is implemented for this assay, stop auto-selecting and require user input.
        return compatible[0]
    if len(compatible) > 1:
        raise PlanError(f"Multiple engines support assay type {assay_type!r}; requested_engine is required.")
    return None


def build_plan(analysis_request: dict[str, Any], inspection: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    validate_inspection(inspection)
    assay_type = require_string(analysis_request, "assay_type", "analysis_request")
    validate_raw_count_compatibility(inspection, assay_type)

    primary = analysis_request.get("primary_factor")
    if not isinstance(primary, dict):
        raise PlanError("analysis_request.primary_factor must be an object.")
    primary_name = require_string(primary, "name", "primary_factor")
    numerator = require_string(primary, "numerator_level", "primary_factor")
    denominator = require_string(primary, "denominator_level", "primary_factor")
    reference = primary.get("reference_level", denominator)
    if not isinstance(reference, str) or not reference:
        raise PlanError("primary_factor.reference_level must be a non-empty string when supplied.")

    paired = as_bool(analysis_request, "paired")
    time_course = as_bool(analysis_request, "time_course")
    subject_id = analysis_request.get("subject_id")
    time_variable = analysis_request.get("time_variable")
    if paired or subject_id:
        raise PlanError("Paired/repeated-measures analysis is not supported in the MVP planner.")
    if time_course or time_variable:
        raise PlanError("Time-course analysis is not supported in the MVP planner.")

    metadata_columns = set(inspection.get("metadata_columns", []))
    if primary_name not in metadata_columns:
        raise PlanError(f"Primary factor {primary_name!r} is not present in inspected metadata columns.")

    metadata_levels = analysis_request.get("metadata_levels")
    if not isinstance(metadata_levels, dict):
        raise PlanError("analysis_request.metadata_levels must be an object mapping variable names to levels.")
    primary_levels = sorted_levels(metadata_levels, primary_name)
    for level in (numerator, denominator, reference):
        if level not in primary_levels:
            raise PlanError(f"Level {level!r} is not declared for primary factor {primary_name!r}.")

    covariates = normalize_covariates(analysis_request.get("covariates", []))
    assumptions_applied: list[str] = []
    resolved_covariates = []
    for covariate in covariates:
        covariate_name = str(covariate["name"])
        if covariate_name not in metadata_columns:
            raise PlanError(f"Covariate {covariate_name!r} is not present in inspected metadata columns.")
        covariate_levels = sorted_levels(metadata_levels, covariate_name)
        covariate_reference = covariate["reference_level"]
        if covariate_reference is None:
            covariate_reference = covariate_levels[0]
            assumptions_applied.append(
                f"Reference level for '{covariate_name}' set to '{covariate_reference}' "
                "(alphabetically first; not explicitly chosen)."
            )
        if covariate_reference not in covariate_levels:
            raise PlanError(f"Reference level {covariate_reference!r} is not declared for covariate {covariate_name!r}.")
        resolved_covariates.append(
            {
                "name": covariate_name,
                "reference_level": covariate_reference,
                "levels": covariate_levels,
            }
        )

    thresholds = analysis_request.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        raise PlanError("analysis_request.thresholds must be a non-empty object of user-confirmed values.")
    engine_parameters = analysis_request.get("engine_parameters")
    if not isinstance(engine_parameters, dict) or not engine_parameters:
        raise PlanError("analysis_request.engine_parameters must be a non-empty object of user-confirmed values.")

    requested_engine = analysis_request.get("requested_engine")
    recommended_engine = choose_engine(assay_type, requested_engine)
    design_terms = [primary_name] + [str(covariate["name"]) for covariate in resolved_covariates]

    feature_matrix_meta = {
        "schema_version": 1,
        "assay_type": assay_type,
        "feature_id_column": inspection.get("feature_id_column"),
        "sample_id_column": inspection.get("sample_id_column"),
        "n_features": inspection.get("n_features"),
        "n_samples": inspection.get("n_samples"),
        "sample_ids": inspection.get("matrix_sample_ids", []),
        "value_profile": {
            "integer_fraction": inspection.get("integer_fraction"),
            "zero_fraction": inspection.get("zero_fraction"),
            "missing_fraction": inspection.get("missing_fraction"),
            "suggested_value_scale": inspection.get("suggested_value_scale"),
        },
    }
    design_spec = {
        "schema_version": 1,
        "primary_factor": {
            "name": primary_name,
            "reference_level": reference,
            "levels": primary_levels,
        },
        "covariates": resolved_covariates,
        "paired": False,
        "subject_id": None,
        "time_course": False,
        "time_variable": None,
        "formula_terms": design_terms,
        "formula": "~ " + " + ".join(design_terms),
    }
    contrast_spec = {
        "schema_version": 1,
        "contrasts": [
            {
                "contrast_id": f"{primary_name}_{numerator}_vs_{denominator}",
                "type": "factor_level",
                "factor": primary_name,
                "numerator_level": numerator,
                "denominator_level": denominator,
                "positive_effect_definition": f"{numerator} relative to {denominator}",
            }
        ],
    }
    analysis_plan = {
        "schema_version": 1,
        "status": "planned",
        "assay_type": assay_type,
        "recommended_engine": recommended_engine,
        "requested_engine": requested_engine,
        "engine_selection_reason": (
            f"{recommended_engine} is the only currently implemented compatible engine for {assay_type}."
            if recommended_engine and requested_engine is None
            else "Engine was explicitly requested by the user."
            if recommended_engine
            else "No compatible engine is currently implemented for this assay type."
        ),
        "thresholds": thresholds,
        "engine_parameters": engine_parameters,
        "assumptions_applied": assumptions_applied,
        "user_confirmed_parameters": {
            "thresholds": thresholds,
            "engine_parameters": engine_parameters,
            "primary_factor": primary,
            "covariates": analysis_request.get("covariates", []),
        },
    }
    return feature_matrix_meta, design_spec, contrast_spec, analysis_plan


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure_outputs(args: argparse.Namespace, message: str) -> None:
    failure = {"schema_version": 1, "status": "failed", "errors": [message]}
    for path in (
        args.out_feature_matrix_meta,
        args.out_design_spec,
        args.out_contrast_spec,
        args.out_analysis_plan,
    ):
        write_json(path, failure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build explicit guided differential-analysis planning JSON files."
    )
    parser.add_argument("--analysis-request", required=True, type=Path, help="User-confirmed analysis request JSON.")
    parser.add_argument("--input-inspection", required=True, type=Path, help="Input inspection JSON.")
    parser.add_argument("--out-feature-matrix-meta", required=True, type=Path)
    parser.add_argument("--out-design-spec", required=True, type=Path)
    parser.add_argument("--out-contrast-spec", required=True, type=Path)
    parser.add_argument("--out-analysis-plan", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        analysis_request = load_json(args.analysis_request, "analysis request")
        inspection = load_json(args.input_inspection, "input inspection")
        outputs = build_plan(analysis_request, inspection)
    except PlanError as exc:
        write_failure_outputs(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for path, payload in zip(
        (
            args.out_feature_matrix_meta,
            args.out_design_spec,
            args.out_contrast_spec,
            args.out_analysis_plan,
        ),
        outputs,
    ):
        write_json(path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
