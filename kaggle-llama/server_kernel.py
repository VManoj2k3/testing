# Runs INSIDE a Kaggle 2x T4 session. Builds llama.cpp, serves a GGUF of the
# requested model through an OpenAI-compatible API behind a Cloudflare quick
# tunnel, reports links via ntfy, and listens for a kill switch.
# __PLACEHOLDERS__ are substituted by launch.sh.
import json, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MODEL_REPO = "__MODEL_REPO__"
QUANT = "__QUANT__"
CTX = int("__CTX__")
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")  # dead-man switch: hard stop
ALIAS = MODEL_REPO.split("/")[-1].lower()
LLAMA_PORT, KILL_PORT = 8080, 8081
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

def shutdown(reason, error=False):
    notify(f"{'ERROR' if error else 'STOPPED'} {reason}")
    for p in procs:
        try: p.terminate()
        except Exception: pass
    time.sleep(3)
    for p in procs:
        try: p.kill()
        except Exception: pass
    os._exit(1 if error else 0)  # ends the Kaggle run, which releases the GPUs

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

def find_gguf():
    """Return (repo, [files]) for the requested quant; never substitutes another model."""
    from huggingface_hub import list_repo_files
    name = MODEL_REPO.split("/")[-1]
    for repo in (f"{MODEL_REPO}-GGUF", f"unsloth/{name}-GGUF", MODEL_REPO):
        try:
            files = list_repo_files(repo)
        except Exception as e:
            print(f"[model] {repo}: {type(e).__name__}", flush=True)
            continue
        hits = sorted(f for f in files if f.endswith(".gguf") and QUANT.lower() in f.lower()
                      and "mmproj" not in f.lower())
        if hits:
            # Split GGUFs (-00001-of-0000N) need every shard; llama-server loads from the first.
            return repo, hits
        print(f"[model] {repo}: no {QUANT} .gguf among {len(files)} files", flush=True)
    return None, []

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    # Kill switch is up before the slow steps so it works at any point.
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")

    sh("pip install -q -U huggingface_hub")
    repo, files = find_gguf()
    if not repo:
        shutdown(f"no-gguf: no {QUANT} GGUF found for {MODEL_REPO}", error=True)
    notify(f"MODEL {repo} {files[0]}")

    sh("nvidia-smi")
    nvcc = next((p for p in ["/usr/local/cuda/bin/nvcc", *sorted(__import__("glob").glob("/usr/local/cuda-*/bin/nvcc"))]
                 if os.path.exists(p)), None)
    if not nvcc:
        shutdown("nvcc not found under /usr/local/cuda*", error=True)
    os.environ["CUDACXX"] = nvcc
    os.environ["PATH"] = os.path.dirname(nvcc) + ":" + os.environ["PATH"]
    sh("rm -rf /tmp/llama.cpp && git clone --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama.cpp")
    # Kaggle ships the driver as libcuda.so.1 only; CMake's FindCUDAToolkit wants libcuda.so.
    cuda_root = os.path.dirname(os.path.dirname(nvcc))
    sh("mkdir -p /tmp/cudalib && L=$(ldconfig -p | grep -o '/.*libcuda\\.so\\.1$' | head -1); "
       "[ -n \"$L\" ] && ln -sf \"$L\" /tmp/cudalib/libcuda.so; ls -l /tmp/cudalib " + cuda_root + "/lib64/stubs || true")
    sh(f"cmake -S /tmp/llama.cpp -B /tmp/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 "
       f"-DCMAKE_CUDA_COMPILER={nvcc} -DCMAKE_LIBRARY_PATH='/tmp/cudalib;{cuda_root}/lib64/stubs' "
       f"-DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF")
    sh("cmake --build /tmp/llama.cpp/build --target llama-server -j$(nproc)")

    from huggingface_hub import hf_hub_download
    paths = [hf_hub_download(repo, f) for f in files]

    server = subprocess.Popen(["/tmp/llama.cpp/build/bin/llama-server", "-m", paths[0],
                               "--host", "127.0.0.1", "--port", str(LLAMA_PORT),
                               "-ngl", "99", "--split-mode", "layer", "--tensor-split", "1,1",
                               "-c", str(CTX), "--jinja", "--api-key", SECRET, "--alias", ALIAS],
                              stderr=subprocess.PIPE, text=True)
    procs.append(server)
    tail = []
    threading.Thread(target=lambda: [tail.append(l) or tail.__delitem__(slice(0, -40)) or print(l, end="", flush=True)
                                     for l in server.stderr], daemon=True).start()
    for _ in range(900):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2); break
        except Exception:
            if server.poll() is not None:
                time.sleep(1)
                shutdown("llama-server crashed: " + "".join(tail[-8:])[-1500:], error=True)
            time.sleep(2)
    notify(f"LLM_URL {tunnel(LLAMA_PORT)}/v1")
    notify(f"READY {ALIAS}")
    server.wait()
    shutdown("llama-server exited", error=True)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
