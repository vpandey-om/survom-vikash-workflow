nextflow.enable.dsl = 2

process SURVOM_COMMON_AGGREGATE_SALMON_QUANTMERGE {
    tag "$merge_id"
    cpus 1

    input:
    tuple val(merge_id), path(quant_files)

    output:
    tuple val(merge_id), path("salmon_counts.tsv"), emit: counts

    script:
    def quants = quant_files instanceof List ? quant_files : [quant_files]
    if (quants.size() < 2) {
        error "common.aggregate.salmon_quantmerge requires two or more quant.sf files; received ${quants.size()}."
    }
    def setup_commands = quants.withIndex().collect { quant, index ->
        """
        mkdir -p quantmerge_inputs/sample_${index + 1}
        cp "${quant}" quantmerge_inputs/sample_${index + 1}/quant.sf
        """
    }.join("\n")
    def quant_dirs = (1..quants.size()).collect { "quantmerge_inputs/sample_${it}" }.join(" ")

    """
    ${setup_commands}

    salmon quantmerge \\
      --quants ${quant_dirs} \\
      --column NumReads \\
      --output salmon_counts.tsv
    """
}
