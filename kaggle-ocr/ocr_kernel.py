# Runs INSIDE a Kaggle CPU session. Builds open-code-review and serves app.py (start
# reviews of public GitHub code from a browser, plus ocr's session viewer) behind a
# Cloudflare quick tunnel with HTTP Basic auth. LLM is Qwen on llama-server. Reports via ntfy; kill switch included.
# __PLACEHOLDERS__ are substituted by launch.sh.
import base64, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")  # dead-man switch: hard stop
LLM_URL, LLM_KEY, LLM_MODEL = "__LLM_URL__", "__LLM_KEY__", "__LLM_MODEL__"
APP_USER, APP_PASS = "__APP_USER__", "__APP_PASS__"
APP_PY = base64.b64decode("__APP_B64__").decode()
GO_VERSION = "1.25.5"
REPO, SRC = "https://github.com/alibaba/open-code-review", "/kaggle/working/open-code-review"
OCR = f"{SRC}/dist/opencodereview"
VIEWER_PORT, APP_PORT, KILL_PORT = 5483, 8080, 8081
procs = []

def notify(msg):
    print(f"[notify] {msg}", flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(), method="POST"), timeout=10)
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)

def sh(cmd, check=True, timeout=None):
    print("+", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    print(r.stdout[-4000:], flush=True)
    if check and r.returncode:
        raise RuntimeError(f"`{cmd[:80]}` exit {r.returncode}: ...{r.stdout[-1500:]}")
    return r

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

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")

    sh(f"curl -fsSL https://go.dev/dl/go{GO_VERSION}.linux-amd64.tar.gz | tar -C /usr/local -xz")
    os.environ["PATH"] = "/usr/local/go/bin:" + os.environ["PATH"]
    os.environ["GOTOOLCHAIN"] = "local"
    sh(f"rm -rf {SRC} && git clone -q --depth 30 {REPO} {SRC}")
    sh(f"cd {SRC} && make build")
    notify("OCR " + sh(f"{OCR} --version").stdout.strip().splitlines()[0])

    for k, v in [("provider", "kaggle-qwen"), ("custom_providers.kaggle-qwen.url", LLM_URL),
                 ("custom_providers.kaggle-qwen.protocol", "openai"),
                 ("custom_providers.kaggle-qwen.model", LLM_MODEL),
                 ("custom_providers.kaggle-qwen.api_key", LLM_KEY),
                 ("custom_providers.kaggle-qwen.timeout_sec", "1800")]:
        subprocess.run([OCR, "config", "set", k, v], check=True, capture_output=True)

    # ocr's viewer stays on loopback (its host guard accepts 127.0.0.1); app.py fronts it,
    # adds the /run page, and puts everything behind HTTP Basic auth.
    viewer = subprocess.Popen([OCR, "viewer", "--addr", f"127.0.0.1:{VIEWER_PORT}", "--open=never", "--color", "never"])
    procs.append(viewer)
    with open("/tmp/app.py", "w") as f:
        f.write(APP_PY)
    app = subprocess.Popen(["python3", "/tmp/app.py"], env={
        **os.environ, "APP_USER": APP_USER, "APP_PASS": APP_PASS, "OCR_BIN": OCR,
        "VIEWER": f"http://127.0.0.1:{VIEWER_PORT}", "WORK_DIR": "/kaggle/working/ocr-jobs",
        "PORT": str(APP_PORT), "MODEL_NAME": LLM_MODEL})
    procs.append(app)
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/run", timeout=3)
        except urllib.error.HTTPError:
            break  # 401 = app is up and enforcing auth
        except Exception:
            time.sleep(1)
    app_url = tunnel(APP_PORT)
    notify(f"APP_URL {app_url}/run")
    notify("READY app")
    while viewer.poll() is None and app.poll() is None:
        time.sleep(10)
    shutdown("viewer or app exited", error=True)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
