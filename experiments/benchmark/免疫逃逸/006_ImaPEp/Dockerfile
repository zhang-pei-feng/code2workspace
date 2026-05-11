FROM python:3.9-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY ImaPEp/ /workspace/ImaPEp/

RUN pip install --no-cache-dir \
    torch==1.13.0 \
    torchvision==0.14.0 \
    numpy==1.25.2 \
    tqdm \
    matplotlib==3.7.2 \
    biopython==1.78 \
    scikit-learn==1.3.0 \
    Pillow==10.0.1 \
    click \
    pandas

RUN apt-get update && apt-get install -y hmmer && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir biopython && \
    pip install --no-cache-dir git+https://github.com/oxpig/ANARCI.git@master#egg=anarci && \
    pip install --no-cache-dir abnumber

ENV PYTHONPATH="/workspace/ImaPEp:${PYTHONPATH}"

WORKDIR /workspace/ImaPEp

CMD ["/bin/bash"]
