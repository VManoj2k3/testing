#!/usr/bin/env bash
# Pushes fleetq_kernel.py to Kaggle as a private CPU run (no GPU quota). Qwen comes from the kaggle-llama
# notebook: its ntfy topic and API key are baked in so FleetQ connects to it once Qwen is up.
# Needs KAGGLE_API_TOKEN, KAGGLE_USERNAME, and ../kaggle-llama/.state/{topic,secret}. Optional: MAX_RUNTIME_MIN (300).
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
Q=../kaggle-llama/.state
[ -s $Q/topic ] && [ -s $Q/secret ] || { echo "launch kaggle-llama first (needs its .state/topic and .state/secret)"; exit 1; }
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=fleetq-$(openssl rand -hex 16)
ADMIN_EMAIL=admin@fleetq.local; ADMIN_PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"
printf '%s\n%s\n' "$ADMIN_EMAIL" "$ADMIN_PASS" > "$STATE/login"; chmod 600 "$STATE"/*
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" \
    -e "s|__ADMIN_EMAIL__|$ADMIN_EMAIL|" -e "s|__ADMIN_PASS__|$ADMIN_PASS|" \
    -e "s|__QWEN_TOPIC__|$(cat $Q/topic)|" -e "s|__QWEN_KEY__|$(cat $Q/secret)|" -e "s|__QWEN_MODEL__|${QWEN_MODEL:-qwen3.8-27b}|" \
    -e "s|__SETUP_B64__|$(base64 -w0 setup_fleetq.sh)|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-300}|" fleetq_kernel.py > "$STATE/kernel/fleetq_kernel.py"
grep -q "__[A-Z_]*__" "$STATE/kernel/fleetq_kernel.py" && { echo "unfilled placeholder:"; grep -o "__[A-Z_]*__" "$STATE/kernel/fleetq_kernel.py" | sort -u; exit 1; }
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/fleetq-server", "title": "fleetq-server",
 "code_file": "fleetq_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": false, "enable_internet": true}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/fleetq-server"
echo "Launched. Next: ./wait_for_link.sh"
