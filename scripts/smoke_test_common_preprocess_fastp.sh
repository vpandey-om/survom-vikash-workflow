#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.preprocess.fastp atomic step.
#
# Usage:
#   scripts/smoke_test_common_preprocess_fastp.sh
#   scripts/smoke_test_common_preprocess_fastp.sh --cleanup
#
# The script creates a timestamped run directory under /tmp/survom-fastp-smoke/,
# runs the fastp Nextflow module on paired public/test RNA-seq samples with
# Docker, verifies trimmed FASTQ.GZ plus native HTML/JSON reports for both
# approved profiles, verifies illumina_pe_q20 rejects single-end input, and
# prints the output paths. Temporary outputs are kept by default for inspection.

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
      sed -n '2,12p' "$0"
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
module_file="${repo_root}/modules/local/common/preprocess/fastp/main.nf"
image="survom/fastp:1.3.6-dev"

hbr_r1="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read1.fastq.gz"
hbr_r2="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read2.fastq.gz"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: fastp module is missing: $module_file" >&2; exit 1; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required local Docker image is missing: $image" >&2; exit 1; }

for dataset in "$hbr_r1" "$hbr_r2"; do
  [ -r "$dataset" ] || { echo "ERROR: dataset file is missing or unreadable: $dataset" >&2; exit 1; }
done

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-fastp-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
log_file="${run_dir}/nextflow.log"
reject_log_file="${run_dir}/single_end_reject.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir"

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_PREPROCESS_FASTP } from '${module_file}'

workflow {
    reads = Channel.of(
        tuple(
            'HBR_Rep1_default',
            [
                file('${hbr_r1}'),
                file('${hbr_r2}')
            ],
            'default'
        ),
        tuple(
            'HBR_Rep1_illumina_pe_q20',
            [
                file('${hbr_r1}'),
                file('${hbr_r2}')
            ],
            'illumina_pe_q20'
        )
    )

    SURVOM_COMMON_PREPROCESS_FASTP(reads)

    SURVOM_COMMON_PREPROCESS_FASTP.out.paired_trimmed.view { "PAIRED_TRIMMED \${it[1].name} \${it[2].name}" }
    SURVOM_COMMON_PREPROCESS_FASTP.out.html.view { "HTML \${it.name}" }
    SURVOM_COMMON_PREPROCESS_FASTP.out.json.view { "JSON \${it.name}" }
}
NF

cat > "${harness_dir}/reject_single_end.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_PREPROCESS_FASTP } from '${module_file}'

workflow {
    reads = Channel.of(
        tuple(
            'HBR_Rep1_single',
            file('${hbr_r1}'),
            'illumina_pe_q20'
        )
    )

    SURVOM_COMMON_PREPROCESS_FASTP(reads)
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
  echo "ERROR: Nextflow fastp smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

fastq_count="$(find "$out_dir" -type f -name '*.trimmed.fastq.gz' | wc -l | tr -d ' ')"
html_count="$(find "$out_dir" -type f -name '*.fastp.html' | wc -l | tr -d ' ')"
json_count="$(find "$out_dir" -type f -name '*.fastp.json' | wc -l | tr -d ' ')"

if [ "$fastq_count" -ne 4 ]; then
  echo "ERROR: expected 4 trimmed paired-end FASTQ files, found $fastq_count in $out_dir" >&2
  exit 1
fi
if [ "$html_count" -ne 2 ]; then
  echo "ERROR: expected 2 fastp HTML reports, found $html_count in $out_dir" >&2
  exit 1
fi
if [ "$json_count" -ne 2 ]; then
  echo "ERROR: expected 2 fastp JSON reports, found $json_count in $out_dir" >&2
  exit 1
fi

set +e
nextflow run "${harness_dir}/reject_single_end.nf" \
  -c "${harness_dir}/nextflow.config" \
  -work-dir "${work_dir}-reject" \
  -with-docker > "$reject_log_file" 2>&1
reject_status=$?
set -e

if [ "$reject_status" -eq 0 ]; then
  echo "ERROR: illumina_pe_q20 single-end rejection harness unexpectedly passed" >&2
  echo "Log: $reject_log_file" >&2
  exit 1
fi
if ! grep -F "requires paired-end input" "$reject_log_file" >/dev/null; then
  echo "ERROR: single-end rejection log did not contain the expected clear error" >&2
  echo "Log: $reject_log_file" >&2
  sed -n '1,220p' "$reject_log_file" >&2
  exit 1
fi

echo "fastp smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: $out_dir"
echo "Output files:"
find "$out_dir" -type f \( -name '*.trimmed.fastq.gz' -o -name '*.fastp.html' -o -name '*.fastp.json' \) | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
