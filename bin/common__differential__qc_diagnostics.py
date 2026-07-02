#!/usr/bin/env python3
"""Generate reusable QC diagnostics and HTML assets for differential analysis."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
from typing import Any


MISSING = {"", "na", "n/a", "nan", "null", "none"}


class QCError(Exception):
    """Raised for expected QC failures."""


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise QCError(f"Missing {label}: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QCError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise QCError(f"{label} must contain a JSON object.")
    return parsed


def read_tsv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise QCError(f"Missing {label}: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise QCError(f"{label} is empty or missing a header row.")
        return list(reader.fieldnames), [dict(row) for row in reader]


def is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING


def parse_number(value: str, context: str) -> float | None:
    if is_missing(value):
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise QCError(f"Non-numeric value in {context}: {value!r}") from exc
    if not math.isfinite(parsed):
        return None
    return parsed


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def svg_wrap(width: int, height: int, content: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<text x="16" y="24" font-family="Arial" font-size="16" font-weight="bold">{html.escape(title)}</text>'
        f"{content}</svg>\n"
    )


def scale(values: list[float], low: float, high: float) -> list[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [(low + high) / 2 for _ in values]
    return [low + (value - min_v) * (high - low) / (max_v - min_v) for value in values]


def write_bar_svg(path: Path, values: dict[str, float], title: str) -> None:
    labels = list(values)
    heights = scale(list(values.values()), 0, 180)
    pieces = []
    for idx, label in enumerate(labels):
        x = 45 + idx * 55
        h = heights[idx]
        y = 245 - h
        pieces.append(f'<rect x="{x}" y="{y:.2f}" width="32" height="{h:.2f}" fill="#4c78a8"/>')
        pieces.append(f'<text x="{x}" y="268" font-family="Arial" font-size="10">{html.escape(label)}</text>')
    path.write_text(svg_wrap(420, 290, "".join(pieces), title), encoding="utf-8")


def write_scatter_svg(path: Path, points: list[tuple[float, float, str]], title: str, x_label: str, y_label: str) -> None:
    xs = scale([point[0] for point in points], 55, 360)
    ys = scale([point[1] for point in points], 250, 45)
    pieces = [
        '<line x1="45" y1="255" x2="370" y2="255" stroke="#333"/>',
        '<line x1="45" y1="255" x2="45" y2="38" stroke="#333"/>',
        f'<text x="170" y="290" font-family="Arial" font-size="11">{html.escape(x_label)}</text>',
        f'<text x="5" y="145" font-family="Arial" font-size="11" transform="rotate(-90 12,145)">{html.escape(y_label)}</text>',
    ]
    for idx, (_, _, label) in enumerate(points):
        pieces.append(f'<circle cx="{xs[idx]:.2f}" cy="{ys[idx]:.2f}" r="4" fill="#e45756"/>')
        pieces.append(f'<text x="{xs[idx] + 5:.2f}" y="{ys[idx] + 3:.2f}" font-family="Arial" font-size="9">{html.escape(label)}</text>')
    path.write_text(svg_wrap(420, 310, "".join(pieces), title), encoding="utf-8")


def write_hist_svg(path: Path, values: list[float], title: str) -> None:
    bins = [0] * 10
    for value in values:
        if value is None or math.isnan(value):
            continue
        idx = min(9, max(0, int(value * 10)))
        bins[idx] += 1
    heights = scale([float(value) for value in bins], 0, 180)
    pieces = []
    for idx, height in enumerate(heights):
        x = 45 + idx * 32
        y = 245 - height
        pieces.append(f'<rect x="{x}" y="{y:.2f}" width="24" height="{height:.2f}" fill="#72b7b2"/>')
    path.write_text(svg_wrap(420, 280, "".join(pieces), title), encoding="utf-8")


def write_heatmap_svg(path: Path, matrix: list[list[float]], labels: list[str], title: str) -> None:
    size = 34
    pieces = []
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            intensity = int(255 - (value + 1) / 2 * 180)
            color = f"rgb({intensity},{intensity},255)"
            pieces.append(f'<rect x="{70 + j * size}" y="{45 + i * size}" width="{size}" height="{size}" fill="{color}" stroke="#fff"/>')
    for idx, label in enumerate(labels):
        pieces.append(f'<text x="{70 + idx * size}" y="38" font-family="Arial" font-size="9">{html.escape(label)}</text>')
        pieces.append(f'<text x="20" y="{68 + idx * size}" font-family="Arial" font-size="9">{html.escape(label)}</text>')
    path.write_text(svg_wrap(420, 300, "".join(pieces), title), encoding="utf-8")


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(v: list[float]) -> float:
    return math.sqrt(dot(v, v))


def mat_vec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [dot(row, vector) for row in matrix]


def first_eigenvector(matrix: list[list[float]], seed_index: int = 0) -> list[float]:
    n = len(matrix)
    vector = [0.0] * n
    vector[seed_index % n] = 1.0
    for _ in range(80):
        next_v = mat_vec(matrix, vector)
        length = norm(next_v)
        if length == 0:
            break
        vector = [value / length for value in next_v]
    return vector


def pca_points(sample_matrix: list[list[float]], sample_ids: list[str]) -> list[tuple[float, float, str]]:
    n_samples = len(sample_ids)
    centered_rows = []
    for feature_values in sample_matrix:
        mean = sum(feature_values) / len(feature_values)
        centered_rows.append([value - mean for value in feature_values])
    covariance = [[0.0 for _ in range(n_samples)] for _ in range(n_samples)]
    for row in centered_rows:
        for i in range(n_samples):
            for j in range(n_samples):
                covariance[i][j] += row[i] * row[j]
    pc1 = first_eigenvector(covariance, 0)
    lambda1 = dot(pc1, mat_vec(covariance, pc1))
    residual = [
        [covariance[i][j] - lambda1 * pc1[i] * pc1[j] for j in range(n_samples)]
        for i in range(n_samples)
    ]
    pc2 = first_eigenvector(residual, 1)
    return [(pc1[i], pc2[i], sample_ids[i]) for i in range(n_samples)]


def correlation(a: list[float], b: list[float]) -> float:
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    centered_a = [value - mean_a for value in a]
    centered_b = [value - mean_b for value in b]
    denom = norm(centered_a) * norm(centered_b)
    return dot(centered_a, centered_b) / denom if denom else 0.0


def sanitize(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in text)


def matrix_from_tsv(header: list[str], rows: list[dict[str, str]]) -> tuple[str, list[str], list[str], list[list[float]]]:
    feature_id_column = header[0]
    sample_ids = header[1:]
    feature_ids = []
    values = []
    for row in rows:
        feature_ids.append(row[feature_id_column])
        values.append([parse_number(row.get(sample_id, ""), f"matrix sample {sample_id}") or 0.0 for sample_id in sample_ids])
    return feature_id_column, sample_ids, feature_ids, values


def transform_matrix(values: list[list[float]], params: dict[str, Any]) -> tuple[list[list[float]], str]:
    scale_type = params.get("value_scale", "raw_count")
    if scale_type == "raw_count":
        return [[math.log2(value + 1.0) for value in row] for row in values], "log2(count + 1)"
    if scale_type == "transformed_continuous":
        return values, "identity (already transformed continuous values)"
    raise QCError("qc_params.value_scale must be raw_count or transformed_continuous.")


def generate_qc(args: argparse.Namespace) -> dict[str, Any]:
    params = read_json(args.qc_params, "QC parameters")
    combined_diagnostics = read_json(args.combined_diagnostics, "combined diagnostics")
    matrix_header, matrix_rows = read_tsv(args.filtered_feature_matrix, "filtered feature matrix")
    _, sample_rows = read_tsv(args.sample_metadata, "sample metadata")
    results_header, result_rows = read_tsv(args.combined_results, "combined results")
    required = {"feature_id", "contrast_id", "effect_estimate", "p_value", "adjusted_p_value", "method"}
    missing = sorted(required - set(results_header))
    if missing:
        raise QCError(f"combined_results.tsv missing required column(s): {', '.join(missing)}")

    _, sample_ids, _, values = matrix_from_tsv(matrix_header, matrix_rows)
    transformed, pca_transform = transform_matrix(values, params)
    assets_dir = args.out_qc_assets
    assets_dir.mkdir(parents=True, exist_ok=True)

    generated: list[str] = []
    skipped: list[dict[str, str]] = []
    warnings: list[str] = []

    library_sizes = {sample_id: sum(row[idx] for row in values) for idx, sample_id in enumerate(sample_ids)}
    write_bar_svg(assets_dir / "library_size_distribution.svg", library_sizes, "Library Size Distribution")
    generated.append("library_size_distribution.svg")

    write_scatter_svg(assets_dir / "pca_plot.svg", pca_points(transformed, sample_ids), "PCA Plot", "PC1", "PC2")
    generated.append("pca_plot.svg")

    sample_vectors = [[row[idx] for row in transformed] for idx in range(len(sample_ids))]
    corr_matrix = [[correlation(a, b) for b in sample_vectors] for a in sample_vectors]
    write_heatmap_svg(assets_dir / "sample_correlation_heatmap.svg", corr_matrix, sample_ids, "Sample Correlation Heatmap")
    generated.append("sample_correlation_heatmap.svg")

    contrasts = sorted({row["contrast_id"] for row in result_rows})
    for contrast in contrasts:
        rows = [row for row in result_rows if row["contrast_id"] == contrast]
        safe = sanitize(contrast)
        p_values = [parse_number(row.get("p_value", ""), f"p_value {contrast}") for row in rows]
        p_values = [value for value in p_values if value is not None]
        write_hist_svg(assets_dir / f"p_value_histogram__{safe}.svg", p_values, f"P-value Histogram: {contrast}")
        generated.append(f"p_value_histogram__{safe}.svg")

        volcano_points = []
        for row in rows:
            effect = parse_number(row["effect_estimate"], f"effect_estimate {contrast}") or 0.0
            adjusted = parse_number(row.get("adjusted_p_value", ""), f"adjusted_p_value {contrast}")
            p_value = parse_number(row.get("p_value", ""), f"p_value {contrast}")
            chosen = adjusted if adjusted is not None and adjusted > 0 else p_value
            y_value = -math.log10(chosen if chosen and chosen > 0 else 1e-300)
            volcano_points.append((effect, y_value, row["feature_id"]))
        write_scatter_svg(assets_dir / f"volcano__{safe}.svg", volcano_points, f"Volcano: {contrast}", "effect_estimate", "-log10(p)")
        generated.append(f"volcano__{safe}.svg")

        if "base_mean" not in results_header:
            warning = f"Skipping MA plot for {contrast}: base_mean column is absent."
            warnings.append(warning)
            skipped.append({"plot": f"ma__{safe}.svg", "reason": warning})
        else:
            ma_points = [
                (
                    parse_number(row.get("base_mean", ""), f"base_mean {contrast}") or 0.0,
                    parse_number(row["effect_estimate"], f"effect_estimate {contrast}") or 0.0,
                    row["feature_id"],
                )
                for row in rows
            ]
            write_scatter_svg(assets_dir / f"ma__{safe}.svg", ma_points, f"MA Plot: {contrast}", "base_mean", "effect_estimate")
            generated.append(f"ma__{safe}.svg")

    methods = sorted({row["method"] for row in result_rows})
    diagnostics = {
        "schema_version": 1,
        "status": "passed",
        "n_samples": len(sample_ids),
        "n_features": len(matrix_rows),
        "contrasts": contrasts,
        "methods": methods,
        "pca_transform": pca_transform,
        "generated_plots": generated,
        "skipped_plots": skipped,
        "warnings": warnings,
        "errors": [],
        "parameters_used": params,
        "upstream_combined_diagnostics_status": combined_diagnostics.get("status"),
        "metadata_rows": len(sample_rows),
    }
    return diagnostics


def write_html(path: Path, diagnostics: dict[str, Any]) -> None:
    plot_links = "\n".join(
        f'<li><a href="qc_assets/{html.escape(name)}">{html.escape(name)}</a></li>'
        for name in diagnostics["generated_plots"]
    )
    warning_items = "\n".join(f"<li>{html.escape(warning)}</li>" for warning in diagnostics["warnings"])
    content = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>QC Diagnostics</title></head>
<body>
<h1>Differential Analysis QC Diagnostics</h1>
<p>Samples: {diagnostics['n_samples']} Features: {diagnostics['n_features']}</p>
<p>PCA transformation: {html.escape(diagnostics['pca_transform'])}</p>
<h2>Generated Plots</h2>
<ul>{plot_links}</ul>
<h2>Warnings</h2>
<ul>{warning_items}</ul>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate QC diagnostics and HTML assets for differential analysis.")
    parser.add_argument("--filtered-feature-matrix", required=True, type=Path)
    parser.add_argument("--sample-metadata", required=True, type=Path)
    parser.add_argument("--combined-results", required=True, type=Path)
    parser.add_argument("--combined-diagnostics", required=True, type=Path)
    parser.add_argument("--qc-params", required=True, type=Path)
    parser.add_argument("--out-qc-report", required=True, type=Path)
    parser.add_argument("--out-qc-diagnostics", required=True, type=Path)
    parser.add_argument("--out-qc-assets", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        diagnostics = generate_qc(args)
    except QCError as exc:
        payload = {
            "schema_version": 1,
            "status": "failed",
            "n_samples": 0,
            "n_features": 0,
            "contrasts": [],
            "methods": [],
            "pca_transform": None,
            "generated_plots": [],
            "skipped_plots": [],
            "warnings": [],
            "errors": [str(exc)],
            "parameters_used": {},
        }
        write_json(args.out_qc_diagnostics, payload)
        raise SystemExit(f"ERROR: {exc}")

    write_json(args.out_qc_diagnostics, diagnostics)
    write_html(args.out_qc_report, diagnostics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
