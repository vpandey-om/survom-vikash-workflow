#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture_root="${repo_root}/tests/fixtures/common_differential_report"
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

run_report() {
  local fixture="$1"
  local outdir="$2"
  mkdir -p "${outdir}"
  python "${repo_root}/bin/common__differential__report.py" \
    --analysis-plan "${fixture_root}/${fixture}/analysis_plan.json" \
    --design-validation-report "${fixture_root}/${fixture}/design_validation_report.json" \
    --filter-report "${fixture_root}/${fixture}/filter_report.json" \
    --combined-results "${fixture_root}/${fixture}/combined_results.tsv" \
    --combined-diagnostics "${fixture_root}/${fixture}/combined_diagnostics.json" \
    --qc-report "${fixture_root}/${fixture}/qc_report.html" \
    --report-params "${fixture_root}/${fixture}/report_params.json" \
    --out-report "${outdir}/differential_analysis_report.html" \
    --out-significant-features "${outdir}/significant_features.tsv" \
    --out-upregulated-features "${outdir}/upregulated_features.tsv" \
    --out-downregulated-features "${outdir}/downregulated_features.tsv" \
    --out-analysis-manifest "${outdir}/analysis_manifest.json"
}

happy_out="${tmpdir}/happy"
run_report happy_path "${happy_out}"

python - "${happy_out}" <<'PY'
import csv
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
expected = [
    "differential_analysis_report.html",
    "significant_features.tsv",
    "upregulated_features.tsv",
    "downregulated_features.tsv",
    "analysis_manifest.json",
]
for name in expected:
    assert (out / name).exists(), f"missing output {name}"

def read_rows(name):
    with (out / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

sig = read_rows("significant_features.tsv")
up = read_rows("upregulated_features.tsv")
down = read_rows("downregulated_features.tsv")
assert [row["feature_id"] for row in sig] == ["gene_up", "gene_down"], sig
assert [row["feature_id"] for row in up] == ["gene_up"], up
assert [row["feature_id"] for row in down] == ["gene_down"], down
for row in sig:
    assert float(row["adjusted_p_value"]) <= 0.05
    assert abs(float(row["effect_estimate"])) >= 1.0

manifest = json.loads((out / "analysis_manifest.json").read_text(encoding="utf-8"))
assert manifest["status"] == "passed"
assert manifest["step_id"] == "common.differential.report"
assert manifest["version"] == "0.1.0"
assert manifest["assumptions_applied"], manifest
assert manifest["report_thresholds"]["adjusted_p_value_max"] == 0.05
assert manifest["report_thresholds"]["absolute_log2_fold_change_min"] == 1.0
assert manifest["summary_counts"]["significant_by_contrast"]["treatment_vs_control"] == 2
html = (out / "differential_analysis_report.html").read_text(encoding="utf-8")
assert "Analysis Question" in html
assert "Positive effect estimate means higher abundance in treatment than control." in html
PY

zero_out="${tmpdir}/zero"
run_report zero_significant_features "${zero_out}"

python - "${zero_out}" <<'PY'
import csv
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
for name in ["significant_features.tsv", "upregulated_features.tsv", "downregulated_features.tsv"]:
    with (out / name).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows == [], f"{name} should contain only the header"
PY

multi_out="${tmpdir}/multi"
run_report multiple_contrasts "${multi_out}"

python - "${multi_out}" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
manifest = json.loads((out / "analysis_manifest.json").read_text(encoding="utf-8"))
counts = manifest["summary_counts"]["significant_by_contrast"]
assert counts["treatment_vs_control"] == 2
assert counts["drug_b_vs_control"] == 1
PY

missing_threshold_out="${tmpdir}/missing_threshold"
set +e
run_report missing_required_threshold "${missing_threshold_out}" >/tmp/common_differential_report_missing_threshold.out 2>&1
missing_threshold_status=$?
set -e
if [[ "${missing_threshold_status}" -eq 0 ]]; then
  echo "Expected missing_required_threshold fixture to fail." >&2
  exit 1
fi

python - "${missing_threshold_out}" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
manifest = json.loads((out / "analysis_manifest.json").read_text(encoding="utf-8"))
assert manifest["status"] == "failed"
assert "absolute_log2_fold_change_min" in " ".join(manifest["errors"])
PY

missing_column_out="${tmpdir}/missing_column"
set +e
run_report missing_required_result_column "${missing_column_out}" >/tmp/common_differential_report_missing_column.out 2>&1
missing_column_status=$?
set -e
if [[ "${missing_column_status}" -eq 0 ]]; then
  echo "Expected missing_required_result_column fixture to fail." >&2
  exit 1
fi

echo "common.differential.report smoke test passed"
