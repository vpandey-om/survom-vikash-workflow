#!/usr/bin/env python3
"""Validate generic contrasts and emit engine-agnostic resolved contrasts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SUPPORTED_TYPES = {"factor_levels", "factor_level"}


class ContrastError(Exception):
    """Raised for expected user-facing contrast validation failures."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ContrastError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContrastError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ContrastError(f"{label} must contain a JSON object.")
    return parsed


def require_string(payload: dict[str, Any], keys: tuple[str, ...], context: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    raise ContrastError(f"{context} requires one of these non-empty string fields: {', '.join(keys)}.")


def design_variables(validated_design: dict[str, Any]) -> dict[str, list[str]]:
    variables: dict[str, list[str]] = {}
    primary = validated_design.get("primary_factor")
    if isinstance(primary, dict):
        name = primary.get("name")
        levels = primary.get("observed_levels")
        if isinstance(name, str) and isinstance(levels, list):
            variables[name] = [str(level) for level in levels]
    covariates = validated_design.get("covariates", [])
    if isinstance(covariates, list):
        for covariate in covariates:
            if not isinstance(covariate, dict):
                continue
            name = covariate.get("name")
            levels = covariate.get("observed_levels")
            if isinstance(name, str) and isinstance(levels, list):
                variables[name] = [str(level) for level in levels]
    return variables


def normalize_contrasts(contrast_spec: dict[str, Any]) -> list[dict[str, Any]]:
    contrasts = contrast_spec.get("contrasts")
    if not isinstance(contrasts, list) or not contrasts:
        raise ContrastError("contrast_spec.contrasts must be a non-empty list.")
    normalized = []
    for index, contrast in enumerate(contrasts, start=1):
        if not isinstance(contrast, dict):
            raise ContrastError(f"Contrast {index} must be an object.")
        contrast_type = require_string(contrast, ("type",), f"Contrast {index}")
        if contrast_type not in SUPPORTED_TYPES:
            raise ContrastError(
                f"Contrast {index} uses unsupported type {contrast_type!r}. "
                "MVP supports only factor_levels contrasts."
            )
        normalized.append(
            {
                "contrast_id": require_string(contrast, ("id", "contrast_id"), f"Contrast {index}"),
                "type": "factor_levels",
                "variable": require_string(contrast, ("variable", "factor"), f"Contrast {index}"),
                "numerator": require_string(contrast, ("numerator", "numerator_level"), f"Contrast {index}"),
                "denominator": require_string(contrast, ("denominator", "denominator_level"), f"Contrast {index}"),
            }
        )
    return normalized


def build_contrasts(validated_design: dict[str, Any], contrast_spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if validated_design.get("status") != "passed":
        raise ContrastError("validated_design.json must have status 'passed' before contrasts can be built.")
    variables = design_variables(validated_design)
    if not variables:
        raise ContrastError("validated_design.json does not declare any design variables with observed levels.")

    requested = normalize_contrasts(contrast_spec)
    duplicate_ids = sorted(
        contrast_id for contrast_id, count in Counter(item["contrast_id"] for item in requested).items() if count > 1
    )
    if duplicate_ids:
        raise ContrastError(f"Contrast IDs must be unique. Duplicates: {', '.join(duplicate_ids)}.")

    resolved = []
    for contrast in requested:
        contrast_id = contrast["contrast_id"]
        variable = contrast["variable"]
        numerator = contrast["numerator"]
        denominator = contrast["denominator"]
        if variable not in variables:
            raise ContrastError(f"Contrast {contrast_id!r} uses variable {variable!r}, which is not in validated design.")
        levels = variables[variable]
        if numerator not in levels:
            raise ContrastError(f"Contrast {contrast_id!r} numerator level {numerator!r} is not observed for {variable!r}.")
        if denominator not in levels:
            raise ContrastError(f"Contrast {contrast_id!r} denominator level {denominator!r} is not observed for {variable!r}.")
        if numerator == denominator:
            raise ContrastError(f"Contrast {contrast_id!r} numerator and denominator must be different.")
        label = f"{variable}: {numerator} vs {denominator}"
        resolved.append(
            {
                "contrast_id": contrast_id,
                "type": "factor_levels",
                "variable": variable,
                "numerator": numerator,
                "denominator": denominator,
                "label": label,
                "positive_effect_definition": (
                    f"Positive effect estimate means higher abundance in {numerator} than {denominator}."
                ),
            }
        )

    payload = {
        "schema_version": 1,
        "status": "passed",
        "contrasts": resolved,
    }
    report = {
        "schema_version": 1,
        "status": "passed",
        "errors": [],
        "warnings": [],
        "n_contrasts": len(resolved),
        "contrast_ids": [contrast["contrast_id"] for contrast in resolved],
    }
    return payload, report


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(args: argparse.Namespace, message: str) -> None:
    payload = {"schema_version": 1, "status": "failed", "errors": [message], "warnings": []}
    write_json(args.out_resolved_contrasts, payload)
    write_json(args.out_contrast_validation_report, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate factor-level contrasts against a validated design and emit resolved contrasts."
    )
    parser.add_argument("--validated-design", required=True, type=Path)
    parser.add_argument("--contrast-spec", required=True, type=Path)
    parser.add_argument("--out-resolved-contrasts", required=True, type=Path)
    parser.add_argument("--out-contrast-validation-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        validated_design = load_json(args.validated_design, "validated design")
        contrast_spec = load_json(args.contrast_spec, "contrast spec")
        resolved, report = build_contrasts(validated_design, contrast_spec)
    except ContrastError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_json(args.out_resolved_contrasts, resolved)
    write_json(args.out_contrast_validation_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
