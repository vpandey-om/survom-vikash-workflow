nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_VALIDATE_DESIGN {
    tag "${meta.id}"

    input:
    tuple val(meta), path(feature_matrix)
    path feature_matrix_meta
    path sample_metadata
    path design_spec
    val minimum_group_size

    output:
    tuple val(meta), path("validated_design.json"), emit: validated_design
    tuple val(meta), path("design_validation_report.json"), emit: validation_report

    script:
    """
    python ${projectDir}/bin/common__differential__validate_design.py \\
      --feature-matrix "${feature_matrix}" \\
      --feature-matrix-meta "${feature_matrix_meta}" \\
      --sample-metadata "${sample_metadata}" \\
      --design-spec "${design_spec}" \\
      --minimum-group-size "${minimum_group_size}" \\
      --out-validated-design validated_design.json \\
      --out-design-validation-report design_validation_report.json
    """
}
