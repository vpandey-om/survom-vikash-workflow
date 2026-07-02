#!/usr/bin/env python3
"""Generate a beginner-readable differential-analysis report and exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STEP_ID = "common.differential.report"
STEP_VERSION = "0.1.0"

REQUIRED_RESULT_COLUMNS = {
    "feature_id",
    "contrast_id",
    "effect_estimate",
    "adjusted_p_value",
    "positive_effect_definition",
}

MISSING = {"", "na", "n/a", "nan", "null", "none"}


class ReportError(Exception):
    """Raised for expected report generation failures."""


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ReportError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ReportError(f"{label} must contain a JSON object.")
    return parsed


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise ReportError(f"Missing {label}: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ReportError(f"{label} is empty or missing a header row.")
        return list(reader.fieldnames), [dict(row) for row in reader]


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_number(value: str, context: str, required: bool = True) -> float | None:
    if value is None or value.strip().lower() in MISSING:
        if required:
            raise ReportError(f"Missing numeric value for {context}.")
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ReportError(f"Non-numeric value for {context}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ReportError(f"Non-finite numeric value for {context}: {value!r}")
    return parsed


def require_thresholds(params: dict[str, Any]) -> tuple[float, float]:
    missing = [
        key
        for key in ("adjusted_p_value_max", "absolute_log2_fold_change_min")
        if key not in params
    ]
    if missing:
        raise ReportError("Missing required report parameter(s): " + ", ".join(missing))
    try:
        adjusted_p_value_max = float(params["adjusted_p_value_max"])
        absolute_lfc_min = float(params["absolute_log2_fold_change_min"])
    except (TypeError, ValueError) as exc:
        raise ReportError(
            "Report parameters adjusted_p_value_max and absolute_log2_fold_change_min must be numeric."
        ) from exc
    if not (0 <= adjusted_p_value_max <= 1):
        raise ReportError("adjusted_p_value_max must be between 0 and 1.")
    if absolute_lfc_min < 0:
        raise ReportError("absolute_log2_fold_change_min must be non-negative.")
    return adjusted_p_value_max, absolute_lfc_min


def validate_results(header: list[str]) -> None:
    missing = sorted(REQUIRED_RESULT_COLUMNS - set(header))
    if missing:
        raise ReportError("combined_results.tsv is missing required column(s): " + ", ".join(missing))


def selected_rows(
    rows: list[dict[str, str]], adjusted_p_value_max: float, absolute_lfc_min: float
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    significant: list[dict[str, str]] = []
    upregulated: list[dict[str, str]] = []
    downregulated: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        adjusted = parse_number(row.get("adjusted_p_value", ""), f"adjusted_p_value on row {index}")
        effect = parse_number(row.get("effect_estimate", ""), f"effect_estimate on row {index}")
        assert adjusted is not None
        assert effect is not None
        passes_p = adjusted <= adjusted_p_value_max
        if passes_p and abs(effect) >= absolute_lfc_min:
            significant.append(row)
        if passes_p and effect >= absolute_lfc_min:
            upregulated.append(row)
        if passes_p and effect <= -absolute_lfc_min:
            downregulated.append(row)
    return significant, upregulated, downregulated


def counts_by_contrast(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        contrast_id = row.get("contrast_id", "")
        counts[contrast_id] = counts.get(contrast_id, 0) + 1
    return dict(sorted(counts.items()))


def top_features(rows: list[dict[str, str]], limit: int = 10) -> list[dict[str, str]]:
    sortable: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        adjusted = parse_number(row.get("adjusted_p_value", ""), "adjusted_p_value", required=False)
        if adjusted is not None:
            sortable.append((adjusted, row))
    return [row for _, row in sorted(sortable, key=lambda item: item[0])[:limit]]


def unique_values(rows: list[dict[str, str]], column: str) -> list[str]:
    return sorted({row.get(column, "") for row in rows if row.get(column, "")})


def summarize_design(report: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "status",
        "resolved_formula",
        "formula",
        "group_sizes",
        "design_matrix_rank",
        "n_samples",
        "errors",
        "warnings",
    ]
    return {key: report[key] for key in keys if key in report}


def summarize_filter(report: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "n_features_before",
        "n_features_after",
        "assay_type",
        "value_scale",
        "filter_rules",
        "min_count",
        "min_samples_count",
        "min_samples_fraction",
        "resolved_min_samples",
        "warnings",
    ]
    return {key: report[key] for key in keys if key in report}


def make_html_report(
    analysis_plan: dict[str, Any],
    design_report: dict[str, Any],
    filter_report: dict[str, Any],
    combined_diagnostics: dict[str, Any],
    rows: list[dict[str, str]],
    significant: list[dict[str, str]],
    upregulated: list[dict[str, str]],
    downregulated: list[dict[str, str]],
    params: dict[str, Any],
    qc_report: Path,
    warnings: list[str],
) -> str:
    question = analysis_plan.get("analysis_question") or analysis_plan.get("question") or "Differential analysis"
    formula = (
        design_report.get("resolved_formula")
        or design_report.get("formula")
        or analysis_plan.get("resolved_formula")
        or "Not provided"
    )
    methods = combined_diagnostics.get("methods") or unique_values(rows, "method") or ["not provided"]
    contrasts = unique_values(rows, "contrast_id")
    total_features = len({row.get("feature_id", "") for row in rows if row.get("feature_id", "")})
    top = top_features(significant)

    def table(headers: list[str], table_rows: list[list[str]]) -> str:
        head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row) + "</tr>"
            for row in table_rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    contrast_rows = []
    for contrast in contrasts:
        example = next((row for row in rows if row.get("contrast_id") == contrast), {})
        contrast_rows.append(
            [
                contrast,
                example.get("positive_effect_definition", "Positive effect direction was not provided."),
                str(counts_by_contrast(significant).get(contrast, 0)),
                str(counts_by_contrast(upregulated).get(contrast, 0)),
                str(counts_by_contrast(downregulated).get(contrast, 0)),
            ]
        )

    top_rows = [
        [
            row.get("feature_id", ""),
            row.get("contrast_id", ""),
            row.get("effect_estimate", ""),
            row.get("adjusted_p_value", ""),
            row.get("positive_effect_definition", ""),
        ]
        for row in top
    ]
    if not top_rows:
        top_rows = [["No features passed both report thresholds.", "", "", "", ""]]

    warnings_list = warnings + list(design_report.get("warnings", []) or []) + list(filter_report.get("warnings", []) or [])
    if not warnings_list:
        warnings_list = ["No report-generation warnings were recorded."]

    style = """
    body { font-family: Arial, sans-serif; margin: 32px; line-height: 1.45; color: #1f2933; }
    h1, h2 { color: #102a43; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0 24px; }
    th, td { border: 1px solid #bcccdc; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #f0f4f8; }
    .summary { background: #f8fafc; border-left: 4px solid #486581; padding: 12px 16px; }
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Differential Analysis Report</title>
  <style>{style}</style>
</head>
<body>
  <h1>Differential Analysis Report</h1>
  <section class="summary">
    <h2>Analysis Question</h2>
    <p>{html.escape(str(question))}</p>
    <p>This report highlights features that meet the explicit adjusted p-value and effect-size thresholds. Positive and negative directions are interpreted using each contrast's direction statement.</p>
  </section>
  <h2>Data And Sample Summary</h2>
  <p>Combined result rows: {len(rows)}. Unique tested features in the combined table: {total_features}. Contrasts: {html.escape(", ".join(contrasts) or "none")}.</p>
  <h2>Resolved Model Formula</h2>
  <p><code>{html.escape(str(formula))}</code></p>
  <h2>Contrast Descriptions</h2>
  {table(["Contrast", "Direction interpretation", "Significant", "Higher", "Lower"], contrast_rows)}
  <h2>Filtering Summary</h2>
  <p>Features before filtering: {html.escape(str(filter_report.get("n_features_before", "not provided")))}. Features after filtering: {html.escape(str(filter_report.get("n_features_after", "not provided")))}. Value scale: {html.escape(str(filter_report.get("value_scale", "not provided")))}.</p>
  <h2>Methods And Parameters</h2>
  <p>Methods: {html.escape(", ".join(str(method) for method in methods))}. Report thresholds were applied to the standardized combined result table without changing p-values, adjusted p-values, or effect estimates.</p>
  <h2>Significance Thresholds</h2>
  <p>Adjusted p-value <= {html.escape(str(params["adjusted_p_value_max"]))}; absolute log2 fold change >= {html.escape(str(params["absolute_log2_fold_change_min"]))}.</p>
  <h2>Top Features By Adjusted P-Value</h2>
  {table(["Feature", "Contrast", "Effect estimate", "Adjusted p-value", "Direction interpretation"], top_rows)}
  <h2>Warnings And Limitations</h2>
  <ul>{"".join(f"<li>{html.escape(str(warning))}</li>" for warning in warnings_list)}</ul>
  <h2>QC Report</h2>
  <p>QC report reference: <a href="{html.escape(qc_report.name)}">{html.escape(str(qc_report))}</a></p>
</body>
</html>
"""


def build_manifest(
    args: argparse.Namespace,
    analysis_plan: dict[str, Any],
    design_report: dict[str, Any],
    filter_report: dict[str, Any],
    combined_diagnostics: dict[str, Any],
    params: dict[str, Any],
    outputs: dict[str, str],
    warnings: list[str],
    status: str = "passed",
    errors: list[str] | None = None,
) -> dict[str, Any]:
    input_paths = {
        "analysis_plan": Path(args.analysis_plan),
        "design_validation_report": Path(args.design_validation_report),
        "filter_report": Path(args.filter_report),
        "combined_results": Path(args.combined_results),
        "combined_diagnostics": Path(args.combined_diagnostics),
        "qc_report": Path(args.qc_report),
        "report_params": Path(args.report_params),
    }
    checksums = {}
    for name, path in input_paths.items():
        checksums[name] = {"path": str(path), "sha256": sha256(path) if path.exists() else None}
    return {
        "status": status,
        "step_id": STEP_ID,
        "version": STEP_VERSION,
        "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_file_checksums": checksums,
        "analysis_plan": analysis_plan,
        "analysis_plan_values": analysis_plan,
        "assumptions_applied": analysis_plan.get("assumptions_applied", []),
        "design_validation_summary": summarize_design(design_report),
        "filtering_parameters_and_resolved_values": summarize_filter(filter_report),
        "combined_methods": combined_diagnostics.get("methods", []),
        "report_thresholds": {
            "adjusted_p_value_max": params.get("adjusted_p_value_max"),
            "absolute_log2_fold_change_min": params.get("absolute_log2_fold_change_min"),
        },
        "all_output_filenames": outputs,
        "tool_package_versions": {
            "python": platform.python_version(),
        },
        "warnings": warnings,
        "errors": errors or [],
    }


def run(args: argparse.Namespace) -> int:
    warnings: list[str] = []
    outputs = {
        "differential_analysis_report": Path(args.out_report).name,
        "significant_features": Path(args.out_significant_features).name,
        "upregulated_features": Path(args.out_upregulated_features).name,
        "downregulated_features": Path(args.out_downregulated_features).name,
        "analysis_manifest": Path(args.out_analysis_manifest).name,
    }
    try:
        analysis_plan = read_json(Path(args.analysis_plan), "analysis_plan.json")
        design_report = read_json(Path(args.design_validation_report), "design_validation_report.json")
        filter_report = read_json(Path(args.filter_report), "filter_report.json")
        combined_diagnostics = read_json(Path(args.combined_diagnostics), "combined_diagnostics.json")
        params = read_json(Path(args.report_params), "report_params.json")
        adjusted_p_value_max, absolute_lfc_min = require_thresholds(params)
        header, rows = read_tsv(Path(args.combined_results), "combined_results.tsv")
        validate_results(header)
        if not Path(args.qc_report).exists():
            raise ReportError(f"Missing qc_report.html: {args.qc_report}")

        significant, upregulated, downregulated = selected_rows(rows, adjusted_p_value_max, absolute_lfc_min)
        write_tsv(Path(args.out_significant_features), header, significant)
        write_tsv(Path(args.out_upregulated_features), header, upregulated)
        write_tsv(Path(args.out_downregulated_features), header, downregulated)
        html_report = make_html_report(
            analysis_plan,
            design_report,
            filter_report,
            combined_diagnostics,
            rows,
            significant,
            upregulated,
            downregulated,
            params,
            Path(args.qc_report),
            warnings,
        )
        Path(args.out_report).write_text(html_report, encoding="utf-8")
        manifest = build_manifest(
            args,
            analysis_plan,
            design_report,
            filter_report,
            combined_diagnostics,
            params,
            outputs,
            warnings,
        )
        manifest["summary_counts"] = {
            "significant_by_contrast": counts_by_contrast(significant),
            "higher_by_contrast": counts_by_contrast(upregulated),
            "lower_by_contrast": counts_by_contrast(downregulated),
            "n_significant_rows": len(significant),
            "n_upregulated_rows": len(upregulated),
            "n_downregulated_rows": len(downregulated),
        }
        write_json(Path(args.out_analysis_manifest), manifest)
        return 0
    except ReportError as exc:
        message = str(exc)
        try:
            partial_manifest = build_manifest(
                args,
                analysis_plan if "analysis_plan" in locals() else {},
                design_report if "design_report" in locals() else {},
                filter_report if "filter_report" in locals() else {},
                combined_diagnostics if "combined_diagnostics" in locals() else {},
                params if "params" in locals() else {},
                outputs,
                warnings,
                status="failed",
                errors=[message],
            )
            write_json(Path(args.out_analysis_manifest), partial_manifest)
        except Exception:
            pass
        print(f"ERROR: {message}", file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate beginner-readable differential-analysis report exports from combined results."
    )
    parser.add_argument("--analysis-plan", required=True, help="Analysis plan JSON.")
    parser.add_argument("--design-validation-report", required=True, help="Design validation report JSON.")
    parser.add_argument("--filter-report", required=True, help="Filter report JSON.")
    parser.add_argument("--combined-results", required=True, help="Combined standardized result TSV.")
    parser.add_argument("--combined-diagnostics", required=True, help="Combined diagnostics JSON.")
    parser.add_argument("--qc-report", required=True, help="QC report HTML.")
    parser.add_argument("--report-params", required=True, help="Explicit report parameters JSON.")
    parser.add_argument("--out-report", required=True, help="Output differential analysis HTML report.")
    parser.add_argument("--out-significant-features", required=True, help="Output significant-features TSV.")
    parser.add_argument("--out-upregulated-features", required=True, help="Output higher/upregulated-features TSV.")
    parser.add_argument("--out-downregulated-features", required=True, help="Output lower/downregulated-features TSV.")
    parser.add_argument("--out-analysis-manifest", required=True, help="Output analysis manifest JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
