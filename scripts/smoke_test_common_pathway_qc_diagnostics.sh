#!/usr/bin/env bash
# Smoke test for the SurvOm common.pathway.qc_diagnostics atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_pathway_qc_diagnostics"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-pathway-qc-diagnostics.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_qc() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__pathway__qc_diagnostics.py" \
    --combined-results "${fixtures}/${fixture}/combined_pathway_results.tsv" \
    --combined-diagnostics "${fixtures}/${fixture}/combined_pathway_diagnostics.json" \
    --resolution-reports "${fixtures}/${fixture}/resolution_report.json" \
    --gene-set-validation-reports "${fixtures}/${fixture}/gene_set_validation_report.json" \
    --qc-params "${fixtures}/${fixture}/qc_params.json" \
    --out-qc-diagnostics "${out_dir}/pathway_qc_diagnostics.json" \
    --out-qc-summary "${out_dir}/pathway_qc_summary.tsv"
}

happy_dir="${tmp_dir}/happy_with_reports"
threshold_dir="${tmp_dir}/significance_threshold_user_supplied"
run_qc happy_with_reports "${happy_dir}"
run_qc significance_threshold_user_supplied "${threshold_dir}"

python - "${happy_dir}" "${threshold_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

happy_dir = Path(sys.argv[1])
threshold_dir = Path(sys.argv[2])

happy = json.loads((happy_dir / "pathway_qc_diagnostics.json").read_text(encoding="utf-8"))
assert happy["status"] == "passed", happy
assert happy["parameters"] == {"significance_max": 0.2, "significance_metric": "adjusted_p_value"}, happy
assert happy["combined_results"]["n_total_pathways"] == 3, happy
assert happy["combined_results"]["n_significant_pathways"] == 2, happy
assert happy["mapping"]["resolved_background_universe.n_unique_resolved_identifiers"] == 100, happy
assert happy["gene_sets"]["databases"][0]["checksum_sha256"].startswith("a74077"), happy

with (happy_dir / "pathway_qc_summary.tsv").open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
assert {row["database_id"] for row in rows} == {"reactome_hs", "go_bp_hs"}, rows

threshold = json.loads((threshold_dir / "pathway_qc_diagnostics.json").read_text(encoding="utf-8"))
assert threshold["parameters"]["significance_max"] == 0.07, threshold
assert threshold["combined_results"]["n_significant_pathways"] == 2, threshold
PY

for fixture in missing_significance_param missing_required_column; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_qc "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/pathway_qc_diagnostics.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

diagnostics = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert diagnostics["status"] == "failed", diagnostics
assert diagnostics["errors"], diagnostics
joined = " ".join(diagnostics["errors"])
if fixture == "missing_significance_param":
    assert "significance_max" in joined and "explicit numeric value" in joined, diagnostics
if fixture == "missing_required_column":
    assert "missing required column" in joined and "adjusted_p_value" in joined, diagnostics
PY
done

echo "common.pathway.qc_diagnostics smoke test passed."
