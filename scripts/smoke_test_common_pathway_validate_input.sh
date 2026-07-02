#!/usr/bin/env bash
# Smoke test for the SurvOm common.pathway.validate_input atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_pathway_validate_input"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-pathway-validate-input.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_validate_input() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__pathway__validate_input.py" \
    --enrichment-input "${fixtures}/${fixture}/enrichment_input.tsv" \
    --background-universe "${fixtures}/${fixture}/background_universe.tsv" \
    --validation-params "${fixtures}/${fixture}/validation_params.json" \
    --out-validated-enrichment-input "${out_dir}/validated_enrichment_input.tsv" \
    --out-validated-background-universe "${out_dir}/validated_background_universe.tsv" \
    --out-validation-report "${out_dir}/validation_report.json"
}

selection_dir="${tmp_dir}/happy_selection"
threshold_dir="${tmp_dir}/happy_threshold"
run_validate_input happy_selection "${selection_dir}"
run_validate_input happy_threshold "${threshold_dir}"

python - "${selection_dir}" "${threshold_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

selection_dir = Path(sys.argv[1])
threshold_dir = Path(sys.argv[2])

def read_report(path):
    return json.loads((path / "validation_report.json").read_text(encoding="utf-8"))

def read_rows(path, name):
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

selection_report = read_report(selection_dir)
threshold_report = read_report(threshold_dir)
assert selection_report["status"] == "passed", selection_report
assert selection_report["selection_policy"] == "selection_column", selection_report
assert selection_report["direction"] == "both", selection_report
assert selection_report["n_selected_features"] == 2, selection_report
assert selection_report["selected_feature_ids"] == ["gene_a", "gene_c"], selection_report
assert threshold_report["status"] == "passed", threshold_report
assert threshold_report["selection_policy"] == "threshold", threshold_report
assert threshold_report["direction"] == "up", threshold_report
assert threshold_report["selected_feature_ids"] == ["gene_a"], threshold_report

selection_rows = read_rows(selection_dir, "validated_enrichment_input.tsv")
assert selection_rows[0]["survom_pathway_selected"] == "true", selection_rows
assert selection_rows[1]["survom_pathway_selected"] == "false", selection_rows
background_rows = read_rows(selection_dir, "validated_background_universe.tsv")
assert [row["feature_id"] for row in background_rows] == ["gene_a", "gene_b", "gene_c", "gene_d"], background_rows
PY

for fixture in both_selection_and_threshold neither_selection_nor_threshold missing_direction_column invalid_direction_value selected_not_in_background; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_validate_input "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/validation_report.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
if fixture in {"both_selection_and_threshold", "neither_selection_nor_threshold"}:
    assert "exactly one selection policy" in joined, report
if fixture == "missing_direction_column":
    assert "direction" in joined and "missing required column" in joined, report
if fixture == "invalid_direction_value":
    assert "Column 'direction'" in joined and "Invalid values" in joined, report
if fixture == "selected_not_in_background":
    assert "subset of the background universe" in joined, report
PY
done

echo "common.pathway.validate_input smoke test passed."
