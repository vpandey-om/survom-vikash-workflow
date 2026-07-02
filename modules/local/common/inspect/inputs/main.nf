nextflow.enable.dsl = 2

process SURVOM_COMMON_INSPECT_INPUTS {
    tag "${meta.id}"

    input:
    tuple val(meta), path(feature_matrix)
    path sample_metadata
    val feature_id_column
    val sample_id_column

    output:
    tuple val(meta), path("input_inspection.json"), emit: inspection

    script:
    """
    python ${projectDir}/bin/common__inspect__inputs.py \\
      --feature-matrix "${feature_matrix}" \\
      --sample-metadata "${sample_metadata}" \\
      --feature-id-column "${feature_id_column}" \\
      --sample-id-column "${sample_id_column}" \\
      --out-inspection input_inspection.json
    """
}
