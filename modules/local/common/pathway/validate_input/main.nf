nextflow.enable.dsl = 2

process SURVOM_COMMON_PATHWAY_VALIDATE_INPUT {
    tag "${meta.id}"

    input:
    tuple val(meta), path(enrichment_input)
    path background_universe
    path validation_params

    output:
    tuple val(meta), path("validated_enrichment_input.tsv"), emit: validated_enrichment_input
    tuple val(meta), path("validated_background_universe.tsv"), emit: validated_background_universe
    tuple val(meta), path("validation_report.json"), emit: validation_report

    script:
    """
    python ${projectDir}/bin/common__pathway__validate_input.py \\
      --enrichment-input "${enrichment_input}" \\
      --background-universe "${background_universe}" \\
      --validation-params "${validation_params}" \\
      --out-validated-enrichment-input validated_enrichment_input.tsv \\
      --out-validated-background-universe validated_background_universe.tsv \\
      --out-validation-report validation_report.json
    """
}
