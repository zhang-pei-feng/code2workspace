# Dockerfile for AutoCirc v1.3.1
# AutoCirc: Computational tool to detect circular RNAs from RNA-Seq data
FROM ubuntu:20.04

LABEL maintainer="AutoCirc Docker Build"
LABEL description="AutoCirc: A computational program to automatically identify back-splice junctions of potential circular RNAs"
LABEL version="1.3.1"

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Install system dependencies
RUN apt-get update && apt-get install -y \
    perl \
    perl-base \
    wget \
    curl \
    make \
    gcc \
    g++ \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libncurses5-dev \
    python3 \
    python3-pip \
    bedtools \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Samtools (version 1.15)
WORKDIR /tmp
RUN wget https://github.com/samtools/samtools/releases/download/1.15/samtools-1.15.tar.bz2 && \
    tar -xjf samtools-1.15.tar.bz2 && \
    cd samtools-1.15 && \
    ./configure --prefix=/usr/local && \
    make && \
    make install && \
    cd .. && \
    rm -rf samtools-1.15*

# Install Bowtie2 (version 2.4.5)
RUN wget https://github.com/BenLangmead/bowtie2/releases/download/v2.4.5/bowtie2-2.4.5-linux-x86_64.zip && \
    unzip bowtie2-2.4.5-linux-x86_64.zip && \
    mv bowtie2-2.4.5-linux-x86_64/bowtie2* /usr/local/bin/ && \
    rm -rf bowtie2-2.4.5-linux-x86_64*

# Copy AutoCirc repository into container
WORKDIR /opt/autocirc
COPY AutoCirc/AutoCirc_v1.3.1.pl /opt/autocirc/AutoCirc_v1.3.1.pl
COPY AutoCirc/script /opt/autocirc/script
COPY AutoCirc/example /opt/autocirc/example

# Make scripts executable
RUN chmod +x /opt/autocirc/AutoCirc_v1.3.1.pl && \
    chmod +x /opt/autocirc/script/*

# Add AutoCirc to PATH
ENV PATH="/opt/autocirc:${PATH}"

# Set working directory for execution
WORKDIR /data

# Default command shows help
ENTRYPOINT ["/opt/autocirc/AutoCirc_v1.3.1.pl"]
CMD ["--help"]
