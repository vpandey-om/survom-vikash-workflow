#!/usr/bin/env bash
# Smoke test for the SurvOm common.pathway.resolve_identifiers atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_pathway_resolve_identifiers"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-pathway-resolve-identifiers.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_resolve_identifiers() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__pathway__resolve_identifiers.py" \
    --validated-enrichment-input "${fixtures}/${fixture}/validated_enrichment_input.tsv" \
    --validated-background-universe "${fixtures}/${fixture}/validated_background_universe.tsv" \
    --identifier-mapping "${fixtures}/${fixture}/identifier_mapping.tsv" \
    --resolution-params "${fixtures}/${fixture}/resolution_params.json" \
    --out-resolved-identifiers "${out_dir}/resolved_identifiers.tsv" \
    --out-resolved-background-universe "${out_dir}/resolved_background_universe.tsv" \
    --out-resolution-report "${out_dir}/resolution_report.json"
}

happy_dir="${tmp_dir}/happy_retain_all"
background_dir="${tmp_dir}/background_resolves_separately"
run_resolve_identifiers happy_retain_all "${happy_dir}"
run_resolve_identifiers background_resolves_separately "${background_dir}"

python - "${happy_dir}" "${background_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

happy_dir = Path(sys.argv[1])
background_dir = Path(sys.argv[2])

def read_rows(root, name):
    with (root / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

happy_report = json.loads((happy_dir / "resolution_report.json").read_text(encoding="utf-8"))
assert happy_report["status"] == "passed", happy_report
assert happy_report["policies"]["ambiguous_mapping_policy"] == "retain_all", happy_report
assert happy_report["policies"]["unmapped_identifier_policy"] == "drop", happy_report
assert happy_report["policies"]["duplicate_resolved_identifier_policy"] == "retain_all", happy_report
assert happy_report["resolved_identifiers"]["n_ambiguous_source_identifiers"] == 1, happy_report
assert happy_report["resolved_background_universe"]["n_unmapped_source_identifiers"] == 1, happy_report

resolved = read_rows(happy_dir, "resolved_identifiers.tsv")
assert [row["resolved_identifier"] for row in resolved] == ["ENSG000001", "ENSG000002", "ENSG000003"], resolved
assert resolved[1]["resolution_status"] == "ambiguous_retained", resolved
assert resolved[2]["resolution_status"] == "ambiguous_retained", resolved
background = read_rows(happy_dir, "resolved_background_universe.tsv")
assert [row["resolved_identifier"] for row in background] == ["ENSG000001", "ENSG000002", "ENSG000003"], background

background_report = json.loads((background_dir / "resolution_report.json").read_text(encoding="utf-8"))
assert background_report["status"] == "passed", background_report
background_rows = read_rows(background_dir, "resolved_background_universe.tsv")
assert [row["resolved_identifier"] for row in background_rows] == ["ENSG000001", "ENSG000002", "ENSG000004"], background_rows
assert "ENSG000004" not in [row["resolved_identifier"] for row in read_rows(background_dir, "resolved_identifiers.tsv")]
PY

for fixture in missing_policy ambiguous_fail unmapped_fail duplicate_fail; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_resolve_identifiers "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/resolution_report.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
if fixture == "missing_policy":
    assert "ambiguous_mapping_policy" in joined, report
if fixture == "ambiguous_fail":
    assert "ambiguous mapping" in joined, report
if fixture == "unmapped_fail":
    assert "unmapped identifier" in joined, report
if fixture == "duplicate_fail":
    assert "duplicate resolved identifier" in joined, report
PY
done

echo "common.pathway.resolve_identifiers smoke test passed."
