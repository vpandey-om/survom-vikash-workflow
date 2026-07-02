nextflow.enable.dsl = 2

process SURVOM_COMMON_PATHWAY_COMBINE_RESULTS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(enrichment_results)
    path combine_params

    output:
    tuple val(meta), path("combined_pathway_results.tsv"), emit: combined_results
    tuple val(meta), path("combined_pathway_diagnostics.json"), emit: combined_diagnostics

    script:
    """
    python ${projectDir}/bin/common__pathway__combine_results.py \\
      --enrichment-results "${enrichment_results.join(',')}" \\
      --combine-params "${combine_params}" \\
      --out-combined-results combined_pathway_results.tsv \\
      --out-combined-diagnostics combined_pathway_diagnostics.json
    """
}
