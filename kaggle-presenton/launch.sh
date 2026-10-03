#!/usr/bin/env bash
# Pushes presenton_kernel.py to Kaggle as a private CPU-only run (no GPU quota used).
# Needs: KAGGLE_API_TOKEN, KAGGLE_USERNAME, and a running Qwen server
# (../kaggle-llama/.state/llm_url + secret). Optional: MAX_RUNTIME_MIN (default 300).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
LLM_URL=$(cat ../kaggle-llama/.state/llm_url); LLM_KEY=$(cat ../kaggle-llama/.state/secret)
command -v kaggle >/dev/null || pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=presenton-$(openssl rand -hex 16)
AUTH_USER=admin; AUTH_PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"
printf '%s\n%s\n' "$AUTH_USER" "$AUTH_PASS" > "$STATE/login"; chmod 600 "$STATE"/*
B64=$(base64 -w0 setup_presenton.sh)
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" -e "s|__SETUP_B64__|$B64|" \
    -e "s|__LLM_URL__|$LLM_URL|" -e "s|__LLM_KEY__|$LLM_KEY|" -e "s|__LLM_MODEL__|${LLM_MODEL:-qwen3.8-27b}|" \
    -e "s|__AUTH_USER__|$AUTH_USER|" -e "s|__AUTH_PASS__|$AUTH_PASS|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-300}|" presenton_kernel.py > "$STATE/kernel/presenton_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/presenton-server", "title": "presenton-server",
 "code_file": "presenton_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": false, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/presenton-server"
echo "Launched. Next: ./wait_for_link.sh"
