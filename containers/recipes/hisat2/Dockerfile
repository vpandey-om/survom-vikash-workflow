FROM quay.io/biocontainers/samtools:1.23.1--ha83d96e_0 AS samtools
FROM quay.io/biocontainers/hisat2:2.2.2--h503566f_0

COPY --from=samtools /usr/local/bin/samtools /usr/local/bin/samtools
COPY --from=samtools /usr/local/lib/ /usr/local/lib/

LABEL org.opencontainers.image.title="SurvOm HISAT2/Samtools development image"
LABEL org.opencontainers.image.description="Pinned HISAT2 and Samtools runtime for common.reference.hisat2_index and common.align.hisat2 development validation"

RUN hisat2 --version | head -1 && hisat2-build --version | head -1 && samtools --version | head -1
