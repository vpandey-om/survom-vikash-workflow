#!/usr/bin/env bash
# Smoke test for the SurvOm common.pathway.combine_results atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_pathway_combine_results"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-pathway-combine-results.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_combine_results() {
  local result_tables="$1"
  local params="$2"
  local out_dir="$3"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__pathway__combine_results.py" \
    --enrichment-results "${result_tables}" \
    --combine-params "${params}" \
    --out-combined-results "${out_dir}/combined_pathway_results.tsv" \
    --out-combined-diagnostics "${out_dir}/combined_pathway_diagnostics.json"
}

happy_dir="${tmp_dir}/happy_two_databases"
run_combine_results \
  "${fixtures}/happy_two_databases/reactome_results.tsv,${fixtures}/happy_two_databases/go_results.tsv" \
  "${fixtures}/happy_two_databases/combine_params.json" \
  "${happy_dir}"

allowed_dir="${tmp_dir}/mixed_versions_allowed"
run_combine_results \
  "${fixtures}/mixed_versions_allowed/reactome_v92.tsv,${fixtures}/mixed_versions_allowed/reactome_v93.tsv" \
  "${fixtures}/mixed_versions_allowed/combine_params.json" \
  "${allowed_dir}"

python - "${happy_dir}" "${allowed_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

happy_dir = Path(sys.argv[1])
allowed_dir = Path(sys.argv[2])

def rows(root):
    with (root / "combined_pathway_results.tsv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

happy_diag = json.loads((happy_dir / "combined_pathway_diagnostics.json").read_text(encoding="utf-8"))
assert happy_diag["status"] == "passed", happy_diag
assert happy_diag["parameters"]["allow_mixed_database_versions"] is False, happy_diag
assert happy_diag["n_input_result_files"] == 2, happy_diag
assert happy_diag["n_total_result_rows"] == 3, happy_diag
assert happy_diag["mixed_database_versions"] == {}, happy_diag
happy_rows = rows(happy_dir)
assert [row["database_id"] for row in happy_rows] == ["reactome_hs", "reactome_hs", "go_bp_hs"], happy_rows
assert "consensus_score" not in happy_rows[0], happy_rows[0]
assert happy_rows[0]["contrast_id"] == "treatment_vs_control", happy_rows[0]

allowed_diag = json.loads((allowed_dir / "combined_pathway_diagnostics.json").read_text(encoding="utf-8"))
assert allowed_diag["status"] == "passed", allowed_diag
assert allowed_diag["parameters"]["allow_mixed_database_versions"] is True, allowed_diag
assert allowed_diag["mixed_database_versions"] == {"reactome_hs": ["Reactome 92", "Reactome 93"]}, allowed_diag
allowed_rows = rows(allowed_dir)
assert [row["database_version"] for row in allowed_rows] == ["Reactome 92", "Reactome 93"], allowed_rows
PY

for fixture in mixed_versions_fail missing_required_param missing_required_column; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  case "${fixture}" in
    mixed_versions_fail)
      run_combine_results \
        "${fixtures}/${fixture}/reactome_v92.tsv,${fixtures}/${fixture}/reactome_v93.tsv" \
        "${fixtures}/${fixture}/combine_params.json" \
        "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
      ;;
    *)
      run_combine_results \
        "${fixtures}/${fixture}/reactome_results.tsv" \
        "${fixtures}/${fixture}/combine_params.json" \
        "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
      ;;
  esac
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/combined_pathway_diagnostics.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

diagnostics = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert diagnostics["status"] == "failed", diagnostics
assert diagnostics["errors"], diagnostics
joined = " ".join(diagnostics["errors"])
if fixture == "mixed_versions_fail":
    assert "allow_mixed_database_versions is false" in joined and "Reactome 92" in joined and "Reactome 93" in joined, diagnostics
if fixture == "missing_required_param":
    assert "allow_mixed_database_versions" in joined and "explicit boolean" in joined, diagnostics
if fixture == "missing_required_column":
    assert "missing required column" in joined and "adjusted_p_value" in joined, diagnostics
PY
done

echo "common.pathway.combine_results smoke test passed."
