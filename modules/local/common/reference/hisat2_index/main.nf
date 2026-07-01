nextflow.enable.dsl = 2

process SURVOM_COMMON_REFERENCE_HISAT2_INDEX {
    tag "$reference_id"
    cpus 2

    input:
    tuple val(reference_id), path(genome_fasta), path(annotation_gtf)

    output:
    tuple val(reference_id), path("hisat2_index"), emit: index
    tuple val(reference_id), path("annotation.ss"), emit: splice_sites
    tuple val(reference_id), path("annotation.exon"), emit: exons

    script:
    def fasta_name = genome_fasta.getName()
    def gtf_name = annotation_gtf.getName()
    if (!(fasta_name ==~ /.+\.(fa|fasta)(\.gz)?$/)) {
        error "common.reference.hisat2_index requires genome FASTA ending in .fa, .fasta, .fa.gz, or .fasta.gz; received ${fasta_name}."
    }
    if (!(gtf_name ==~ /.+\.gtf$/)) {
        error "common.reference.hisat2_index requires GTF annotation ending in .gtf; received ${gtf_name}."
    }

    """
    mkdir -p hisat2_index

    hisat2_extract_splice_sites.py "${annotation_gtf}" > annotation.ss
    hisat2_extract_exons.py "${annotation_gtf}" > annotation.exon

    hisat2-build \\
      --ss annotation.ss \\
      --exon annotation.exon \\
      "${genome_fasta}" \\
      hisat2_index/reference
    """
}
