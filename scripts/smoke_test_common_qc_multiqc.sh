#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.qc.multiqc atomic step.
#
# Usage:
#   scripts/smoke_test_common_qc_multiqc.sh [FASTQC_REPORT_DIR] [--cleanup]
#   scripts/smoke_test_common_qc_multiqc.sh --cleanup
#
# If FASTQC_REPORT_DIR is supplied, it must contain FastQC *_fastqc.html and/or
# *_fastqc.zip reports. If it is not supplied, this script runs the local
# FastQC smoke-test script first when available and uses its output directory.
# Temporary outputs are kept by default for inspection. With --cleanup, only the
# current MultiQC run directory is removed after a successful run.

set -euo pipefail

cleanup=false
fastqc_report_dir=""

for arg in "$@"; do
  case "$arg" in
    --cleanup)
      cleanup=true
      ;;
    -h|--help)
      sed -n '2,11p' "$0"
      exit 0
      ;;
    --*)
      echo "ERROR: unknown argument: $arg" >&2
      exit 2
      ;;
    *)
      if [ -n "$fastqc_report_dir" ]; then
        echo "ERROR: expected at most one FASTQC_REPORT_DIR argument" >&2
        exit 2
      fi
      fastqc_report_dir="$arg"
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
module_file="${repo_root}/modules/local/common/qc/multiqc/main.nf"
fastqc_smoke_script="${script_dir}/smoke_test_common_qc_fastqc.sh"
image="survom/multiqc:1.35-dev"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$module_file" ] || { echo "ERROR: MultiQC module is missing: $module_file" >&2; exit 1; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "ERROR: required local Docker image is missing: $image" >&2; exit 1; }

if [ -z "$fastqc_report_dir" ]; then
  if [ ! -x "$fastqc_smoke_script" ]; then
    echo "ERROR: FASTQC_REPORT_DIR was not supplied and FastQC smoke script is unavailable: $fastqc_smoke_script" >&2
    echo "Run FastQC first and pass its output fastqc directory, for example:" >&2
    echo "  $0 /tmp/survom-fastqc-smoke/<run>/out/fastqc" >&2
    exit 1
  fi
  fastqc_log="$(mktemp /tmp/survom-fastqc-smoke-for-multiqc.XXXXXX.log)"
  "$fastqc_smoke_script" > "$fastqc_log"
  fastqc_output_dir="$(sed -n 's/^Output directory: //p' "$fastqc_log" | tail -1)"
  if [ -z "$fastqc_output_dir" ]; then
    echo "ERROR: could not determine FastQC smoke output directory from log: $fastqc_log" >&2
    exit 1
  fi
  fastqc_report_dir="${fastqc_output_dir}/fastqc"
fi

[ -d "$fastqc_report_dir" ] || { echo "ERROR: FastQC report directory is missing: $fastqc_report_dir" >&2; exit 1; }
if ! find -L "$fastqc_report_dir" -maxdepth 1 -type f \( -name '*_fastqc.html' -o -name '*_fastqc.zip' \) | grep -q .; then
  echo "ERROR: FastQC report directory contains no *_fastqc.html or *_fastqc.zip files: $fastqc_report_dir" >&2
  exit 1
fi

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-multiqc-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
out_dir="${run_dir}/out"
log_file="${run_dir}/nextflow.log"
mkdir -p "$harness_dir" "$work_dir" "$out_dir"

cat > "${harness_dir}/main.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_QC_MULTIQC } from '${module_file}'

workflow {
    reports = Channel.of(
        tuple(
            'fastqc_reports',
            file('${fastqc_report_dir}')
        )
    )

    SURVOM_COMMON_QC_MULTIQC(reports)

    SURVOM_COMMON_QC_MULTIQC.out.report.view { "REPORT \${it.name}" }
    SURVOM_COMMON_QC_MULTIQC.out.data.view { "DATA \${it.name}" }
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
  echo "ERROR: Nextflow MultiQC smoke test failed with exit status $nextflow_status" >&2
  echo "Log: $log_file" >&2
  sed -n '1,220p' "$log_file" >&2
  exit "$nextflow_status"
fi

report_path="${out_dir}/multiqc/multiqc_report.html"
data_dir="${out_dir}/multiqc/multiqc_data"
[ -f "$report_path" ] || { echo "ERROR: missing MultiQC report: $report_path" >&2; exit 1; }
[ -d "$data_dir" ] || { echo "ERROR: missing MultiQC data directory: $data_dir" >&2; exit 1; }

echo "MultiQC smoke test passed."
echo "Run directory: $run_dir"
echo "FastQC report directory: $fastqc_report_dir"
echo "Output directory: ${out_dir}/multiqc"
echo "Output files:"
find "${out_dir}/multiqc" -maxdepth 2 \( -type f -o -type d \) | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
