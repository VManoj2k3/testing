#!/usr/bin/env bash
# Pushes ticket_kernel.py to Kaggle as a private CPU-only run. Needs KAGGLE_API_TOKEN, KAGGLE_USERNAME.
set -euo pipefail
: "${KAGGLE_API_TOKEN:?}" "${KAGGLE_USERNAME:?}"
cd "$(dirname "$0")"
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
KEY=$(openssl rand -hex 24); TOPIC=ticket-$(openssl rand -hex 16)
echo "$KEY" > "$STATE/key"; echo "$TOPIC" > "$STATE/topic"; chmod 600 "$STATE"/*
B64=$(base64 -w0 ../kaggle-ragflow/tests/ticket_mcp.py)
sed -e "s|__KEY__|$KEY|" -e "s|__NTFY_TOPIC__|$TOPIC|" -e "s|__SERVER_B64__|$B64|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-90}|" ticket_kernel.py > "$STATE/kernel/ticket_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/ticket-mcp-test", "title": "ticket-mcp-test",
 "code_file": "ticket_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": false, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
