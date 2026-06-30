FROM quay.io/biocontainers/seqkit:2.10.1--he881be0_0@sha256:fbc9b1d536fab653a3f54cb92c13ced505d994e4811918a44315fd4123fa492b

LABEL org.opencontainers.image.title="SurvOm SeqKit development image"
LABEL org.opencontainers.image.description="Pinned SeqKit runtime for common.qc.seqkit_fastq_stats development validation"

RUN seqkit version

ENTRYPOINT ["seqkit"]
