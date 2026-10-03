#!/usr/bin/env bash
# Pushes server_kernel.py to Kaggle as a private GPU run.
# Needs: KAGGLE_API_TOKEN, KAGGLE_USERNAME. Optional: MAX_RUNTIME_MIN (default 180).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
pip install -q --upgrade kaggle
STATE=.state; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24)
echo "$SECRET" > "$STATE/secret"; chmod 600 "$STATE/secret"
sed -e "s/__SECRET__/$SECRET/" -e "s/__MAX_RUNTIME_MIN__/${MAX_RUNTIME_MIN:-180}/" server_kernel.py > "$STATE/kernel/server_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/ocr-llama-server", "title": "ocr-llama-server",
 "code_file": "server_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": true, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
echo "Pushed. Open https://www.kaggle.com/code/$KAGGLE_USERNAME/ocr-llama-server, watch the log for"
echo "KILL_URL=... and LLM_URL=..., then: echo <url> > $STATE/kill_url ; echo <url> > $STATE/llm_url"
