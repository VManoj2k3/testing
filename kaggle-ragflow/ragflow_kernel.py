# Runs INSIDE a Kaggle CPU session. Builds RAGFlow (Go v1.0) + web UI from source and runs
# it natively (no Docker) with MySQL/Redis/MinIO/NATS/ClickHouse/Elasticsearch, a local bge-m3
# embedding server (llama.cpp CPU), a single admin account (sign-up disabled), and a Cloudflare
# quick tunnel. Reports via ntfy; kill switch included. __PLACEHOLDERS__ filled by launch.sh.
import base64, json, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")
ADMIN_EMAIL, ADMIN_PASS = "__ADMIN_EMAIL__", "__ADMIN_PASS__"
SCRIPTS = {name: base64.b64decode(b).decode() for name, b in [
    ("deps_ragflow.sh", "__DEPS_B64__"), ("setup_ragflow.sh", "__SETUP_B64__"), ("run_ragflow.sh", "__RUN_B64__")]}
SRC = "/opt/ragflow"
EMBED_PORT, WEB_PORT, KILL_PORT = 8092, 80, 8081
procs = []

def notify(msg):
    print(f"[notify] {msg}", flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(), method="POST"), timeout=10)
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)

_run_no = [0]

def _run_logged(cmd, timeout_s, env, on_line):
    """Run cmd with output to a log file and poll for exit. Never waits for pipe EOF: daemons a
    script starts can inherit its output and keep a pipe open forever after the script exits."""
    _run_no[0] += 1
    path = f"/tmp/step-{_run_no[0]}.log"
    print("+", cmd, "->", path, flush=True)
    with open(path, "w") as out:
        p = subprocess.Popen(cmd, shell=True, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env={**os.environ, **(env or {})}, start_new_session=True)
    deadline, pos, lines = time.time() + timeout_s, 0, []
    while True:
        rc = p.poll()
        with open(path, errors="replace") as f:
            f.seek(pos)
            chunk = f.read()
            pos = f.tell()
        for line in chunk.splitlines():
            print(line, flush=True)
            lines = (lines + [line])[-40:]
            on_line(line)
        if rc is not None:
            return rc, lines, open(path, errors="replace").read()
        if time.time() > deadline:
            p.kill()
            raise RuntimeError(f"`{cmd[:50]}` timed out after {timeout_s}s; last lines: " + " | ".join(lines[-12:])[-1400:])
        time.sleep(2)

def sh(cmd, env=None, timeout_s=1800):
    rc, lines, full = _run_logged(cmd, timeout_s, env, lambda l: None)
    if rc:
        raise RuntimeError(f"`{cmd[:60]}` exit {rc}: ...{full[-1500:]}")
    return full

def sh_steps(cmd, timeout_s, env=None):
    """Like sh(), forwarding '=== step' lines to ntfy as they appear."""
    def fwd(line):
        if line.startswith("=== "):
            notify("STEP " + line[4:].strip()[:200])
    rc, lines, _ = _run_logged(cmd, timeout_s, env, fwd)
    if rc:
        raise RuntimeError(f"`{cmd[:50]}` exit {rc}: " + " | ".join(lines[-15:])[-1400:])

def shutdown(reason, error=False):
    notify(f"{'ERROR' if error else 'STOPPED'} {reason}")
    for p in procs:
        try: p.terminate()
        except Exception: pass
    os._exit(1 if error else 0)

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

def start_embedder():
    """bge-m3 GGUF behind llama.cpp's prebuilt CPU llama-server, OpenAI-compatible /v1/embeddings."""
    # Build llama-server (CPU) from source: prebuilt release asset names change between releases.
    sh("rm -rf /tmp/llama.cpp && git clone -q --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama.cpp && "
       "cmake -S /tmp/llama.cpp -B /tmp/llama.cpp/build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF "
       "-DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release && "
       "cmake --build /tmp/llama.cpp/build --target llama-server -j$(nproc)", timeout_s=1500)
    server = "/tmp/llama.cpp/build/bin/llama-server"
    sh("pip install -q -U huggingface_hub")
    from huggingface_hub import list_repo_files, hf_hub_download
    files = list_repo_files("gpustack/bge-m3-GGUF")
    fname = next(f for pref in ("Q8_0", "FP16", "F16") for f in files if pref in f and f.endswith(".gguf"))
    model = hf_hub_download("gpustack/bge-m3-GGUF", fname)
    p = subprocess.Popen([server, "-m", model, "--embedding", "--pooling", "cls", "-c", "8192", "-ub", "8192",
                          "--host", "127.0.0.1", "--port", str(EMBED_PORT), "--alias", "bge-m3"],
                         cwd=os.path.dirname(server),
                         stdout=open("/tmp/embedder.log", "w"), stderr=subprocess.STDOUT)
    procs.append(p)
    for _ in range(120):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{EMBED_PORT}/v1/embeddings",
                                         data=json.dumps({"input": "hello", "model": "bge-m3"}).encode(),
                                         headers={"Content-Type": "application/json"})
            dim = len(json.load(urllib.request.urlopen(req, timeout=10))["data"][0]["embedding"])
            return f"llama-server (source) + {fname}, dim {dim}"
        except Exception:
            if p.poll() is not None:
                raise RuntimeError("embedder exited: " + open("/tmp/embedder.log").read()[-800:])
            time.sleep(2)
    raise RuntimeError("embedder never answered")

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")
    for name, body in SCRIPTS.items():
        with open(f"/tmp/{name}", "w") as f:
            f.write(body)
    sh(f"rm -rf {SRC} && git clone -q --depth 1 https://github.com/infiniflow/ragflow {SRC}")
    notify("COMMIT " + sh(f"git -C {SRC} log -1 --format='%h %cs %s'").strip())

    # Sequential on purpose: both steps use apt-get (dpkg lock), and MinIO is built with the Go
    # toolchain that setup_ragflow.sh installs.
    t0 = time.time()
    sh_steps("bash /tmp/setup_ragflow.sh", 3600, env={"RAGFLOW_SRC": SRC})
    notify(f"BUILT in {int(time.time() - t0)}s")
    sh_steps("bash /tmp/deps_ragflow.sh install", 1500)
    sh_steps("bash /tmp/deps_ragflow.sh start", 900)
    notify("DEPS " + sh("bash /tmp/deps_ragflow.sh status").replace("\n", " ").strip())

    try:
        notify("EMBEDDER " + start_embedder())
    except Exception as e:  # keep going: the app is still usable, and this is fixable without a rebuild
        notify(f"WARN embedder failed, continuing without it: {type(e).__name__}: {e}"[:600])
    sh_steps("bash /tmp/run_ragflow.sh start", 600, env={"RAGFLOW_SRC": SRC, "RAGFLOW_WEB_PORT": str(WEB_PORT)})
    out = sh(f"bash /tmp/run_ragflow.sh create_admin '{ADMIN_EMAIL}' '{ADMIN_PASS}'", env={"RAGFLOW_SRC": SRC})
    notify("ADMIN " + " | ".join(l for l in out.splitlines() if l.startswith(("login:", "sign-up:")))[:400])
    notify(f"APP_URL {tunnel(WEB_PORT)}")
    notify("READY ragflow")
    # Forward ingestor errors to ntfy so parse failures are diagnosable from outside Kaggle.
    def forward_errors():
        path, pos = "/var/log/ragflow/ingestor.log", 0
        while True:
            try:
                with open(path, errors="replace") as f:
                    f.seek(pos); chunk = f.read(); pos = f.tell()
                for line in chunk.splitlines():
                    if re.search(r"\t(error|fatal|panic)\t|failed|timeout|deadline", line, re.I):
                        notify("INGEST " + line[:500])
            except FileNotFoundError:
                pass
            time.sleep(10)
    threading.Thread(target=forward_errors, daemon=True).start()
    while True:
        time.sleep(30)
        if "ok" not in sh("curl -s -m 10 http://127.0.0.1:9380/api/v1/system/healthz || true"):
            notify("WARN healthz not ok")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
