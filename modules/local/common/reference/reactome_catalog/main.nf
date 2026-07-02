nextflow.enable.dsl = 2

process SURVOM_COMMON_REFERENCE_REACTOME_CATALOG {
    tag "${meta.id}"

    input:
    tuple val(meta), path(mapping_file)
    val release_version
    val organism
    val mapping_kind
    val source_identifier_namespace

    output:
    tuple val(meta), path("reactome_mapping_catalog.parquet"), emit: catalog
    tuple val(meta), path("reactome_catalog_manifest.yaml"), emit: manifest
    tuple val(meta), path("reactome_catalog_diagnostics.json"), emit: diagnostics

    script:
    """
    python ${projectDir}/bin/common__reference__reactome_catalog.py \\
      --mapping-file "${mapping_file}" \\
      --release-version "${release_version}" \\
      --organism "${organism}" \\
      --mapping-kind "${mapping_kind}" \\
      --source-identifier-namespace "${source_identifier_namespace}" \\
      --out-parquet reactome_mapping_catalog.parquet \\
      --out-manifest reactome_catalog_manifest.yaml \\
      --out-diagnostics reactome_catalog_diagnostics.json
    """
}
