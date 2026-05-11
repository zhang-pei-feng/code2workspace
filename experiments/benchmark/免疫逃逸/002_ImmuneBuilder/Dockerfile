FROM continuumio/miniconda3:4.12.0

LABEL maintainer="ImmuneBuilder Docker"
LABEL description="Docker image for ImmuneBuilder - Deep learning models for immune protein structure prediction"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN conda install -y -c conda-forge mamba

RUN mamba install -y python=3.9 -c conda-forge && mamba clean -a -y

RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir numpy scipy einops requests

RUN mamba install -y -c conda-forge libstdcxx-ng && mamba clean -a -y

RUN mamba install -y openmm pdbfixer anarci -c conda-forge -c bioconda && mamba clean -a -y

WORKDIR /app

COPY ImmuneBuilder /app/ImmuneBuilder

WORKDIR /app/ImmuneBuilder

RUN pip install --no-cache-dir -e .

WORKDIR /data

ENV PYTHONPATH=/app/ImmuneBuilder:$PYTHONPATH
ENV LD_LIBRARY_PATH=/opt/conda/lib:$LD_LIBRARY_PATH

CMD ["/bin/bash"]
