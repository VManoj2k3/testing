#!/usr/bin/env bash
# Bring the whole local RAGFlow test stack up after a container restart:
# dependencies, RAGFlow services + nginx (sign-up stays off), and the CPU bge-m3 embedder on :8092.
# Usage: local_up.sh   (env: RAGFLOW_SRC, LLAMA_SERVER, BGE_M3_GGUF, LOG_DIR to override defaults)
set -euo pipefail
cd "$(dirname "$0")"
export RAGFLOW_SRC=${RAGFLOW_SRC:-/home/user/infiniflow/ragflow}
LLAMA_SERVER=${LLAMA_SERVER:-/tmp/claude-0/llama.cpp/build/bin/llama-server}
BGE_M3_GGUF=${BGE_M3_GGUF:-$(ls /root/.cache/huggingface/hub/models--gpustack--bge-m3-GGUF/snapshots/*/bge-m3-Q8_0.gguf | head -1)}
LOG_DIR=${LOG_DIR:-/var/log/ragflow}
mkdir -p "$LOG_DIR"

bash deps_ragflow.sh start </dev/null >"$LOG_DIR/deps_start.log" 2>&1
bash deps_ragflow.sh status
if ! curl -s -m 5 http://127.0.0.1:9380/api/v1/system/healthz | grep -q '"status":"ok"'; then
  bash run_ragflow.sh start </dev/null 2>&1 | tail -1
fi
if [ "$(curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1/)" != 200 ]; then
  nginx </dev/null >/dev/null 2>&1 || nginx -s reload </dev/null >/dev/null 2>&1 || true   # web UI was not served after a restart
fi
echo "web:      $(curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1/)"
if ! curl -s -m 5 http://127.0.0.1:8092/health | grep -q ok; then
  # -ub 4096: an 8192 micro-batch was OOM-killed (~9 GB) on the 'one' chunking method.
  nohup "$LLAMA_SERVER" -m "$BGE_M3_GGUF" --embedding --pooling cls -c 4096 -ub 4096 -b 4096 -np 1 \
    -t "$(nproc)" --host 127.0.0.1 --port 8092 --alias bge-m3 >"$LOG_DIR/embedder.log" 2>&1 </dev/null &
  for _ in $(seq 120); do curl -s -m 5 http://127.0.0.1:8092/health | grep -q ok && break; sleep 2; done
fi
echo "embedder: $(curl -s -m 5 http://127.0.0.1:8092/health)"
echo "sign-up:  $(curl -s -m 5 http://127.0.0.1:9380/api/v1/system/config)"
