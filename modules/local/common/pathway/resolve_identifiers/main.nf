nextflow.enable.dsl = 2

process SURVOM_COMMON_PATHWAY_RESOLVE_IDENTIFIERS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(validated_enrichment_input)
    path validated_background_universe
    path identifier_mapping
    path resolution_params

    output:
    tuple val(meta), path("resolved_identifiers.tsv"), emit: resolved_identifiers
    tuple val(meta), path("resolved_background_universe.tsv"), emit: resolved_background_universe
    tuple val(meta), path("resolution_report.json"), emit: resolution_report

    script:
    """
    python ${projectDir}/bin/common__pathway__resolve_identifiers.py \\
      --validated-enrichment-input "${validated_enrichment_input}" \\
      --validated-background-universe "${validated_background_universe}" \\
      --identifier-mapping "${identifier_mapping}" \\
      --resolution-params "${resolution_params}" \\
      --out-resolved-identifiers resolved_identifiers.tsv \\
      --out-resolved-background-universe resolved_background_universe.tsv \\
      --out-resolution-report resolution_report.json
    """
}
