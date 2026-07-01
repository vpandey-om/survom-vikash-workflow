nextflow.enable.dsl = 2

process SURVOM_COMMON_PREPROCESS_FASTP {
    tag "$sample_id"
    cpus 2

    input:
    tuple val(sample_id), path(fastq_files), val(trimming_profile)

    output:
    tuple val(sample_id), path("fastp/${sample_id}_trimmed.fastq.gz"), emit: single_trimmed, optional: true
    tuple val(sample_id), path("fastp/${sample_id}_R1.trimmed.fastq.gz"), path("fastp/${sample_id}_R2.trimmed.fastq.gz"), emit: paired_trimmed, optional: true
    path "fastp/${sample_id}.fastp.html", emit: html
    path "fastp/${sample_id}.fastp.json", emit: json

    script:
    def reads = fastq_files instanceof List ? fastq_files : [fastq_files]
    def read_count = reads.size()
    def is_paired = read_count == 2
    if (!(trimming_profile in ["default", "illumina_pe_q20"])) {
        error "Unsupported fastp trimming_profile '${trimming_profile}'. Supported profiles: default, illumina_pe_q20."
    }
    if (trimming_profile == "illumina_pe_q20" && !is_paired) {
        error "fastp trimming_profile 'illumina_pe_q20' requires paired-end input with exactly two FASTQ files."
    }
    if (!(read_count in [1, 2])) {
        error "common.preprocess.fastp requires single-end or paired-end input; received ${read_count} FASTQ files."
    }

    def input_args = is_paired
        ? "--in1 ${reads[0]} --in2 ${reads[1]}"
        : "--in1 ${reads[0]}"
    def output_args = is_paired
        ? "--out1 fastp/${sample_id}_R1.trimmed.fastq.gz --out2 fastp/${sample_id}_R2.trimmed.fastq.gz"
        : "--out1 fastp/${sample_id}_trimmed.fastq.gz"
    def profile_args = ""
    if (is_paired && trimming_profile == "default") {
        profile_args = "--detect_adapter_for_pe"
    } else if (trimming_profile == "illumina_pe_q20") {
        profile_args = "--detect_adapter_for_pe --cut_tail --cut_window_size 4 --cut_mean_quality 20 --length_required 30"
    }

    """
    mkdir -p fastp
    fastp \\
      --thread "${task.cpus}" \\
      ${input_args} \\
      ${output_args} \\
      --html fastp/${sample_id}.fastp.html \\
      --json fastp/${sample_id}.fastp.json \\
      ${profile_args}
    """
}
