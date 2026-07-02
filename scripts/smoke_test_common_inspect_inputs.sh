#!/usr/bin/env bash
# Smoke test for the SurvOm common.inspect.inputs atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_inspect_inputs"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-inspect-inputs.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

happy_json="${tmp_dir}/happy.input_inspection.json"
python "${repo_root}/bin/common__inspect__inputs.py" \
  --feature-matrix "${fixtures}/happy_path/gene_counts.tsv" \
  --sample-metadata "${fixtures}/happy_path/sample_metadata.tsv" \
  --feature-id-column gene_id \
  --sample-id-column sample_id \
  --out-inspection "${happy_json}"

python - "${happy_json}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["status"] == "passed", report
assert report["n_features"] == 4, report
assert report["n_samples"] == 6, report
assert report["sample_matching"]["status"] == "matched", report
assert report["suggested_value_scale"] == "raw_count", report
assert report["integer_fraction"] == 1.0, report
PY

failure_json="${tmp_dir}/sample_mismatch.input_inspection.json"
set +e
python "${repo_root}/bin/common__inspect__inputs.py" \
  --feature-matrix "${fixtures}/sample_mismatch/gene_counts.tsv" \
  --sample-metadata "${fixtures}/sample_mismatch/sample_metadata.tsv" \
  --feature-id-column gene_id \
  --sample-id-column sample_id \
  --out-inspection "${failure_json}" >/tmp/survom-common-inspect-inputs.stdout 2>/tmp/survom-common-inspect-inputs.stderr
status=$?
set -e

if [ "$status" -eq 0 ]; then
  echo "ERROR: sample mismatch fixture unexpectedly passed" >&2
  exit 1
fi

python - "${failure_json}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["status"] == "failed", report
assert report["sample_matching"]["status"] == "mismatched", report
assert any("sample IDs do not match" in error for error in report["errors"]), report
PY

echo "common.inspect.inputs smoke test passed."
