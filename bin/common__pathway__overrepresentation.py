#!/usr/bin/env python3
"""Run pathway over-representation analysis on resolved identifiers."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any


TEST_METHODS = {"fisher_exact", "hypergeometric"}
P_ADJUST_METHODS = {"none", "bonferroni", "bh"}
DIRECTIONS = {"both", "up", "down"}


class OverrepresentationError(Exception):
    """Raised for expected user-facing ORA failures."""


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise OverrepresentationError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OverrepresentationError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise OverrepresentationError(f"{label} must contain a JSON object.")
    return parsed


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise OverrepresentationError(f"Missing {label}: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise OverrepresentationError(f"{label} is empty or missing a header row.")
        header = [name if name is not None else "" for name in reader.fieldnames]
        if any(not column for column in header):
            raise OverrepresentationError(f"{label} contains an empty column name.")
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    if not rows:
        raise OverrepresentationError(f"{label} must contain at least one data row.")
    return header, rows


def require_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise OverrepresentationError(f"overrepresentation_params.{key} must be an explicit non-empty string.")
    return value


def require_choice(params: dict[str, Any], key: str, allowed: set[str]) -> str:
    value = require_string(params, key).lower()
    if value not in allowed:
        raise OverrepresentationError(f"overrepresentation_params.{key} must be one of: {', '.join(sorted(allowed))}.")
    return value


def check_required_columns(header: list[str], required: list[str], label: str) -> None:
    missing = [column for column in required if column not in header]
    if missing:
        raise OverrepresentationError(f"{label} is missing required column(s): {', '.join(missing)}.")


def parse_bool(raw: str, column: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "selected"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", ""}:
        return False
    raise OverrepresentationError(f"Column {column!r} must contain boolean-like values.")


def read_gmt(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise OverrepresentationError(f"Missing validated gene sets: {path}")
    gene_sets: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            if not row:
                continue
            if len(row) < 3:
                raise OverrepresentationError(f"validated gene sets GMT line {line_number} has fewer than 3 columns.")
            gene_set_id = row[0].strip()
            if not gene_set_id:
                raise OverrepresentationError(f"validated gene sets GMT line {line_number} has an empty gene-set ID.")
            if gene_set_id in seen:
                raise OverrepresentationError(f"validated gene sets GMT contains duplicate gene-set ID: {gene_set_id}.")
            seen.add(gene_set_id)
            members = {member.strip() for member in row[2:] if member.strip()}
            if not members:
                raise OverrepresentationError(f"validated gene set {gene_set_id} contains zero identifiers.")
            gene_sets.append(
                {
                    "gene_set_id": gene_set_id,
                    "description": row[1].strip(),
                    "members": members,
                }
            )
    if not gene_sets:
        raise OverrepresentationError("validated gene sets GMT must contain at least one gene set.")
    return gene_sets


def hypergeom_upper_tail(population_size: int, success_states: int, draws: int, observed_successes: int) -> float:
    max_successes = min(success_states, draws)
    denominator = math.comb(population_size, draws)
    probability = 0.0
    for successes in range(observed_successes, max_successes + 1):
        failures_drawn = draws - successes
        if failures_drawn < 0 or failures_drawn > population_size - success_states:
            continue
        probability += math.comb(success_states, successes) * math.comb(population_size - success_states, failures_drawn) / denominator
    return min(1.0, max(0.0, probability))


def adjust_p_values(values: list[float], method: str) -> list[float]:
    if method == "none":
        return values[:]
    if method == "bonferroni":
        return [min(1.0, value * len(values)) for value in values]
    indexed = sorted(enumerate(values), key=lambda item: item[1], reverse=True)
    adjusted = [1.0] * len(values)
    running_min = 1.0
    total = len(values)
    for rank_from_end, (index, value) in enumerate(indexed, start=1):
        rank = total - rank_from_end + 1
        running_min = min(running_min, value * total / rank)
        adjusted[index] = min(1.0, running_min)
    return adjusted


def format_float(value: float) -> str:
    return f"{value:.12g}"


def selected_resolved_ids(rows: list[dict[str, str]], direction: str) -> set[str]:
    selected: set[str] = set()
    for row in rows:
        if not parse_bool(row.get("survom_pathway_selected", ""), "survom_pathway_selected"):
            continue
        if direction != "both" and row.get("direction", "").strip().lower() != direction:
            continue
        resolved = row.get("resolved_identifier", "").strip()
        if not resolved:
            raise OverrepresentationError("resolved identifiers must not contain empty resolved_identifier values.")
        selected.add(resolved)
    return selected


def base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "step_id": "common.pathway.overrepresentation",
        "version": "0.1.0",
        "status": "failed",
        "parameters": {},
        "database": {},
        "counts": {},
        "warnings": [],
        "errors": [],
    }


def run_overrepresentation(
    resolved_identifiers_path: Path,
    resolved_background_path: Path,
    validated_gene_sets_path: Path,
    validated_manifest_path: Path,
    params: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    test_method = require_choice(params, "test_method", TEST_METHODS)
    p_adjust_method = require_choice(params, "p_adjust_method", P_ADJUST_METHODS)
    direction = require_choice(params, "direction", DIRECTIONS)

    input_header, input_rows = read_tsv(resolved_identifiers_path, "resolved identifiers")
    background_header, background_rows = read_tsv(resolved_background_path, "resolved background universe")
    check_required_columns(input_header, ["resolved_identifier", "survom_pathway_selected"], "resolved identifiers")
    check_required_columns(background_header, ["resolved_identifier"], "resolved background universe")
    if direction != "both":
        check_required_columns(input_header, ["direction"], "resolved identifiers")

    manifest = read_json(validated_manifest_path, "validated gene-set manifest")
    gene_sets = read_gmt(validated_gene_sets_path)
    background_ids = {row.get("resolved_identifier", "").strip() for row in background_rows}
    if "" in background_ids:
        raise OverrepresentationError("resolved background universe must not contain empty resolved_identifier values.")
    selected_ids = selected_resolved_ids(input_rows, direction)
    if not selected_ids:
        raise OverrepresentationError("Over-representation analysis selected zero resolved identifiers.")

    missing_selected = sorted(selected_ids - background_ids)
    if missing_selected:
        raise OverrepresentationError(
            "Selected resolved identifiers must be a subset of the resolved background universe. "
            f"Missing: {', '.join(missing_selected)}."
        )

    gene_set_member_union = set().union(*(gene_set["members"] for gene_set in gene_sets))
    gene_set_members_outside_background = sorted(gene_set_member_union - background_ids)
    if gene_set_members_outside_background:
        raise OverrepresentationError(
            "Validated gene-set members must be a subset of the resolved background universe. "
            f"Outside background: {', '.join(gene_set_members_outside_background)}."
        )

    population_size = len(background_ids)
    selected_count = len(selected_ids)
    result_rows: list[dict[str, str]] = []
    p_values: list[float] = []
    for gene_set in gene_sets:
        members = gene_set["members"]
        overlap = selected_ids & members
        gene_set_size = len(members)
        overlap_count = len(overlap)
        p_value = hypergeom_upper_tail(population_size, gene_set_size, selected_count, overlap_count)
        p_values.append(p_value)
        result_rows.append(
            {
                "database_id": str(manifest.get("database_id", "")),
                "database_version": str(manifest.get("release_version", "")),
                "gene_set_id": gene_set["gene_set_id"],
                "gene_set_name": gene_set["description"],
                "test_method": test_method,
                "direction": direction,
                "background_count": str(population_size),
                "selected_count": str(selected_count),
                "gene_set_size": str(gene_set_size),
                "overlap_count": str(overlap_count),
                "overlap_resolved_identifiers": ",".join(sorted(overlap)),
                "p_value": format_float(p_value),
                "p_adjust_method": p_adjust_method,
                "adjusted_p_value": "",
            }
        )

    adjusted = adjust_p_values(p_values, p_adjust_method)
    for row, value in zip(result_rows, adjusted, strict=True):
        row["adjusted_p_value"] = format_float(value)

    report = base_report()
    report.update(
        {
            "status": "passed",
            "parameters": {
                "test_method": test_method,
                "p_adjust_method": p_adjust_method,
                "direction": direction,
            },
            "database": {
                "database_id": manifest.get("database_id"),
                "release_version": manifest.get("release_version"),
                "identifier_namespace": manifest.get("identifier_namespace"),
                "checksum_sha256": manifest.get("checksum_sha256"),
            },
            "counts": {
                "n_input_rows": len(input_rows),
                "n_unique_selected_resolved_identifiers": selected_count,
                "n_background_rows": len(background_rows),
                "n_unique_background_resolved_identifiers": population_size,
                "n_gene_sets_tested": len(gene_sets),
            },
            "warnings": [],
            "errors": [],
        }
    )
    return result_rows, report


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    header = [
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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(args: argparse.Namespace, message: str) -> None:
    report = base_report()
    report["errors"] = [message]
    write_json(args.out_overrepresentation_report, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pathway over-representation analysis.")
    parser.add_argument("--resolved-identifiers", required=True, type=Path)
    parser.add_argument("--resolved-background-universe", required=True, type=Path)
    parser.add_argument("--validated-gene-sets", required=True, type=Path)
    parser.add_argument("--validated-manifest", required=True, type=Path)
    parser.add_argument("--overrepresentation-params", required=True, type=Path)
    parser.add_argument("--out-enrichment-results", required=True, type=Path)
    parser.add_argument("--out-overrepresentation-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        params = read_json(args.overrepresentation_params, "overrepresentation params")
        rows, report = run_overrepresentation(
            args.resolved_identifiers,
            args.resolved_background_universe,
            args.validated_gene_sets,
            args.validated_manifest,
            params,
        )
    except OverrepresentationError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_tsv(args.out_enrichment_results, rows)
    write_json(args.out_overrepresentation_report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
