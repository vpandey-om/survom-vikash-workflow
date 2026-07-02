FROM bioconductor/bioconductor_docker:RELEASE_3_21@sha256:359702d482e70e343d2a436731b7c6deffd1ec184a1f1700de5d64b0c97cacba

LABEL org.opencontainers.image.title="SurvOm DESeq2 development image"
LABEL org.opencontainers.image.description="Pinned Bioconductor DESeq2/apeglm runtime for transcriptomics.stats.deseq2 development validation"

RUN Rscript -e 'BiocManager::install(c("DESeq2", "apeglm", "jsonlite", "data.table"), version = "3.21", ask = FALSE, update = FALSE)'

RUN Rscript -e 'library(DESeq2); library(apeglm); library(jsonlite); library(data.table); cat(R.version.string, "\n"); cat("DESeq2", as.character(packageVersion("DESeq2")), "\n"); cat("apeglm", as.character(packageVersion("apeglm")), "\n"); cat("jsonlite", as.character(packageVersion("jsonlite")), "\n"); cat("data.table", as.character(packageVersion("data.table")), "\n")'
