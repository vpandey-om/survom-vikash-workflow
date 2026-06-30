nextflow.enable.dsl = 2

process SURVOM_COMMON_QC_FASTQC {
    tag "$sample_id"
    cpus 2

    input:
    tuple val(sample_id), path(fastq_files)

    output:
    path "fastqc/*_fastqc.html", emit: html
    path "fastqc/*_fastqc.zip", emit: zip

    script:
    """
    mkdir -p fastqc
    fastqc \\
      --threads "${task.cpus}" \\
      --outdir fastqc \\
      --quiet \\
      ${fastq_files}
    """
}
