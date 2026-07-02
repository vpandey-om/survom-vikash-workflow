nextflow.enable.dsl = 2

process SURVOM_COMMON_PATHWAY_VALIDATE_GENE_SETS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(gene_set_manifest)
    path gene_set_file
    path validation_params

    output:
    tuple val(meta), path("validated_gene_sets.gmt"), emit: validated_gene_sets
    tuple val(meta), path("validated_gene_set_manifest.json"), emit: validated_manifest
    tuple val(meta), path("gene_set_validation_report.json"), emit: validation_report

    script:
    """
    python ${projectDir}/bin/common__pathway__validate_gene_sets.py \\
      --gene-set-manifest "${gene_set_manifest}" \\
      --gene-set-file "${gene_set_file}" \\
      --validation-params "${validation_params}" \\
      --out-validated-gene-sets validated_gene_sets.gmt \\
      --out-validated-manifest validated_gene_set_manifest.json \\
      --out-validation-report gene_set_validation_report.json
    """
}
