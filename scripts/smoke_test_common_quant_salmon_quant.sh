#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.quant.salmon_quant atomic step.
#
# Usage:
#   scripts/smoke_test_common_quant_salmon_quant.sh
#   scripts/smoke_test_common_quant_salmon_quant.sh --cleanup

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
module_file="${repo_root}/modules/local/common/quant/salmon_quant/main.nf"
fixture_dir="${repo_root}/tests/fixtures/salmon"
transcripts="${fixture_dir}/transcripts.fa"
single_fastq="${fixture_dir}/sample_single.fastq"
r1_fastq="${fixture_dir}/sample_R1.fastq"
r2_fastq="${fixture_dir}/sample_R2.fastq"
image="combinelab/salmon:1.10.3"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: Salmon quant module is missing: $module_file" >&2; exit 1; }
for fixture in "$transcripts" "$single_fastq" "$r1_fastq" "$r2_fastq"; do
  [ -r "$fixture" ] || { echo "ERROR: fixture is missing or unreadable: $fixture" >&2; exit 1; }
done
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-salmon-quant-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
index_dir="${run_dir}/salmon_index"
single_out_dir="${run_dir}/out_single"
paired_out_dir="${run_dir}/out_paired"
single_log_file="${run_dir}/single.nextflow.log"
paired_log_file="${run_dir}/paired.nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$single_out_dir" "$paired_out_dir"

docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "${fixture_dir}:/fixtures:ro" \
  -v "${run_dir}:/work" \
  -w /work \
  "$image" \
  salmon index --transcripts /fixtures/transcripts.fa --index salmon_index --threads 2 >/dev/null 2>&1

cat > "${harness_dir}/single.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_QUANT_SALMON_QUANT } from '${module_file}'

workflow {
    reads = Channel.of(tuple('synthetic_single', file('${index_dir}'), file('${single_fastq}')))
    SURVOM_COMMON_QUANT_SALMON_QUANT(reads)
    SURVOM_COMMON_QUANT_SALMON_QUANT.out.quant.view { "QUANT \${it[0]} \${it[1].name}" }
}
NF

cat > "${harness_dir}/paired.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_QUANT_SALMON_QUANT } from '${module_file}'

workflow {
    reads = Channel.of(tuple('synthetic_paired', file('${index_dir}'), [file('${r1_fastq}'), file('${r2_fastq}')]))
    SURVOM_COMMON_QUANT_SALMON_QUANT(reads)
    SURVOM_COMMON_QUANT_SALMON_QUANT.out.quant.view { "QUANT \${it[0]} \${it[1].name}" }
}
NF

run_quant() {
  local harness="$1"
  local out_dir="$2"
  local log_file="$3"
  cat > "${harness_dir}/nextflow.config" <<NF
process.container = '${image}'
process.publishDir = [ path: '${out_dir}', mode: 'copy' ]
docker.enabled = true
docker.runOptions = '-u $(id -u):$(id -g)'
NF

  set +e
  nextflow run "$harness" \
    -c "${harness_dir}/nextflow.config" \
    -work-dir "$work_dir" \
    -with-docker > "$log_file" 2>&1
  local nextflow_status=$?
  set -e

  if [ "$nextflow_status" -ne 0 ]; then
    echo "ERROR: Nextflow Salmon quant smoke test failed with exit status $nextflow_status" >&2
    echo "Log: $log_file" >&2
    sed -n '1,220p' "$log_file" >&2
    exit "$nextflow_status"
  fi
}

run_quant "${harness_dir}/single.nf" "$single_out_dir" "$single_log_file"
run_quant "${harness_dir}/paired.nf" "$paired_out_dir" "$paired_log_file"

for out_dir in "$single_out_dir" "$paired_out_dir"; do
  [ -f "${out_dir}/salmon_quant/quant.sf" ] || { echo "ERROR: missing quant.sf in $out_dir" >&2; exit 1; }
  [ -f "${out_dir}/salmon_quant/cmd_info.json" ] || { echo "ERROR: missing cmd_info.json in $out_dir" >&2; exit 1; }
  [ -d "${out_dir}/salmon_quant/aux_info" ] || { echo "ERROR: missing aux_info in $out_dir" >&2; exit 1; }
  [ -d "${out_dir}/salmon_quant/libParams" ] || { echo "ERROR: missing libParams in $out_dir" >&2; exit 1; }
done

echo "salmon_quant smoke test passed."
echo "Run directory: $run_dir"
echo "Single-end output directory: $single_out_dir"
echo "Paired-end output directory: $paired_out_dir"

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
