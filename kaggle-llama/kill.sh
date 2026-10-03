#!/usr/bin/env bash
# Kill switch: tells the Kaggle run to stop llama-server and exit, releasing the GPUs.
set -euo pipefail
cd "$(dirname "$0")"
URL=${1:-$(cat .state/kill_url 2>/dev/null || true)}
if [ -z "$URL" ] && [ -f .state/topic ]; then
  URL=$(curl -fsS "https://ntfy.sh/$(cat .state/topic)/json?poll=1&since=all" | grep -o 'KILL_URL https://[^"]*' | tail -1 | cut -d' ' -f2 || true)
fi
[ -n "$URL" ] && curl -fsS -X POST -H "X-Kill-Secret: $(cat .state/secret)" "$URL/shutdown" \
  && { echo "Kill signal accepted."; exit 0; }
echo "Kill endpoint unreachable. Fallback: Kaggle UI > your notebook > Cancel run."
echo "Status: kaggle kernels status ${KAGGLE_USERNAME:-<user>}/ocr-llama-server"; exit 1
