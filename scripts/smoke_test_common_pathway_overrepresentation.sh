#!/usr/bin/env bash
# Smoke test for the SurvOm common.pathway.overrepresentation atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_pathway_overrepresentation"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-pathway-overrepresentation.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_overrepresentation() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__pathway__overrepresentation.py" \
    --resolved-identifiers "${fixtures}/${fixture}/resolved_identifiers.tsv" \
    --resolved-background-universe "${fixtures}/${fixture}/resolved_background_universe.tsv" \
    --validated-gene-sets "${fixtures}/${fixture}/validated_gene_sets.gmt" \
    --validated-manifest "${fixtures}/${fixture}/validated_manifest.json" \
    --overrepresentation-params "${fixtures}/${fixture}/overrepresentation_params.json" \
    --out-enrichment-results "${out_dir}/enrichment_results.tsv" \
    --out-overrepresentation-report "${out_dir}/overrepresentation_report.json"
}

happy_dir="${tmp_dir}/happy_unique_overlap"
direction_dir="${tmp_dir}/direction_filter"
run_overrepresentation happy_unique_overlap "${happy_dir}"
run_overrepresentation direction_filter "${direction_dir}"

python - "${happy_dir}" "${direction_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

happy_dir = Path(sys.argv[1])
direction_dir = Path(sys.argv[2])

def read_rows(root):
    with (root / "enrichment_results.tsv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

happy_report = json.loads((happy_dir / "overrepresentation_report.json").read_text(encoding="utf-8"))
assert happy_report["status"] == "passed", happy_report
assert happy_report["parameters"] == {"direction": "both", "p_adjust_method": "bh", "test_method": "fisher_exact"}, happy_report
assert happy_report["counts"]["n_input_rows"] == 4, happy_report
assert happy_report["counts"]["n_unique_selected_resolved_identifiers"] == 2, happy_report

happy_rows = {row["gene_set_id"]: row for row in read_rows(happy_dir)}
assert happy_rows["PATHWAY_ALPHA"]["overlap_count"] == "2", happy_rows
assert happy_rows["PATHWAY_ALPHA"]["selected_count"] == "2", happy_rows
assert happy_rows["PATHWAY_ALPHA"]["overlap_resolved_identifiers"] == "ENSG000001,ENSG000002", happy_rows
assert happy_rows["PATHWAY_ALPHA"]["test_method"] == "fisher_exact", happy_rows
assert happy_rows["PATHWAY_BETA"]["overlap_count"] == "0", happy_rows

direction_report = json.loads((direction_dir / "overrepresentation_report.json").read_text(encoding="utf-8"))
assert direction_report["status"] == "passed", direction_report
assert direction_report["parameters"]["direction"] == "up", direction_report
assert direction_report["counts"]["n_unique_selected_resolved_identifiers"] == 2, direction_report
direction_rows = {row["gene_set_id"]: row for row in read_rows(direction_dir)}
assert direction_rows["PATHWAY_UP"]["overlap_count"] == "2", direction_rows
assert direction_rows["PATHWAY_DOWN"]["overlap_count"] == "0", direction_rows
assert direction_rows["PATHWAY_UP"]["test_method"] == "hypergeometric", direction_rows
assert direction_rows["PATHWAY_UP"]["p_adjust_method"] == "bonferroni", direction_rows
PY

for fixture in missing_required_param invalid_background_overlap invalid_gene_set_member; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_overrepresentation "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/overrepresentation_report.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
if fixture == "missing_required_param":
    assert "p_adjust_method" in joined and "explicit non-empty string" in joined, report
if fixture == "invalid_background_overlap":
    assert "subset of the resolved background universe" in joined and "ENSG999999" in joined, report
if fixture == "invalid_gene_set_member":
    assert "gene-set members" in joined and "ENSG999999" in joined, report
PY
done

echo "common.pathway.overrepresentation smoke test passed."
