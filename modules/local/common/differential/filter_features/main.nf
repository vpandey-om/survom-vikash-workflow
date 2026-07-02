nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_FILTER_FEATURES {
    tag "${meta.id}"

    input:
    tuple val(meta), path(feature_matrix)
    path feature_matrix_meta
    path filter_spec

    output:
    tuple val(meta), path("filtered_feature_matrix.tsv"), emit: filtered_matrix
    tuple val(meta), path("filter_report.json"), emit: filter_report

    script:
    """
    python ${projectDir}/bin/common__differential__filter_features.py \\
      --feature-matrix "${feature_matrix}" \\
      --feature-matrix-meta "${feature_matrix_meta}" \\
      --filter-spec "${filter_spec}" \\
      --out-filtered-feature-matrix filtered_feature_matrix.tsv \\
      --out-filter-report filter_report.json
    """
}
