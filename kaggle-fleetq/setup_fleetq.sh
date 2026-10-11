#!/usr/bin/env bash
# Installs FleetQ (escapeboy/agent-fleet-o, Laravel 13) natively on Ubuntu (no Docker): PHP 8.4 + extensions
# from ppa:ondrej/php, PostgreSQL 17 + pgvector (PGDG), Redis, Node, Composer; builds and migrates the app,
# creates the admin with a real password, and serves it with nginx + php-fpm (Reverb proxied on /app/).
# Usage: APP_URL=https://<host> ADMIN_EMAIL=.. ADMIN_PASS=.. setup_fleetq.sh        (root)
set -euo pipefail
: "${APP_URL:?}" "${ADMIN_EMAIL:?}" "${ADMIN_PASS:?}"
SRC=${FLEETQ_SRC:-/opt/fleetq}; DBPASS=$(openssl rand -hex 12); HOST=${APP_URL#https://}
export DEBIAN_FRONTEND=noninteractive COMPOSER_ALLOW_SUPERUSER=1
step() { echo "=== [$(date -u +%T)] $*"; }
. /etc/os-release
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d   # no auto-start

step "apt: php 8.4, postgres 17 + pgvector, redis, nginx"
apt-get update -qq && apt-get install -y -qq --no-install-recommends software-properties-common ca-certificates curl gnupg lsb-release >/dev/null
add-apt-repository -y ppa:ondrej/php >/dev/null
install -d /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $VERSION_CODENAME-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq --no-install-recommends php8.4-cli php8.4-fpm php8.4-pgsql php8.4-zip php8.4-intl php8.4-bcmath \
  php8.4-gd php8.4-mbstring php8.4-xml php8.4-curl php8.4-redis php8.4-opcache postgresql-17 postgresql-17-pgvector \
  redis-server nginx git unzip >/dev/null
php -v | head -1
if [ "$(node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/')" -lt 20 ] 2>/dev/null || ! command -v node >/dev/null; then
  step "node 22"; curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null; apt-get install -y -qq nodejs >/dev/null
fi
command -v composer >/dev/null || curl -fsSL https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer >/dev/null

step "postgres + redis"
pg_ctlcluster 17 main start
su postgres -c "psql -qc \"CREATE ROLE agent_fleet LOGIN SUPERUSER PASSWORD '$DBPASS'\""   # migrations create a role + extensions
su postgres -c "createdb -O agent_fleet agent_fleet"
redis-server --daemonize yes --bind 127.0.0.1 >/dev/null

step "clone + composer + npm build"
rm -rf "$SRC" && git clone -q --depth 1 https://github.com/escapeboy/agent-fleet-o.git "$SRC"
cd "$SRC" && git log -1 --format='commit %h %cs %s'
cp .env.example .env
setenv() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
setenv APP_ENV local; setenv APP_DEBUG false; setenv APP_URL "$APP_URL"; setenv APP_AUTH_BYPASS false
setenv DB_HOST 127.0.0.1; setenv DB_PASSWORD "$DBPASS"; setenv REDIS_HOST 127.0.0.1
setenv LOCAL_LLM_ENABLED true; setenv LOCAL_LLM_SSRF_PROTECTION true; setenv LOCAL_LLM_TIMEOUT 600
setenv REVERB_HOST 127.0.0.1; setenv REVERB_PORT 8081; setenv REVERB_SCHEME http
setenv VITE_REVERB_HOST "$HOST"; setenv VITE_REVERB_PORT 443; setenv VITE_REVERB_SCHEME https
setenv SESSION_SECURE_COOKIE true
composer install -q --no-interaction --no-dev --optimize-autoloader
php artisan key:generate --force -q
npm ci --no-audit --no-fund --loglevel=error && npm run build >/tmp/vite.log 2>&1 || { tail -20 /tmp/vite.log; exit 1; }

step "migrate + install"
php artisan migrate --force -q
# --force + no TTY would create admin@fleetq.local / "password"; the password is replaced right after.
printf 'Admin\n%s\n\n' "$ADMIN_EMAIL" | php artisan app:install --force --no-interaction >/tmp/install.log 2>&1 || { tail -30 /tmp/install.log; exit 1; }
php artisan tinker --execute="\$u=App\Models\User::first(); \$u->email='$ADMIN_EMAIL'; \$u->password=Illuminate\Support\Facades\Hash::make('$ADMIN_PASS'); \$u->save(); echo 'admin='.\$u->email.PHP_EOL;"
php artisan storage:link -q || true
php artisan config:cache -q && php artisan route:cache -q || true
chown -R www-data:www-data storage bootstrap/cache

step "sidecars: mjml, searxng, browserless shim (native, no Docker)"
# mjml: FleetQ's own docker/mjml server.js, run with node (email template rendering)
mkdir -p /opt/mjml && cp docker/mjml/server.js /opt/mjml/ && (cd /opt/mjml && npm init -y >/dev/null && npm install --no-audit --no-fund --loglevel=error mjml express)
# SearXNG (web search) from source in a venv, with FleetQ's settings.yml (JSON output on, limiter off)
apt-get install -y -qq --no-install-recommends python3-venv python3-dev build-essential libxml2-dev libxslt1-dev zlib1g-dev >/dev/null
rm -rf /opt/searxng && git clone -q --depth 1 https://github.com/searxng/searxng /opt/searxng
mkvenv() { python3 -m venv --without-pip "$1" && curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$1/bin/python" - -q; }   # Kaggle's ensurepip is broken
mkvenv /opt/searxng/venv && /opt/searxng/venv/bin/pip install -q -U pip setuptools wheel pyyaml msgspec
(cd /opt/searxng && /opt/searxng/venv/bin/pip install -q --use-pep517 --no-build-isolation -e .)
SXKEY=$(openssl rand -hex 16); sed "s|\${SEARXNG_SECRET_KEY:-[^}]*}|$SXKEY|" docker/searxng/settings.yml > /opt/searxng/settings.yml
# browserless-compatible shim on Playwright Chromium (FleetQ only calls /screenshot, /content, /pdf)
mkvenv /opt/browserless && /opt/browserless/bin/pip install -q playwright && /opt/browserless/bin/playwright install --with-deps chromium >/dev/null
BLTOKEN=$(openssl rand -hex 16); echo "$BLTOKEN" > /opt/browserless/token
setenv MJML_SERVER_URL http://127.0.0.1:15500; setenv SEARXNG_URL http://127.0.0.1:8888; setenv WEB_SEARCH_DRIVER searxng
setenv BROWSERLESS_URL http://127.0.0.1:3000; setenv BROWSERLESS_TOKEN "$BLTOKEN"
php artisan config:cache -q

step "nginx + php-fpm"
cat > /etc/nginx/sites-enabled/default <<NGINX
server {
    listen 127.0.0.1:80;
    root $SRC/public;
    index index.php;
    client_max_body_size 64m;
    # Open self-registration is hard-wired on (Fortify); the admin exists, so close it at the edge.
    location ~ ^/(register|setup)(/|\$) { return 403; }
    location /app/ { proxy_pass http://127.0.0.1:8081; proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade; proxy_set_header Connection "Upgrade"; proxy_set_header Host \$host; }
    location / { try_files \$uri \$uri/ /index.php?\$query_string; }
    location ~ \.php\$ { fastcgi_pass unix:/run/php/php8.4-fpm.sock; include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME \$realpath_root\$fastcgi_script_name; fastcgi_param HTTPS on; fastcgi_read_timeout 600; }
    location ~ /\.(?!well-known).* { deny all; }
}
NGINX
mkdir -p /run/php && php-fpm8.4 -D && (nginx -t 2>&1 | tail -1) && (nginx -s reload 2>/dev/null || nginx)
step "setup done: web $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/login), register $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/register)"
