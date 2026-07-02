nextflow.enable.dsl = 2

process SURVOM_COMMON_PATHWAY_OVERREPRESENTATION {
    tag "${meta.id}"

    input:
    tuple val(meta), path(resolved_identifiers)
    path resolved_background_universe
    path validated_gene_sets
    path validated_manifest
    path overrepresentation_params

    output:
    tuple val(meta), path("enrichment_results.tsv"), emit: enrichment_results
    tuple val(meta), path("overrepresentation_report.json"), emit: overrepresentation_report

    script:
    """
    python ${projectDir}/bin/common__pathway__overrepresentation.py \\
      --resolved-identifiers "${resolved_identifiers}" \\
      --resolved-background-universe "${resolved_background_universe}" \\
      --validated-gene-sets "${validated_gene_sets}" \\
      --validated-manifest "${validated_manifest}" \\
      --overrepresentation-params "${overrepresentation_params}" \\
      --out-enrichment-results enrichment_results.tsv \\
      --out-overrepresentation-report overrepresentation_report.json
    """
}
