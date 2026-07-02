#!/usr/bin/env python3
"""Resolve pathway input and background identifiers into a shared namespace."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


AMBIGUOUS_POLICIES = {"fail", "drop", "retain_all"}
UNMAPPED_POLICIES = {"fail", "drop"}
DUPLICATE_POLICIES = {"fail", "retain_first", "retain_all"}
RESERVED_OUTPUT_COLUMNS = {"source_identifier", "resolved_identifier", "resolution_status"}


class ResolutionError(Exception):
    """Raised for expected user-facing identifier-resolution failures."""


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ResolutionError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResolutionError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ResolutionError(f"{label} must contain a JSON object.")
    return parsed


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise ResolutionError(f"Missing {label}: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ResolutionError(f"{label} is empty or missing a header row.")
        header = [name if name is not None else "" for name in reader.fieldnames]
        if any(not column for column in header):
            raise ResolutionError(f"{label} contains an empty column name.")
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    if not rows:
        raise ResolutionError(f"{label} must contain at least one data row.")
    return header, rows


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ResolutionError(f"resolution_params.{key} must be an explicit non-empty string.")
    return value


def require_policy(params: dict[str, Any], key: str, allowed: set[str]) -> str:
    value = require_string(params, key)
    if value not in allowed:
        raise ResolutionError(f"resolution_params.{key} must be one of: {', '.join(sorted(allowed))}.")
    return value


def check_required_columns(header: list[str], required: list[str], label: str) -> None:
    missing = [column for column in required if column not in header]
    if missing:
        raise ResolutionError(f"{label} is missing required column(s): {', '.join(missing)}.")


def check_reserved_columns(header: list[str], label: str) -> None:
    collisions = sorted(RESERVED_OUTPUT_COLUMNS.intersection(header))
    if collisions:
        raise ResolutionError(f"{label} uses reserved output column(s): {', '.join(collisions)}.")


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_mapping(
    rows: list[dict[str, str]],
    source_column: str,
    target_column: str,
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    for index, row in enumerate(rows, start=2):
        source = row.get(source_column, "").strip()
        target = row.get(target_column, "").strip()
        if not source:
            raise ResolutionError(f"identifier mapping row {index} has an empty source identifier.")
        if not target:
            raise ResolutionError(f"identifier mapping row {index} has an empty resolved identifier.")
        mapping[source].append(target)
    return {source: ordered_unique(targets) for source, targets in mapping.items()}


def resolve_rows(
    rows: list[dict[str, str]],
    id_column: str,
    mapping: dict[str, list[str]],
    label: str,
    ambiguous_policy: str,
    unmapped_policy: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    resolved_rows: list[dict[str, str]] = []
    ambiguous_ids: list[str] = []
    unmapped_ids: list[str] = []

    for row in rows:
        source = row.get(id_column, "").strip()
        if not source:
            raise ResolutionError(f"{label} column {id_column!r} must not contain empty identifiers.")
        targets = mapping.get(source, [])
        if not targets:
            unmapped_ids.append(source)
            if unmapped_policy == "fail":
                continue
            if unmapped_policy == "drop":
                continue
        if len(targets) > 1:
            ambiguous_ids.append(source)
            if ambiguous_policy == "fail":
                continue
            if ambiguous_policy == "drop":
                continue

        for target in targets:
            out_row = dict(row)
            out_row["source_identifier"] = source
            out_row["resolved_identifier"] = target
            out_row["resolution_status"] = "ambiguous_retained" if len(targets) > 1 else "resolved"
            resolved_rows.append(out_row)

    if ambiguous_ids and ambiguous_policy == "fail":
        raise ResolutionError(
            f"{label} contains ambiguous mapping(s) and ambiguous_mapping_policy is 'fail': "
            f"{', '.join(sorted(set(ambiguous_ids)))}."
        )
    if unmapped_ids and unmapped_policy == "fail":
        raise ResolutionError(
            f"{label} contains unmapped identifier(s) and unmapped_identifier_policy is 'fail': "
            f"{', '.join(sorted(set(unmapped_ids)))}."
        )

    diagnostics = {
        "n_input_rows": len(rows),
        "n_resolved_rows_before_duplicate_policy": len(resolved_rows),
        "n_ambiguous_source_identifiers": len(set(ambiguous_ids)),
        "n_unmapped_source_identifiers": len(set(unmapped_ids)),
        "ambiguous_source_identifiers": sorted(set(ambiguous_ids)),
        "unmapped_source_identifiers": sorted(set(unmapped_ids)),
    }
    return resolved_rows, diagnostics


def apply_duplicate_policy(
    rows: list[dict[str, str]],
    label: str,
    duplicate_policy: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    resolved_to_sources: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        resolved_to_sources[row["resolved_identifier"]].append(row["source_identifier"])

    duplicate_ids = sorted(
        resolved_id
        for resolved_id, sources in resolved_to_sources.items()
        if len(set(sources)) > 1
    )
    if duplicate_ids and duplicate_policy == "fail":
        raise ResolutionError(
            f"{label} contains duplicate resolved identifier(s) and "
            f"duplicate_resolved_identifier_policy is 'fail': {', '.join(duplicate_ids)}."
        )
    if duplicate_policy == "retain_all":
        kept = rows
    else:
        seen: set[str] = set()
        kept = []
        for row in rows:
            resolved_id = row["resolved_identifier"]
            if resolved_id in seen:
                continue
            seen.add(resolved_id)
            kept.append(row)

    diagnostics = {
        "n_duplicate_resolved_identifiers": len(duplicate_ids),
        "duplicate_resolved_identifiers": duplicate_ids,
        "n_resolved_rows": len(kept),
        "n_unique_resolved_identifiers": len({row["resolved_identifier"] for row in kept}),
    }
    return kept, diagnostics


def base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "step_id": "common.pathway.resolve_identifiers",
        "version": "0.1.0",
        "status": "failed",
        "policies": {},
        "columns": {},
        "identifier_mapping": {},
        "resolved_identifiers": {},
        "resolved_background_universe": {},
        "warnings": [],
        "errors": [],
    }


def resolve_identifiers(
    validated_enrichment_input: Path,
    validated_background_universe: Path,
    identifier_mapping: Path,
    params: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]], list[str], list[dict[str, str]], dict[str, Any]]:
    input_id_column = require_string(params, "input_id_column")
    background_id_column = require_string(params, "background_id_column")
    mapping_source_column = require_string(params, "mapping_source_id_column")
    mapping_target_column = require_string(params, "mapping_target_id_column")
    ambiguous_policy = require_policy(params, "ambiguous_mapping_policy", AMBIGUOUS_POLICIES)
    unmapped_policy = require_policy(params, "unmapped_identifier_policy", UNMAPPED_POLICIES)
    duplicate_policy = require_policy(params, "duplicate_resolved_identifier_policy", DUPLICATE_POLICIES)

    input_header, input_rows = read_tsv(validated_enrichment_input, "validated enrichment input")
    background_header, background_rows = read_tsv(validated_background_universe, "validated background universe")
    mapping_header, mapping_rows = read_tsv(identifier_mapping, "identifier mapping")
    check_reserved_columns(input_header, "validated enrichment input")
    check_reserved_columns(background_header, "validated background universe")
    check_required_columns(input_header, [input_id_column], "validated enrichment input")
    check_required_columns(background_header, [background_id_column], "validated background universe")
    check_required_columns(mapping_header, [mapping_source_column, mapping_target_column], "identifier mapping")

    mapping = build_mapping(mapping_rows, mapping_source_column, mapping_target_column)
    resolved_input, input_diagnostics = resolve_rows(
        input_rows,
        input_id_column,
        mapping,
        "validated enrichment input",
        ambiguous_policy,
        unmapped_policy,
    )
    resolved_background, background_diagnostics = resolve_rows(
        background_rows,
        background_id_column,
        mapping,
        "validated background universe",
        ambiguous_policy,
        unmapped_policy,
    )

    resolved_input, input_duplicate_diagnostics = apply_duplicate_policy(
        resolved_input,
        "resolved identifiers",
        duplicate_policy,
    )
    resolved_background, background_duplicate_diagnostics = apply_duplicate_policy(
        resolved_background,
        "resolved background universe",
        duplicate_policy,
    )
    if not resolved_input:
        raise ResolutionError("Identifier resolution produced zero resolved enrichment input rows.")
    if not resolved_background:
        raise ResolutionError("Identifier resolution produced zero resolved background universe rows.")

    input_out_header = input_header + ["source_identifier", "resolved_identifier", "resolution_status"]
    background_out_header = background_header + ["source_identifier", "resolved_identifier", "resolution_status"]
    report = base_report()
    report.update(
        {
            "status": "passed",
            "policies": {
                "ambiguous_mapping_policy": ambiguous_policy,
                "unmapped_identifier_policy": unmapped_policy,
                "duplicate_resolved_identifier_policy": duplicate_policy,
            },
            "columns": {
                "input_id_column": input_id_column,
                "background_id_column": background_id_column,
                "mapping_source_id_column": mapping_source_column,
                "mapping_target_id_column": mapping_target_column,
            },
            "identifier_mapping": {
                "n_mapping_rows": len(mapping_rows),
                "n_unique_source_identifiers": len(mapping),
                "n_unique_resolved_identifiers": len({target for targets in mapping.values() for target in targets}),
                "n_ambiguous_mapping_sources": sum(1 for targets in mapping.values() if len(targets) > 1),
            },
            "resolved_identifiers": {**input_diagnostics, **input_duplicate_diagnostics},
            "resolved_background_universe": {**background_diagnostics, **background_duplicate_diagnostics},
            "warnings": [],
            "errors": [],
        }
    )
    return input_out_header, resolved_input, background_out_header, resolved_background, report


def write_failure(args: argparse.Namespace, message: str) -> None:
    report = base_report()
    report["errors"] = [message]
    write_json(args.out_resolution_report, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve pathway input and background identifiers.")
    parser.add_argument("--validated-enrichment-input", required=True, type=Path)
    parser.add_argument("--validated-background-universe", required=True, type=Path)
    parser.add_argument("--identifier-mapping", required=True, type=Path)
    parser.add_argument("--resolution-params", required=True, type=Path)
    parser.add_argument("--out-resolved-identifiers", required=True, type=Path)
    parser.add_argument("--out-resolved-background-universe", required=True, type=Path)
    parser.add_argument("--out-resolution-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        params = read_json(args.resolution_params, "resolution params")
        input_header, input_rows, background_header, background_rows, report = resolve_identifiers(
            args.validated_enrichment_input,
            args.validated_background_universe,
            args.identifier_mapping,
            params,
        )
    except ResolutionError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_tsv(args.out_resolved_identifiers, input_header, input_rows)
    write_tsv(args.out_resolved_background_universe, background_header, background_rows)
    write_json(args.out_resolution_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
