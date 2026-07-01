FROM bioconductor/bioconductor_docker:RELEASE_3_21

LABEL org.opencontainers.image.title="SurvOm tximport development image"
LABEL org.opencontainers.image.description="Pinned Bioconductor tximport runtime for common.aggregate.tximport development validation"

RUN Rscript -e 'BiocManager::install("tximport", version = "3.21", ask = FALSE, update = FALSE); stopifnot(as.character(packageVersion("tximport")) == "1.36.1")'

RUN Rscript -e 'cat(R.version.string, "\n"); cat("tximport", as.character(packageVersion("tximport")), "\n")'
