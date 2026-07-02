#!/usr/bin/env bash
# Smoke test for the SurvOm common.differential.plan atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_differential_plan"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-differential-plan.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_plan() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__differential__plan.py" \
    --analysis-request "${fixtures}/${fixture}/analysis_request.json" \
    --input-inspection "${fixtures}/${fixture}/input_inspection.json" \
    --out-feature-matrix-meta "${out_dir}/feature_matrix.meta.json" \
    --out-design-spec "${out_dir}/design_spec.json" \
    --out-contrast-spec "${out_dir}/contrast_spec.json" \
    --out-analysis-plan "${out_dir}/analysis_plan.json"
}

happy_dir="${tmp_dir}/happy"
run_plan happy_path "${happy_dir}"

python - "${happy_dir}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
feature_meta = json.loads((out_dir / "feature_matrix.meta.json").read_text(encoding="utf-8"))
design = json.loads((out_dir / "design_spec.json").read_text(encoding="utf-8"))
contrast = json.loads((out_dir / "contrast_spec.json").read_text(encoding="utf-8"))
plan = json.loads((out_dir / "analysis_plan.json").read_text(encoding="utf-8"))
assert feature_meta["assay_type"] == "bulk_rnaseq_counts", feature_meta
assert feature_meta["value_profile"]["suggested_value_scale"] == "raw_count", feature_meta
assert design["formula"] == "~ condition + batch", design
assert design["covariates"][0]["reference_level"] == "batch_1", design
assert contrast["contrasts"][0]["contrast_id"] == "condition_treated_vs_control", contrast
assert plan["recommended_engine"] == "transcriptomics.stats.deseq2", plan
assert plan["assumptions_applied"], plan
assert "alphabetically first" in plan["assumptions_applied"][0], plan
assert plan["thresholds"]["adjusted_p_value_max"] == 0.05, plan
PY

for fixture in raw_count_mismatch paired_unsupported; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_plan "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/analysis_plan.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
if fixture == "raw_count_mismatch":
    assert "raw non-negative integer counts" in joined, report
if fixture == "paired_unsupported":
    assert "Paired/repeated-measures analysis is not supported" in joined, report
PY
done

echo "common.differential.plan smoke test passed."
