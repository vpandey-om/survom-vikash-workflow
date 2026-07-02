nextflow.enable.dsl = 2

process SURVOM_COMMON_PATHWAY_QC_DIAGNOSTICS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(combined_results)
    path combined_diagnostics
    path resolution_reports
    path gene_set_validation_reports
    path qc_params

    output:
    tuple val(meta), path("pathway_qc_diagnostics.json"), emit: qc_diagnostics
    tuple val(meta), path("pathway_qc_summary.tsv"), emit: qc_summary

    script:
    """
    python ${projectDir}/bin/common__pathway__qc_diagnostics.py \\
      --combined-results "${combined_results}" \\
      --combined-diagnostics "${combined_diagnostics}" \\
      --resolution-reports "${resolution_reports.join(',')}" \\
      --gene-set-validation-reports "${gene_set_validation_reports.join(',')}" \\
      --qc-params "${qc_params}" \\
      --out-qc-diagnostics pathway_qc_diagnostics.json \\
      --out-qc-summary pathway_qc_summary.tsv
    """
}
