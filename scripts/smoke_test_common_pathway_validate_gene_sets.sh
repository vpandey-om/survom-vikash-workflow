#!/usr/bin/env bash
# Smoke test for the SurvOm common.pathway.validate_gene_sets atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/common_pathway_validate_gene_sets"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-common-pathway-validate-gene-sets.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

run_validate_gene_sets() {
  local fixture="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  python "${repo_root}/bin/common__pathway__validate_gene_sets.py" \
    --gene-set-manifest "${fixtures}/${fixture}/manifest.yml" \
    --gene-set-file "${fixtures}/${fixture}/gene_sets.gmt" \
    --validation-params "${fixtures}/${fixture}/validation_params.json" \
    --out-validated-gene-sets "${out_dir}/validated_gene_sets.gmt" \
    --out-validated-manifest "${out_dir}/validated_gene_set_manifest.json" \
    --out-validation-report "${out_dir}/gene_set_validation_report.json"
}

valid_dir="${tmp_dir}/valid"
run_validate_gene_sets valid "${valid_dir}"

python - "${valid_dir}" <<'PY'
import json
import sys
from pathlib import Path

valid_dir = Path(sys.argv[1])
report = json.loads((valid_dir / "gene_set_validation_report.json").read_text(encoding="utf-8"))
manifest = json.loads((valid_dir / "validated_gene_set_manifest.json").read_text(encoding="utf-8"))
validated_gmt = (valid_dir / "validated_gene_sets.gmt").read_text(encoding="utf-8").splitlines()

assert report["status"] == "passed", report
assert report["manifest"]["database_id"] == "synthetic_pathway_hs", report
assert report["manifest"]["identifier_namespace"] == "ensembl_gene_id", report
assert report["gene_sets"]["n_gene_sets"] == 2, report
assert report["gene_sets"]["min_observed_gene_set_size"] == 2, report
assert report["gene_sets"]["max_observed_gene_set_size"] == 3, report
assert report["validation_params"] == {"min_gene_set_size": 2, "max_gene_set_size": 5}, report
assert manifest["gene_set_format"] == "gmt", manifest
assert len(validated_gmt) == 2, validated_gmt
PY

for fixture in missing_required_manifest checksum_mismatch duplicate_gene_set_id size_limit_fail missing_size_param; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_validate_gene_sets "${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/gene_set_validation_report.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert report["status"] == "failed", report
assert report["errors"], report
joined = " ".join(report["errors"])
if fixture == "missing_required_manifest":
    assert "license_note" in joined and "missing required field" in joined, report
if fixture == "checksum_mismatch":
    assert "checksum_sha256" in joined and "does not match" in joined, report
if fixture == "duplicate_gene_set_id":
    assert "must be unique" in joined and "PATHWAY_ALPHA" in joined, report
if fixture == "size_limit_fail":
    assert "gene-set sizes" in joined and "PATHWAY_TOO_SMALL=1" in joined, report
if fixture == "missing_size_param":
    assert "max_gene_set_size" in joined and "explicit integer" in joined, report
PY
done

echo "common.pathway.validate_gene_sets smoke test passed."
