#!/usr/bin/env bash
# Pushes ragflow_kernel.py to Kaggle as a private CPU-only run (no GPU quota used).
# Needs: KAGGLE_API_TOKEN, KAGGLE_USERNAME. Optional: MAX_RUNTIME_MIN (default 300).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
command -v kaggle >/dev/null || pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=ragflow-$(openssl rand -hex 16)
ADMIN_EMAIL=admin@ragflow.local; ADMIN_PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"
printf '%s\n%s\n' "$ADMIN_EMAIL" "$ADMIN_PASS" > "$STATE/login"; chmod 600 "$STATE"/*
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" \
    -e "s|__ADMIN_EMAIL__|$ADMIN_EMAIL|" -e "s|__ADMIN_PASS__|$ADMIN_PASS|" \
    -e "s|__DEPS_B64__|$(base64 -w0 deps_ragflow.sh)|" -e "s|__SETUP_B64__|$(base64 -w0 setup_ragflow.sh)|" \
    -e "s|__RUN_B64__|$(base64 -w0 run_ragflow.sh)|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-300}|" ragflow_kernel.py > "$STATE/kernel/ragflow_kernel.py"
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/ragflow-server", "title": "ragflow-server",
 "code_file": "ragflow_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": false, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/ragflow-server"
echo "Launched. Next: ./wait_for_link.sh"
