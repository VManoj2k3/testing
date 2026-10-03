# Runs INSIDE a Kaggle GPU session. Builds llama.cpp, serves a Qwen GGUF model
# through an OpenAI-compatible API, exposes it via a Cloudflare quick tunnel,
# and listens for a kill switch. __SECRET__ is substituted by launch.sh.
import os, re, signal, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
HF_REPO = "Qwen/Qwen3-8B-GGUF"
HF_FILE = "Qwen3-8B-Q4_K_M.gguf"
CTX = 32768
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")  # dead-man switch: hard stop
LLAMA_PORT, KILL_PORT = 8080, 8081
procs = []

def sh(cmd):
    print("+", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)

def shutdown(reason):
    print(f"[kill-switch] shutting down: {reason}", flush=True)
    for p in procs:
        try: p.terminate()
        except Exception: pass
    time.sleep(3)
    for p in procs:
        try: p.kill()
        except Exception: pass
    os._exit(0)  # ends the Kaggle run, which releases the GPU session

class KillHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/shutdown" and self.headers.get("X-Kill-Secret") == SECRET:
            self.send_response(200); self.end_headers(); self.wfile.write(b"bye\n")
            threading.Thread(target=shutdown, args=("remote request",)).start()
        else:
            self.send_response(403); self.end_headers()
    def log_message(self, *a): pass

def tunnel(port):
    p = subprocess.Popen(["./cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
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
    sh("curl -fsSL -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x cloudflared")
    kill_url = tunnel(KILL_PORT)
    print(f"KILL_URL={kill_url}", flush=True)

    sh("nvidia-smi")
    sh("git clone --depth 1 https://github.com/ggml-org/llama.cpp")
    sh("cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES='60;75' -DLLAMA_CURL=OFF")
    sh("cmake --build llama.cpp/build --target llama-server -j$(nproc)")
    sh("pip install -q huggingface_hub")
    from huggingface_hub import hf_hub_download
    model = hf_hub_download(HF_REPO, HF_FILE)

    server = subprocess.Popen(["llama.cpp/build/bin/llama-server", "-m", model, "--host", "127.0.0.1",
                               "--port", str(LLAMA_PORT), "-ngl", "99", "-c", str(CTX), "--jinja",
                               "--api-key", SECRET, "--alias", "qwen3-8b"])
    procs.append(server)
    for _ in range(600):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2); break
        except Exception:
            if server.poll() is not None: shutdown("llama-server crashed")
            time.sleep(2)
    print(f"LLM_URL={tunnel(LLAMA_PORT)}/v1", flush=True)
    print("READY", flush=True)
    server.wait()
    shutdown("llama-server exited")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    main()
