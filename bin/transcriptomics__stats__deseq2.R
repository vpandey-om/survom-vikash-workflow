#!/usr/bin/env Rscript

usage <- function(status = 0) {
  cat(
    paste(
      "Usage: transcriptomics__stats__deseq2.R",
      "--filtered-feature-matrix PATH",
      "--sample-metadata PATH",
      "--validated-design PATH",
      "--resolved-contrasts PATH",
      "--deseq2-params PATH",
      "--out-results PATH",
      "--out-diagnostics PATH",
      "[--out-dds-rds PATH]",
      "\n\nRun DESeq2 Wald tests for transcriptomics raw-count data.\n"
    )
  )
  quit(save = "no", status = status)
}

parse_args <- function(argv) {
  if (length(argv) == 1 && argv[[1]] %in% c("-h", "--help")) {
    usage(0)
  }
  args <- list()
  i <- 1
  while (i <= length(argv)) {
    key <- argv[[i]]
    if (!startsWith(key, "--")) {
      stop(sprintf("Unexpected argument: %s", key), call. = FALSE)
    }
    if (i == length(argv)) {
      stop(sprintf("Missing value for argument: %s", key), call. = FALSE)
    }
    args[[substring(key, 3)]] <- argv[[i + 1]]
    i <- i + 2
  }
  required <- c(
    "filtered-feature-matrix",
    "sample-metadata",
    "validated-design",
    "resolved-contrasts",
    "deseq2-params",
    "out-results",
    "out-diagnostics"
  )
  missing <- setdiff(required, names(args))
  if (length(missing) > 0) {
    stop(sprintf("Missing required argument(s): %s", paste(missing, collapse = ", ")), call. = FALSE)
  }
  args
}

fail <- function(message, diagnostics_path = NULL) {
  if (!is.null(diagnostics_path)) {
    payload <- list(
      schema_version = 1,
      status = "failed",
      method = "deseq2",
      errors = list(message),
      warnings = list()
    )
    try(jsonlite::write_json(payload, diagnostics_path, pretty = TRUE, auto_unbox = TRUE), silent = TRUE)
  }
  stop(message, call. = FALSE)
}

require_namespace <- function(package) {
  if (!requireNamespace(package, quietly = TRUE)) {
    stop(
      sprintf(
        "Required R package '%s' is not installed. Install '%s' in the R environment used by this step.",
        package,
        package
      ),
      call. = FALSE
    )
  }
}

read_json <- function(path, label) {
  if (!file.exists(path)) {
    stop(sprintf("Missing %s: %s", label, path), call. = FALSE)
  }
  jsonlite::read_json(path, simplifyVector = FALSE)
}

required_param <- function(params, name) {
  if (is.null(params[[name]])) {
    stop(sprintf("Missing required DESeq2 parameter: %s", name), call. = FALSE)
  }
  params[[name]]
}

validate_counts <- function(count_table, feature_id_column) {
  if (!(feature_id_column %in% colnames(count_table))) {
    stop(sprintf("Feature ID column '%s' is missing from filtered feature matrix.", feature_id_column), call. = FALSE)
  }
  feature_ids <- count_table[[feature_id_column]]
  if (anyDuplicated(feature_ids)) {
    duplicates <- unique(feature_ids[duplicated(feature_ids)])
    stop(sprintf("Feature IDs must be unique. Duplicates: %s", paste(duplicates, collapse = ", ")), call. = FALSE)
  }
  count_columns <- setdiff(colnames(count_table), feature_id_column)
  counts <- as.matrix(count_table[, count_columns, drop = FALSE])
  suppressWarnings(mode(counts) <- "numeric")
  if (any(is.na(counts))) {
    stop("Filtered feature matrix contains non-numeric or missing count values.", call. = FALSE)
  }
  if (any(counts < 0)) {
    stop("Filtered feature matrix contains negative counts; DESeq2 requires non-negative raw counts.", call. = FALSE)
  }
  if (any(abs(counts - round(counts)) > 1e-9)) {
    stop("Filtered feature matrix contains non-integer counts; DESeq2 requires raw integer counts.", call. = FALSE)
  }
  storage.mode(counts) <- "integer"
  rownames(counts) <- feature_ids
  counts
}

as_named_vector <- function(values) {
  if (is.null(values)) {
    character()
  } else {
    unlist(values, use.names = FALSE)
  }
}

apply_reference_levels <- function(metadata, validated_design) {
  reference_levels <- list()
  primary <- validated_design$primary_factor
  variables <- list(primary)
  if (!is.null(validated_design$covariates)) {
    variables <- c(variables, validated_design$covariates)
  }
  for (variable in variables) {
    name <- variable$name
    reference <- variable$reference_level
    if (!(name %in% colnames(metadata))) {
      stop(sprintf("Design variable '%s' is missing from sample metadata.", name), call. = FALSE)
    }
    metadata[[name]] <- factor(metadata[[name]])
    if (!(reference %in% levels(metadata[[name]]))) {
      stop(sprintf("Reference level '%s' is not present for design variable '%s'.", reference, name), call. = FALSE)
    }
    metadata[[name]] <- stats::relevel(metadata[[name]], ref = reference)
    reference_levels[[name]] <- reference
  }
  list(metadata = metadata, reference_levels = reference_levels)
}

coef_name_for_contrast <- function(results_names, variable, numerator, denominator) {
  expected <- sprintf("%s_%s_vs_%s", variable, numerator, denominator)
  if (expected %in% results_names) {
    return(expected)
  }
  NA_character_
}

main <- function() {
  args <- tryCatch(parse_args(commandArgs(trailingOnly = TRUE)), error = function(e) {
    cat(sprintf("ERROR: %s\n", conditionMessage(e)), file = stderr())
    usage(2)
  })

  require_namespace("jsonlite")
  diagnostics_path <- args[["out-diagnostics"]]
  tryCatch({
    require_namespace("DESeq2")

    params <- read_json(args[["deseq2-params"]], "DESeq2 parameters")
    test_type <- required_param(params, "test_type")
    apply_shrinkage <- required_param(params, "apply_shrinkage")
    shrinkage_method <- required_param(params, "shrinkage_method")
    p_adjust_method <- required_param(params, "p_adjust_method")
    save_rds <- required_param(params, "save_rds")

    if (!identical(test_type, "wald")) {
      stop("Unsupported test_type. MVP supports only 'wald'.", call. = FALSE)
    }
    if (!is.logical(apply_shrinkage) || length(apply_shrinkage) != 1) {
      stop("apply_shrinkage must be explicitly supplied as true or false.", call. = FALSE)
    }
    if (!identical(shrinkage_method, "apeglm")) {
      stop("Unsupported shrinkage_method. MVP supports only 'apeglm'.", call. = FALSE)
    }
    if (!is.character(p_adjust_method) || length(p_adjust_method) != 1 || p_adjust_method == "") {
      stop("p_adjust_method must be an explicitly supplied non-empty string.", call. = FALSE)
    }
    if (!is.logical(save_rds) || length(save_rds) != 1) {
      stop("save_rds must be explicitly supplied as true or false.", call. = FALSE)
    }
    if (isTRUE(apply_shrinkage)) {
      require_namespace("apeglm")
    }

    validated_design <- read_json(args[["validated-design"]], "validated design")
    resolved_contrasts <- read_json(args[["resolved-contrasts"]], "resolved contrasts")
    if (!identical(validated_design$status, "passed")) {
      stop("validated_design.json must have status 'passed'.", call. = FALSE)
    }
    if (!identical(resolved_contrasts$status, "passed")) {
      stop("resolved_contrasts.json must have status 'passed'.", call. = FALSE)
    }

    feature_id_column <- "feature_id"
    count_table <- utils::read.delim(
      args[["filtered-feature-matrix"]],
      check.names = FALSE,
      stringsAsFactors = FALSE
    )
    if ("gene_id" %in% colnames(count_table)) {
      feature_id_column <- "gene_id"
    }
    counts <- validate_counts(count_table, feature_id_column)

    metadata <- utils::read.delim(
      args[["sample-metadata"]],
      check.names = FALSE,
      stringsAsFactors = FALSE
    )
    sample_id_column <- validated_design$sample_id_column
    if (is.null(sample_id_column) || !(sample_id_column %in% colnames(metadata))) {
      stop("validated_design sample_id_column is missing from sample metadata.", call. = FALSE)
    }
    sample_ids <- as_named_vector(validated_design$sample_ids)
    if (!setequal(colnames(counts), metadata[[sample_id_column]]) || !setequal(colnames(counts), sample_ids)) {
      stop("Filtered matrix, sample metadata, and validated_design sample IDs must match exactly.", call. = FALSE)
    }
    metadata <- metadata[match(colnames(counts), metadata[[sample_id_column]]), , drop = FALSE]
    rownames(metadata) <- metadata[[sample_id_column]]

    ref_result <- apply_reference_levels(metadata, validated_design)
    metadata <- ref_result$metadata
    reference_levels <- ref_result$reference_levels
    formula <- stats::as.formula(validated_design$resolved_formula)

    dds <- DESeq2::DESeqDataSetFromMatrix(countData = counts, colData = metadata, design = formula)
    dds <- DESeq2::DESeq(dds, test = "Wald", quiet = TRUE)
    size_factors <- as.list(stats::setNames(as.numeric(DESeq2::sizeFactors(dds)), colnames(counts)))
    results_names <- DESeq2::resultsNames(dds)

    output_rows <- list()
    warnings <- list()
    for (contrast in resolved_contrasts$contrasts) {
      if (!identical(contrast$type, "factor_levels")) {
        stop("DESeq2 MVP supports only factor_levels contrasts.", call. = FALSE)
      }
      contrast_vector <- c(contrast$variable, contrast$numerator, contrast$denominator)
      result <- DESeq2::results(dds, contrast = contrast_vector, pAdjustMethod = p_adjust_method)
      if (isTRUE(apply_shrinkage)) {
        coef_name <- coef_name_for_contrast(results_names, contrast$variable, contrast$numerator, contrast$denominator)
        if (is.na(coef_name)) {
          stop(
            sprintf(
              "apeglm shrinkage requires a direct DESeq2 coefficient for contrast '%s'; available resultsNames: %s",
              contrast$contrast_id,
              paste(results_names, collapse = ", ")
            ),
            call. = FALSE
          )
        }
        result <- DESeq2::lfcShrink(dds, coef = coef_name, res = result, type = "apeglm")
      }
      frame <- as.data.frame(result)
      frame$feature_id <- rownames(frame)
      status <- ifelse(is.na(frame$pvalue), "unavailable", "tested")
      output_rows[[length(output_rows) + 1]] <- data.frame(
        feature_id = frame$feature_id,
        contrast_id = contrast$contrast_id,
        effect_estimate = frame$log2FoldChange,
        effect_type = "log2_fold_change",
        p_value = frame$pvalue,
        adjusted_p_value = frame$padj,
        base_mean = frame$baseMean,
        status = status,
        method = "deseq2",
        positive_effect_definition = contrast$positive_effect_definition,
        stringsAsFactors = FALSE,
        check.names = FALSE
      )
    }
    results_table <- do.call(rbind, output_rows)
    utils::write.table(
      results_table,
      args[["out-results"]],
      sep = "\t",
      quote = FALSE,
      row.names = FALSE,
      na = ""
    )

    if (isTRUE(save_rds)) {
      out_rds <- args[["out-dds-rds"]]
      if (is.null(out_rds) || out_rds == "") {
        stop("save_rds is true, so --out-dds-rds is required.", call. = FALSE)
      }
      saveRDS(dds, out_rds)
    }

    diagnostics <- list(
      schema_version = 1,
      status = "passed",
      method = "deseq2",
      `DESeq2 version` = as.character(utils::packageVersion("DESeq2")),
      `R version` = paste(R.version$major, R.version$minor, sep = "."),
      formula = validated_design$resolved_formula,
      reference_levels = reference_levels,
      n_samples = ncol(counts),
      n_features_input = nrow(counts),
      n_features_tested = nrow(results_table),
      size_factors = size_factors,
      results_names = as.list(results_names),
      parameters_used = list(
        test_type = test_type,
        apply_shrinkage = apply_shrinkage,
        shrinkage_method = shrinkage_method,
        p_adjust_method = p_adjust_method,
        save_rds = save_rds
      ),
      apply_shrinkage = apply_shrinkage,
      shrinkage_method = shrinkage_method,
      warnings = warnings,
      errors = list()
    )
    jsonlite::write_json(diagnostics, diagnostics_path, pretty = TRUE, auto_unbox = TRUE)
  }, error = function(e) {
    fail(conditionMessage(e), diagnostics_path)
  })
}

main()
