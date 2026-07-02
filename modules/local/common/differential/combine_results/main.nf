nextflow.enable.dsl = 2

process SURVOM_COMMON_DIFFERENTIAL_COMBINE_RESULTS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(result_tables)
    path diagnostics

    output:
    tuple val(meta), path("combined_results.tsv"), emit: combined_results
    tuple val(meta), path("combined_diagnostics.json"), emit: combined_diagnostics

    script:
    def result_arg = result_tables instanceof List ? result_tables.join(",") : result_tables.toString()
    def diagnostics_arg = diagnostics instanceof List ? diagnostics.join(",") : diagnostics.toString()
    """
    python ${projectDir}/bin/common__differential__combine_results.py \\
      --result-tables "${result_arg}" \\
      --diagnostics "${diagnostics_arg}" \\
      --out-combined-results combined_results.tsv \\
      --out-combined-diagnostics combined_diagnostics.json
    """
}
