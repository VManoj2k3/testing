#!/usr/bin/env bash
# Builds RAGFlow (Go v1.0) and its web UI from source, natively (no Docker).
# Steps rehearsed in a Ubuntu 24.04 container: Go per go.mod, Clang/LLD 20,
# CMake >= 4, PCRE2, download_deps.py, build.sh --all, web `npm run build`.
# Usage: RAGFLOW_SRC=/path/to/checkout setup_ragflow.sh            (needs root)
set -euo pipefail
SRC=${RAGFLOW_SRC:?set RAGFLOW_SRC}
export DEBIAN_FRONTEND=noninteractive GOTOOLCHAIN=local
step() { echo "=== [$(date -u +%T)] $*"; }
. /etc/os-release

step "toolchain: clang-20, lld-20, pcre2, nginx, openssl"
curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key -o /etc/apt/trusted.gpg.d/apt.llvm.org.asc
echo "deb http://apt.llvm.org/$VERSION_CODENAME/ llvm-toolchain-$VERSION_CODENAME-20 main" > /etc/apt/sources.list.d/llvm20.list
apt-get update -qq
apt-get install -y -qq --no-install-recommends clang-20 lld-20 libpcre2-dev nginx openssl git >/dev/null
python3 -m pip install -q "cmake>=4"
if [ "$(node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/')" != 22 ]; then
  step "node 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi

GO_MINOR=$(sed -n 's/^go \([0-9]*\.[0-9]*\).*/\1/p' "$SRC/go.mod")
if ! /usr/local/goragflow/bin/go version 2>/dev/null | grep -q "go$GO_MINOR"; then
  GOV=$(curl -fsSL 'https://go.dev/dl/?mode=json' | python3 -c "import sys,json;print([r['version'] for r in json.load(sys.stdin) if r['version'].startswith('go$GO_MINOR')][0])")
  step "go $GOV"
  rm -rf /usr/local/goragflow && mkdir -p /usr/local/goragflow
  curl -fsSL "https://go.dev/dl/$GOV.linux-amd64.tar.gz" | tar -C /usr/local/goragflow --strip-components=1 -xz
fi
export PATH=/usr/local/goragflow/bin:$PATH CC=clang-20 CXX=clang++-20

step "native deps + models (download_deps.py)"
python3 -m venv /tmp/ragflow-dl && /tmp/ragflow-dl/bin/pip install -q requests huggingface-hub
(cd "$SRC" && /tmp/ragflow-dl/bin/python ragflow_deps/download_deps.py >/tmp/ragflow-deps.log 2>&1) \
  || { tail -30 /tmp/ragflow-deps.log; exit 1; }

step "build.sh --all"
(cd "$SRC" && bash build.sh --all >/tmp/ragflow-build.log 2>&1) || { grep -iE "error" /tmp/ragflow-build.log | tail -20; tail -20 /tmp/ragflow-build.log; exit 1; }
ls -la "$SRC/bin/ragflow_server"

step "web UI build"
(cd "$SRC/web" && CYPRESS_INSTALL_BINARY=0 PUPPETEER_SKIP_DOWNLOAD=1 npm ci --no-audit --no-fund --loglevel=error >/tmp/ragflow-web.log 2>&1 \
  && NODE_OPTIONS=--max-old-space-size=6144 npm run build >>/tmp/ragflow-web.log 2>&1) || { tail -30 /tmp/ragflow-web.log; exit 1; }
test -f "$SRC/web/dist/index.html"
step "build done"
