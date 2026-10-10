#!/usr/bin/env bash
# Polls ntfy until READY or ERROR. The timeout counts from when the run posts its first message
# (i.e. it is RUNNING), not from push: Kaggle's GPU queue alone took ~35 min once.
set -euo pipefail
cd "$(dirname "$0")"
TOPIC=$(cat .state/topic); TIMEOUT_MIN=${TIMEOUT_MIN:-120}; QUEUE_MAX_MIN=${QUEUE_MAX_MIN:-120}
started=""; t0=$(date +%s)
while :; do
  MSGS=$(curl -fsS "https://ntfy.sh/$TOPIC/json?poll=1&since=all" | python3 -c 'import sys,json
for l in sys.stdin:
    l=l.strip()
    if l and json.loads(l).get("event")=="message": print(json.loads(l)["message"])' || true)
  for k in KILL_URL APP_URL; do
    v=$(sed -n "s/^$k //p" <<<"$MSGS" | tail -1); [ -n "$v" ] && echo "$v" > .state/$(tr A-Z a-z <<<"$k")
  done
  if grep -q '^ERROR' <<<"$MSGS"; then echo "$MSGS"; echo "Run failed (see ERROR above)."; exit 1; fi
  if grep -q '^READY' <<<"$MSGS"; then echo "$MSGS"; echo "RAGFlow URL: $(cat .state/app_url)"; exit 0; fi
  now=$(date +%s)
  if [ -z "$started" ] && [ -n "$MSGS" ]; then started=$now; fi
  if [ -z "$started" ] && (( now - t0 > QUEUE_MAX_MIN * 60 )); then echo "Still queued after $QUEUE_MAX_MIN min."; exit 1; fi
  if [ -n "$started" ] && (( now - started > TIMEOUT_MIN * 60 )); then echo "Timed out $TIMEOUT_MIN min after start."; exit 1; fi
  echo "[$(date +%T)] ${started:+running }waiting... last: $(tail -1 <<<"$MSGS" | cut -c1-160)"
  sleep 30
done
