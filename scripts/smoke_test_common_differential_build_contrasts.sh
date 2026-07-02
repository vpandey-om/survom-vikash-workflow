#!/usr/bin/env bash
# Smoke test for the SurvOm common.differential.build_contrasts atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_differential_build_contrasts"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-differential-build-contrasts.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_build_contrasts() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__differential__build_contrasts.py" \
    --validated-design "${fixtures}/${fixture}/validated_design.json" \
    --contrast-spec "${fixtures}/${fixture}/contrast_spec.json" \
    --out-resolved-contrasts "${out_dir}/resolved_contrasts.json" \
    --out-contrast-validation-report "${out_dir}/contrast_validation_report.json"
}

happy_dir="${tmp_dir}/happy_path"
run_build_contrasts happy_path "${happy_dir}"

python - "${happy_dir}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
resolved = json.loads((out_dir / "resolved_contrasts.json").read_text(encoding="utf-8"))
report = json.loads((out_dir / "contrast_validation_report.json").read_text(encoding="utf-8"))
assert resolved["status"] == "passed", resolved
assert report["status"] == "passed", report
assert report["n_contrasts"] == 1, report
contrast = resolved["contrasts"][0]
assert contrast["contrast_id"] == "treated_vs_control", contrast
assert contrast["type"] == "factor_levels", contrast
assert contrast["variable"] == "condition", contrast
assert contrast["numerator"] == "treated", contrast
assert contrast["denominator"] == "control", contrast
assert "higher abundance in treated than control" in contrast["positive_effect_definition"], contrast
PY

failure_dir="${tmp_dir}/duplicate_contrast_id"
set +e
run_build_contrasts duplicate_contrast_id "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
status=$?
set -e
if [ "${status}" -eq 0 ]; then
  echo "ERROR: duplicate contrast ID fixture unexpectedly passed" >&2
  exit 1
fi

python - "${failure_dir}/contrast_validation_report.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["status"] == "failed", report
assert report["errors"], report
assert "Contrast IDs must be unique" in " ".join(report["errors"]), report
PY

echo "common.differential.build_contrasts smoke test passed."
