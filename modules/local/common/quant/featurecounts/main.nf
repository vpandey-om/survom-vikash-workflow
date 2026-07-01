nextflow.enable.dsl = 2

process SURVOM_COMMON_QUANT_FEATURECOUNTS {
    tag "$sample_id"
    cpus 2

    input:
    tuple val(sample_id), path(sorted_bam), path(bam_index), path(annotation_gtf)

    output:
    tuple val(sample_id), path("gene_counts.tsv"), emit: counts
    tuple val(sample_id), path("gene_counts.tsv.summary"), emit: summary

    script:
    def bam_name = sorted_bam.getName()
    def bai_name = bam_index.getName()
    def gtf_name = annotation_gtf.getName()
    if (!(bam_name ==~ /.+\.bam$/)) {
        error "common.quant.featurecounts requires a sorted BAM input ending in .bam; received ${bam_name}."
    }
    if (!(bai_name ==~ /.+\.(bam\.bai|bai)$/)) {
        error "common.quant.featurecounts requires a BAM index ending in .bam.bai or .bai; received ${bai_name}."
    }
    if (!(gtf_name ==~ /.+\.gtf$/)) {
        error "common.quant.featurecounts requires a GTF annotation ending in .gtf; received ${gtf_name}."
    }

    """
    featureCounts \\
      -a "${annotation_gtf}" \\
      -o gene_counts.tsv \\
      -T "${task.cpus}" \\
      -p \\
      -t exon \\
      -g gene_id \\
      "${sorted_bam}"
    """
}
