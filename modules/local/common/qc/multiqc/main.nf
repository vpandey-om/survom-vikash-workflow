nextflow.enable.dsl = 2

process SURVOM_COMMON_QC_MULTIQC {
    tag "$sample_id"
    cpus 1

    input:
    tuple val(sample_id), path(fastqc_reports_dir)

    output:
    path "multiqc/multiqc_report.html", emit: report
    path "multiqc/multiqc_data", emit: data

    script:
    """
    if ! find -L "${fastqc_reports_dir}" -maxdepth 1 -type f \\( -name '*_fastqc.html' -o -name '*_fastqc.zip' \\) | grep -q .; then
      echo "ERROR: no FastQC HTML or ZIP reports found in declared input directory: ${fastqc_reports_dir}" >&2
      exit 1
    fi

    multiqc \\
      --outdir multiqc \\
      --filename multiqc_report.html \\
      --data-dir \\
      "${fastqc_reports_dir}"

    if [ ! -d multiqc/multiqc_report_data ]; then
      echo "ERROR: expected MultiQC data directory was not created: multiqc/multiqc_report_data" >&2
      exit 1
    fi
    mv multiqc/multiqc_report_data multiqc/multiqc_data
    """
}
