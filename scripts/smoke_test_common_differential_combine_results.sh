#!/usr/bin/env bash
# Smoke test for the SurvOm common.differential.combine_results atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_differential_combine_results"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-differential-combine-results.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_combine_results() {
  local result_tables="$1"
  local diagnostics="$2"
  local out_dir="$3"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__differential__combine_results.py" \
    --result-tables "${result_tables}" \
    --diagnostics "${diagnostics}" \
    --out-combined-results "${out_dir}/combined_results.tsv" \
    --out-combined-diagnostics "${out_dir}/combined_diagnostics.json"
}

happy_dir="${tmp_dir}/happy_path_single_deseq2"
run_combine_results \
  "${fixtures}/happy_path_single_deseq2/deseq2_results.tsv" \
  "${fixtures}/happy_path_single_deseq2/deseq2_diagnostics.json" \
  "${happy_dir}"

python - "${happy_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
diagnostics = json.loads((out_dir / "combined_diagnostics.json").read_text(encoding="utf-8"))
assert diagnostics["status"] == "passed", diagnostics
assert diagnostics["methods"] == ["deseq2"], diagnostics
assert diagnostics["n_input_result_files"] == 1, diagnostics
assert diagnostics["n_total_result_rows"] == 3, diagnostics
assert diagnostics["contrasts"] == ["treatment_vs_control"], diagnostics
with (out_dir / "combined_results.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
assert len(rows) == 3, rows
required = {
    "feature_id",
    "contrast_id",
    "effect_estimate",
    "effect_type",
    "p_value",
    "adjusted_p_value",
    "status",
    "method",
    "positive_effect_definition",
    "base_mean",
}
assert required.issubset(rows[0]), rows[0]
assert rows[0]["effect_estimate"] == "3.2", rows[0]
PY

for fixture in missing_required_column duplicate_feature_contrast_method; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_combine_results \
    "${fixtures}/${fixture}/deseq2_results.tsv" \
    "${fixtures}/${fixture}/deseq2_diagnostics.json" \
    "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/combined_diagnostics.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

diagnostics = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert diagnostics["status"] == "failed", diagnostics
assert diagnostics["errors"], diagnostics
joined = " ".join(diagnostics["errors"])
if fixture == "missing_required_column":
    assert "missing required column" in joined, diagnostics
if fixture == "duplicate_feature_contrast_method":
    assert "unique by feature_id + contrast_id + method" in joined, diagnostics
PY
done

echo "common.differential.combine_results smoke test passed."
