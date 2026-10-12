#!/usr/bin/env bash
# Pushes langflow_kernel.py to Kaggle as a private 2x T4 run: Qwen 27B (llama.cpp CUDA) + Langflow in one
# notebook. Needs KAGGLE_API_TOKEN, KAGGLE_USERNAME.
# Optional: MAX_RUNTIME_MIN (240), CTX (65536), NP (2), TENSOR_SPLIT (1,1), MODEL_REPO, QUANT, LANGFLOW_VERSION.
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
LO=../langflow-offline
command -v kaggle >/dev/null || pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=langflowdemo-$(openssl rand -hex 16)
ADMIN_PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"
printf 'admin\n%s\n' "$ADMIN_PASS" > "$STATE/login"; chmod 600 "$STATE"/*
b64() { base64 -w0 "$1"; }
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" -e "s|__ADMIN_PASS__|$ADMIN_PASS|" \
    -e "s|__MODEL_REPO__|${MODEL_REPO:-Qwen/Qwen3.8-27B}|" -e "s|__QUANT__|${QUANT:-Q4_K_M}|" \
    -e "s|__CTX__|${CTX:-65536}|" -e "s|__NP__|${NP:-2}|" -e "s|__TENSOR_SPLIT__|${TENSOR_SPLIT:-1,1}|" \
    -e "s|__LANGFLOW_VERSION__|${LANGFLOW_VERSION:-1.12.5}|" -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-240}|" \
    -e "s|__PHASES_B64__|$(b64 lf_phases.py)|" -e "s|__DRIVE_B64__|$(b64 $LO/lf_drive.py)|" \
    -e "s|__ENV_B64__|$(b64 $LO/langflow.env.example)|" langflow_kernel.py > "$STATE/kernel/langflow_kernel.py"
grep -q "__[A-Z_]*__" "$STATE/kernel/langflow_kernel.py" && { echo "unfilled placeholder"; grep -o "__[A-Z_]*__" "$STATE/kernel/langflow_kernel.py" | sort -u; exit 1; }
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/langflow-demo", "title": "langflow-demo",
 "code_file": "langflow_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": true, "enable_internet": true, "machine_shape": "NvidiaTeslaT4"}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/langflow-demo"
echo "Launched. Next: ./wait_for_link.sh"
