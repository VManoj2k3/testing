#!/usr/bin/env bash
# Pushes server_kernel.py to Kaggle as a private 2x T4 run.
# Needs: KAGGLE_API_TOKEN, KAGGLE_USERNAME.
# Optional: MODEL_REPO (default Qwen/Qwen3.8-27B), QUANT (Q4_K_M), CTX (16384), MAX_RUNTIME_MIN (180).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=ocr-$(openssl rand -hex 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"; chmod 600 "$STATE"/*
MODEL_REPO=${MODEL_REPO:-Qwen/Qwen3.8-27B}
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" -e "s|__MODEL_REPO__|$MODEL_REPO|" \
    -e "s|__QUANT__|${QUANT:-Q4_K_M}|" -e "s|__CTX__|${CTX:-16384}|" -e "s|__EMBED_REPO__|${EMBED_REPO-gpustack/bge-m3-GGUF}|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-180}|" server_kernel.py > "$STATE/kernel/server_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/ocr-llama-server", "title": "ocr-llama-server",
 "code_file": "server_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": true, "enable_internet": true,
 "machine_shape": "NvidiaTeslaT4"}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/ocr-llama-server"
echo "Launched $MODEL_REPO. Next: ./wait_for_link.sh"
