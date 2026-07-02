nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_QC_DIAGNOSTICS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(filtered_feature_matrix)
    path sample_metadata
    path combined_results
    path combined_diagnostics
    path qc_params

    output:
    tuple val(meta), path("qc_report.html"), emit: qc_report
    tuple val(meta), path("qc_diagnostics.json"), emit: qc_diagnostics
    tuple val(meta), path("qc_assets"), emit: qc_assets

    script:
    """
    python ${projectDir}/bin/common__differential__qc_diagnostics.py \\
      --filtered-feature-matrix "${filtered_feature_matrix}" \\
      --sample-metadata "${sample_metadata}" \\
      --combined-results "${combined_results}" \\
      --combined-diagnostics "${combined_diagnostics}" \\
      --qc-params "${qc_params}" \\
      --out-qc-report qc_report.html \\
      --out-qc-diagnostics qc_diagnostics.json \\
      --out-qc-assets qc_assets
    """
}
