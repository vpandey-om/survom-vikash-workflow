#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.quant.featurecounts atomic step.
#
# Usage:
#   scripts/smoke_test_common_quant_featurecounts.sh
#   scripts/smoke_test_common_quant_featurecounts.sh --cleanup

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
hisat2_module="${repo_root}/modules/local/common/align/hisat2/main.nf"
featurecounts_module="${repo_root}/modules/local/common/quant/featurecounts/main.nf"
hisat2_image="survom/hisat2:2.2.2-samtools1.23.1-dev"
subread_image="survom/subread:2.1.1-dev"
dataset_root="${repo_root}/../mult-omics/testdatasets/test_data/human_chr22_rnaseq"
genome_fasta="${dataset_root}/refs/chr22_with_ERCC92.fa"
annotation_gtf="${dataset_root}/refs/chr22_with_ERCC92.gtf"
r1="${dataset_root}/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read1.fastq.gz"
r2="${dataset_root}/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read2.fastq.gz"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$hisat2_module" ] || { echo "ERROR: HISAT2 align module is missing: $hisat2_module" >&2; exit 1; }
[ -f "$featurecounts_module" ] || { echo "ERROR: FeatureCounts module is missing: $featurecounts_module" >&2; exit 1; }
for required in "$genome_fasta" "$annotation_gtf" "$r1" "$r2"; do
  [ -r "$required" ] || { echo "ERROR: required smoke-test input is missing or unreadable: $required" >&2; exit 1; }
done
docker image inspect "$hisat2_image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $hisat2_image" >&2; exit 1; }
docker image inspect "$subread_image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $subread_image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-featurecounts-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
index_dir="${run_dir}/hisat2_index"
align_out_dir="${run_dir}/hisat2_out"
featurecounts_out_dir="${run_dir}/featurecounts_out"
mkdir -p "$harness_dir" "$work_dir" "$index_dir" "$align_out_dir" "$featurecounts_out_dir"

docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$(dirname "$genome_fasta"):/refs:ro" \
  -v "${run_dir}:/work" \
  -w /work \
  "$hisat2_image" \
  /bin/bash -lc "hisat2_extract_splice_sites.py /refs/$(basename "$annotation_gtf") > annotation.ss && hisat2_extract_exons.py /refs/$(basename "$annotation_gtf") > annotation.exon && hisat2-build --ss annotation.ss --exon annotation.exon /refs/$(basename "$genome_fasta") hisat2_index/reference" >/dev/null 2>&1

cat > "${harness_dir}/align.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_ALIGN_HISAT2 } from '${hisat2_module}'

workflow {
    reads = Channel.of(tuple('HBR_Rep1', [file('${r1}'), file('${r2}')], file('${index_dir}')))
    SURVOM_COMMON_ALIGN_HISAT2(reads)
    SURVOM_COMMON_ALIGN_HISAT2.out.bam.view { "BAM \${it[1].name}" }
}
NF

cat > "${harness_dir}/align.config" <<NF
process.container = '${hisat2_image}'
process.publishDir = [ path: '${align_out_dir}', mode: 'copy' ]
docker.enabled = true
docker.runOptions = '-u $(id -u):$(id -g)'
NF

align_log="${run_dir}/hisat2_align.nextflow.log"
set +e
nextflow run "${harness_dir}/align.nf" \
  -c "${harness_dir}/align.config" \
  -work-dir "$work_dir" \
  -with-docker > "$align_log" 2>&1
align_status=$?
set -e

if [ "$align_status" -ne 0 ]; then
  echo "ERROR: HISAT2 prerequisite alignment failed with exit status $align_status" >&2
  echo "Log: $align_log" >&2
  sed -n '1,220p' "$align_log" >&2
  exit "$align_status"
fi

bam="${align_out_dir}/HBR_Rep1.sorted.bam"
bai="${align_out_dir}/HBR_Rep1.sorted.bam.bai"
[ -f "$bam" ] || { echo "ERROR: missing prerequisite BAM: $bam" >&2; exit 1; }
[ -f "$bai" ] || { echo "ERROR: missing prerequisite BAM index: $bai" >&2; exit 1; }

cat > "${harness_dir}/featurecounts.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_QUANT_FEATURECOUNTS } from '${featurecounts_module}'

workflow {
    inputs = Channel.of(tuple('HBR_Rep1', file('${bam}'), file('${bai}'), file('${annotation_gtf}')))
    SURVOM_COMMON_QUANT_FEATURECOUNTS(inputs)
    SURVOM_COMMON_QUANT_FEATURECOUNTS.out.counts.view { "COUNTS \${it[1].name}" }
}
NF

cat > "${harness_dir}/featurecounts.config" <<NF
process.container = '${subread_image}'
process.publishDir = [ path: '${featurecounts_out_dir}', mode: 'copy' ]
docker.enabled = true
docker.runOptions = '-u $(id -u):$(id -g)'
NF

featurecounts_log="${run_dir}/featurecounts.nextflow.log"
set +e
nextflow run "${harness_dir}/featurecounts.nf" \
  -c "${harness_dir}/featurecounts.config" \
  -work-dir "$work_dir" \
  -with-docker > "$featurecounts_log" 2>&1
featurecounts_status=$?
set -e

if [ "$featurecounts_status" -ne 0 ]; then
  echo "ERROR: Nextflow FeatureCounts smoke test failed with exit status $featurecounts_status" >&2
  echo "Log: $featurecounts_log" >&2
  sed -n '1,220p' "$featurecounts_log" >&2
  exit "$featurecounts_status"
fi

counts="${featurecounts_out_dir}/gene_counts.tsv"
summary="${featurecounts_out_dir}/gene_counts.tsv.summary"
[ -f "$counts" ] || { echo "ERROR: missing FeatureCounts output: $counts" >&2; exit 1; }
[ -f "$summary" ] || { echo "ERROR: missing FeatureCounts summary: $summary" >&2; exit 1; }
if ! grep -v '^#' "$counts" | awk -F '\t' 'NR > 1 && $1 != "" { found = 1 } END { exit found ? 0 : 1 }'; then
  echo "ERROR: FeatureCounts output does not contain gene IDs" >&2
  exit 1
fi

echo "featurecounts smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: $featurecounts_out_dir"
find "$featurecounts_out_dir" -maxdepth 1 -type f | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
