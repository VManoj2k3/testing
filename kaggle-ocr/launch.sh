#!/usr/bin/env bash
# Pushes ocr_kernel.py to Kaggle as a private CPU-only run (no GPU quota used).
# Needs: KAGGLE_API_TOKEN, KAGGLE_USERNAME, and a running Qwen server
# (../kaggle-llama/.state/llm_url + secret). Optional: MAX_RUNTIME_MIN (default 300).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
LLM_URL=$(cat ../kaggle-llama/.state/llm_url); LLM_KEY=$(cat ../kaggle-llama/.state/secret)
command -v kaggle >/dev/null || pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=ocr-$(openssl rand -hex 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"
APP_USER=admin; APP_PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
printf '%s\n%s\n' "$APP_USER" "$APP_PASS" > "$STATE/login"; chmod 600 "$STATE"/*
B64=$(base64 -w0 app.py)
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" \
    -e "s|__LLM_URL__|$LLM_URL|" -e "s|__LLM_KEY__|$LLM_KEY|" -e "s|__LLM_MODEL__|${LLM_MODEL:-qwen3.8-27b}|" \
    -e "s|__APP_USER__|$APP_USER|" -e "s|__APP_PASS__|$APP_PASS|" -e "s|__APP_B64__|$B64|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-300}|" ocr_kernel.py > "$STATE/kernel/ocr_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/ocr-viewer", "title": "ocr-viewer",
 "code_file": "ocr_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": false, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/ocr-viewer"
echo "Launched. Next: ./wait_for_link.sh"
