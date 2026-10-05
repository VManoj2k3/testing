"""Web front end for open-code-review: queue reviews of public GitHub code from a browser.

One link serves both: /run (start reviews, live logs) and ocr's own read-only session
viewer (everything else, reverse-proxied). Everything is behind HTTP Basic auth.
Jobs run one at a time because the LLM backend has a single slot.
Env: APP_USER, APP_PASS, OCR_BIN, VIEWER (http://127.0.0.1:5483), WORK_DIR, PORT.
"""
import base64, hmac, html, json, os, re, shutil, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USER, PASS = os.environ["APP_USER"], os.environ["APP_PASS"]
OCR = os.environ["OCR_BIN"]
VIEWER = os.environ.get("VIEWER", "http://127.0.0.1:5483")
WORK = os.environ.get("WORK_DIR", "/tmp/ocr-jobs")
REPO_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
SHA_RE, PR_RE = re.compile(r"^[0-9a-fA-F]{7,40}$"), re.compile(r"^\d{1,7}$")
HISTORY = "300"

jobs, jobs_lock, queue = [], threading.Lock(), []
queue_cv = threading.Condition(jobs_lock)


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout.strip()


def run_job(job):
    owner, name = REPO_RE.match(job["repo"]).groups()
    d = os.path.join(WORK, f"{owner}__{name}")
    log = job["log"]
    log.append(f"$ git clone {job['repo']}")
    if not os.path.isdir(os.path.join(d, ".git")):
        shutil.rmtree(d, ignore_errors=True)
        git("clone", "-q", "--depth", HISTORY, job["repo"], d)
    else:
        git("fetch", "-q", "--depth", HISTORY, "origin", cwd=d)
    default = git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=d)  # e.g. origin/main
    kind, val = job["kind"], job["value"]
    if kind == "latest":
        sha = git("rev-parse", default, cwd=d)
        args, job["target"] = ["-c", sha], f"latest commit on {default} ({sha[:9]})"
    elif kind == "commit":
        try:
            git("cat-file", "-e", f"{val}^{{commit}}", cwd=d)
        except RuntimeError:
            git("fetch", "-q", "--depth", HISTORY, "origin", val, cwd=d)
        args, job["target"] = ["-c", val], f"commit {val[:9]}"
    else:
        ref = f"refs/remotes/pr/{val}"
        git("fetch", "-q", "--depth", HISTORY, "origin", f"pull/{val}/head:{ref}", cwd=d)
        args, job["target"] = ["--from", default, "--to", ref], f"PR #{val} vs {default}"
    cmd = [OCR, "review", *args, "--repo", d, "--timeout", "60", "--color", "never"]
    log.append("$ ocr review " + " ".join(args))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    job["pid"] = p.pid
    for line in p.stdout:
        log.append(line.rstrip("\n"))
        del log[:-2000]
    rc = p.wait()
    text = "\n".join(log)
    m = re.search(r"Review complete: (\d+) finding", text)
    s = re.search(r"Session: ([0-9a-f-]{36})", text)
    job["session"] = s.group(1) if s else None
    if m:
        job["status"], job["summary"] = "done", f"{m.group(1)} finding(s)"
    elif "Review skipped" in text:
        job["status"], job["summary"] = "skipped", "no reviewable code files in this change"
    else:
        job["status"], job["summary"] = "failed", f"ocr exited {rc}"


def worker():
    while True:
        with queue_cv:
            while not queue:
                queue_cv.wait()
            job = queue.pop(0)
            job["status"], job["started"] = "running", time.time()
        try:
            run_job(job)
        except Exception as e:
            job["status"], job["summary"] = "failed", str(e)[:500]
            job["log"].append(f"ERROR: {e}")
        job["finished"] = time.time()


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Run Code Review</title>
<style>
:root{--bg:#f7f7f8;--fg:#1d1d1f;--muted:#666;--card:#fff;--line:#ddd;--acc:#2563eb;--ok:#15803d;--bad:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#111214;--fg:#e8e8ea;--muted:#9a9aa0;--card:#1b1c1f;--line:#333;--acc:#60a5fa;--ok:#4ade80;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}p.sub{color:var(--muted);margin:0 0 20px}
form,.job{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
label{display:block;font-weight:600;margin:10px 0 4px}input,select{width:100%;padding:9px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--fg);font:inherit}
.row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1 1 200px}
button{margin-top:14px;padding:10px 18px;border:0;border-radius:7px;background:var(--acc);color:#fff;font-weight:600;cursor:pointer}
.head{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.st{font-weight:700}.done{color:var(--ok)}.skipped{color:var(--muted)}.failed{color:var(--bad)}
pre{white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;background:var(--bg);padding:10px;border-radius:7px;font-size:12.5px}
a{color:var(--acc)}.muted{color:var(--muted)}
</style></head><body><main>
<h1>Run a code review</h1>
<p class="sub">open-code-review + __MODEL__ &middot; reviews run one at a time &middot; <a href="/">browse all past reviews</a></p>
<form id="f"><label for="repo">Public GitHub repository</label>
<input id="repo" required placeholder="https://github.com/owner/repo">
<div class="row"><div><label for="kind">What to review</label>
<select id="kind"><option value="latest">Latest commit on default branch</option>
<option value="commit">A specific commit</option><option value="pr">A pull request</option></select></div>
<div><label for="value">Commit SHA or PR number</label><input id="value" placeholder="only for commit / PR"></div></div>
<button>Run review</button> <span id="msg" class="muted"></span></form>
<div id="jobs"></div>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
$("#f").onsubmit=async e=>{e.preventDefault();$("#msg").textContent="queuing…";
 const r=await fetch("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({repo:$("#repo").value.trim(),kind:$("#kind").value,value:$("#value").value.trim()})});
 const j=await r.json();$("#msg").textContent=r.ok?"queued":("error: "+j.error);load();};
async function load(){const js=await (await fetch("/api/jobs")).json();
 $("#jobs").innerHTML=js.map(j=>`<div class="job"><div class="head"><div><b>${esc(j.repo)}</b> <span class="muted">${esc(j.target||j.kind+" "+(j.value||""))}</span></div>
 <div class="st ${j.status}">${esc(j.status)}${j.summary?" · "+esc(j.summary):""}${j.elapsed?" · "+j.elapsed:""}</div></div>
 ${j.status==="done"?'<p><a href="/">Open in viewer</a> (newest session at the top of its repo)</p>':""}
 <pre>${esc(j.log)}</pre></div>`).join("")||'<p class="muted">No reviews yet.</p>';}
load();setInterval(load,5000);
</script></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _authed(self):
        got = self.headers.get("Authorization", "")
        want = "Basic " + base64.b64encode(f"{USER}:{PASS}".encode()).decode()
        if hmac.compare_digest(got, want):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="code review"')
        self.end_headers()
        return False

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._authed():
            return
        if self.path == "/run":
            return self._send(200, PAGE.replace("__MODEL__", html.escape(os.environ.get("MODEL_NAME", "LLM"))),
                              "text/html; charset=utf-8")
        if self.path == "/api/jobs":
            with jobs_lock:
                out = [{k: j.get(k) for k in ("id", "repo", "kind", "value", "target", "status", "summary")}
                       | {"log": "\n".join(j["log"][-150:]),
                          "elapsed": (f"{int(((j.get('finished') or time.time()) - j['started']) / 60)}m"
                                      if j.get("started") else None)}
                       for j in reversed(jobs)]
            return self._send(200, json.dumps(out))
        # Everything else is ocr's own viewer (its host guard accepts our loopback Host).
        try:
            with urllib.request.urlopen(VIEWER + self.path, timeout=30) as r:
                body = r.read()
                if self.path in ("/", "") and b"</body>" in body:
                    body = body.replace(b"</body>", b'<p style="text-align:center;margin:24px"><a href="/run">'
                                        b'&rarr; Run a new review</a></p></body>', 1)
                return self._send(r.status, body, r.headers.get("Content-Type", "text/html"))
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read(), e.headers.get("Content-Type", "text/plain"))
        except Exception as e:
            return self._send(502, f"viewer unavailable: {e}", "text/plain")

    def do_POST(self):
        if not self._authed():
            return
        if self.path != "/api/jobs":
            return self._send(404, '{"error":"not found"}')
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            repo, kind, value = str(req.get("repo", "")).strip(), req.get("kind"), str(req.get("value", "")).strip()
        except Exception:
            return self._send(400, '{"error":"bad JSON"}')
        if not REPO_RE.match(repo):
            return self._send(400, json.dumps({"error": "repository must look like https://github.com/owner/repo"}))
        if kind not in ("latest", "commit", "pr"):
            return self._send(400, json.dumps({"error": "unknown review type"}))
        if kind == "commit" and not SHA_RE.match(value):
            return self._send(400, json.dumps({"error": "commit must be a 7-40 character hex SHA"}))
        if kind == "pr" and not PR_RE.match(value):
            return self._send(400, json.dumps({"error": "PR must be a number"}))
        with queue_cv:
            job = {"id": len(jobs) + 1, "repo": repo, "kind": kind, "value": value if kind != "latest" else "",
                   "status": "queued", "log": [], "created": time.time()}
            jobs.append(job)
            queue.append(job)
            queue_cv.notify()
        return self._send(202, json.dumps({"id": job["id"]}))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    os.makedirs(WORK, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
