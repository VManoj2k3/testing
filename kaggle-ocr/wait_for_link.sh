#!/usr/bin/env bash
# Polls the run's ntfy topic until READY (or ERROR). Writes .state/viewer_url and .state/kill_url.
set -euo pipefail
cd "$(dirname "$0")"
TOPIC=$(cat .state/topic); TIMEOUT_MIN=${TIMEOUT_MIN:-45}
for ((i = 0; i < TIMEOUT_MIN * 2; i++)); do
  MSGS=$(curl -fsS "https://ntfy.sh/$TOPIC/json?poll=1&since=all" | python3 -c 'import sys,json
for l in sys.stdin:
    l=l.strip()
    if l and json.loads(l).get("event")=="message": print(json.loads(l)["message"])' || true)
  sed -n 's/^KILL_URL //p' <<<"$MSGS" | tail -1 > .state/kill_url.tmp && [ -s .state/kill_url.tmp ] && mv .state/kill_url.tmp .state/kill_url
  sed -n 's/^VIEWER_URL //p'  <<<"$MSGS" | tail -1 > .state/viewer_url.tmp  && [ -s .state/viewer_url.tmp ]  && mv .state/viewer_url.tmp .state/viewer_url
  if grep -q '^ERROR' <<<"$MSGS"; then echo "$MSGS"; echo "Run failed (see ERROR above)."; exit 1; fi
  if grep -q '^READY' <<<"$MSGS"; then echo "$MSGS"; echo "Viewer URL: $(cat .state/viewer_url)"; exit 0; fi
  echo "[$(date +%T)] waiting... last: $(tail -1 <<<"$MSGS")"
  sleep 30
done
echo "Timed out after $TIMEOUT_MIN min."; exit 1
