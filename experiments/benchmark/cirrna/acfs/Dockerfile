# ACFS Dockerfile - Accurate CircRNA Finder Suite
# Base image: Ubuntu 20.04 for stability and compatibility
FROM ubuntu:20.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /opt/acfs

# Install system dependencies
RUN apt-get update && apt-get install -y \
    perl \
    build-essential \
    zlib1g-dev \
    wget \
    tar \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# Copy ACFS source code
COPY acfs/ /opt/acfs/

# Build BWA 0.7.3a (required by ACFS)
RUN cd /opt/acfs && \
    tar -xf bwa-0.7.3a.tar && \
    cd bwa-0.7.3a && \
    make && \
    cd /opt/acfs && \
    chmod +x bwa-0.7.3a/bwa

# Make all Perl scripts executable
RUN chmod +x /opt/acfs/*.pl && \
    chmod +x /opt/acfs/CB_splice/me2x5

# Set PATH to include BWA and ACFS scripts
ENV PATH="/opt/acfs:/opt/acfs/bwa-0.7.3a:${PATH}"

# Create working directory for data processing
WORKDIR /data

# Entry point: show help message with available commands
ENTRYPOINT ["/bin/bash", "-c"]
CMD ["echo 'ACFS - Accurate CircRNA Finder Suite' && \
     echo '' && \
     echo 'Available commands:' && \
     echo '  ACF_MAKE.pl <spec_file> <output_bash>' && \
     echo '  ACF_Step1.pl <unmap.sam> <unmap.parsed> <minMappingQuality> <Coverage>' && \
     echo '  ACF_Step2.pl <CBR_folder> <input> <genome_folder> <output>' && \
     echo '  ACF_Step3.pl <input> <summary_input>' && \
     echo '  ACF_Step4.pl <input> <agtf> <output_prefix> <minSplicingScore> <minJump> <maxJump> <minScore>' && \
     echo '  ACF_Step5.pl <sam> <CL> <output> <Seq_len> <minSpanJunc> <ErrorRate> <Strandness>' && \
     echo '  ACF_Step6.pl <refFlat> <expr> <bed12> <prefix> <minScore> <minSampleCnt> <minReadCnt> <maxReadCnt> <maxSampleCnt>' && \
     echo '' && \
     echo 'Utility scripts:' && \
     echo '  change_fastq_header.pl <input.fasta> <output.fa> <sample_prefix>' && \
     echo '  Truseq_merge_unique_fa.pl <output> <input1.fa> [input2.fa ...]' && \
     echo '  convert_unmapped_SAM_to_fa_for_acfs.pl <output.fa> <unmapped.sam> <sample_id>' && \
     echo '  get_split_exon_border_biotype_genename.pl <input.gtf> <output.gtf>' && \
     echo '' && \
     echo 'For full pipeline execution:' && \
     echo '  1. Prepare your SPEC file with all parameters' && \
     echo '  2. Run: perl /opt/acfs/ACF_MAKE.pl <your_spec.txt> <output.sh>' && \
     echo '  3. Execute: bash <output.sh>' && \
     echo '' && \
     echo 'Example with test data:' && \
     echo '  docker run -v /path/to/data:/data -v /path/to/results:/results benchmark/acfs:circrna' && \
     echo '' && \
     echo 'Documentation: https://github.com/arthuryxt/acfs'"]
