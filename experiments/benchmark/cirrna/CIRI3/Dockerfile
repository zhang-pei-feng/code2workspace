FROM ubuntu:20.04

# Set non-interactive mode for apt
ENV DEBIAN_FRONTEND=noninteractive

# Install base dependencies
RUN apt-get update && apt-get install -y \
    openjdk-17-jre-headless \
    wget \
    curl \
    bzip2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy CIRI3 files
COPY CIRI3/CIRI3_Java_18.0.1.jar /app/CIRI3.jar
COPY CIRI3/data/ /app/data/
COPY CIRI3/scripts/ /app/scripts/

# Set permissions
RUN chmod +x /app/CIRI3.jar

# Default command shows help
ENTRYPOINT ["java", "-jar", "/app/CIRI3.jar"]