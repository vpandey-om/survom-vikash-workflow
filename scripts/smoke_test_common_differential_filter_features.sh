#!/usr/bin/env bash
# Smoke test for the SurvOm common.differential.filter_features atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_differential_filter_features"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-differential-filter-features.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_filter_features() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__differential__filter_features.py" \
    --feature-matrix "${fixtures}/${fixture}/feature_matrix.tsv" \
    --feature-matrix-meta "${fixtures}/${fixture}/feature_matrix.meta.json" \
    --filter-spec "${fixtures}/${fixture}/filter_spec.json" \
    --out-filtered-feature-matrix "${out_dir}/filtered_feature_matrix.tsv" \
    --out-filter-report "${out_dir}/filter_report.json"
}

fraction_dir="${tmp_dir}/happy_path_fraction"
count_dir="${tmp_dir}/happy_path_count"
run_filter_features happy_path_fraction "${fraction_dir}"
run_filter_features happy_path_count "${count_dir}"

python - "${fraction_dir}" "${count_dir}" <<'PY'
import json
import sys
from pathlib import Path

fraction_dir = Path(sys.argv[1])
count_dir = Path(sys.argv[2])
fraction_report = json.loads((fraction_dir / "filter_report.json").read_text(encoding="utf-8"))
count_report = json.loads((count_dir / "filter_report.json").read_text(encoding="utf-8"))
assert fraction_report["status"] == "passed", fraction_report
assert count_report["status"] == "passed", count_report
assert fraction_report["n_features_before"] == 4, fraction_report
assert fraction_report["n_features_after"] == 2, fraction_report
assert fraction_report["min_samples_fraction"] == 0.5, fraction_report
assert fraction_report["resolved_min_samples"] == 3, fraction_report
assert count_report["min_samples_count"] == 3, count_report
assert (fraction_dir / "filtered_feature_matrix.tsv").read_text(encoding="utf-8") == (
    count_dir / "filtered_feature_matrix.tsv"
).read_text(encoding="utf-8")
PY

for fixture in both_selection_modes neither_selection_mode all_features_removed; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_filter_features "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/filter_report.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
if fixture in {"both_selection_modes", "neither_selection_mode"}:
    assert "exactly one" in joined, report
if fixture == "all_features_removed":
    assert "All features were removed" in joined, report
PY
done

echo "common.differential.filter_features smoke test passed."
