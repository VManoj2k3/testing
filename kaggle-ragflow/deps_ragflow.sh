#!/usr/bin/env bash
# Installs and starts RAGFlow's backing services natively (no Docker), bound to
# 127.0.0.1 with the ports/credentials from RAGFlow's conf/service_conf.yaml:
#   MySQL 3306, Redis 6379 (stands in for Kvrocks; RAGFlow only uses standard
#   Redis commands), MinIO 9000, NATS 4222 (JetStream), ClickHouse 9900,
#   Elasticsearch 1200.
# Usage: deps_ragflow.sh install | start | status        (needs root)
set -euo pipefail
PW=infini_rag_flow
DATA=${RAGFLOW_DATA:-/var/lib/ragflow-deps}
ES_VERSION=8.11.3 NATS_VERSION=2.14.2
export DEBIAN_FRONTEND=noninteractive PATH=/usr/local/goragflow/bin:/usr/local/go127/bin:$PATH GOTOOLCHAIN=local
step() { echo "=== [$(date -u +%T)] $*"; }

install() {
  # Stop apt postinst scripts from auto-starting mysqld/redis: on hosts without a
  # policy-rc.d (Kaggle) those daemons inherit the caller's stdout pipe and the step never ends.
  # We start every service ourselves in start().
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d
  step "apt: mysql, redis"
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends mysql-server redis-server curl ca-certificates >/dev/null

  if [ ! -x /usr/local/bin/minio ]; then
    # dl.min.io no longer serves community binaries (HTTP 410); build from source.
    step "minio (go install)"
    GOBIN=/usr/local/bin go install github.com/minio/minio@latest
  fi
  if [ ! -x /usr/local/bin/nats-server ]; then
    step "nats-server $NATS_VERSION"
    curl -fsSL "https://github.com/nats-io/nats-server/releases/download/v$NATS_VERSION/nats-server-v$NATS_VERSION-linux-amd64.tar.gz" \
      | tar -xz -C /tmp && mv "/tmp/nats-server-v$NATS_VERSION-linux-amd64/nats-server" /usr/local/bin/
  fi
  if [ ! -x /usr/local/bin/clickhouse ]; then
    step "clickhouse binary"
    curl -fsSL -o /usr/local/bin/clickhouse https://builds.clickhouse.com/master/amd64/clickhouse
    chmod +x /usr/local/bin/clickhouse
  fi
  if [ ! -d /opt/elasticsearch ]; then
    step "elasticsearch $ES_VERSION"
    curl -fsSL "https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-$ES_VERSION-linux-x86_64.tar.gz" | tar -xz -C /opt
    mv "/opt/elasticsearch-$ES_VERSION" /opt/elasticsearch
    id es >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin es
  fi
  if [ ! -d /usr/share/infinity/resource/rag ]; then
    # Analyzer dictionaries the tokenizer loads at startup (RAGFLOW_DICT_PATH default);
    # without them ingestor/api die with "failed to load base analyzer". Same as upstream Dockerfile.
    step "infinity analyzer resources"
    rm -rf /tmp/infinity-resource
    git clone -q --depth 1 --single-branch https://github.com/infiniflow/resource.git /tmp/infinity-resource
    mkdir -p /usr/share/infinity/resource
    for d in rag opencc wordnet; do cp -r "/tmp/infinity-resource/$d" /usr/share/infinity/resource/; done
    rm -rf /tmp/infinity-resource
  fi
  step "install done"
}

wait_port() {  # name port seconds
  for _ in $(seq "$3"); do
    (exec 3<>"/dev/tcp/127.0.0.1/$2") 2>/dev/null && { echo "  $1 up on :$2"; return 0; }
    sleep 1
  done
  echo "  $1 did NOT come up on :$2" >&2
  return 1
}

start_mysql() {
  step "mysql"
  mkdir -p /var/run/mysqld && chown mysql:mysql /var/run/mysqld
  cat > /etc/mysql/mysql.conf.d/zz-ragflow.cnf <<EOF
[mysqld]
bind-address = 127.0.0.1
max_allowed_packet = 1073741824
max_connections = 900
EOF
  (mysqld --user=mysql >"$DATA/logs/mysql.log" 2>&1 &)
  wait_port mysql 3306 120
  if ! mysql -uroot -p"$PW" -h127.0.0.1 -e "SELECT 1" >/dev/null 2>&1; then
    mysql -uroot <<EOF
ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '$PW';
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '$PW';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
CREATE DATABASE IF NOT EXISTS rag_flow;
FLUSH PRIVILEGES;
EOF
  fi
}

start_redis() {
  step "redis (Kvrocks stand-in)"
  redis-server --bind 127.0.0.1 --port 6379 --requirepass "$PW" --daemonize yes \
    --dir "$DATA" --logfile "$DATA/logs/redis.log"
  wait_port redis 6379 30
}

start_minio() {
  step "minio"
  (MINIO_ROOT_USER=rag_flow MINIO_ROOT_PASSWORD="$PW" minio server "$DATA/minio" \
     --address 127.0.0.1:9000 --console-address 127.0.0.1:9001 >"$DATA/logs/minio.log" 2>&1 &)
  wait_port minio 9000 60
}

start_nats() {
  step "nats (JetStream)"
  (nats-server -js -sd "$DATA/nats" -a 127.0.0.1 -p 4222 --http_port 8222 >"$DATA/logs/nats.log" 2>&1 &)
  wait_port nats 4222 30
}

start_clickhouse() {
  step "clickhouse"
  mkdir -p "$DATA/clickhouse"
  cat > "$DATA/clickhouse/config.xml" <<EOF
<clickhouse>
  <listen_host>127.0.0.1</listen_host>
  <tcp_port>9900</tcp_port>
  <http_port>8123</http_port>
  <path>$DATA/clickhouse/data/</path>
  <tmp_path>$DATA/clickhouse/tmp/</tmp_path>
  <user_files_path>$DATA/clickhouse/user_files/</user_files_path>
  <format_schema_path>$DATA/clickhouse/format_schemas/</format_schema_path>
  <users_config>$DATA/clickhouse/users.xml</users_config>
  <logger><level>warning</level><log>$DATA/logs/clickhouse.log</log><errorlog>$DATA/logs/clickhouse.err.log</errorlog></logger>
  <mark_cache_size>268435456</mark_cache_size>
</clickhouse>
EOF
  cat > "$DATA/clickhouse/users.xml" <<EOF
<clickhouse>
  <profiles><default/></profiles>
  <quotas><default/></quotas>
  <users>
    <default><password></password><networks><ip>127.0.0.1</ip></networks><profile>default</profile><quota>default</quota></default>
    <ragflow><password>$PW</password><networks><ip>127.0.0.1</ip><ip>::1</ip></networks>
      <profile>default</profile><quota>default</quota><access_management>1</access_management></ragflow>
  </users>
</clickhouse>
EOF
  (cd "$DATA/clickhouse" && clickhouse server --config-file="$DATA/clickhouse/config.xml" >"$DATA/logs/clickhouse.out" 2>&1 &)
  wait_port clickhouse 9900 90
  clickhouse client --port 9900 --user ragflow --password "$PW" -q "CREATE DATABASE IF NOT EXISTS ragflow"
}

start_es() {
  step "elasticsearch"
  chown -R es:es /opt/elasticsearch "$DATA/es"
  cat > /opt/elasticsearch/config/elasticsearch.yml <<EOF
cluster.name: ragflow
node.name: es01
network.host: 127.0.0.1
http.port: 1200
discovery.type: single-node
path.data: $DATA/es
xpack.security.enabled: true
xpack.security.http.ssl.enabled: false
xpack.security.transport.ssl.enabled: false
xpack.ml.enabled: false
cluster.routing.allocation.disk.watermark.low: 5gb
cluster.routing.allocation.disk.watermark.high: 3gb
cluster.routing.allocation.disk.watermark.flood_stage: 2gb
EOF
  if ! su -s /bin/bash es -c "/opt/elasticsearch/bin/elasticsearch-keystore list" 2>/dev/null | grep -q bootstrap.password; then
    su -s /bin/bash es -c "/opt/elasticsearch/bin/elasticsearch-keystore create -s >/dev/null 2>&1 || true; \
      echo '$PW' | /opt/elasticsearch/bin/elasticsearch-keystore add -x -f bootstrap.password"
  fi
  su -s /bin/bash es -c "ES_JAVA_OPTS='-Xms2g -Xmx2g' /opt/elasticsearch/bin/elasticsearch -d -p $DATA/es/es.pid" \
    >"$DATA/logs/es-start.log" 2>&1 || { tail -30 "$DATA/logs/es-start.log"; return 1; }
  wait_port elasticsearch 1200 180
  for _ in $(seq 60); do
    curl -s -u "elastic:$PW" http://127.0.0.1:1200/_cluster/health | grep -q '"status":"\(green\|yellow\)"' && break
    sleep 2
  done
  curl -s -u "elastic:$PW" http://127.0.0.1:1200/_cluster/health; echo
}

start() {
  mkdir -p "$DATA"/{minio,nats,clickhouse,es,logs}
  start_mysql; start_redis; start_minio; start_nats; start_clickhouse; start_es
  step "all dependencies up"
}

status() {
  for p in mysql:3306 redis:6379 minio:9000 nats:4222 clickhouse:9900 elasticsearch:1200; do
    if (exec 3<>"/dev/tcp/127.0.0.1/${p#*:}") 2>/dev/null; then echo "up   $p"; else echo "DOWN $p"; fi
  done
}

if [ "${1:-status}" = start_one ]; then mkdir -p "$DATA"/logs "$DATA"/es; "start_$2"; else "${1:-status}"; fi
