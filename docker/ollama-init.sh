#!/bin/sh
set -eu

MODEL_CHAT="${OLLAMA_CHAT_MODEL:-qwen3.5:4b}"
MODEL_EMBED="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

ollama serve &
OLLAMA_PID=$!

until ollama list >/dev/null 2>&1; do
  echo "Esperando a que Ollama inicie..."
  sleep 2
done

echo "Verificando modelo de chat: ${MODEL_CHAT}"
if ! ollama list | grep -q "${MODEL_CHAT}"; then
  ollama pull "${MODEL_CHAT}" || true
fi

echo "Verificando modelo de embeddings: ${MODEL_EMBED}"
if ! ollama list | grep -q "${MODEL_EMBED}"; then
  ollama pull "${MODEL_EMBED}" || true
fi

wait "$OLLAMA_PID"
