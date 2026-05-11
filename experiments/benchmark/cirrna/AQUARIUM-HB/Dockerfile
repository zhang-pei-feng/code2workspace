FROM ubuntu:22.04

# Set non-interactive frontend
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /opt/AQUARIUM-HB

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    perl \
    default-jre-headless \
    r-base \
    python3 \
    python3-pip \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -fs /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone

# Install R packages
RUN R -e "install.packages(c('argparse', 'data.table', 'tidyr', 'plyr', 'dplyr'), repos='https://cloud.r-project.org/', quiet=TRUE)" 2>/dev/null || echo "R package installation may have warnings"

# Copy source code
COPY . /opt/AQUARIUM-HB/

# Create entrypoint script
RUN echo '#!/bin/bash' > /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'cd /opt/AQUARIUM-HB' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export path_Rscript=/usr/bin/Rscript' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export path_perl=/usr/bin/perl' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export path_java=/usr/bin/java' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export path_bwa=bwa' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export path_salmon=salmon' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export scriptsdir=/opt/AQUARIUM-HB/bin/' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export referencesdir=/opt/AQUARIUM-HB/data/' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export fa=/opt/AQUARIUM-HB/data/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export gtf=/opt/AQUARIUM-HB/data/Homo_sapiens.GRCh38.94.chr.gtf' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export FLcircAS=/opt/AQUARIUM-HB/data/FLcircAS.final.datatable' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export IsoCirc=/opt/AQUARIUM-HB/data/IsoCirc.final.datatable' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'export THREAD_COUNT=4' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "AQUARIUM-HB: A bioinformatics pipeline for human blood circular RNA analysis"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo ""' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "Usage: AQUARIUM_HB.sh <module> [options]"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo ""' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "Modules:"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  detect      - Detect circRNA from RNA-seq data"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  reference   - Construct a reference set of human blood full-length circRNAs"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  reconstruct - Reconstruct incomplete circRNAs from RNA-seq data"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  quant       - Quantify human blood full-length circRNAs from RNA-seq data"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo ""' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "Examples:"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  AQUARIUM_HB.sh detect --fastq1 sample_1.fastq.gz --fastq2 sample_2.fastq.gz --outdir output"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  AQUARIUM_HB.sh reference --stoutlist_path input.txt --reference_prefix output_prefix"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  AQUARIUM_HB.sh reconstruct --cirireport_file ciri.report --stoutlist_file stout.txt --reference_file ref.txt --outputdir output"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "  AQUARIUM_HB.sh quant --fastq1 sample_1.fastq.gz --fastq2 sample_2.fastq.gz --gtfdir gtfdir --quantdir quantdir"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo ""' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    echo "For more information, see: https://github.com/NJUCMbioinfo/AQUARIUM-HB"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo '    exit 0' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'fi' >> /usr/local/bin/AQUARIUM_HB.sh && \
    echo 'bash /opt/AQUARIUM-HB/AQUARIUM_HB.sh "$@"' >> /usr/local/bin/AQUARIUM_HB.sh && \
    chmod +x /usr/local/bin/AQUARIUM_HB.sh

# Set default command
ENTRYPOINT ["AQUARIUM_HB.sh"]
CMD ["--help"]
