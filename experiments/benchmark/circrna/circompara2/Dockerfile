# Dockerfile for CirComPara2
# CircRNA detection pipeline from RNA-seq data
FROM ubuntu:20.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python2.7 \
    python-dev-is-python2 \
    python-is-python2 \
    wget \
    unzip \
    pkg-config \
    default-jre \
    r-base-core \
    libcurl4-openssl-dev \
    libxml2-dev \
    libssl-dev \
    curl \
    pigz \
    build-essential \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libncurses5-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /circompara2

# Copy the repository
COPY circompara2/ /circompara2/

# Keep CIRCexplorer2 on a Python-2-compatible dependency path.
RUN python2.7 - <<'PY'
import io

path = "/circompara2/src/sconstructs/install_tools.py"
with io.open(path, "r", encoding="utf-8") as handle:
    text = handle.read()
old = "                           ['pip install ' + SET_PIP_USER + ' circexplorer2==2.3.8']) #--ignore-installed not added because it will install pysam > v0.15.4 that does not support reading gzip'd files\n"
new = "                           ['pip install ' + SET_PIP_USER + ' requests==2.27.1 scipy==1.2.3 docopt==0.6.2 pybedtools==0.8.2 --no-use-pep517 && pip install ' + SET_PIP_USER + ' circexplorer2==2.3.8 --no-deps'])\n"
if old not in text:
    raise SystemExit("expected CIRCexplorer2 install stanza not found")
with io.open(path, "w", encoding="utf-8") as handle:
    handle.write(text.replace(old, new))
PY

# Run the installation script (with continue on errors for problematic packages)
RUN cd /circompara2 && \
    ./src/utils/bash/install_circompara -i && \
    ln -sf src/utils/bash/circompara circompara2

# Set PATH to include circompara2 binaries
ENV PATH="/circompara2/bin:/circompara2:${PATH}"
ENV CIRCOMPARA_HOME="/circompara2"
ENV R_LIBS="/circompara2/tools/R_libs"

# Set the entrypoint to circompara2 main script
ENTRYPOINT ["/circompara2/circompara2"]
CMD ["-h"]
