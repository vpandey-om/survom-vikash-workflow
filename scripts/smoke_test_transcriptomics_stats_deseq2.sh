#!/usr/bin/env bash
# Smoke test for the SurvOm transcriptomics.stats.deseq2 atomic step.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
fixtures="${repo_root}/tests/fixtures/transcriptomics_stats_deseq2"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/survom-transcriptomics-stats-deseq2.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
image="survom/deseq2:3.21-dev"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not available on PATH. Build and run the ${image} container to test transcriptomics.stats.deseq2." >&2
  exit 1
fi

docker run --rm "${image}" Rscript -e 'missing <- c("jsonlite", "DESeq2", "apeglm")[!vapply(c("jsonlite", "DESeq2", "apeglm"), requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop(sprintf("Missing required R package(s): %s. Install them in this R environment.", paste(missing, collapse=", ")), call.=FALSE)'

happy_fixture="${tmp_dir}/happy_fixture"
mkdir -p "${happy_fixture}"
python - "${happy_fixture}" <<'PY'
import json
import random
import sys
from pathlib import Path

out = Path(sys.argv[1])
samples = ["C1", "C2", "C3", "T1", "T2", "T3"]
with (out / "filtered_feature_matrix.tsv").open("w", encoding="utf-8") as handle:
    handle.write("gene_id\t" + "\t".join(samples) + "\n")
    handle.write("gene_up\t20\t22\t21\t220\t235\t230\n")
    handle.write("gene_down\t220\t235\t230\t20\t22\t21\n")
    handle.write("gene_flat\t80\t82\t78\t81\t79\t83\n")
    random.seed(7)
    for index in range(1, 201):
        base = 20 + (index % 70) * 4
        sigma = 0.15 + (index % 11) * 0.08
        control = [int(random.lognormvariate(0, sigma) * base) for _ in range(3)]
        treatment = [int(random.lognormvariate(0, sigma) * base) for _ in range(3)]
        if index % 5 == 0:
            treatment = [int(value * 1.8) + 5 for value in treatment]
        if index % 7 == 0:
            treatment = [max(1, int(value * 0.45)) for value in treatment]
        values = [str(max(1, value)) for value in control + treatment]
        handle.write(f"gene_bg_{index:02d}\t" + "\t".join(values) + "\n")
(out / "sample_metadata.tsv").write_text(
    "sample_id\tcondition\n"
    "C1\tcontrol\nC2\tcontrol\nC3\tcontrol\n"
    "T1\ttreatment\nT2\ttreatment\nT3\ttreatment\n",
    encoding="utf-8",
)
(out / "validated_design.json").write_text(json.dumps({
    "schema_version": 1,
    "status": "passed",
    "sample_id_column": "sample_id",
    "sample_ids": samples,
    "primary_factor": {
        "name": "condition",
        "reference_level": "control",
        "observed_levels": ["control", "treatment"],
        "group_sizes": {"control": 3, "treatment": 3},
    },
    "covariates": [],
    "resolved_formula": "~ condition",
}, indent=2) + "\n", encoding="utf-8")
(out / "resolved_contrasts.json").write_text(json.dumps({
    "schema_version": 1,
    "status": "passed",
    "contrasts": [{
        "contrast_id": "treatment_vs_control",
        "type": "factor_levels",
        "variable": "condition",
        "numerator": "treatment",
        "denominator": "control",
        "label": "condition: treatment vs control",
        "positive_effect_definition": "Positive effect estimate means higher abundance in treatment than control.",
    }],
}, indent=2) + "\n", encoding="utf-8")
(out / "deseq2_params.json").write_text(json.dumps({
    "test_type": "wald",
    "apply_shrinkage": False,
    "shrinkage_method": "apeglm",
    "p_adjust_method": "BH",
    "save_rds": False,
}, indent=2) + "\n", encoding="utf-8")
PY

run_deseq2() {
  local fixture_dir="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"
  docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "${repo_root}:/repo:ro" \
    -v "${tmp_dir}:${tmp_dir}" \
    -v "${out_dir}:/out" \
    -w /repo \
    "${image}" \
    Rscript bin/transcriptomics__stats__deseq2.R \
      --filtered-feature-matrix "${fixture_dir}/filtered_feature_matrix.tsv" \
      --sample-metadata "${fixture_dir}/sample_metadata.tsv" \
      --validated-design "${fixture_dir}/validated_design.json" \
      --resolved-contrasts "${fixture_dir}/resolved_contrasts.json" \
      --deseq2-params "${fixture_dir}/deseq2_params.json" \
      --out-results "/out/deseq2_results.tsv" \
      --out-diagnostics "/out/deseq2_diagnostics.json"
}

happy_dir="${tmp_dir}/happy_path"
run_deseq2 "${happy_fixture}" "${happy_dir}"

python - "${happy_dir}" <<'PY'
import csv
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
diagnostics = json.loads((out_dir / "deseq2_diagnostics.json").read_text(encoding="utf-8"))
assert diagnostics["status"] == "passed", diagnostics
assert diagnostics["method"] == "deseq2", diagnostics
assert diagnostics["parameters_used"]["apply_shrinkage"] is False, diagnostics
required = {
    "feature_id",
    "contrast_id",
    "effect_estimate",
    "effect_type",
    "p_value",
    "adjusted_p_value",
    "base_mean",
    "status",
    "method",
    "positive_effect_definition",
}
with (out_dir / "deseq2_results.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
assert rows, rows
assert required.issubset(rows[0]), rows[0]
by_feature = {row["feature_id"]: row for row in rows}
assert all(row["method"] == "deseq2" for row in rows), rows
assert all(row["effect_type"] == "log2_fold_change" for row in rows), rows
assert all("higher abundance in treatment than control" in row["positive_effect_definition"] for row in rows), rows
assert float(by_feature["gene_up"]["effect_estimate"]) > 0, by_feature["gene_up"]
assert float(by_feature["gene_down"]["effect_estimate"]) < 0, by_feature["gene_down"]
PY

for fixture in non_integer_counts missing_required_parameter; do
  failure_dir="${tmp_dir}/${fixture}"
  set +e
  run_deseq2 "/repo/tests/fixtures/transcriptomics_stats_deseq2/${fixture}" "${failure_dir}" >/dev/null 2>"${failure_dir}.stderr"
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    echo "ERROR: ${fixture} unexpectedly passed" >&2
    exit 1
  fi
  python - "${failure_dir}/deseq2_diagnostics.json" "${fixture}" <<'PY'
import json
import sys
from pathlib import Path

diagnostics = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fixture = sys.argv[2]
assert diagnostics["status"] == "failed", diagnostics
assert diagnostics["errors"], diagnostics
joined = " ".join(diagnostics["errors"])
if fixture == "non_integer_counts":
    assert "non-integer counts" in joined, diagnostics
if fixture == "missing_required_parameter":
    assert "Missing required DESeq2 parameter" in joined, diagnostics
PY
done

echo "transcriptomics.stats.deseq2 smoke test passed."
