nextflow.enable.dsl = 2

process SURVOM_TRANSCRIPTOMICS_STATS_DESEQ2 {
    tag "${meta.id}"
    container "survom/deseq2:3.21-dev@sha256:fd8b92a1fb52e9c082fc648a18a5c6e35fe7c691b9db26456e97e54eb7ff9633"

    input:
    tuple val(meta), path(filtered_feature_matrix)
    path sample_metadata
    path validated_design
    path resolved_contrasts
    path deseq2_params

    output:
    tuple val(meta), path("deseq2_results.tsv"), emit: results
    tuple val(meta), path("deseq2_diagnostics.json"), emit: diagnostics
    tuple val(meta), path("deseq2_dds.rds"), optional: true, emit: dds_rds

    script:
    """
    cp ${projectDir}/bin/transcriptomics__stats__deseq2.R transcriptomics__stats__deseq2.R
    Rscript transcriptomics__stats__deseq2.R \\
      --filtered-feature-matrix "${filtered_feature_matrix}" \\
      --sample-metadata "${sample_metadata}" \\
      --validated-design "${validated_design}" \\
      --resolved-contrasts "${resolved_contrasts}" \\
      --deseq2-params "${deseq2_params}" \\
      --out-results deseq2_results.tsv \\
      --out-diagnostics deseq2_diagnostics.json \\
      --out-dds-rds deseq2_dds.rds
    """
}
