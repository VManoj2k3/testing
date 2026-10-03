#!/usr/bin/env bash
# Pushes mcp_kernel.py to Kaggle as a private CPU-only run (no GPU quota used).
# Needs: KAGGLE_API_TOKEN, KAGGLE_USERNAME. Optional: MAX_RUNTIME_MIN (default 300).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
command -v kaggle >/dev/null || pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=kicad-$(openssl rand -hex 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"; chmod 600 "$STATE"/*
B64=$(base64 -w0 mcp_http.py)
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" -e "s|__MCP_HTTP_B64__|$B64|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-300}|" mcp_kernel.py > "$STATE/kernel/mcp_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/kicad-mcp-server", "title": "kicad-mcp-server",
 "code_file": "mcp_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": false, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/kicad-mcp-server"
echo "Launched. Next: ./wait_for_link.sh"
