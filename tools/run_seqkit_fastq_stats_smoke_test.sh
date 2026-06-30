#!/usr/bin/env bash
set -euo pipefail

IMAGE="survom/seqkit:2.10.1-dev"
DEFAULT_R1="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read1.fastq.gz"
DEFAULT_R2="/data/shared/vikash/mult-omics/testdatasets/test_data/human_chr22_rnaseq/fastq/HBR_Rep1_ERCC-Mix2_Build37-ErccTranscripts-chr22.read2.fastq.gz"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
r1=""
r2=""
out_dir="/tmp/survom-seqkit-smoke-test"

usage() {
  cat <<'USAGE'
Usage: tools/run_seqkit_fastq_stats_smoke_test.sh [--r1 FASTQ_GZ] [--r2 FASTQ_GZ] [--out-dir DIR]

Runs an optional local smoke test for common.qc.seqkit_fastq_stats using external
FASTQ files only. Outputs are written under --out-dir and are never copied into
repository fixtures.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --r1)
      r1="${2:-}"
      shift 2
      ;;
    --r2)
      r2="${2:-}"
      shift 2
      ;;
    --out-dir)
      out_dir="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$r1" && -r "$DEFAULT_R1" ]]; then
  r1="$DEFAULT_R1"
fi
if [[ -z "$r2" && -r "$DEFAULT_R2" ]]; then
  r2="$DEFAULT_R2"
fi

if [[ -z "$r1" || ! -r "$r1" ]]; then
  echo "ERROR: R1 FASTQ is missing or unreadable. Provide --r1 PATH." >&2
  exit 1
fi
if [[ -z "$r2" || ! -r "$r2" ]]; then
  echo "ERROR: R2 FASTQ is missing or unreadable. Provide --r2 PATH." >&2
  exit 1
fi
if [[ -z "$out_dir" ]]; then
  echo "ERROR: --out-dir must not be empty." >&2
  exit 1
fi

mkdir -p "$out_dir"
out_abs="$(cd "$out_dir" && pwd)"
fixtures_abs="$(cd "$repo_root/tests/fixtures" && pwd)"
case "$out_abs" in
  "$fixtures_abs"|"$fixtures_abs"/*)
    echo "ERROR: --out-dir must be outside tracked repository fixtures: $fixtures_abs" >&2
    exit 1
    ;;
esac

seqkit_tsv="$out_abs/smoke_seqkit_stats.tsv"
summary_json="$out_abs/smoke_summary.json"
summary_tsv="$out_abs/smoke_summary.normalized.tsv"

r1_dir="$(cd "$(dirname "$r1")" && pwd)"
r2_dir="$(cd "$(dirname "$r2")" && pwd)"
r1_base="$(basename "$r1")"
r2_base="$(basename "$r2")"

echo "Image: $IMAGE"
echo "SeqKit version: $(docker run --rm "$IMAGE" version)"
echo "R1: $r1"
echo "R2: $r2"
echo "Output directory: $out_abs"

if [[ "$r1_dir" == "$r2_dir" ]]; then
  docker run --rm -v "$r1_dir:/data:ro" "$IMAGE" stats --all --tabular "/data/$r1_base" "/data/$r2_base" > "$seqkit_tsv"
else
  docker run --rm \
    -v "$r1_dir:/r1:ro" \
    -v "$r2_dir:/r2:ro" \
    "$IMAGE" stats --all --tabular "/r1/$r1_base" "/r2/$r2_base" > "$seqkit_tsv"
fi

python "$repo_root/bin/common__qc__seqkit_fastq_stats.py" \
  --seqkit-tsv "$seqkit_tsv" \
  --json-out "$summary_json" \
  --tsv-out "$summary_tsv"

echo "SeqKit TSV: $seqkit_tsv"
echo "Summary JSON: $summary_json"
echo "Summary TSV: $summary_tsv"
echo "Summary:"
python - "$summary_json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for row in data["files"]:
    print(
        f"- {row['source_file']}: "
        f"num_seqs={row['num_seqs']} "
        f"min_len={row['min_len']} "
        f"avg_len={row['avg_len']} "
        f"max_len={row['max_len']}"
    )
PY
