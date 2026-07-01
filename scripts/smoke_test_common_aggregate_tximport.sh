#!/usr/bin/env bash
# Manual smoke test for the SurvOm common.aggregate.tximport atomic step.
#
# Usage:
#   scripts/smoke_test_common_aggregate_tximport.sh
#   scripts/smoke_test_common_aggregate_tximport.sh --cleanup

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
salmon_module="${repo_root}/modules/local/common/quant/salmon_quant/main.nf"
tximport_module="${repo_root}/modules/local/common/aggregate/tximport/main.nf"
salmon_image="combinelab/salmon:1.10.3"
tximport_image="survom/tximport:3.21-dev"

dataset_root="${repo_root}/../mult-omics/testdatasets/test_data/human_chr22_rnaseq"
transcripts="${dataset_root}/refs/chr22_with_ERCC92.transcripts.fa"
tx2gene="${dataset_root}/refs/chr22_with_ERCC92.tx2gene.tsv"
hbr_r1="${dataset_root}/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read1.fastq.gz"
hbr_r2="${dataset_root}/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read2.fastq.gz"
uhr_r1="${dataset_root}/fastq/UHR_Rep1_ERCC-Mix1_Build37-ErccTranscripts-chr22.read1.fastq.gz"
uhr_r2="${dataset_root}/fastq/UHR_Rep1_ERCC-Mix1_Build37-ErccTranscripts-chr22.read2.fastq.gz"

command -v nextflow >/dev/null 2>&1 || { echo "ERROR: nextflow is not available on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available on PATH" >&2; exit 1; }
[ -f "$salmon_module" ] || { echo "ERROR: Salmon quant module is missing: $salmon_module" >&2; exit 1; }
[ -f "$tximport_module" ] || { echo "ERROR: tximport module is missing: $tximport_module" >&2; exit 1; }
for required in "$transcripts" "$tx2gene" "$hbr_r1" "$hbr_r2" "$uhr_r1" "$uhr_r2"; do
  [ -r "$required" ] || { echo "ERROR: required smoke-test input is missing or unreadable: $required" >&2; exit 1; }
done
docker image inspect "$salmon_image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $salmon_image" >&2; exit 1; }
docker image inspect "$tximport_image" >/dev/null 2>&1 || { echo "ERROR: required Docker image is missing: $tximport_image" >&2; exit 1; }

timestamp="$(date +%Y%m%dT%H%M%S)-$$"
run_dir="/tmp/survom-tximport-smoke/${timestamp}"
harness_dir="${run_dir}/harness"
work_dir="${run_dir}/work"
index_dir="${run_dir}/salmon_index"
hbr_out_dir="${run_dir}/quant/HBR_Rep1"
uhr_out_dir="${run_dir}/quant/UHR_Rep1"
tximport_out_dir="${run_dir}/tximport_out"
mkdir -p "$harness_dir" "$work_dir" "$hbr_out_dir" "$uhr_out_dir" "$tximport_out_dir"

docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$(dirname "$transcripts"):/refs:ro" \
  -v "${run_dir}:/work" \
  -w /work \
  "$salmon_image" \
  salmon index --transcripts "/refs/$(basename "$transcripts")" --index salmon_index --threads 2 >/dev/null 2>&1

run_salmon_quant() {
  local sample_id="$1"
  local r1="$2"
  local r2="$3"
  local out_dir="$4"
  local harness="${harness_dir}/${sample_id}.salmon_quant.nf"
  local config="${harness_dir}/${sample_id}.salmon_quant.config"
  local log_file="${run_dir}/${sample_id}.salmon_quant.log"

  cat > "$harness" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_QUANT_SALMON_QUANT } from '${salmon_module}'

workflow {
    reads = Channel.of(tuple('${sample_id}', file('${index_dir}'), [file('${r1}'), file('${r2}')]))
    SURVOM_COMMON_QUANT_SALMON_QUANT(reads)
    SURVOM_COMMON_QUANT_SALMON_QUANT.out.quant.view { "QUANT \${it[0]} \${it[1].name}" }
}
NF

  cat > "$config" <<NF
process.container = '${salmon_image}'
process.publishDir = [ path: '${out_dir}', mode: 'copy' ]
docker.enabled = true
docker.runOptions = '-u $(id -u):$(id -g)'
NF

  set +e
  nextflow run "$harness" \
    -c "$config" \
    -work-dir "$work_dir" \
    -with-docker > "$log_file" 2>&1
  local nextflow_status=$?
  set -e

  if [ "$nextflow_status" -ne 0 ]; then
    echo "ERROR: Salmon quant smoke prerequisite failed for ${sample_id} with exit status $nextflow_status" >&2
    echo "Log: $log_file" >&2
    sed -n '1,220p' "$log_file" >&2
    exit "$nextflow_status"
  fi
  [ -f "${out_dir}/salmon_quant/quant.sf" ] || { echo "ERROR: missing quant.sf for ${sample_id}" >&2; exit 1; }
}

run_salmon_quant "HBR_Rep1" "$hbr_r1" "$hbr_r2" "$hbr_out_dir"
run_salmon_quant "UHR_Rep1" "$uhr_r1" "$uhr_r2" "$uhr_out_dir"

samples_tsv="${run_dir}/samples.tsv"
cat > "$samples_tsv" <<TSV
sample_id	quant_sf
HBR_Rep1	${hbr_out_dir}/salmon_quant/quant.sf
UHR_Rep1	${uhr_out_dir}/salmon_quant/quant.sf
TSV

cat > "${harness_dir}/tximport.nf" <<NF
nextflow.enable.dsl = 2

include { SURVOM_COMMON_AGGREGATE_TXIMPORT } from '${tximport_module}'

workflow {
    inputs = Channel.of(tuple('HBR_UHR_chr22', file('${samples_tsv}'), file('${tx2gene}')))
    SURVOM_COMMON_AGGREGATE_TXIMPORT(inputs)
    SURVOM_COMMON_AGGREGATE_TXIMPORT.out.counts.view { "COUNTS \${it[1].name}" }
}
NF

cat > "${harness_dir}/tximport.config" <<NF
process.container = '${tximport_image}'
process.publishDir = [ path: '${tximport_out_dir}', mode: 'copy' ]
docker.enabled = true
docker.runOptions = '-u $(id -u):$(id -g) -v ${repo_root}:${repo_root}:ro -v ${run_dir}:${run_dir}'
NF

tximport_log="${run_dir}/tximport.nextflow.log"
set +e
nextflow run "${harness_dir}/tximport.nf" \
  -c "${harness_dir}/tximport.config" \
  -work-dir "$work_dir" \
  -with-docker > "$tximport_log" 2>&1
tximport_status=$?
set -e

if [ "$tximport_status" -ne 0 ]; then
  echo "ERROR: Nextflow tximport smoke test failed with exit status $tximport_status" >&2
  echo "Log: $tximport_log" >&2
  sed -n '1,220p' "$tximport_log" >&2
  exit "$tximport_status"
fi

for output in gene_counts.tsv gene_abundance.tsv gene_lengths.tsv; do
  output_path="${tximport_out_dir}/tximport/${output}"
  [ -f "$output_path" ] || { echo "ERROR: missing tximport output: $output_path" >&2; exit 1; }
  header="$(head -n 1 "$output_path")"
  case "$header" in
    *HBR_Rep1*UHR_Rep1*) ;;
    *) echo "ERROR: ${output} header does not contain HBR_Rep1 and UHR_Rep1: $header" >&2; exit 1 ;;
  esac
done

echo "tximport smoke test passed."
echo "Run directory: $run_dir"
echo "Output directory: ${tximport_out_dir}/tximport"
find "${tximport_out_dir}/tximport" -maxdepth 1 -type f -name 'gene_*.tsv' | sort

if [ "$cleanup" = true ]; then
  rm -rf "$run_dir"
  echo "Cleaned up run directory: $run_dir"
fi
