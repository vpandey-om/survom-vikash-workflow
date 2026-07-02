#!/usr/bin/env bash
# Smoke test for the SurvOm common.differential.validate_design atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_differential_validate_design"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-differential-validate-design.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_validate_design() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__differential__validate_design.py" \
    --feature-matrix "${fixtures}/${fixture}/feature_matrix.tsv" \
    --feature-matrix-meta "${fixtures}/${fixture}/feature_matrix.meta.json" \
    --sample-metadata "${fixtures}/${fixture}/sample_metadata.tsv" \
    --design-spec "${fixtures}/${fixture}/design_spec.json" \
    --minimum-group-size 2 \
    --out-validated-design "${out_dir}/validated_design.json" \
    --out-design-validation-report "${out_dir}/design_validation_report.json"
}

happy_dir="${tmp_dir}/happy_path"
run_validate_design happy_path "${happy_dir}"

python - "${happy_dir}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
validated = json.loads((out_dir / "validated_design.json").read_text(encoding="utf-8"))
report = json.loads((out_dir / "design_validation_report.json").read_text(encoding="utf-8"))
assert validated["status"] == "passed", validated
assert validated["resolved_formula"] == "~ condition + batch", validated
assert report["status"] == "passed", report
assert report["group_sizes"] == {"control": 3, "treated": 3}, report
assert isinstance(report["design_matrix_rank"], int), report
assert validated["design_matrix"]["full_rank"] is True, validated
PY

failure_dir="${tmp_dir}/rank_deficient_design"
set +e
run_validate_design rank_deficient_design "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
status=$?
set -e
if [ "${status}" -eq 0 ]; then
  echo "ERROR: rank-deficient fixture unexpectedly passed" >&2
  exit 1
fi

python - "${failure_dir}/design_validation_report.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
assert "cannot be evaluated separately" in joined or "rank deficient" in joined, report
PY

echo "common.differential.validate_design smoke test passed."
