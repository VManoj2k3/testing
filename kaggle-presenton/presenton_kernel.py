# Runs INSIDE a Kaggle CPU session. Builds Presenton natively (no Docker), points
# it at the Qwen llama-server, serves it behind a Cloudflare quick tunnel with
# Presenton's own login, reports via ntfy, and listens for a kill switch.
# __PLACEHOLDERS__ are substituted by launch.sh.
import base64, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")  # dead-man switch: hard stop
SETUP_SH = base64.b64decode("__SETUP_B64__").decode()
APP_ENV = {
    "LLM": "custom", "CUSTOM_LLM_URL": "__LLM_URL__", "CUSTOM_LLM_API_KEY": "__LLM_KEY__",
    "CUSTOM_MODEL": "__LLM_MODEL__", "DISABLE_THINKING": "true",
    "AUTH_USERNAME": "__AUTH_USER__", "AUTH_PASSWORD": "__AUTH_PASS__",
    "CAN_CHANGE_KEYS": "false", "DISABLE_IMAGE_GENERATION": "true",
    "PRESENTON_COMMUNITY_ENABLED": "false",
    "APP_DATA_DIRECTORY": "/app_data", "TEMP_DIRECTORY": "/tmp/presenton",
    "EXPORT_PACKAGE_ROOT": "/app/presentation-export", "PRESENTON_APP_ROOT": "/app",
    "HF_HOME": "/root/.cache/huggingface",
    "PRESENTON_FASTEMBED_ICON_CACHE_DIR": "/root/.cache/presenton/fastembed-icons",
    "NODE_ENV": "production", "START_OLLAMA": "false",
    "PUPPETEER_EXECUTABLE_PATH": "/usr/bin/google-chrome",
}
KILL_PORT = 8081
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
        raise RuntimeError(f"`{cmd[:80]}` exit {r.returncode}: ...{r.stdout[-1500:]}")
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
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            threading.Thread(target=lambda: [None for _ in p.stderr], daemon=True).start()
            return m.group(0)
    raise RuntimeError("cloudflared exited without a URL")

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    # Kill switch is up before the slow build so it works at any point.
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")
    # Tunnel the app port before starting the app, so PRESENTON_PUBLIC_URL is known.
    app_url = tunnel(80)
    notify(f"APP_URL_PENDING {app_url}")

    sh("rm -rf /tmp/presenton-src && git clone -q --depth 1 https://github.com/presenton/presenton /tmp/presenton-src")
    notify("COMMIT " + sh("git -C /tmp/presenton-src log -1 --format='%h %cs %s'").strip())
    with open("/tmp/setup_presenton.sh", "w") as f:
        f.write(SETUP_SH)
    t0 = time.time()
    sh("SRC=/tmp/presenton-src bash /tmp/setup_presenton.sh")
    notify(f"BUILT in {int(time.time() - t0)}s")

    env = {**os.environ, **APP_ENV, "PRESENTON_PUBLIC_URL": app_url,
           "PATH": "/opt/venv/bin:" + os.environ["PATH"]}
    log = open("/tmp/presenton.log", "w")
    app = subprocess.Popen(["node", "/app/start.js"], cwd="/app", env=env, stdout=log, stderr=subprocess.STDOUT)
    procs.append(app)
    for _ in range(300):
        if app.poll() is not None:
            break
        try:
            urllib.request.urlopen("http://127.0.0.1:80/", timeout=5)
            break
        except urllib.error.HTTPError:
            break  # nginx + app answered (e.g. a redirect to login)
        except Exception:
            time.sleep(2)
    if app.poll() is not None:
        log.flush()
        shutdown("presenton exited: " + open("/tmp/presenton.log").read()[-1500:], error=True)
    notify(f"APP_URL {app_url}")
    notify("READY presenton")
    app.wait()
    log.flush()
    shutdown("presenton exited: " + open("/tmp/presenton.log").read()[-1500:], error=True)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
