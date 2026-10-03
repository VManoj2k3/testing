#!/usr/bin/env bash
# Builds and installs Presenton natively (no Docker), mirroring the upstream
# Dockerfile's layout: app in /app, Python venv in /opt/venv, data in /app_data.
# Needs root, Ubuntu/Debian, and network. Usage: SRC=<presenton checkout> ./setup_presenton.sh
set -euo pipefail
SRC=${SRC:?set SRC to a presenton checkout}
export DEBIAN_FRONTEND=noninteractive
export HF_HOME=/root/.cache/huggingface PRESENTON_FASTEMBED_ICON_CACHE_DIR=/root/.cache/presenton/fastembed-icons
step() { echo "=== [$(date -u +%T)] $*"; }

step "apt packages"
apt-get update -qq
apt-get install -y -qq --no-install-recommends ca-certificates curl nginx fontconfig imagemagick zstd \
  fonts-liberation fonts-noto-core fonts-noto-color-emoji tesseract-ocr tesseract-ocr-eng >/dev/null

if ! node -v 2>/dev/null | grep -q '^v22'; then
  step "node 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi

# Ubuntu's chromium package is a snap stub, so use Google's deb for PDF/PPTX export.
if [ ! -x /usr/bin/google-chrome ]; then
  step "google-chrome"
  curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  apt-get install -y -qq /tmp/chrome.deb >/dev/null
fi

step "patch: DISABLE_THINKING for llama-server"
# Presenton sends top-level `enable_thinking: false` for LLM=custom, which llama-server
# ignores (measured: Qwen still reasoned). llama-server reads chat_template_kwargs.
python3 - "$SRC/servers/fastapi/utils/llm_config.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = '        extra_body["enable_thinking"] = False\n'
new = old + '        extra_body["chat_template_kwargs"] = {"enable_thinking": False}\n'
if new not in s:
    assert s.count(old) == 1, "upstream changed; patch needs updating"
    open(p, "w").write(s.replace(old, new))
PY
grep -n 'chat_template_kwargs' "$SRC/servers/fastapi/utils/llm_config.py"

step "python venv + fastapi deps"
command -v uv >/dev/null || python3 -m pip install -q uv
uv venv -q --python 3.11 /opt/venv
cd "$SRC/servers/fastapi"
uv export -q --frozen --no-dev --no-emit-project -o /tmp/presenton-req.txt
uv pip install -q --python /opt/venv/bin/python -r /tmp/presenton-req.txt
uv pip install -q --python /opt/venv/bin/python --no-deps .
uv pip install -q --python /opt/venv/bin/python \
  "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
/opt/venv/bin/python scripts/warm_fastembed_cache.py

step "nextjs build"
cd "$SRC/servers/nextjs"
# Cypress (e2e tests) and Puppeteer's bundled Chrome are not needed at runtime; skip
# their large downloads (Chrome comes from the deb above).
CYPRESS_INSTALL_BINARY=0 PUPPETEER_SKIP_DOWNLOAD=1 NEXT_TELEMETRY_DISABLED=1 \
  npm ci --no-audit --no-fund --loglevel=error
NEXT_TELEMETRY_DISABLED=1 npm run build >/tmp/presenton-next-build.log 2>&1 || { tail -40 /tmp/presenton-next-build.log; exit 1; }

step "export + document-extraction assets"
rm -rf /app && mkdir -p /app/scripts /app/servers/fastapi /app/servers/nextjs /app/document-extraction-liteparse
(cd /app/document-extraction-liteparse && npm init -y >/dev/null && npm install -q @llamaindex/liteparse@1.5.2 --omit=dev --no-audit --no-fund)
cp "$SRC/electron/resources/document-extraction/liteparse_runner.mjs" /app/document-extraction-liteparse/
cp "$SRC/package.json" /app/
cp "$SRC/scripts/sync-presentation-export.cjs" "$SRC/scripts/run-presentation-export.mjs" \
   "$SRC/scripts/presenton-terminal-banner.mjs" "$SRC/scripts/user-config-env.cjs" /app/scripts/
# The sync finishes its work but can hang on exit with an idle keep-alive socket,
# so bound it and judge success by the files it installs, not its exit code.
(cd /app && timeout 600 node scripts/sync-presentation-export.cjs --force) || echo "sync exited $? (checking files)"
test -f /app/presentation-export/runner.mjs
test -f /app/presentation-export/node_modules/@presenton/export-core/dist/index.js

step "assemble /app"
cp -r "$SRC/servers/fastapi/." /app/servers/fastapi/
cp -r "$SRC/servers/nextjs/.next-build/standalone/." /app/servers/nextjs/
# Merge: the standalone output already has a partial public/, so a plain cp -r would nest it.
mkdir -p /app/servers/nextjs/public && cp -r "$SRC/servers/nextjs/public/." /app/servers/nextjs/public/
mkdir -p /app/servers/nextjs/.next-build && cp -r "$SRC/servers/nextjs/.next-build/static" /app/servers/nextjs/.next-build/static
cp -r "$SRC/templates" /app/templates
cp "$SRC/start.js" "$SRC/LICENSE" "$SRC/NOTICE" /app/
cp "$SRC/nginx.conf" /etc/nginx/nginx.conf
mkdir -p /app_data/{exports,images,uploads,fonts,templates,pptx-to-html,pptx-to-json} /tmp/presenton
step "done"
