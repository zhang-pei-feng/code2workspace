# AutoDock-Vina Docker Image
# Base image with build essentials
FROM ubuntu:20.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies required for building AutoDock Vina
RUN apt-get update && apt-get install -y \
    build-essential \
    libboost-all-dev \
    swig \
    git \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /opt

# Copy the AutoDock-Vina source code
COPY AutoDock-Vina /opt/AutoDock-Vina

# Build AutoDock Vina from source
WORKDIR /opt/AutoDock-Vina/build/linux/release
RUN make

# Add vina executable to PATH
ENV PATH="/opt/AutoDock-Vina/build/linux/release:${PATH}"

# Copy data files to accessible location
RUN mkdir -p /data && \
    cp /opt/AutoDock-Vina/data/* /data/

# Install Python dependencies for ligand/receptor preparation
RUN pip3 install numpy meeko

# Set working directory for running tests
WORKDIR /workspace

# Default command to show vina help
CMD ["vina", "--help"]
