#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.align.hisat2 atomic step.
#
# Usage:
#   scripts/smoke_test_common_align_hisat2.sh
#   scripts/smoke_test_common_align_hisat2.sh --cleanup

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
module_file="${repo_root}/modules/local/common/align/hisat2/main.nf"
image="survom/hisat2:2.2.2-samtools1.23.1-dev"
dataset_root="${repo_root}/../mult-omics/testdatasets/test_data/human_chr22_rnaseq"
genome_fasta="${dataset_root}/refs/chr22_with_ERCC92.fa"
annotation_gtf="${dataset_root}/refs/chr22_with_ERCC92.gtf"
r1="${dataset_root}/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read1.fastq.gz"
r2="${dataset_root}/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read2.fastq.gz"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: HISAT2 align module is missing: $module_file" >&2; exit 1; }
for required in "$genome_fasta" "$annotation_gtf" "$r1" "$r2"; do
  [ -r "$required" ] || { echo "ERROR: required smoke-test input is missing or unreadable: $required" >&2; exit 1; }
done
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-hisat2-align-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
index_dir="${run_dir}/hisat2_index"
log_file="${run_dir}/nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir" "$index_dir"

docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$(dirname "$genome_fasta"):/refs:ro" \
  -v "${run_dir}:/work" \
  -w /work \
  "$image" \
  /bin/bash -lc "hisat2_extract_splice_sites.py /refs/$(basename "$annotation_gtf") > annotation.ss && hisat2_extract_exons.py /refs/$(basename "$annotation_gtf") > annotation.exon && hisat2-build --ss annotation.ss --exon annotation.exon /refs/$(basename "$genome_fasta") hisat2_index/reference" >/dev/null 2>&1

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_ALIGN_HISAT2 } from '${module_file}'

workflow {
    reads = Channel.of(tuple('HBR_Rep1', [file('${r1}'), file('${r2}')], file('${index_dir}')))
    SURVOM_COMMON_ALIGN_HISAT2(reads)
    SURVOM_COMMON_ALIGN_HISAT2.out.bam.view { "BAM \${it[1].name}" }
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
  echo "ERROR: Nextflow HISAT2 align smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

[ -f "${out_dir}/HBR_Rep1.sorted.bam" ] || { echo "ERROR: missing sorted BAM" >&2; exit 1; }
[ -f "${out_dir}/HBR_Rep1.sorted.bam.bai" ] || { echo "ERROR: missing BAM index" >&2; exit 1; }
[ -f "${out_dir}/hisat2_alignment_summary.txt" ] || { echo "ERROR: missing HISAT2 alignment summary" >&2; exit 1; }
docker run --rm -v "${out_dir}:/out:ro" "$image" samtools quickcheck /out/HBR_Rep1.sorted.bam

echo "hisat2 align smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: $out_dir"
find "$out_dir" -maxdepth 1 -type f | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
