nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_REPORT {
    tag "${meta.id}"

    input:
    tuple val(meta), path(analysis_plan)
    path design_validation_report
    path filter_report
    path combined_results
    path combined_diagnostics
    path qc_report
    path report_params

    output:
    tuple val(meta), path("differential_analysis_report.html"), emit: differential_analysis_report
    tuple val(meta), path("significant_features.tsv"), emit: significant_features
    tuple val(meta), path("upregulated_features.tsv"), emit: upregulated_features
    tuple val(meta), path("downregulated_features.tsv"), emit: downregulated_features
    tuple val(meta), path("analysis_manifest.json"), emit: analysis_manifest

    script:
    """
    python ${projectDir}/bin/common__differential__report.py \\
      --analysis-plan "${analysis_plan}" \\
      --design-validation-report "${design_validation_report}" \\
      --filter-report "${filter_report}" \\
      --combined-results "${combined_results}" \\
      --combined-diagnostics "${combined_diagnostics}" \\
      --qc-report "${qc_report}" \\
      --report-params "${report_params}" \\
      --out-report differential_analysis_report.html \\
      --out-significant-features significant_features.tsv \\
      --out-upregulated-features upregulated_features.tsv \\
      --out-downregulated-features downregulated_features.tsv \\
      --out-analysis-manifest analysis_manifest.json
    """
}
