#!/usr/bin/env bash
# Pushes gpu_kernel.py to Kaggle as a private 2x T4 run: Qwen + bge-m3 on GPU, RAGFlow v1.0.0-rc1 with
# DeepDoc ingestion on GPU 1 (ragflow_deepdoc_gpu.patch). Needs KAGGLE_API_TOKEN, KAGGLE_USERNAME.
# Optional: MAX_RUNTIME_MIN (240), CTX (32768), NP (1), TENSOR_SPLIT (0.6,0.4), MODEL_REPO, QUANT.
set -euo pipefail
: "${KAGGLE_API_TOKEN:?set KAGGLE_API_TOKEN}" "${KAGGLE_USERNAME:?set KAGGLE_USERNAME}"
cd "$(dirname "$0")"
RF=../kaggle-ragflow
command -v kaggle >/dev/null || pip install -q --upgrade kaggle
STATE=.state; rm -rf "$STATE"; mkdir -p "$STATE/kernel"; chmod 700 "$STATE"
SECRET=$(openssl rand -hex 24); TOPIC=ragflowgpu-$(openssl rand -hex 16)
ADMIN_EMAIL=admin@ragflow.local; ADMIN_PASS=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
echo "$SECRET" > "$STATE/secret"; echo "$TOPIC" > "$STATE/topic"
printf '%s\n%s\n' "$ADMIN_EMAIL" "$ADMIN_PASS" > "$STATE/login"; chmod 600 "$STATE"/*
b64() { base64 -w0 "$1"; }
sed -e "s|__SECRET__|$SECRET|" -e "s|__NTFY_TOPIC__|$TOPIC|" \
    -e "s|__ADMIN_EMAIL__|$ADMIN_EMAIL|" -e "s|__ADMIN_PASS__|$ADMIN_PASS|" \
    -e "s|__MODEL_REPO__|${MODEL_REPO:-Qwen/Qwen3.8-27B}|" -e "s|__QUANT__|${QUANT:-Q4_K_M}|" \
    -e "s|__CTX__|${CTX:-32768}|" -e "s|__NP__|${NP:-1}|" -e "s|__TENSOR_SPLIT__|${TENSOR_SPLIT:-0.6,0.4}|" \
    -e "s|__RAGFLOW_COMMIT__|2400ca8eb51432b1d304266d0de9ca232d9b53fa|" \
    -e "s|__MAX_RUNTIME_MIN__|${MAX_RUNTIME_MIN:-240}|" \
    -e "s|__DEPS_B64__|$(b64 $RF/deps_ragflow.sh)|" -e "s|__SETUP_B64__|$(b64 $RF/setup_ragflow.sh)|" \
    -e "s|__RUN_B64__|$(b64 $RF/run_ragflow.sh)|" -e "s|__BUILD_GPU_B64__|$(b64 $RF/build_gpu_server.sh)|" \
    -e "s|__PATCH_B64__|$(b64 $RF/ragflow_deepdoc_gpu.patch)|" gpu_kernel.py > "$STATE/kernel/gpu_kernel.py"
grep -q "__[A-Z_]*__" "$STATE/kernel/gpu_kernel.py" && { echo "unfilled placeholder"; grep -o "__[A-Z_]*__" "$STATE/kernel/gpu_kernel.py" | sort -u; exit 1; }
cat > "$STATE/kernel/kernel-metadata.json" <<JSON
{"id": "$KAGGLE_USERNAME/ragflow-gpu", "title": "ragflow-gpu",
 "code_file": "gpu_kernel.py", "language": "python", "kernel_type": "script",
 "is_private": true, "enable_gpu": true, "enable_internet": true, "machine_shape": "NvidiaTeslaT4"}
JSON
kaggle kernels push -p "$STATE/kernel"
sleep 20
kaggle kernels status "$KAGGLE_USERNAME/ragflow-gpu"
echo "Launched. Next: ./wait_for_link.sh"
