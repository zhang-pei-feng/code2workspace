# ESM (Evolutionary Scale Modeling) Docker Image
# Using Python 3.9 slim base image for faster build
FROM python:3.9-slim

# Set working directory
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install PyTorch (CPU version for faster installation, can be used with GPU if available)
RUN pip install torch==2.0.1 --index-url https://download.pytorch.org/whl/cpu

# Copy the ESM repository into the container
COPY esm/ /workspace/esm/

# Install fair-esm package with dependencies
WORKDIR /workspace/esm
RUN pip install -e . && \
    pip install biopython && \
    pip install biotite

# Create directories for data and results
RUN mkdir -p /data /results

# Set Python path
ENV PYTHONPATH=/workspace/esm:$PYTHONPATH

# Set the working directory back to workspace
WORKDIR /workspace

# Default command - run bash
CMD ["/bin/bash"]
