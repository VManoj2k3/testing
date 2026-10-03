#!/usr/bin/env bash
# Kill switch: tells the Kaggle run to stop llama-server and exit, releasing the GPU.
set -euo pipefail
cd "$(dirname "$0")"
URL=${1:-$(cat .state/kill_url)}
curl -fsS -X POST -H "X-Kill-Secret: $(cat .state/secret)" "$URL/shutdown" \
  && echo "Kill signal accepted." \
  || { echo "Kill endpoint unreachable. Fallback: Kaggle UI > your notebook > Cancel run."; \
       echo "Status: kaggle kernels status ${KAGGLE_USERNAME:-<user>}/ocr-llama-server"; exit 1; }
