# syntax=docker/dockerfile:1.4

# ---- pin base image with digest via build-args ----
ARG PYTHON_BASE_IMAGE=python:3.10-slim
ARG PYTHON_BASE_DIGEST
FROM ${PYTHON_BASE_IMAGE}@${PYTHON_BASE_DIGEST}

WORKDIR /app

# OS deps (mysqlclient 등 빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      default-libmysqlclient-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ---- install torch CPU-only (轻量化, fast build) ----
RUN pip install --no-cache-dir torch sentencepiece transformers

# ---- install llama-cpp-python for local LLM inference ----
RUN pip install --no-cache-dir llama-cpp-python

# ---- download Qwen2.5-0.5B GGUF model (at build time for reproducibility) ----
RUN python3 -c "from huggingface_hub import hf_hub_download; import os; os.makedirs('/app/models', exist_ok=True); hf_hub_download(repo_id='Qwen/Qwen2.5-0.5B-Instruct-GGUF', filename='qwen2.5-0.5b-instruct-q4_k_m.gguf', local_dir='/app/models', local_dir_use_symlinks=False)"

# ---- install python deps from locked file ----
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

# project files
COPY . .

# runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# logs
RUN mkdir -p /app/logs

# entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
