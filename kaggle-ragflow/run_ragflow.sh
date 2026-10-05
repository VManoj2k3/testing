#!/usr/bin/env bash
# Runs a source-built RAGFlow (Go v1.0): migrate, start admin/ingestor/syncer/api
# in the documented order, and serve the built web UI with nginx using upstream's
# docker/nginx config (only the web root path and the bind address are changed).
# Usage: RAGFLOW_SRC=<checkout> run_ragflow.sh start | stop | health     (needs root)
set -euo pipefail
SRC=${RAGFLOW_SRC:?set RAGFLOW_SRC to the built ragflow checkout}
LOGS=${RAGFLOW_LOGS:-/var/log/ragflow}
PORT=${RAGFLOW_WEB_PORT:-80}
step() { echo "=== [$(date -u +%T)] $*"; }

health() {
  for _ in $(seq "${1:-90}"); do
    out=$(curl -s -m 5 http://127.0.0.1:9380/api/v1/system/healthz || true)
    if grep -q '"status":"ok"' <<<"$out"; then echo "$out"; return 0; fi
    sleep 2
  done
  echo "health check failed: ${out:-no response}" >&2
  return 1
}

start() {
  mkdir -p "$LOGS"
  cd "$SRC"
  step "migrate"
  ./bin/ragflow_server --migrate >"$LOGS/migrate.log" 2>&1 || { tail -20 "$LOGS/migrate.log"; exit 1; }
  for m in admin ingestor syncer api; do
    step "start $m"
    (RAGFLOW_DEV_MODE=true nohup ./bin/ragflow_server --"$m" >"$LOGS/$m.log" 2>&1 &)
    if [ "$m" = admin ]; then sleep 6; fi  # upstream: start Admin before the other services
  done
  step "health"
  if ! health 90; then
    for m in admin ingestor syncer api; do echo "--- $m"; grep -iE "error|fatal|panic" "$LOGS/$m.log" | tail -3; done
    exit 1
  fi

  step "nginx (web UI on :$PORT)"
  mkdir -p /etc/nginx/conf.d
  cp "$SRC/docker/nginx/proxy.conf" /etc/nginx/proxy.conf
  sed -e "s|root /ragflow/web/dist;|root $SRC/web/dist;|" -e "s|listen 80;|listen 127.0.0.1:$PORT;|" \
    "$SRC/docker/nginx/ragflow.conf" > /etc/nginx/conf.d/ragflow.conf
  cp "$SRC/docker/nginx/nginx.conf" /etc/nginx/nginx.conf
  rm -f /etc/nginx/sites-enabled/default
  nginx -t 2>&1 | tail -1
  nginx -s reload 2>/dev/null || nginx
  for _ in $(seq 30); do curl -s -o /dev/null http://127.0.0.1:"$PORT"/ && break; sleep 1; done
  step "up: web $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:"$PORT"/), api $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:"$PORT"/api/v1/system/healthz)"
}

# The web UI sends RSA-PKCS1v15(public.pem, base64(password)), and the server hashes
# whatever it decrypts, so API-created accounts must be encrypted the same way or the
# browser login would never match.
enc_pw() {
  printf %s "$(printf %s "$1" | base64 -w0)" \
    | openssl pkeyutl -encrypt -pubin -inkey "$SRC/conf/public.pem" -pkeyopt rsa_padding_mode:pkcs1 | base64 -w0
}

restart_api() {  # restart only the API process with ENABLE_REGISTER=$1
  for pid in $(ps -eo pid,args | awk '$2 ~ /ragflow_server$/ && $3 == "--api" {print $1}'); do kill "$pid"; done
  for _ in $(seq 20); do curl -s -o /dev/null -m 2 http://127.0.0.1:9380/ || break; sleep 1; done
  (cd "$SRC" && ENABLE_REGISTER="$1" RAGFLOW_DEV_MODE=true nohup ./bin/ragflow_server --api >>"$LOGS/api.log" 2>&1 </dev/null &)
  health 60 >/dev/null
}

# Usage: create_admin <email> <password>. Sign-up is off by default in RAGFlow 1.0, so
# enable it just long enough to register this one account, then turn it off again so
# nobody else with the public link can sign up.
create_admin() {
  local email=$1 pw=$2 api=http://127.0.0.1:9380/api/v1 out=$LOGS/create_admin.json
  step "api with sign-up enabled"
  restart_api 1
  step "register $email"
  curl -s -m 30 -o "$out" -H 'Content-Type: application/json' "$api/users" \
    -d "{\"email\":\"$email\",\"nickname\":\"admin\",\"password\":\"$(enc_pw "$pw")\"}"
  cut -c1-200 "$out"; echo
  step "api with sign-up disabled"
  restart_api 0
  step "verify"
  curl -s -m 30 -o "$out" -H 'Content-Type: application/json' "$api/auth/login" \
    -d "{\"email\":\"$email\",\"password\":\"$(enc_pw "$pw")\"}"
  echo "login:   $(cut -c1-160 "$out")"
  curl -s -m 30 -o "$out" -H 'Content-Type: application/json' "$api/users" \
    -d "{\"email\":\"intruder@example.com\",\"nickname\":\"x\",\"password\":\"$(enc_pw x)\"}"
  echo "sign-up: $(cut -c1-160 "$out")"
}

stop() {
  nginx -s stop 2>/dev/null || true
  for pid in $(ps -eo pid,args | awk '$2 ~ /ragflow_server$/ {print $1}'); do kill "$pid"; done
}

"${1:-health}" "${@:2}"
