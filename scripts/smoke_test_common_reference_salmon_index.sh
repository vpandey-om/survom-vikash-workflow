#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.reference.salmon_index atomic step.
#
# Usage:
#   scripts/smoke_test_common_reference_salmon_index.sh
#   scripts/smoke_test_common_reference_salmon_index.sh --cleanup

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
module_file="${repo_root}/modules/local/common/reference/salmon_index/main.nf"
transcripts="${repo_root}/tests/fixtures/salmon/transcripts.fa"
image="combinelab/salmon:1.10.3"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: Salmon index module is missing: $module_file" >&2; exit 1; }
[ -r "$transcripts" ] || { echo "ERROR: transcript FASTA fixture is missing or unreadable: $transcripts" >&2; exit 1; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-salmon-index-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
log_file="${run_dir}/nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir"

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_REFERENCE_SALMON_INDEX } from '${module_file}'

workflow {
    references = Channel.of(tuple('synthetic', file('${transcripts}')))
    SURVOM_COMMON_REFERENCE_SALMON_INDEX(references)
    SURVOM_COMMON_REFERENCE_SALMON_INDEX.out.index.view { "SALMON_INDEX \${it[1].name}" }
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
  echo "ERROR: Nextflow Salmon index smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

if [ ! -d "${out_dir}/salmon_index" ]; then
  echo "ERROR: expected Salmon index directory was not published: ${out_dir}/salmon_index" >&2
  exit 1
fi
if [ ! -f "${out_dir}/salmon_index/versionInfo.json" ]; then
  echo "ERROR: expected Salmon index versionInfo.json was not created" >&2
  exit 1
fi

echo "salmon_index smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: $out_dir"
find "${out_dir}/salmon_index" -maxdepth 1 -type f | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
