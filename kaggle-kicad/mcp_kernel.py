# Runs INSIDE a Kaggle CPU session. Installs KiCad 9 + mcp-server-kicad, serves
# it over streamable HTTP (bearer-token auth) behind a Cloudflare quick tunnel,
# reports links via ntfy, and listens for a kill switch.
# __PLACEHOLDERS__ are substituted by launch.sh.
import base64, json, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")  # dead-man switch: hard stop
MCP_HTTP_PY = base64.b64decode("__MCP_HTTP_B64__").decode()
MCP_PORT, KILL_PORT = 8090, 8081
WORKDIR = "/kaggle/working/project"
procs = []

def notify(msg):
    print(f"[notify] {msg}", flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(), method="POST"), timeout=10)
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)

def sh(cmd):
    print("+", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(r.stdout, flush=True)
    if r.returncode:
        raise RuntimeError(f"`{cmd[:80]}` exit {r.returncode}: ...{r.stdout[-1200:]}")
    return r.stdout

def shutdown(reason, error=False):
    notify(f"{'ERROR' if error else 'STOPPED'} {reason}")
    for p in procs:
        try: p.terminate()
        except Exception: pass
    time.sleep(3)
    for p in procs:
        try: p.kill()
        except Exception: pass
    os._exit(1 if error else 0)  # ends the Kaggle run

class KillHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/shutdown" and self.headers.get("X-Kill-Secret") == SECRET:
            self.send_response(200); self.end_headers(); self.wfile.write(b"bye\n")
            threading.Thread(target=shutdown, args=("kill switch",)).start()
        else:
            self.send_response(403); self.end_headers()
    def log_message(self, *a): pass

def tunnel(port):
    p = subprocess.Popen(["/tmp/cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                         stderr=subprocess.PIPE, text=True)
    procs.append(p)
    for line in p.stderr:
        m = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", line)  # skip api.trycloudflare.com in error lines
        if m:
            threading.Thread(target=lambda: [None for _ in p.stderr], daemon=True).start()
            return m.group(0)
    raise RuntimeError("cloudflared exited without a URL")

def mcp_call(sid, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{MCP_PORT}/mcp", data=json.dumps(payload).encode(),
                                 method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {SECRET}", "MCP-Protocol-Version": "2025-06-18",
        **({"Mcp-Session-Id": sid} if sid else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = [l[6:] for l in r.read().decode().splitlines() if l.startswith("data: ")]
        return r.headers.get("Mcp-Session-Id") or sid, (json.loads(data[-1]) if data else None)

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    # Kill switch is up before the slow steps so it works at any point.
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")

    os.environ["DEBIAN_FRONTEND"] = "noninteractive"
    notify("OS " + sh(". /etc/os-release && echo $PRETTY_NAME").strip())
    sh("apt-get update -qq && apt-get install -y -qq software-properties-common python3-venv default-jre-headless")
    sh("add-apt-repository -y ppa:kicad/kicad-9.0-releases && apt-get update -qq")
    sh("apt-get install -y -qq --no-install-recommends kicad kicad-symbols kicad-footprints")
    notify("KICAD " + sh("kicad-cli version").strip().splitlines()[-1])

    # System python owns the pcbnew bindings; the venv sees them via system site-packages.
    # ensurepip is broken for the system python on Kaggle, so bootstrap pip by hand.
    notify("PY " + sh("/usr/bin/python3 -V; dpkg -L python3-pcbnew 2>/dev/null | grep -m1 'pcbnew.py$' || true").strip().replace("\n", " | "))
    sh("/usr/bin/python3 -m venv --without-pip --system-site-packages /tmp/kvenv && "
       "curl -fsSL https://bootstrap.pypa.io/get-pip.py | /tmp/kvenv/bin/python - -q && "
       "/tmp/kvenv/bin/python -m pip install -q mcp-server-kicad uvicorn")
    try:
        sh("/tmp/kvenv/bin/python -c 'import pcbnew; print(\"pcbnew\", pcbnew.Version())'")
        notify("PCBNEW ok")
    except RuntimeError:
        notify("PCBNEW missing: fill_zones/autoroute_pcb will fail; other tools are fine")

    os.makedirs(WORKDIR, exist_ok=True)
    with open("/tmp/mcp_http.py", "w") as f:
        f.write(MCP_HTTP_PY)
    server = subprocess.Popen(["/tmp/kvenv/bin/python", "/tmp/mcp_http.py"],
                              env={**os.environ, "MCP_TOKEN": SECRET, "PORT": str(MCP_PORT), "MCP_CWD": WORKDIR})
    procs.append(server)
    for _ in range(60):
        try:
            sid, _ = mcp_call(None, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}}})
            break
        except Exception:
            if server.poll() is not None:
                shutdown("mcp server crashed on startup", error=True)
            time.sleep(2)
    else:
        shutdown("mcp server never answered initialize", error=True)
    mcp_call(sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    _, tools = mcp_call(sid, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    notify(f"TOOLS {len(tools['result']['tools'])}")
    notify(f"MCP_URL {tunnel(MCP_PORT)}/mcp")
    notify("READY kicad-mcp")
    server.wait()
    shutdown("mcp server exited", error=True)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
