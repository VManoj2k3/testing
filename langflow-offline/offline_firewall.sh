#!/usr/bin/env bash
# Proves "nothing leaves the machine" on Linux: everything run as USER may only reach the
# listed localhost ports; every other outbound attempt is rejected and logged with tcpdump.
# Note: loopback is NOT blanket-allowed, because a local HTTP proxy (127.0.0.1:<port>)
# would otherwise be a way out.
#
# Usage (root):  offline_firewall.sh on  [user] [ports...]   default: lfoffline 7860 8095
#                offline_firewall.sh log                      blocked attempts, grouped by destination
#                offline_firewall.sh off [user]
set -eu
CMD=${1:-}; USER_NAME=${2:-lfoffline}; shift $(( $# > 2 ? 2 : $# )) || true
PORTS=${*:-7860 8095}
LOG=/var/log/lfoff/blocked.txt
case "$CMD" in
  on)
    id "$USER_NAME" >/dev/null 2>&1 || useradd -r -m -s /bin/bash "$USER_NAME"
    uid=$(id -u "$USER_NAME")
    iptables -N LFOFF 2>/dev/null || iptables -F LFOFF
    iptables -A LFOFF -o lo -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN   # replies to local clients
    for p in $PORTS; do iptables -A LFOFF -d 127.0.0.1 -p tcp --dport "$p" -j RETURN; done
    iptables -A LFOFF -j NFLOG --nflog-group 5 --nflog-prefix lfoff
    iptables -A LFOFF -j REJECT
    iptables -C OUTPUT -m owner --uid-owner "$uid" -j LFOFF 2>/dev/null || iptables -I OUTPUT -m owner --uid-owner "$uid" -j LFOFF
    ip6tables -C OUTPUT -m owner --uid-owner "$uid" ! -d ::1 -j REJECT 2>/dev/null \
      || ip6tables -I OUTPUT -m owner --uid-owner "$uid" ! -d ::1 -j REJECT
    command -v tcpdump >/dev/null || apt-get install -y -qq tcpdump >/dev/null
    mkdir -p "$(dirname "$LOG")"
    pgrep -x tcpdump >/dev/null || nohup tcpdump -i nflog:5 -n -l -tttt >> "$LOG" 2>/dev/null &
    echo "offline firewall on for $USER_NAME (uid $uid); allowed: 127.0.0.1 ports $PORTS; log: $LOG"
    ;;
  log)
    echo "blocked DNS lookups (what it tried to reach):"
    grep -oE "A{1,4}\? [A-Za-z0-9.-]+" "$LOG" | sort | uniq -c | sort -rn || true
    echo "blocked connections by destination:"
    grep -v "\.53: " "$LOG" | grep -oE "> [0-9a-f.:]+\.[0-9]+:" | sort | uniq -c | sort -rn || true
    iptables -L LFOFF -n -v | tail -2
    ;;
  off)
    uid=$(id -u "$USER_NAME")
    iptables -D OUTPUT -m owner --uid-owner "$uid" -j LFOFF 2>/dev/null || true
    ip6tables -D OUTPUT -m owner --uid-owner "$uid" ! -d ::1 -j REJECT 2>/dev/null || true
    iptables -F LFOFF 2>/dev/null || true; iptables -X LFOFF 2>/dev/null || true
    pkill -x tcpdump || true
    echo "offline firewall off for $USER_NAME"
    ;;
  *) sed -n 2,9p "$0"; exit 1 ;;
esac
