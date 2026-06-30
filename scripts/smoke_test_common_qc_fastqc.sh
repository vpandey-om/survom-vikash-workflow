#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.qc.fastqc atomic step.
#
# Usage:
#   scripts/smoke_test_common_qc_fastqc.sh
#   scripts/smoke_test_common_qc_fastqc.sh --cleanup
#
# The script creates a timestamped run directory under /tmp/survom-fastqc-smoke/,
# runs the FastQC Nextflow module on two paired public/test RNA-seq samples with
# Docker, verifies four HTML and four ZIP reports, and prints the output paths.
# Temporary outputs are kept by default for inspection. With --cleanup, only the
# current run directory is removed after a successful run.

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
      sed -n '2,11p' "$0"
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
module_file="${repo_root}/modules/local/common/qc/fastqc/main.nf"
image="survom/fastqc:0.12.1-dev"

hbr_r1="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read1.fastq.gz"
hbr_r2="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read2.fastq.gz"
uhr_r1="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/UHR_Rep1_ERCC-Mix1_Build37-ErccTranscripts-chr22.read1.fastq.gz"
uhr_r2="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/UHR_Rep1_ERCC-Mix1_Build37-ErccTranscripts-chr22.read2.fastq.gz"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: FastQC module is missing: $module_file" >&2; exit 1; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required local Docker image is missing: $image" >&2; exit 1; }

for dataset in "$hbr_r1" "$hbr_r2" "$uhr_r1" "$uhr_r2"; do
  [ -r "$dataset" ] || { echo "ERROR: dataset file is missing or unreadable: $dataset" >&2; exit 1; }
done

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-fastqc-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
log_file="${run_dir}/nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir"

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_QC_FASTQC } from '${module_file}'

workflow {
    reads = Channel.of(
        tuple(
            'HBR_Rep1',
            [
                file('${hbr_r1}'),
                file('${hbr_r2}')
            ]
        ),
        tuple(
            'UHR_Rep1',
            [
                file('${uhr_r1}'),
                file('${uhr_r2}')
            ]
        )
    )

    SURVOM_COMMON_QC_FASTQC(reads)

    SURVOM_COMMON_QC_FASTQC.out.html.view { "HTML \${it.name}" }
    SURVOM_COMMON_QC_FASTQC.out.zip.view { "ZIP \${it.name}" }
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
  echo "ERROR: Nextflow FastQC smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

if grep -F 'undefined parameter `fastqc_threads`' "$log_file" >/dev/null; then
  echo "ERROR: unexpected params.fastqc_threads warning found in Nextflow log: $log_file" >&2
  exit 1
fi

html_count="$(find "$out_dir" -type f -name '*_fastqc.html' | wc -l | tr -d ' ')"
zip_count="$(find "$out_dir" -type f -name '*_fastqc.zip' | wc -l | tr -d ' ')"
report_count="$(find "$out_dir" -type f \( -name '*_fastqc.html' -o -name '*_fastqc.zip' \) | wc -l | tr -d ' ')"

if [ "$html_count" -ne 4 ]; then
  echo "ERROR: expected 4 FastQC HTML reports, found $html_count in $out_dir" >&2
  exit 1
fi
if [ "$zip_count" -ne 4 ]; then
  echo "ERROR: expected 4 FastQC ZIP reports, found $zip_count in $out_dir" >&2
  exit 1
fi
if [ "$report_count" -ne 8 ]; then
  echo "ERROR: expected exactly 8 FastQC report files, found $report_count in $out_dir" >&2
  exit 1
fi

echo "FastQC smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: $out_dir"
echo "Report files:"
find "$out_dir" -type f \( -name '*_fastqc.html' -o -name '*_fastqc.zip' \) | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
