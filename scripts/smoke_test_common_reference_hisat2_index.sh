#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.reference.hisat2_index atomic step.
#
# Usage:
#   scripts/smoke_test_common_reference_hisat2_index.sh
#   scripts/smoke_test_common_reference_hisat2_index.sh --cleanup

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
module_file="${repo_root}/modules/local/common/reference/hisat2_index/main.nf"
image="survom/hisat2:2.2.2-samtools1.23.1-dev"
dataset_root="${repo_root}/../mult-omics/testdatasets/test_data/human_chr22_rnaseq"
genome_fasta="${dataset_root}/refs/chr22_with_ERCC92.fa"
annotation_gtf="${dataset_root}/refs/chr22_with_ERCC92.gtf"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: HISAT2 index module is missing: $module_file" >&2; exit 1; }
for required in "$genome_fasta" "$annotation_gtf"; do
  [ -r "$required" ] || { echo "ERROR: required smoke-test input is missing or unreadable: $required" >&2; exit 1; }
done
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-hisat2-index-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
log_file="${run_dir}/nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir"

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_REFERENCE_HISAT2_INDEX } from '${module_file}'

workflow {
    references = Channel.of(tuple('chr22_ercc92', file('${genome_fasta}'), file('${annotation_gtf}')))
    SURVOM_COMMON_REFERENCE_HISAT2_INDEX(references)
    SURVOM_COMMON_REFERENCE_HISAT2_INDEX.out.index.view { "HISAT2_INDEX \${it[1].name}" }
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
  echo "ERROR: Nextflow HISAT2 index smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

[ -d "${out_dir}/hisat2_index" ] || { echo "ERROR: missing HISAT2 index directory" >&2; exit 1; }
[ -f "${out_dir}/annotation.ss" ] || { echo "ERROR: missing annotation.ss" >&2; exit 1; }
[ -f "${out_dir}/annotation.exon" ] || { echo "ERROR: missing annotation.exon" >&2; exit 1; }
index_count="$(find "${out_dir}/hisat2_index" -maxdepth 1 -type f -name 'reference.*.ht2' | wc -l | tr -d ' ')"
[ "$index_count" -ge 8 ] || { echo "ERROR: expected at least 8 HISAT2 index shards, found $index_count" >&2; exit 1; }

echo "hisat2_index smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: $out_dir"
find "$out_dir" -maxdepth 2 -type f | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
