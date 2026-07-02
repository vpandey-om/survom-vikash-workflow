#!/usr/bin/env python3
"""Generate pathway enrichment QC diagnostics from combined pathway results."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REQUIRED_RESULT_COLUMNS = [
    "database_id",
    "database_version",
    "gene_set_id",
    "test_method",
    "direction",
    "background_count",
    "selected_count",
    "gene_set_size",
    "overlap_count",
    "p_value",
    "p_adjust_method",
    "adjusted_p_value",
]
SIGNIFICANCE_METRICS = {"p_value", "adjusted_p_value"}


class QCDiagnosticsError(Exception):
    """Raised for expected user-facing pathway QC failures."""


def split_paths(raw: str, label: str) -> list[Path]:
    paths = [Path(item) for item in raw.split(",") if item]
    if not paths:
        raise QCDiagnosticsError(f"At least one {label} path is required.")
    return paths


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise QCDiagnosticsError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QCDiagnosticsError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise QCDiagnosticsError(f"{label} must contain a JSON object.")
    return parsed


def read_json_list(raw: str, label: str) -> list[dict[str, Any]]:
    return [read_json(path, label) for path in split_paths(raw, label)]


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise QCDiagnosticsError(f"Missing {label}: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise QCDiagnosticsError(f"{label} is empty or missing a header row.")
        header = [name if name is not None else "" for name in reader.fieldnames]
        missing = [column for column in REQUIRED_RESULT_COLUMNS if column not in header]
        if missing:
            raise QCDiagnosticsError(f"{label} is missing required column(s): {', '.join(missing)}.")
        rows = [{key if key is not None else "": value for key, value in row.items()} for row in reader]
    if not rows:
        raise QCDiagnosticsError(f"{label} must contain at least one data row.")
    return header, rows


def require_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise QCDiagnosticsError(f"qc_params.{key} must be an explicit non-empty string.")
    return value


def require_number(params: dict[str, Any], key: str) -> float:
    value = params.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QCDiagnosticsError(f"qc_params.{key} must be an explicit numeric value.")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise QCDiagnosticsError(f"qc_params.{key} must be finite.")
    return parsed


def parse_float(raw: str, label: str) -> float:
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise QCDiagnosticsError(f"{label} must be numeric: {raw!r}.") from exc
    if not math.isfinite(parsed):
        raise QCDiagnosticsError(f"{label} must be finite: {raw!r}.")
    return parsed


def collect_resolution_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    for report in reports:
        for section_name in ("resolved_identifiers", "resolved_background_universe"):
            section = report.get(section_name, {})
            if isinstance(section, dict):
                for key in (
                    "n_input_rows",
                    "n_resolved_rows",
                    "n_unique_resolved_identifiers",
                    "n_ambiguous_source_identifiers",
                    "n_unmapped_source_identifiers",
                ):
                    value = section.get(key)
                    if isinstance(value, int):
                        totals[f"{section_name}.{key}"] += value
    return dict(sorted(totals.items()))


def collect_gene_set_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    databases: list[dict[str, Any]] = []
    for report in reports:
        manifest = report.get("manifest", {})
        gene_sets = report.get("gene_sets", {})
        if not isinstance(manifest, dict):
            manifest = {}
        if not isinstance(gene_sets, dict):
            gene_sets = {}
        databases.append(
            {
                "database_id": manifest.get("database_id"),
                "release_version": manifest.get("release_version"),
                "identifier_namespace": manifest.get("identifier_namespace"),
                "checksum_sha256": manifest.get("checksum_sha256"),
                "n_gene_sets": gene_sets.get("n_gene_sets"),
                "n_unique_identifiers": gene_sets.get("n_unique_identifiers"),
                "min_observed_gene_set_size": gene_sets.get("min_observed_gene_set_size"),
                "max_observed_gene_set_size": gene_sets.get("max_observed_gene_set_size"),
            }
        )
    return {"databases": databases}


def summarize_results(rows: list[dict[str, str]], significance_metric: str, significance_max: float) -> tuple[list[dict[str, str]], dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    significant_total = 0
    gene_set_sizes: list[float] = []
    overlap_counts: list[float] = []
    for row in rows:
        metric_value = parse_float(row.get(significance_metric, ""), significance_metric)
        gene_set_sizes.append(parse_float(row.get("gene_set_size", ""), "gene_set_size"))
        overlap_counts.append(parse_float(row.get("overlap_count", ""), "overlap_count"))
        if metric_value <= significance_max:
            significant_total += 1
        grouped[(row["database_id"], row["database_version"], row["test_method"], row["direction"])].append(row)

    summary_rows: list[dict[str, str]] = []
    for key, group_rows in sorted(grouped.items()):
        database_id, database_version, test_method, direction = key
        n_significant = sum(
            1 for row in group_rows if parse_float(row.get(significance_metric, ""), significance_metric) <= significance_max
        )
        summary_rows.append(
            {
                "database_id": database_id,
                "database_version": database_version,
                "test_method": test_method,
                "direction": direction,
                "n_pathways": str(len(group_rows)),
                "n_significant_pathways": str(n_significant),
            }
        )

    diagnostics = {
        "n_total_pathways": len(rows),
        "n_significant_pathways": significant_total,
        "database_ids": sorted({row["database_id"] for row in rows}),
        "database_versions": sorted({row["database_version"] for row in rows}),
        "test_methods": sorted({row["test_method"] for row in rows}),
        "directions": sorted({row["direction"] for row in rows}),
        "gene_set_size_distribution": {
            "min": min(gene_set_sizes),
            "max": max(gene_set_sizes),
            "mean": sum(gene_set_sizes) / len(gene_set_sizes),
        },
        "overlap_count_distribution": {
            "min": min(overlap_counts),
            "max": max(overlap_counts),
            "mean": sum(overlap_counts) / len(overlap_counts),
        },
    }
    return summary_rows, diagnostics


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    header = ["database_id", "database_version", "test_method", "direction", "n_pathways", "n_significant_pathways"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "step_id": "common.pathway.qc_diagnostics",
        "version": "0.1.0",
        "status": "failed",
        "parameters": {},
        "combined_results": {},
        "mapping": {},
        "gene_sets": {},
        "combined_diagnostics": {},
        "warnings": [],
        "errors": [],
    }


def build_qc(
    combined_results: Path,
    combined_diagnostics: Path,
    resolution_reports: str,
    gene_set_validation_reports: str,
    params: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    significance_metric = require_string(params, "significance_metric")
    if significance_metric not in SIGNIFICANCE_METRICS:
        raise QCDiagnosticsError("qc_params.significance_metric must be one of: adjusted_p_value, p_value.")
    significance_max = require_number(params, "significance_max")
    if significance_max < 0:
        raise QCDiagnosticsError("qc_params.significance_max must be non-negative.")

    _, rows = read_tsv(combined_results, "combined pathway results")
    combined_diag = read_json(combined_diagnostics, "combined pathway diagnostics")
    resolution = read_json_list(resolution_reports, "resolution report")
    gene_set_reports = read_json_list(gene_set_validation_reports, "gene-set validation report")
    summary_rows, result_summary = summarize_results(rows, significance_metric, significance_max)

    report = base_report()
    report.update(
        {
            "status": "passed",
            "parameters": {
                "significance_metric": significance_metric,
                "significance_max": significance_max,
            },
            "combined_results": result_summary,
            "mapping": collect_resolution_summary(resolution),
            "gene_sets": collect_gene_set_summary(gene_set_reports),
            "combined_diagnostics": {
                "n_input_result_files": combined_diag.get("n_input_result_files"),
                "n_total_result_rows": combined_diag.get("n_total_result_rows"),
                "mixed_database_versions": combined_diag.get("mixed_database_versions", {}),
                "database_versions_by_database_id": combined_diag.get("database_versions_by_database_id", {}),
            },
            "warnings": [],
            "errors": [],
        }
    )
    return summary_rows, report


def write_failure(args: argparse.Namespace, message: str) -> None:
    report = base_report()
    report["errors"] = [message]
    write_json(args.out_qc_diagnostics, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate pathway enrichment QC diagnostics.")
    parser.add_argument("--combined-results", required=True, type=Path)
    parser.add_argument("--combined-diagnostics", required=True, type=Path)
    parser.add_argument("--resolution-reports", required=True)
    parser.add_argument("--gene-set-validation-reports", required=True)
    parser.add_argument("--qc-params", required=True, type=Path)
    parser.add_argument("--out-qc-diagnostics", required=True, type=Path)
    parser.add_argument("--out-qc-summary", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        params = read_json(args.qc_params, "qc params")
        summary_rows, report = build_qc(
            args.combined_results,
            args.combined_diagnostics,
            args.resolution_reports,
            args.gene_set_validation_reports,
            params,
        )
    except QCDiagnosticsError as exc:
        write_failure(args, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_json(args.out_qc_diagnostics, report)
    write_tsv(args.out_qc_summary, summary_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
