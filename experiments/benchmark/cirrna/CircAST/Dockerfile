# Dockerfile for CircAST v1.0.0
# CircRNAs with Alternative Spliced Transcripts - Full-length Assembly and Quantification

FROM python:2.7.18-slim-buster

LABEL maintainer="CircAST Docker Build"
LABEL description="CircAST: Full-length Assembly and Quantification of Alternatively Spliced Isoforms in Circular RNAs"
LABEL version="1.0.0"

WORKDIR /app

RUN echo "deb http://archive.debian.org/debian/ buster main" > /etc/apt/sources.list && \
    echo "deb http://archive.debian.org/debian-security buster/updates main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy==1.16.6

COPY CircAST/CircAST.py /app/CircAST.py
COPY CircAST/CircFullSeq.py /app/CircFullSeq.py

RUN chmod +x /app/CircAST.py /app/CircFullSeq.py

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/app/CircAST.py"]
CMD ["--help"]
