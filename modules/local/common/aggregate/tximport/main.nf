nextflow.enable.dsl = 2

process SURVOM_COMMON_AGGREGATE_TXIMPORT {
    tag "$aggregate_id"
    cpus 1

    input:
    tuple val(aggregate_id), path(samples_tsv), path(tx2gene_tsv)

    output:
    tuple val(aggregate_id), path("tximport/gene_counts.tsv"), emit: counts
    tuple val(aggregate_id), path("tximport/gene_abundance.tsv"), emit: abundance
    tuple val(aggregate_id), path("tximport/gene_lengths.tsv"), emit: lengths

    script:
    """
    Rscript ${moduleDir}/../../../../../bin/common__aggregate__tximport.R \\
      --samples "${samples_tsv}" \\
      --tx2gene "${tx2gene_tsv}" \\
      --outdir tximport
    """
}
