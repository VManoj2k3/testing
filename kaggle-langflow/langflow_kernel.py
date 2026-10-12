# Runs INSIDE a Kaggle 2x T4 session: Qwen (llama.cpp CUDA, both GPUs) + Langflow, in one notebook.
# Langflow reaches the model on loopback (127.0.0.2) only; just Langflow's port is tunnelled (plus the kill switch).
# Helpers are taken from kaggle-ragflow-gpu/gpu_kernel.py; the Langflow steps are lf_phases.py.
# Double-underscore placeholders are filled by launch.sh.
import base64, glob, os, re, signal, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")
ADMIN_PASS = "__ADMIN_PASS__"
MODEL_REPO, QUANT = "__MODEL_REPO__", "__QUANT__"
CTX, NP = int("__CTX__"), int("__NP__")
TENSOR_SPLIT = "__TENSOR_SPLIT__"
LANGFLOW_VERSION = "__LANGFLOW_VERSION__"
FILES = {name: base64.b64decode(b).decode() for name, b in [
    ("lf_phases.py", "__PHASES_B64__"), ("lf_drive.py", "__DRIVE_B64__"), ("langflow.env.example", "__ENV_B64__")]}
ALIAS = MODEL_REPO.split("/")[-1].lower()
LLAMA_PORT, KILL_PORT, LF_PORT = 8080, 8081, 7860
# Not 127.0.0.1: Langflow rewrites that to the Docker host inside a container. Still loopback-only.
LLAMA_HOST = "127.0.0.2"
VENV, HOME = "/opt/lfvenv", "/opt/lfhome"
procs = []


def notify(msg):
    print(f"[notify] {msg}", flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(), method="POST"), timeout=10)
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)


def sh(cmd, env=None, timeout_s=1800):
    """Output to a log file, poll for exit (daemons started by a script can hold a pipe open forever)."""
    path = f"/tmp/step-{abs(hash(cmd)) % 10**8}.log"
    print("+", cmd, "->", path, flush=True)
    with open(path, "w") as out:
        p = subprocess.Popen(cmd, shell=True, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env={**os.environ, **(env or {})}, start_new_session=True)
    try:
        rc = p.wait(timeout_s)
    except subprocess.TimeoutExpired:
        p.kill()
        raise RuntimeError(f"`{cmd[:60]}` timed out after {timeout_s}s: ..." + open(path, errors="replace").read()[-1200:])
    full = open(path, errors="replace").read()
    if rc:
        raise RuntimeError(f"`{cmd[:60]}` exit {rc}: ...{full[-1500:]}")
    return full


def shutdown(reason, error=False):
    notify(f"{'ERROR' if error else 'STOPPED'} {reason}")
    for p in procs:
        try: p.terminate()
        except Exception: pass
    time.sleep(3)
    for p in procs:
        try: p.kill()
        except Exception: pass
    os._exit(1 if error else 0)


def gpu_mem():
    return subprocess.run("nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader",
                          shell=True, capture_output=True, text=True).stdout.strip().replace("\n", " | ")


class KillHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("X-Kill-Secret") != SECRET or self.path != "/shutdown":
            self.send_response(403); self.end_headers(); return
        self.send_response(200); self.end_headers(); self.wfile.write(b"bye\n")
        threading.Thread(target=shutdown, args=("kill switch",)).start()
    def do_GET(self):
        self.send_response(403); self.end_headers()
    def log_message(self, *a): pass


def tunnel(port):
    p = subprocess.Popen(["/tmp/cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                         stderr=subprocess.PIPE, text=True)
    procs.append(p)
    for line in p.stderr:
        m = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            threading.Thread(target=lambda: [None for _ in p.stderr], daemon=True).start()
            return m.group(0)
    raise RuntimeError("cloudflared exited without a URL")


def wait_http(url, p, log, tries=900):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=5)
            return
        except Exception:
            if p.poll() is not None:
                raise RuntimeError(f"{log} exited: " + open(log, errors="replace").read()[-800:])
            time.sleep(2)
    raise RuntimeError(f"{url} never answered")


def download_model(out):
    """Network-bound; runs in a thread while llama.cpp builds."""
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
        name = MODEL_REPO.split("/")[-1]
        for repo in (f"{MODEL_REPO}-GGUF", f"unsloth/{name}-GGUF", MODEL_REPO):
            try:
                files = list_repo_files(repo)
            except Exception:
                continue
            hits = sorted(f for f in files if f.endswith(".gguf") and QUANT.lower() in f.lower() and "mmproj" not in f.lower())
            if hits:
                out["qwen"] = [hf_hub_download(repo, f) for f in hits][0]
                notify(f"MODEL downloaded: {repo}/{hits[0]}")
                return
        raise RuntimeError(f"no {QUANT} GGUF for {MODEL_REPO}")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"


def install_langflow(out):
    """uv instead of venv+pip: Kaggle's ensurepip is broken."""
    try:
        t = time.time()
        sh(f"pip install -q uv && uv venv -q -p python3 {VENV} && uv pip install -q --python {VENV}/bin/python "
           f"langflow=={LANGFLOW_VERSION}", timeout_s=2400)
        notify(f"LANGFLOW {LANGFLOW_VERSION} installed in {int(time.time() - t)}s")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"


def build_llama():
    nvcc = next((p for p in ["/usr/local/cuda/bin/nvcc", *sorted(glob.glob("/usr/local/cuda-*/bin/nvcc"))]
                 if os.path.exists(p)), None)
    if not nvcc:
        raise RuntimeError("nvcc not found under /usr/local/cuda*")
    cuda_root = os.path.dirname(os.path.dirname(nvcc))
    sh("rm -rf /tmp/llama.cpp && git clone -q --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama.cpp")
    sh("mkdir -p /tmp/cudalib && L=$(ldconfig -p | grep -o '/.*libcuda\\.so\\.1$' | head -1); "
       "[ -n \"$L\" ] && ln -sf \"$L\" /tmp/cudalib/libcuda.so; true")
    sh(f"cmake -S /tmp/llama.cpp -B /tmp/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 "
       f"-DCMAKE_CUDA_COMPILER={nvcc} -DCMAKE_LIBRARY_PATH='/tmp/cudalib;{cuda_root}/lib64/stubs' "
       f"-DGGML_CUDA_NO_VMM=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF "
       f"-DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++", env={"PATH": os.path.dirname(nvcc) + ":" + os.environ["PATH"]})
    sh("cmake --build /tmp/llama.cpp/build --target llama-server -j$(nproc)", timeout_s=2400)


def start_llama(qwen):
    # No --api-key: this port is never tunnelled; only Langflow (same machine) calls it.
    log = "/tmp/qwen.log"
    q = subprocess.Popen(["/tmp/llama.cpp/build/bin/llama-server", "-m", qwen, "--host", LLAMA_HOST,
                          "--port", str(LLAMA_PORT), "-ngl", "99", "--split-mode", "layer", "--tensor-split", TENSOR_SPLIT,
                          "-c", str(CTX), "-np", str(NP), "--jinja", "--alias", ALIAS],
                         stdout=open(log, "w"), stderr=subprocess.STDOUT)
    procs.append(q)
    wait_http(f"http://{LLAMA_HOST}:{LLAMA_PORT}/health", q, log)
    notify(f"QWEN up ({ALIAS}, ctx {CTX}, {NP} slots); GPU: {gpu_mem()}")
    return q


def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")
    notify("GPUS " + gpu_mem())
    os.makedirs("/tmp/lf", exist_ok=True)
    for name, body in FILES.items():
        with open(f"/tmp/lf/{name}", "w") as f:
            f.write(body)

    sh("pip install -q -U huggingface_hub")
    model, lf = {}, {}
    threads = [threading.Thread(target=download_model, args=(model,), daemon=True),
               threading.Thread(target=install_langflow, args=(lf,), daemon=True)]
    for t in threads:
        t.start()
    t0 = time.time()
    build_llama()
    notify(f"BUILT llama.cpp in {int(time.time() - t0)}s")
    for t in threads:
        t.join(timeout=3600)
    for what, r in (("model download", model), ("langflow install", lf)):
        if "error" in r:
            raise RuntimeError(f"{what}: {r['error']}")
    if "qwen" not in model:
        raise RuntimeError("model download timed out")
    qwen = start_llama(model["qwen"])

    sys.path.insert(0, "/tmp/lf")
    import lf_phases
    os.makedirs(HOME, exist_ok=True)
    model_url = f"http://{LLAMA_HOST}:{LLAMA_PORT}/v1"
    try:  # Phase A: internal only; no Langflow URL exists yet.
        lf_phases.phase_a(VENV, HOME, model_url, ALIAS, ADMIN_PASS, report=notify)
    except BaseException as e:
        notify(f"ASSIST probe failed: {type(e).__name__}: {e}"[:900])
    lfp = lf_phases.phase_b(VENV, HOME, model_url, ALIAS, ADMIN_PASS, report=notify)
    procs.append(lfp)
    notify(f"APP_URL {tunnel(LF_PORT)}")
    notify("LOGIN user admin (password in .state/login)")
    notify("READY langflow-demo")
    while qwen.poll() is None and lfp.poll() is None:
        time.sleep(30)
    which, log = ("Qwen", "/tmp/qwen.log") if qwen.poll() is not None else ("Langflow", f"{HOME}/langflow.log")
    shutdown(f"{which} exited: " + open(log, errors="replace").read()[-600:], error=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except BaseException as e:  # SystemExit too: a silent exit left the run looking stuck for 1.5 h
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
