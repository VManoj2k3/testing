#!/usr/bin/env bash
# Kill switch: tells the Kaggle run to stop and exit. Uses the newest KILL_URL the run posted
# to its ntfy topic (a saved .state/kill_url can be stale), unless a URL is passed explicitly.
set -euo pipefail
cd "$(dirname "$0")"
URL=${1:-}
if [ -z "$URL" ] && [ -f .state/topic ]; then
  URL=$(curl -fsS "https://ntfy.sh/$(cat .state/topic)/json?poll=1&since=all" | grep -o 'KILL_URL https://[^"\\]*' | tail -1 | cut -d' ' -f2 || true)
fi
[ -n "$URL" ] && curl -fsS -X POST -H "X-Kill-Secret: $(cat .state/secret)" "$URL/shutdown" \
  && { echo "Kill signal accepted."; exit 0; }
echo "Kill endpoint unreachable. Fallback: Kaggle UI > your notebook > Cancel run."
exit 1
