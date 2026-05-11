# ACValidator Dockerfile
# Fixed base image for reproducibility
FROM ubuntu:20.04

# Maintainer info
LABEL maintainer="ACValidator Docker Build"
LABEL description="Assembly based Circular RNA validator (ACValidator)"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python2.7 \
    python-pip-whl \
    python-setuptools \
    wget \
    curl \
    build-essential \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libncurses5-dev \
    libncursesw5-dev \
    bedtools \
    && rm -rf /var/lib/apt/lists/*

# Set up Python 2.7 and pip
RUN wget https://bootstrap.pypa.io/pip/2.7/get-pip.py && \
    python2.7 get-pip.py && \
    rm get-pip.py

# Install Python dependencies
RUN python2.7 -m pip install pysam

# Set working directory for tools
WORKDIR /opt

# Install Samtools v1.4
RUN wget https://github.com/samtools/samtools/releases/download/1.4/samtools-1.4.tar.bz2 && \
    tar -xjf samtools-1.4.tar.bz2 && \
    cd samtools-1.4 && \
    ./configure --prefix=/opt/samtools-1.4 && \
    make && \
    make install && \
    cd .. && \
    rm samtools-1.4.tar.bz2
ENV PATH="/opt/samtools-1.4/bin:${PATH}"

# Install BWA v0.7.12
RUN wget https://github.com/lh3/bwa/releases/download/v0.7.12/bwa-0.7.12.tar.bz2 && \
    tar -xjf bwa-0.7.12.tar.bz2 && \
    cd bwa-0.7.12 && \
    make && \
    cd .. && \
    rm bwa-0.7.12.tar.bz2
ENV PATH="/opt/bwa-0.7.12:${PATH}"

# Install Bowtie2 v2.3.0
RUN wget https://github.com/BenLangmead/bowtie2/releases/download/v2.3.0/bowtie2-2.3.0-linux-x86_64.zip && \
    unzip bowtie2-2.3.0-linux-x86_64.zip && \
    rm bowtie2-2.3.0-linux-x86_64.zip
ENV PATH="/opt/bowtie2-2.3.0:${PATH}"

# Install Trinity v2.3.1
# Note: Trinity requires Java and other dependencies
RUN apt-get update && apt-get install -y \
    default-jre \
    jellyfish \
    salmon \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/trinityrnaseq/trinityrnaseq/releases/download/v2.3.2/trinityrnaseq-v2.3.2.FULL.tar.gz && \
    tar -xzf trinityrnaseq-v2.3.2.FULL.tar.gz && \
    cd trinityrnaseq-v2.3.2 && \
    make && \
    make plugins && \
    cd .. && \
    rm trinityrnaseq-v2.3.2.FULL.tar.gz
ENV PATH="/opt/trinityrnaseq-v2.3.2:${PATH}"

# Copy ACValidator source code
WORKDIR /app
COPY ACValidator/ACValidator /app/ACValidator
COPY ACValidator/setup.py /app/
COPY ACValidator/README.md /app/
COPY ACValidator/LICENSE /app/

# Modify ACValidator_v1.py to use container paths
RUN sed -i 's|SAMTOOLSPATH = "/packages/samtools/1.4.1/bin/samtools"|SAMTOOLSPATH = "/opt/samtools-1.4/bin/samtools"|g' /app/ACValidator/ACValidator_v1.py && \
    sed -i 's|BWAPATH = "/packages/bwa/0.7.12/bwa"|BWAPATH = "/opt/bwa-0.7.12/bwa"|g' /app/ACValidator/ACValidator_v1.py && \
    sed -i 's|BAMTOFASTQPATH = "/packages/BEDTools/2.26.0/bin/bamToFastq"|BAMTOFASTQPATH = "/usr/bin/bamToFastq"|g' /app/ACValidator/ACValidator_v1.py && \
    sed -i 's|REFPATH = "/home/ssekar/splitFastas"|REFPATH = "/data/reference"|g' /app/ACValidator/ACValidator_v1.py && \
    sed -i 's|TRINITYPATH = "/packages/trinityrnaseq/2.4.0/Trinity"|TRINITYPATH = "/opt/trinityrnaseq-v2.3.2/Trinity"|g' /app/ACValidator/ACValidator_v1.py

# Install ACValidator
RUN python2.7 -m pip install .

# Create reference directory
RUN mkdir -p /data/reference

# Set working directory
WORKDIR /work

# Default entrypoint
ENTRYPOINT ["ACValidator"]
CMD ["--help"]
