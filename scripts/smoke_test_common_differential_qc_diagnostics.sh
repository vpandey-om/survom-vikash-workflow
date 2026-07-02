#!/usr/bin/env bash
# Smoke test for the SurvOm common.differential.qc_diagnostics atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_differential_qc_diagnostics"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-differential-qc-diagnostics.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_qc() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__differential__qc_diagnostics.py" \
    --filtered-feature-matrix "${fixtures}/${fixture}/filtered_feature_matrix.tsv" \
    --sample-metadata "${fixtures}/${fixture}/sample_metadata.tsv" \
    --combined-results "${fixtures}/${fixture}/combined_results.tsv" \
    --combined-diagnostics "${fixtures}/${fixture}/combined_diagnostics.json" \
    --qc-params "${fixtures}/${fixture}/qc_params.json" \
    --out-qc-report "${out_dir}/qc_report.html" \
    --out-qc-diagnostics "${out_dir}/qc_diagnostics.json" \
    --out-qc-assets "${out_dir}/qc_assets"
}

happy_dir="${tmp_dir}/happy_path_single_contrast"
run_qc happy_path_single_contrast "${happy_dir}"

python - "${happy_dir}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
d = json.loads((out / "qc_diagnostics.json").read_text(encoding="utf-8"))
assert d["status"] == "passed", d
assert d["pca_transform"] == "log2(count + 1)", d
expected = {
    "library_size_distribution.svg",
    "pca_plot.svg",
    "sample_correlation_heatmap.svg",
    "p_value_histogram__treatment_vs_control.svg",
    "volcano__treatment_vs_control.svg",
    "ma__treatment_vs_control.svg",
}
assert expected.issubset(set(d["generated_plots"])), d
assert (out / "qc_report.html").is_file(), out
for name in expected:
    assert (out / "qc_assets" / name).is_file(), name
PY

missing_dir="${tmp_dir}/missing_base_mean"
run_qc missing_base_mean "${missing_dir}"
python - "${missing_dir}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
d = json.loads((out / "qc_diagnostics.json").read_text(encoding="utf-8"))
assert d["status"] == "passed", d
assert any("base_mean" in warning for warning in d["warnings"]), d
assert not (out / "qc_assets" / "ma__treatment_vs_control.svg").exists(), d
PY

multi_dir="${tmp_dir}/multiple_contrasts"
run_qc multiple_contrasts "${multi_dir}"
python - "${multi_dir}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
d = json.loads((out / "qc_diagnostics.json").read_text(encoding="utf-8"))
assert d["contrasts"] == ["batch2_vs_batch1", "treatment_vs_control"], d
for name in [
    "p_value_histogram__batch2_vs_batch1.svg",
    "volcano__batch2_vs_batch1.svg",
    "p_value_histogram__treatment_vs_control.svg",
    "volcano__treatment_vs_control.svg",
]:
    assert (out / "qc_assets" / name).is_file(), name
PY

echo "common.differential.qc_diagnostics smoke test passed."
