# BIQ - Backsplice Junction Indexing and Querying
# Base image with Node.js for React app and Perl for scripts
FROM node:16-bullseye-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    perl \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy repository files
COPY biq/package*.json ./
COPY biq/scripts_ensembl /app/scripts_ensembl
COPY biq/src /app/src
COPY biq/public /app/public
COPY biq/flowchart /app/flowchart
COPY biq/http_endpoints /app/http_endpoints

# Install Node.js dependencies
RUN npm install

# Make Perl scripts executable
RUN chmod +x /app/scripts_ensembl/*.pl

# Build the React application
RUN npm run build

# Set PATH to include scripts directory
ENV PATH="/app/scripts_ensembl:${PATH}"

# Default command shows help
CMD ["node", "--version"]

# Expose port for web server (if needed)
EXPOSE 3000

# Add labels
LABEL maintainer="BIQ Docker Build"
LABEL description="BIQ - Backsplice Junction Indexing and Querying Tool"
LABEL version="1.0"
