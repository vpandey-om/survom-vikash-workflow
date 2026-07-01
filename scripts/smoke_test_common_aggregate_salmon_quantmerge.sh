#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.aggregate.salmon_quantmerge atomic step.
#
# Usage:
#   scripts/smoke_test_common_aggregate_salmon_quantmerge.sh
#   scripts/smoke_test_common_aggregate_salmon_quantmerge.sh --cleanup

set -euo pipefail

cleanup=false
if [ "$#" -gt 1 ]; then
  echo "ERROR: expected zero arguments or --cleanup" >&2
  exit 2
fi
if [ "$#" -eq 1 ]; then
  case "$1" in
    --cleanup)
      cleanup=true
      ;;
    -h|--help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 2
      ;;
  esac
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
module_file="${repo_root}/modules/local/common/aggregate/salmon_quantmerge/main.nf"
fixture_dir="${repo_root}/tests/fixtures/salmon"
sample1="${fixture_dir}/sample1_quant.sf"
sample2="${fixture_dir}/sample2_quant.sf"
image="combinelab/salmon:1.10.3"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: Salmon quantmerge module is missing: $module_file" >&2; exit 1; }
for fixture in "$sample1" "$sample2"; do
  [ -r "$fixture" ] || { echo "ERROR: fixture is missing or unreadable: $fixture" >&2; exit 1; }
done
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-salmon-quantmerge-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
log_file="${run_dir}/nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir"

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_AGGREGATE_SALMON_QUANTMERGE } from '${module_file}'

workflow {
    quant_files = Channel.of(tuple('synthetic_merge', [file('${sample1}'), file('${sample2}')]))
    SURVOM_COMMON_AGGREGATE_SALMON_QUANTMERGE(quant_files)
    SURVOM_COMMON_AGGREGATE_SALMON_QUANTMERGE.out.counts.view { "COUNTS \${it[1].name}" }
}
NF

cat > "${harness_dir}/nextflow.config" <<NF
process.container = '${image}'
process.publishDir = [ path: '${out_dir}', mode: 'copy' ]
docker.enabled = true
docker.runOptions = '-u $(id -u):$(id -g)'
NF

set +e
nextflow run "${harness_dir}/main.nf" \
  -c "${harness_dir}/nextflow.config" \
  -work-dir "$work_dir" \
  -with-docker > "$log_file" 2>&1
nextflow_status=$?
set -e

if [ "$nextflow_status" -ne 0 ]; then
  echo "ERROR: Nextflow Salmon quantmerge smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

if [ ! -f "${out_dir}/salmon_counts.tsv" ]; then
  echo "ERROR: expected merged counts file was not published: ${out_dir}/salmon_counts.tsv" >&2
  exit 1
fi
if ! grep -F "tx1" "${out_dir}/salmon_counts.tsv" >/dev/null; then
  echo "ERROR: merged counts file does not contain expected transcript tx1" >&2
  exit 1
fi

echo "salmon_quantmerge smoke test passed."
echo "Run directory: $run_dir"
echo "Output file: ${out_dir}/salmon_counts.tsv"
cat "${out_dir}/salmon_counts.tsv"

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
