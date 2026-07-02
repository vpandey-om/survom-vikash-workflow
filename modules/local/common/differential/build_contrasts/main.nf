nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_BUILD_CONTRASTS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(validated_design)
    path contrast_spec

    output:
    tuple val(meta), path("resolved_contrasts.json"), emit: resolved_contrasts
    tuple val(meta), path("contrast_validation_report.json"), emit: validation_report

    script:
    """
    python ${projectDir}/bin/common__differential__build_contrasts.py \\
      --validated-design "${validated_design}" \\
      --contrast-spec "${contrast_spec}" \\
      --out-resolved-contrasts resolved_contrasts.json \\
      --out-contrast-validation-report contrast_validation_report.json
    """
}
