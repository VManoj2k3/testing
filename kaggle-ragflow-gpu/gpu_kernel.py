# Runs INSIDE a Kaggle 2x T4 session: Qwen (llama.cpp CUDA) + bge-m3 embedder on the GPUs, and RAGFlow
# v1.0.0-rc1 built natively with ragflow_deepdoc_gpu.patch so DeepDoc ingestion can run on GPU 1.
# Assembled from kaggle-llama/server_kernel.py and kaggle-ragflow/ragflow_kernel.py.
# The kill-switch server also takes secret-protected POST /ingestor/<cpu|cuda> (restart the ingestor on
# that device) and GET /gpu (nvidia-smi), so CPU vs GPU parsing can be benchmarked from outside.
# Double-underscore placeholders are filled by launch.sh.
import base64, glob, json, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")
ADMIN_EMAIL, ADMIN_PASS = "__ADMIN_EMAIL__", "__ADMIN_PASS__"
MODEL_REPO, QUANT = "__MODEL_REPO__", "__QUANT__"
CTX, NP = int("__CTX__"), int("__NP__")
TENSOR_SPLIT = "__TENSOR_SPLIT__"        # Qwen weighted to GPU 0 so DeepDoc has room on GPU 1
RAGFLOW_COMMIT = "__RAGFLOW_COMMIT__"     # the commit the patch and all test results are on
ORT_URL = ("https://github.com/microsoft/onnxruntime/releases/download/v1.29.0/"
           "onnxruntime-linux-x64-gpu_cuda12-1.29.0.tgz")
FILES = {name: base64.b64decode(b).decode() for name, b in [
    ("deps_ragflow.sh", "__DEPS_B64__"), ("setup_ragflow.sh", "__SETUP_B64__"), ("run_ragflow.sh", "__RUN_B64__"),
    ("build_gpu_server.sh", "__BUILD_GPU_B64__"), ("ragflow_deepdoc_gpu.patch", "__PATCH_B64__")]}
SRC = "/opt/ragflow"
ALIAS = MODEL_REPO.split("/")[-1].lower()
LLAMA_PORT, KILL_PORT, EMBED_PORT, WEB_PORT = 8080, 8081, 8093, 80
procs, gpu_env = [], {}

def notify(msg):
    print(f"[notify] {msg}", flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(), method="POST"), timeout=10)
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)

_run_no = [0]

def _run_logged(cmd, timeout_s, env, on_line):
    """Output to a log file, poll for exit (daemons started by a script can hold a pipe open forever)."""
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
            f.seek(pos); chunk = f.read(); pos = f.tell()
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
    time.sleep(3)
    for p in procs:
        try: p.kill()
        except Exception: pass
    os._exit(1 if error else 0)

def gpu_mem():
    return subprocess.run("nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader",
                          shell=True, capture_output=True, text=True).stdout.strip().replace("\n", " | ")

class ControlHandler(BaseHTTPRequestHandler):
    def _ok(self, body):
        self.send_response(200); self.end_headers(); self.wfile.write(body.encode())
    def do_GET(self):
        if self.path == "/gpu" and self.headers.get("X-Kill-Secret") == SECRET:
            return self._ok(gpu_mem() + "\n")
        self.send_response(403); self.end_headers()
    def do_POST(self):
        if self.headers.get("X-Kill-Secret") != SECRET:
            self.send_response(403); self.end_headers(); return
        if self.path == "/shutdown":
            self._ok("bye\n")
            threading.Thread(target=shutdown, args=("kill switch",)).start()
        elif self.path in ("/ingestor/cpu", "/ingestor/cuda"):
            dev = self.path.rsplit("/", 1)[1]
            r = subprocess.run(f"bash /tmp/run_ragflow.sh restart_ingestor {dev}", shell=True, capture_output=True,
                               text=True, env={**os.environ, **gpu_env, "RAGFLOW_SRC": SRC}, timeout=120)
            self._ok((r.stdout + r.stderr)[-1500:] + f"\nrc={r.returncode}\n{gpu_mem()}\n")
        else:
            self.send_response(404); self.end_headers()
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

def wait_http(url, p, log, tries=900, data=None, headers=None):
    for _ in range(tries):
        try:
            urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers or {}), timeout=5)
            return
        except Exception:
            if p.poll() is not None:
                raise RuntimeError(f"{log} exited: " + open(log, errors="replace").read()[-800:])
            time.sleep(2)
    raise RuntimeError(f"{url} never answered")

def find_gguf():
    from huggingface_hub import list_repo_files
    name = MODEL_REPO.split("/")[-1]
    for repo in (f"{MODEL_REPO}-GGUF", f"unsloth/{name}-GGUF", MODEL_REPO):
        try:
            files = list_repo_files(repo)
        except Exception:
            continue
        hits = sorted(f for f in files if f.endswith(".gguf") and QUANT.lower() in f.lower() and "mmproj" not in f.lower())
        if hits:
            return repo, hits
    return None, []

def download_models(out):
    """Network-bound; runs in a thread while RAGFlow builds."""
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
        repo, files = find_gguf()
        if not repo:
            raise RuntimeError(f"no {QUANT} GGUF for {MODEL_REPO}")
        out["qwen"] = [hf_hub_download(repo, f) for f in files][0]
        ef = list_repo_files("gpustack/bge-m3-GGUF")
        out["embed"] = hf_hub_download("gpustack/bge-m3-GGUF",
                                       next(f for p in ("Q8_0", "FP16", "F16") for f in ef if p in f and f.endswith(".gguf")))
        notify(f"MODELS downloaded: {os.path.basename(out['qwen'])}, {os.path.basename(out['embed'])}")
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
    return cuda_root

def setup_gpu_ort(cuda_root):
    """GPU ONNX Runtime + the CUDA 12 / cuDNN 9 libraries it loads (Kaggle ships cuDNN inside pip wheels)."""
    sh(f"mkdir -p /opt/ortgpu && curl -fsSL {ORT_URL} | tar -xz -C /opt/ortgpu --strip-components=1 "
       "&& rm -f /opt/ortgpu/lib/libonnxruntime_providers_tensorrt.so")
    if not glob.glob("/usr/local/lib/python3*/*-packages/nvidia/cudnn/lib/libcudnn.so.9*"):
        sh("pip install -q nvidia-cudnn-cu12==9.*")
    libdirs = ["/opt/ortgpu/lib", f"{cuda_root}/lib64",
               *sorted(glob.glob("/usr/local/lib/python3*/*-packages/nvidia/*/lib"))]
    gpu_env.update({
        "RAGFLOW_ORT_LIBRARY_PATH": "/opt/ortgpu/lib/libonnxruntime.so",
        "RAGFLOW_DEEPDOC_CUDA_DEVICE_ID": "1",
        "RAGFLOW_DEEPDOC_CUDA_MEM_MB": "512",
        "LD_LIBRARY_PATH": ":".join(libdirs + [os.environ.get("LD_LIBRARY_PATH", "")]),
    })
    notify("ORT_GPU " + sh("ls /opt/ortgpu/lib | tr '\\n' ' '; ls " + " ".join(libdirs[2:]) +
                           " 2>/dev/null | grep -oE 'lib(cudnn|cublas|cudart)\\.so\\.[0-9]+' | sort -u | tr '\\n' ' '")[:400])

def start_llama(qwen, embed):
    log = "/tmp/qwen.log"
    q = subprocess.Popen(["/tmp/llama.cpp/build/bin/llama-server", "-m", qwen, "--host", "127.0.0.1",
                          "--port", str(LLAMA_PORT), "-ngl", "99", "--split-mode", "layer", "--tensor-split", TENSOR_SPLIT,
                          "-c", str(CTX), "-np", str(NP), "--jinja", "--api-key", SECRET, "--alias", ALIAS],
                         stdout=open(log, "w"), stderr=subprocess.STDOUT)
    procs.append(q)
    wait_http(f"http://127.0.0.1:{LLAMA_PORT}/health", q, log)
    notify(f"GPU after Qwen: {gpu_mem()}")
    elog = "/tmp/embedder.log"
    e = subprocess.Popen(["/tmp/llama.cpp/build/bin/llama-server", "-m", embed, "--embedding", "--pooling", "cls",
                          "-c", "8192", "-ub", "4096", "-b", "4096", "-np", "2", "-ngl", "99", "--main-gpu", "0",
                          "--split-mode", "none", "--host", "127.0.0.1", "--port", str(EMBED_PORT),
                          "--api-key", SECRET, "--alias", "bge-m3"], stdout=open(elog, "w"), stderr=subprocess.STDOUT)
    procs.append(e)
    wait_http(f"http://127.0.0.1:{EMBED_PORT}/v1/embeddings", e, elog, tries=120,
              data=json.dumps({"input": "hello", "model": "bge-m3"}).encode(),
              headers={"Content-Type": "application/json", "Authorization": f"Bearer {SECRET}"})
    notify(f"GPU after embedder: {gpu_mem()}")
    return q

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), ControlHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")
    notify("GPUS " + gpu_mem())
    for name, body in FILES.items():
        with open(f"/tmp/{name}", "w") as f:
            f.write(body)

    sh("pip install -q -U huggingface_hub")
    models = {}
    dl = threading.Thread(target=download_models, args=(models,), daemon=True)
    dl.start()

    sh(f"rm -rf {SRC} && git init -q {SRC} && git -C {SRC} fetch -q --depth 1 https://github.com/infiniflow/ragflow "
       f"{RAGFLOW_COMMIT} && git -C {SRC} checkout -q FETCH_HEAD && git -C {SRC} apply /tmp/ragflow_deepdoc_gpu.patch")
    notify("COMMIT " + sh(f"git -C {SRC} log -1 --format='%h %cs %s'").strip() + " + GPU patch")
    t0 = time.time()
    sh_steps("bash /tmp/setup_ragflow.sh", 3600, env={"RAGFLOW_SRC": SRC})
    sh("bash /tmp/build_gpu_server.sh", env={"RAGFLOW_SRC": SRC, "PATH": "/usr/local/goragflow/bin:" + os.environ["PATH"]},
       timeout_s=1800)
    sh("PATH=/usr/local/goragflow/bin:$PATH go clean -cache; rm -rf /root/.npm", timeout_s=600)  # ~8 GB of build cache
    notify(f"BUILT ragflow + gpu binary in {int(time.time() - t0)}s; disk: " + sh("df -h / | tail -1").strip())
    cuda_root = build_llama()
    setup_gpu_ort(cuda_root)
    sh_steps("bash /tmp/deps_ragflow.sh install", 1500)
    sh_steps("bash /tmp/deps_ragflow.sh start", 900)
    notify("DEPS " + sh("bash /tmp/deps_ragflow.sh status").replace("\n", " ").strip())

    dl.join(timeout=3600)
    if "error" in models or "qwen" not in models:
        raise RuntimeError("model download: " + models.get("error", "timed out"))
    qwen = start_llama(models["qwen"], models["embed"])

    # Ingestor starts on the GPU; if CUDA can't be used it refuses to start, so fall back to CPU and say so.
    try:
        sh_steps("bash /tmp/run_ragflow.sh start", 600,
                 env={**gpu_env, "RAGFLOW_SRC": SRC, "RAGFLOW_WEB_PORT": str(WEB_PORT), "RAGFLOW_INGESTOR_DEVICE": "cuda"})
    except Exception:
        for m in ("api", "ingestor", "admin"):
            notify(f"LOG {m}: " + sh(f"tail -n 6 /var/log/ragflow/{m}.log 2>&1 || true")[-900:])
        raise
    time.sleep(20)
    if "--ingestor" not in sh("ps -eo args | grep -- '--ingestor$' || true"):
        notify("WARN cuda ingestor did not start: " + sh("grep -iE 'fatal|device check' /var/log/ragflow/ingestor.log | tail -2 || true")[-700:])
        notify("INGESTOR " + sh("bash /tmp/run_ragflow.sh restart_ingestor cpu || true", env={"RAGFLOW_SRC": SRC}).strip()[-200:])
    else:
        notify("INGESTOR up on cuda: " + sh("grep -m1 'inference device' /var/log/ragflow/ingestor.log || true").strip()[-200:])
    out = sh(f"bash /tmp/run_ragflow.sh create_admin '{ADMIN_EMAIL}' '{ADMIN_PASS}'", env={"RAGFLOW_SRC": SRC})
    notify("ADMIN " + " | ".join(l for l in out.splitlines() if l.startswith(("login:", "sign-up:")))[:400])
    notify(f"APP_URL {tunnel(WEB_PORT)}")
    notify(f"LLM_LOCAL http://127.0.0.1:{LLAMA_PORT}/v1 EMBED_LOCAL http://127.0.0.1:{EMBED_PORT}/v1")
    notify("READY ragflow-gpu")

    def forward_errors():
        path, pos = "/var/log/ragflow/ingestor.log", 0
        while True:
            try:
                with open(path, errors="replace") as f:
                    f.seek(pos); chunk = f.read(); pos = f.tell()
                for line in chunk.splitlines():
                    if re.search(r"\t(error|fatal|panic)\t|failed|timeout|deadline|cuda", line, re.I):
                        notify("INGEST " + line[:500])
            except FileNotFoundError:
                pass
            time.sleep(10)
    threading.Thread(target=forward_errors, daemon=True).start()
    while qwen.poll() is None:
        time.sleep(30)
    shutdown("Qwen llama-server exited: " + open("/tmp/qwen.log", errors="replace").read()[-600:], error=True)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
