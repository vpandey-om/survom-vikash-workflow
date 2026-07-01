nextflow.enable.dsl = 2

process SURVOM_COMMON_REFERENCE_SALMON_INDEX {
    tag "$reference_id"
    cpus 2

    input:
    tuple val(reference_id), path(transcript_fasta)

    output:
    tuple val(reference_id), path("salmon_index"), emit: index

    script:
    def fasta_name = transcript_fasta.getName()
    if (!(fasta_name ==~ /.+\.(fa|fasta)(\.gz)?$/)) {
        error "common.reference.salmon_index requires transcript_fasta ending in .fa, .fasta, .fa.gz, or .fasta.gz; received ${fasta_name}."
    }

    """
    salmon index \\
      --transcripts "${transcript_fasta}" \\
      --index salmon_index \\
      --threads "${task.cpus}"
    """
}
