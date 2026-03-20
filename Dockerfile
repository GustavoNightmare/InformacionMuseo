FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/instance /app/chroma_db /app/static/uploads \
    && chmod +x /app/docker/entrypoint.sh /app/docker/ollama-init.sh

EXPOSE 5000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
