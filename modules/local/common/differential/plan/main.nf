nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_PLAN {
    tag "${meta.id}"

    input:
    tuple val(meta), path(analysis_request)
    path input_inspection

    output:
    tuple val(meta), path("feature_matrix.meta.json"), emit: feature_matrix_meta
    tuple val(meta), path("design_spec.json"), emit: design_spec
    tuple val(meta), path("contrast_spec.json"), emit: contrast_spec
    tuple val(meta), path("analysis_plan.json"), emit: analysis_plan

    script:
    """
    python ${projectDir}/bin/common__differential__plan.py \\
      --analysis-request "${analysis_request}" \\
      --input-inspection "${input_inspection}" \\
      --out-feature-matrix-meta feature_matrix.meta.json \\
      --out-design-spec design_spec.json \\
      --out-contrast-spec contrast_spec.json \\
      --out-analysis-plan analysis_plan.json
    """
}
