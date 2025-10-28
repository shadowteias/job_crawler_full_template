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
