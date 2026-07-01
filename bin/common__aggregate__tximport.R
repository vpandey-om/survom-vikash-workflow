#!/usr/bin/env Rscript

fail <- function(message) {
  cat("ERROR:", message, "\n", file = stderr())
  quit(status = 1)
}

parse_args <- function(args) {
  if ("--help" %in% args || "-h" %in% args) {
    cat("Contract runner for SURVOM_COMMON_AGGREGATE_TXIMPORT.\n")
    cat("Required: --samples samples.tsv --tx2gene tx2gene.tsv --outdir output_dir\n")
    quit(status = 0)
  }
  parsed <- list()
  index <- 1
  while (index <= length(args)) {
    key <- args[[index]]
    if (!key %in% c("--samples", "--tx2gene", "--outdir")) {
      fail(paste("unknown argument:", key))
    }
    if (index == length(args)) {
      fail(paste("missing value for", key))
    }
    parsed[[sub("^--", "", key)]] <- args[[index + 1]]
    index <- index + 2
  }
  for (required in c("samples", "tx2gene", "outdir")) {
    if (is.null(parsed[[required]]) || parsed[[required]] == "") {
      fail(paste("missing required argument --", required, sep = ""))
    }
  }
  parsed
}

read_table_checked <- function(path, expected_header, label) {
  if (!file.exists(path)) {
    fail(paste(label, "does not exist:", path))
  }
  header <- strsplit(readLines(path, n = 1, warn = FALSE), "\t", fixed = TRUE)[[1]]
  if (!identical(header, expected_header)) {
    fail(paste(label, "must have header:", paste(expected_header, collapse = "\t")))
  }
  table <- tryCatch(
    read.delim(path, header = TRUE, sep = "\t", stringsAsFactors = FALSE, check.names = FALSE),
    error = function(error) fail(paste("could not read", label, ":", conditionMessage(error)))
  )
  if (!identical(names(table), expected_header)) {
    fail(paste(label, "must have columns:", paste(expected_header, collapse = ", ")))
  }
  table
}

format_matrix <- function(matrix_like, id_name) {
  data <- as.data.frame(matrix_like, check.names = FALSE, stringsAsFactors = FALSE)
  data <- data[order(rownames(data)), , drop = FALSE]
  data <- data[, sort(colnames(data)), drop = FALSE]
  data[[id_name]] <- rownames(data)
  data <- data[, c(id_name, setdiff(names(data), id_name)), drop = FALSE]
  for (column in setdiff(names(data), id_name)) {
    data[[column]] <- formatC(as.numeric(data[[column]]), digits = 10, format = "fg", flag = "#")
  }
  data
}

write_tsv <- function(data, path) {
  write.table(data, file = path, sep = "\t", quote = FALSE, row.names = FALSE, col.names = TRUE)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))

samples <- read_table_checked(args$samples, c("sample_id", "quant_sf"), "samples.tsv")
tx2gene <- read_table_checked(args$tx2gene, c("transcript_id", "gene_id"), "tx2gene.tsv")

if (nrow(samples) < 2) {
  fail("samples.tsv must contain at least two samples")
}
if (any(samples$sample_id == "" | is.na(samples$sample_id))) {
  fail("samples.tsv contains empty sample_id values")
}
if (anyDuplicated(samples$sample_id)) {
  fail("samples.tsv contains duplicate sample_id values")
}
if (any(samples$quant_sf == "" | is.na(samples$quant_sf))) {
  fail("samples.tsv contains empty quant_sf values")
}
if (any(tx2gene$transcript_id == "" | is.na(tx2gene$transcript_id))) {
  fail("tx2gene.tsv contains empty transcript_id values")
}
if (any(tx2gene$gene_id == "" | is.na(tx2gene$gene_id))) {
  fail("tx2gene.tsv contains empty gene_id values")
}
if (anyDuplicated(tx2gene$transcript_id)) {
  fail("tx2gene.tsv contains duplicate transcript_id values")
}

sample_dir <- dirname(normalizePath(args$samples, mustWork = TRUE))
resolve_quant <- function(path) {
  candidate <- if (grepl("^/", path)) path else file.path(sample_dir, path)
  normalizePath(candidate, mustWork = FALSE)
}
quant_paths <- vapply(samples$quant_sf, resolve_quant, character(1))
missing <- quant_paths[!file.exists(quant_paths)]
if (length(missing) > 0) {
  fail(paste("quant_sf file does not exist:", missing[[1]]))
}

required_quant_header <- c("Name", "Length", "EffectiveLength", "TPM", "NumReads")
quant_transcripts <- list()
for (i in seq_along(quant_paths)) {
  quant_header <- strsplit(readLines(quant_paths[[i]], n = 1, warn = FALSE), "\t", fixed = TRUE)[[1]]
  if (!identical(quant_header, required_quant_header)) {
    fail(paste("quant.sf has malformed header:", quant_paths[[i]]))
  }
  quant_table <- tryCatch(
    read.delim(quant_paths[[i]], header = TRUE, sep = "\t", stringsAsFactors = FALSE, check.names = FALSE),
    error = function(error) fail(paste("could not read quant.sf:", conditionMessage(error)))
  )
  if (anyDuplicated(quant_table$Name)) {
    fail(paste("quant.sf contains duplicate transcript IDs:", quant_paths[[i]]))
  }
  quant_transcripts[[i]] <- quant_table$Name
}

shared_transcripts <- Reduce(intersect, c(quant_transcripts, list(tx2gene$transcript_id)))
if (length(shared_transcripts) == 0) {
  fail("zero shared transcript IDs between quant.sf files and tx2gene.tsv")
}

if (!requireNamespace("tximport", quietly = TRUE)) {
  fail("R package tximport is not installed")
}

dir.create(args$outdir, recursive = TRUE, showWarnings = FALSE)
files <- stats::setNames(quant_paths, samples$sample_id)
txi <- tximport::tximport(
  files = files,
  type = "salmon",
  tx2gene = tx2gene
)

write_tsv(format_matrix(txi$counts, "gene_id"), file.path(args$outdir, "gene_counts.tsv"))
write_tsv(format_matrix(txi$abundance, "gene_id"), file.path(args$outdir, "gene_abundance.tsv"))
write_tsv(format_matrix(txi$length, "gene_id"), file.path(args$outdir, "gene_lengths.tsv"))
