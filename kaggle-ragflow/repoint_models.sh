#!/usr/bin/env bash
# Repoint a running RAGFlow's model instances (no rebuild): the Qwen chat instance and the
# bge-m3 embedding instance get new base URLs/keys, e.g. after the GPU notebook restarts.
# Usage: repoint_models.sh <ragflow url> <email> <password> <qwen /v1 url> <embed /v1 url> <api key>
set -euo pipefail
BASE=$1 EMAIL=$2 PW=$3 QWEN_URL=$4 EMBED_URL=$5 KEY=$6
API=$BASE/api/v1 P=OpenAI-API-Compatible
PUB=$(dirname "$0")/public.pem
enc() { printf %s "$(printf %s "$1" | base64 -w0)" | openssl pkeyutl -encrypt -pubin -inkey "$PUB" -pkeyopt rsa_padding_mode:pkcs1 | base64 -w0; }
TOK=$(curl -s -m 30 -D - -o /dev/null -H 'Content-Type: application/json' "$API/auth/login" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$(enc "$PW")\"}" | grep -i '^authorization:' | cut -d' ' -f2 | tr -d '\r')
[ -n "$TOK" ] || { echo "login failed" >&2; exit 1; }
put() {  # instance url model type max_tokens
  curl -s -m 60 -X PUT -H "Authorization: $TOK" -H 'Content-Type: application/json' "$API/providers/$P/instances/$1" \
    -d "{\"instance_name\":\"$1\",\"api_key\":\"$KEY\",\"base_url\":\"$2\",\"model_info\":[{\"model_name\":\"$3\",\"model_type\":[\"$4\"],\"max_tokens\":$5}]}"
  echo
}
echo "qwen:   $(put kaggle-qwen "$QWEN_URL" qwen3.8-27b chat 65536)"
echo "bge-m3: $(put local-bge-m3 "$EMBED_URL" bge-m3 embedding 8192)"
curl -s -m 30 -H "Authorization: $TOK" "$API/providers/$P/instances" | python3 -c '
import sys,json
d=json.load(sys.stdin).get("data") or []
d=d if isinstance(d,list) else d.get("instances",[])
for i in d: print("now:   ", i.get("instance_name") or i.get("name"), "->", i.get("base_url"))'
