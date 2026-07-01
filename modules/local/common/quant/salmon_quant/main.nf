nextflow.enable.dsl = 2

process SURVOM_COMMON_QUANT_SALMON_QUANT {
    tag "$sample_id"
    cpus 2

    input:
    tuple val(sample_id), path(salmon_index), path(fastq_files)

    output:
    tuple val(sample_id), path("salmon_quant/quant.sf"), emit: quant
    tuple val(sample_id), path("salmon_quant/cmd_info.json"), emit: cmd_info
    tuple val(sample_id), path("salmon_quant/aux_info"), emit: aux_info
    tuple val(sample_id), path("salmon_quant/libParams"), emit: lib_params

    script:
    def reads = fastq_files instanceof List ? fastq_files : [fastq_files]
    def read_count = reads.size()
    def is_paired = read_count == 2
    if (!(read_count in [1, 2])) {
        error "common.quant.salmon_quant requires one single-end FASTQ or exactly two paired-end FASTQ files; received ${read_count} FASTQ files."
    }

    def read_args = is_paired
        ? "--mates1 ${reads[0]} --mates2 ${reads[1]}"
        : "--unmated ${reads[0]}"

    """
    salmon quant \\
      --index "${salmon_index}" \\
      --libType A \\
      ${read_args} \\
      --validateMappings \\
      --output salmon_quant
    """
}
