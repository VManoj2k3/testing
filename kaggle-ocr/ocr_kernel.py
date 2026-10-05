# Runs INSIDE a Kaggle CPU session. Builds open-code-review, serves its read-only
# session viewer behind a Cloudflare quick tunnel, and reviews the repo's own recent
# commits one at a time with Qwen (llama-server). Reports via ntfy; kill switch included.
# __PLACEHOLDERS__ are substituted by launch.sh.
import os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")  # dead-man switch: hard stop
LLM_URL, LLM_KEY, LLM_MODEL = "__LLM_URL__", "__LLM_KEY__", "__LLM_MODEL__"
N_COMMITS = int("__N_COMMITS__")
GO_VERSION = "1.25.5"
REPO, SRC = "https://github.com/alibaba/open-code-review", "/kaggle/working/open-code-review"
OCR = f"{SRC}/dist/opencodereview"
VIEWER_PORT, KILL_PORT = 5483, 8081
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
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
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

    # Viewer first, so the link works (empty) while reviews run; it re-reads sessions per request.
    viewer_url = tunnel(VIEWER_PORT)
    viewer = subprocess.Popen([OCR, "viewer", "--addr", f"127.0.0.1:{VIEWER_PORT}", "--open=never", "--color", "never"],
                              env={**os.environ, "OCR_VIEWER_ALLOWED_HOSTS": viewer_url.split("//")[1]})
    procs.append(viewer)
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{VIEWER_PORT}/", timeout=3); break
        except Exception:
            time.sleep(1)
    notify(f"VIEWER_URL {viewer_url}")
    notify("READY viewer")

    commits = sh(f"git -C {SRC} log --no-merges -{N_COMMITS} --format='%h %s'").stdout.strip().splitlines()
    for line in commits:
        h, subject = line.split(" ", 1)
        if viewer.poll() is not None:
            shutdown("viewer exited", error=True)
        t0 = time.time()
        notify(f"REVIEW_START {h} {subject[:70]}")
        try:
            r = sh(f"cd {SRC} && {OCR} review -c {h} --timeout 60 --color never", check=False, timeout=90 * 60)
            out = r.stdout
            m = re.search(r"Review complete: (\d+) finding", out)
            summary = (m and f"{m.group(1)} findings") or f"exit {r.returncode}: {out.strip().splitlines()[-1][:300] if out.strip() else ''}"
        except subprocess.TimeoutExpired:
            summary = "timed out after 90 min"
        notify(f"REVIEW_DONE {h} {summary} in {int((time.time() - t0) / 60)}m")
    notify("ALL_REVIEWS_DONE")
    viewer.wait()
    shutdown("viewer exited", error=True)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
