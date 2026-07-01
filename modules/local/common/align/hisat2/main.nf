nextflow.enable.dsl = 2

process SURVOM_COMMON_ALIGN_HISAT2 {
    tag "$sample_id"
    cpus 2

    input:
    tuple val(sample_id), path(reads), path(hisat2_index)

    output:
    tuple val(sample_id), path("${sample_id}.sorted.bam"), emit: bam
    tuple val(sample_id), path("${sample_id}.sorted.bam.bai"), emit: bai
    tuple val(sample_id), path("hisat2_alignment_summary.txt"), emit: summary

    script:
    def fastq_files = reads instanceof List ? reads : [reads]
    if (fastq_files.size() != 2) {
        error "common.align.hisat2 requires exactly two paired-end FASTQ files; received ${fastq_files.size()}."
    }

    """
    hisat2 \\
      -x "${hisat2_index}/reference" \\
      -1 "${fastq_files[0]}" \\
      -2 "${fastq_files[1]}" \\
      --dta \\
      -p "${task.cpus}" \\
      --summary-file hisat2_alignment_summary.txt \\
    | samtools sort \\
        -@ "${task.cpus}" \\
        -o ${sample_id}.sorted.bam

    samtools index ${sample_id}.sorted.bam
    """
}
