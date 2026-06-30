nextflow.enable.dsl = 2

process SURVOM_COMMON_QC_SEQKIT_FASTQ_STATS {
    tag "$sample_id"

    input:
    tuple val(sample_id), path(reads)

    output:
    path "${sample_id}.seqkit_stats.tsv", emit: seqkit_stats
    path "${sample_id}.seqkit_summary.json", emit: json_summary
    path "${sample_id}.seqkit_summary.normalized.tsv", emit: tsv_summary

    script:
    """
    seqkit stats --all --tabular ${reads} > ${sample_id}.seqkit_stats.tsv
    python ${projectDir}/bin/common__qc__seqkit_fastq_stats.py \\
      --seqkit-tsv ${sample_id}.seqkit_stats.tsv \\
      --json-out ${sample_id}.seqkit_summary.json \\
      --tsv-out ${sample_id}.seqkit_summary.normalized.tsv
    """
}
