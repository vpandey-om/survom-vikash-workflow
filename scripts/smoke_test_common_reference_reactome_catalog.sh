#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture_root="${repo_root}/tests/fixtures/common_reference_reactome_catalog"
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

command -v python >/dev/null 2>&1 || { echo "ERROR: python is not available on PATH" >&2; exit 1; }
python - <<'PY'
try:
    import duckdb  # noqa: F401
except ImportError as exc:
    raise SystemExit("ERROR: duckdb is required for this smoke test and for Parquet write/read-back validation.") from exc
PY

valid_out="${tmpdir}/valid"
mkdir -p "${valid_out}"
python "${repo_root}/bin/common__reference__reactome_catalog.py" \
  --mapping-file "${fixture_root}/valid/reactome_all_levels_small.txt" \
  --release-version 97 \
  --organism "Homo sapiens" \
  --mapping-kind ensembl_protein_all_levels \
  --source-identifier-namespace ensembl_protein_id \
  --out-parquet "${valid_out}/reactome_mapping_catalog.parquet" \
  --out-manifest "${valid_out}/reactome_catalog_manifest.yaml" \
  --out-diagnostics "${valid_out}/reactome_catalog_diagnostics.json"

python - "${valid_out}" <<'PY'
import json
import pathlib
import re
import sys

import duckdb

out = pathlib.Path(sys.argv[1])
parquet = out / "reactome_mapping_catalog.parquet"
manifest = out / "reactome_catalog_manifest.yaml"
diagnostics = out / "reactome_catalog_diagnostics.json"
for path in [parquet, manifest, diagnostics]:
    assert path.exists(), f"missing output: {path}"

connection = duckdb.connect(database=":memory:")
try:
    rows = connection.execute(
        "SELECT source_identifier, species FROM read_parquet(?) ORDER BY source_identifier",
        [str(parquet)],
    ).fetchall()
finally:
    connection.close()
assert len(rows) == 2, rows
assert {row[1] for row in rows} == {"Homo sapiens"}, rows

manifest_text = manifest.read_text(encoding="utf-8")
assert 'release_version: "97"' in manifest_text
assert "mapping_kind: ensembl_protein_all_levels" in manifest_text
assert "source_identifier_namespace: ensembl_protein_id" in manifest_text
assert "rows: 2" in manifest_text
assert re.search(r"mapping_sha256: \"[0-9a-f]{64}\"", manifest_text), manifest_text
assert "compression: zstd" in manifest_text

diag = json.loads(diagnostics.read_text(encoding="utf-8"))
assert diag["input_row_count"] == 3, diag
assert diag["retained_organism_row_count"] == 2, diag
assert diag["output_row_count"] == 2, diag
assert diag["malformed_row_count"] == 0, diag
assert re.fullmatch(r"[0-9a-f]{64}", diag["source_sha256"])
assert re.fullmatch(r"[0-9a-f]{64}", diag["output_sha256"])
PY

expect_failure() {
  local label="$1"
  shift
  set +e
  "$@" >"${tmpdir}/${label}.out" 2>"${tmpdir}/${label}.err"
  local status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    echo "ERROR: expected ${label} to fail" >&2
    exit 1
  fi
}

expect_failure empty_input \
  python "${repo_root}/bin/common__reference__reactome_catalog.py" \
    --mapping-file "${fixture_root}/invalid/empty_mapping.txt" \
    --release-version 97 \
    --organism "Homo sapiens" \
    --mapping-kind ensembl_protein_all_levels \
    --source-identifier-namespace ensembl_protein_id \
    --out-parquet "${tmpdir}/empty/reactome_mapping_catalog.parquet" \
    --out-manifest "${tmpdir}/empty/reactome_catalog_manifest.yaml" \
    --out-diagnostics "${tmpdir}/empty/reactome_catalog_diagnostics.json"

expect_failure malformed_input \
  python "${repo_root}/bin/common__reference__reactome_catalog.py" \
    --mapping-file "${fixture_root}/invalid/malformed_row_count.txt" \
    --release-version 97 \
    --organism "Homo sapiens" \
    --mapping-kind ensembl_protein_all_levels \
    --source-identifier-namespace ensembl_protein_id \
    --out-parquet "${tmpdir}/malformed/reactome_mapping_catalog.parquet" \
    --out-manifest "${tmpdir}/malformed/reactome_catalog_manifest.yaml" \
    --out-diagnostics "${tmpdir}/malformed/reactome_catalog_diagnostics.json"

expect_failure no_human_rows \
  python "${repo_root}/bin/common__reference__reactome_catalog.py" \
    --mapping-file "${fixture_root}/invalid/no_human_rows.txt" \
    --release-version 97 \
    --organism "Homo sapiens" \
    --mapping-kind ensembl_protein_all_levels \
    --source-identifier-namespace ensembl_protein_id \
    --out-parquet "${tmpdir}/no_human/reactome_mapping_catalog.parquet" \
    --out-manifest "${tmpdir}/no_human/reactome_catalog_manifest.yaml" \
    --out-diagnostics "${tmpdir}/no_human/reactome_catalog_diagnostics.json"

expect_failure missing_required_metadata \
  python "${repo_root}/bin/common__reference__reactome_catalog.py" \
    --mapping-file "${fixture_root}/valid/reactome_all_levels_small.txt" \
    --release-version 97 \
    --organism "Homo sapiens" \
    --mapping-kind ensembl_protein_all_levels \
    --out-parquet "${tmpdir}/missing_meta/reactome_mapping_catalog.parquet" \
    --out-manifest "${tmpdir}/missing_meta/reactome_catalog_manifest.yaml" \
    --out-diagnostics "${tmpdir}/missing_meta/reactome_catalog_diagnostics.json"

echo "common.reference.reactome_catalog smoke test passed"
