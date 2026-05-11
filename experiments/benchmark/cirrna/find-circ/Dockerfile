# find_circ Docker Image
# Base image: Ubuntu 18.04 with Python 2.7
FROM ubuntu:18.04

# Metadata
LABEL maintainer="find_circ containerization"
LABEL description="Containerized find_circ for circular RNA detection"
LABEL version="1.2"

# Set non-interactive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python2.7 \
    python-pip \
    wget \
    curl \
    git \
    build-essential \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libncurses5-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python 2.7 packages
# Install cython first as pysam depends on it
RUN pip install --no-cache-dir cython==0.29.24
RUN pip install --no-cache-dir numpy==1.16.6
RUN pip install --no-cache-dir pysam==0.15.4

# Install samtools 1.9
WORKDIR /tmp
RUN wget https://github.com/samtools/samtools/releases/download/1.9/samtools-1.9.tar.bz2 && \
    tar -xjf samtools-1.9.tar.bz2 && \
    cd samtools-1.9 && \
    ./configure --prefix=/usr/local && \
    make && \
    make install && \
    cd .. && \
    rm -rf samtools-1.9 samtools-1.9.tar.bz2

# Install bowtie2 2.3.5
RUN wget https://github.com/BenLangmead/bowtie2/releases/download/v2.3.5.1/bowtie2-2.3.5.1-linux-x86_64.zip && \
    unzip bowtie2-2.3.5.1-linux-x86_64.zip && \
    mv bowtie2-2.3.5.1-linux-x86_64/bowtie2* /usr/local/bin/ && \
    rm -rf bowtie2-2.3.5.1-linux-x86_64*

# Set working directory
WORKDIR /app

# Copy find_circ repository files
COPY find_circ/ /app/

# Make Python scripts executable
RUN chmod +x /app/*.py

# Add /app to PATH so scripts can be called directly
ENV PATH="/app:${PATH}"

# Set Python path
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Default command: show help for find_circ.py
ENTRYPOINT ["python2.7", "/app/find_circ.py"]
CMD ["--help"]
