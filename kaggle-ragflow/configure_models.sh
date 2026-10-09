#!/usr/bin/env bash
# Registers Qwen (chat) and the local bge-m3 (embedding) as OpenAI-API-Compatible providers
# in a running RAGFlow and makes them the account's defaults, via RAGFlow's own API.
# Usage: configure_models.sh <ragflow base url> <email> <password> <qwen /v1 url> <qwen api key> [embed /v1 url] [embed api key]
# The embed URL is from RAGFlow's point of view (default: the bge-m3 server beside it on :8092).
set -euo pipefail
BASE=$1 EMAIL=$2 PW=$3 QWEN_URL=$4 QWEN_KEY=$5 EMBED_URL=${6:-http://127.0.0.1:8092/v1}
# The GPU embedder on the Qwen notebook requires the same key as Qwen; the local CPU one ignores it.
EMBED_KEY=${7:-$QWEN_KEY}
API=$BASE/api/v1 P=OpenAI-API-Compatible
PUB=${RAGFLOW_PUBLIC_PEM:-$(dirname "$0")/public.pem}

# Same encoding as the web UI: RSA-PKCS1v15(public.pem, base64(password)).
enc() { printf %s "$(printf %s "$1" | base64 -w0)" | openssl pkeyutl -encrypt -pubin -inkey "$PUB" -pkeyopt rsa_padding_mode:pkcs1 | base64 -w0; }
TOK=$(curl -s -m 30 -D - -o /dev/null -H 'Content-Type: application/json' "$API/auth/login" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$(enc "$PW")\"}" | grep -i '^authorization:' | cut -d' ' -f2 | tr -d '\r')
[ -n "$TOK" ] || { echo "login failed" >&2; exit 1; }
J() { curl -s -m 60 -X "$1" -H "Authorization: $TOK" -H 'Content-Type: application/json' "$API$2" ${3:+-d "$3"}; echo; }

echo "provider:  $(J PUT /providers "{\"provider_name\":\"$P\"}")"
echo "qwen:      $(J POST /providers/$P/instances "{\"instance_name\":\"kaggle-qwen\",\"api_key\":\"$QWEN_KEY\",\"base_url\":\"$QWEN_URL\"}")"
echo "           $(J POST /providers/$P/instances/kaggle-qwen/models '{"model_name":"qwen3.8-27b","model_type":["chat"],"max_tokens":65536}')"
echo "bge-m3:    $(J POST /providers/$P/instances "{\"instance_name\":\"local-bge-m3\",\"api_key\":\"$EMBED_KEY\",\"base_url\":\"$EMBED_URL\"}")"
echo "           $(J POST /providers/$P/instances/local-bge-m3/models '{"model_name":"bge-m3","model_type":["embedding"],"max_tokens":8192}')"
TID=$(J GET /users/me/models | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["tenant_id"])')
# asr_id and img2txt_id are required by the API even when unused.
echo "defaults:  $(J PATCH /users/me/models "{\"tenant_id\":\"$TID\",\"llm_id\":\"qwen3.8-27b@kaggle-qwen@$P\",\"embd_id\":\"bge-m3@local-bge-m3@$P\",\"asr_id\":\"\",\"img2txt_id\":\"\",\"rerank_id\":\"\",\"tts_id\":\"\"}")"
J GET /users/me/models | python3 -c 'import sys,json;d=json.load(sys.stdin)["data"];print("now:       llm_id =",d["llm_id"],"| embd_id =",d["embd_id"])'
