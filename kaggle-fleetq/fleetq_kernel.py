# Runs INSIDE a Kaggle CPU session: FleetQ (escapeboy/agent-fleet-o, Laravel 13) installed natively by
# setup_fleetq.sh, served through a Cloudflare quick tunnel, with Qwen (the kaggle-llama GPU notebook) connected as
# its OpenAI-compatible LLM once that notebook posts LLM_URL on its ntfy topic. Kill switch + safety timer included.
# Double-underscore placeholders are filled by launch.sh.
import base64, json, os, re, signal, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "__SECRET__"
NTFY_TOPIC = "__NTFY_TOPIC__"
MAX_RUNTIME_MIN = int("__MAX_RUNTIME_MIN__")
ADMIN_EMAIL, ADMIN_PASS = "__ADMIN_EMAIL__", "__ADMIN_PASS__"
QWEN_TOPIC, QWEN_KEY, QWEN_MODEL = "__QWEN_TOPIC__", "__QWEN_KEY__", "__QWEN_MODEL__"
SETUP = base64.b64decode("__SETUP_B64__").decode()
SHIM = base64.b64decode("__SHIM_B64__").decode()
SRC, WEB_PORT, KILL_PORT = "/opt/fleetq", 80, 8081 + 1000
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
    def do_GET(self):
        # Secret-protected diagnostics: last lines of the Laravel log and worker logs.
        if self.path.startswith("/log") and self.headers.get("X-Kill-Secret") == SECRET:
            out = subprocess.run(f"tail -n 150 {SRC}/storage/logs/laravel.log; for f in /tmp/horizon.log /tmp/reverb.log; "
                                 "do echo \"== $f\"; tail -n 20 $f; done", shell=True, capture_output=True, text=True).stdout
            self.send_response(200); self.end_headers(); self.wfile.write(out.encode(errors="replace"))
        else:
            self.send_response(403); self.end_headers()
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


def qwen_url():
    """Newest LLM_URL the Qwen notebook posted (None until it is up)."""
    raw = urllib.request.urlopen(f"https://ntfy.sh/{QWEN_TOPIC}/json?poll=1&since=all", timeout=30).read().decode()
    urls = [json.loads(l)["message"].split()[1] for l in raw.splitlines()
            if l.strip() and json.loads(l).get("event") == "message" and json.loads(l)["message"].startswith("LLM_URL ")]
    return urls[-1] if urls else None

def connect_qwen():
    for _ in range(240):                       # up to 2 h
        url = None
        try:
            url = qwen_url()
        except Exception as e:
            print("ntfy poll failed:", e, flush=True)
        if url:
            break
        time.sleep(30)
    else:
        notify("WARN Qwen never posted LLM_URL; connect it in Settings > AI providers by hand"); return
    script = f"""<?php
require '{SRC}/vendor/autoload.php';
$app = require '{SRC}/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
$t = App\\Domain\\Shared\\Models\\Team::first();
App\\Domain\\Shared\\Models\\TeamProviderCredential::updateOrCreate(
    ['team_id' => $t->id, 'provider' => 'openai_compatible'],
    ['credentials' => ['base_url' => {json.dumps(url.rstrip('/'))}, 'api_key' => {json.dumps(QWEN_KEY)},
                       'models' => [{json.dumps(QWEN_MODEL)}]], 'is_active' => true]);
$s = $t->settings ?? [];
$s['default_llm_provider'] = 'openai_compatible'; $s['default_llm_model'] = {json.dumps(QWEN_MODEL)};
$s['assistant_llm_provider'] = 'openai_compatible'; $s['assistant_llm_model'] = {json.dumps(QWEN_MODEL)};
$t->update(['settings' => $s]);
echo 'qwen connected for team ' . $t->name . PHP_EOL;
"""
    with open("/tmp/connect_qwen.php", "w") as f:
        f.write(script)
    out = sh(f"su -s /bin/bash www-data -c 'php /tmp/connect_qwen.php'")
    notify("QWEN " + url + " | " + out.strip().splitlines()[-1][:200])

def main():
    deadline = time.time() + MAX_RUNTIME_MIN * 60
    threading.Thread(target=lambda: (time.sleep(max(0, deadline - time.time())),
                                     shutdown(f"max runtime {MAX_RUNTIME_MIN} min reached")), daemon=True).start()
    threading.Thread(target=HTTPServer(("127.0.0.1", KILL_PORT), KillHandler).serve_forever, daemon=True).start()
    sh("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared")
    notify(f"KILL_URL {tunnel(KILL_PORT)}")
    app_url = tunnel(WEB_PORT)                  # first, so APP_URL and the websocket host are baked into the build
    notify(f"TUNNEL {app_url}")
    with open("/tmp/setup_fleetq.sh", "w") as f:
        f.write(SETUP)
    with open("/tmp/browserless_shim.py", "w") as f:
        f.write(SHIM)
    t0 = time.time()
    sh_steps("bash /tmp/setup_fleetq.sh", 3600,
             env={"APP_URL": app_url, "ADMIN_EMAIL": ADMIN_EMAIL, "ADMIN_PASS": ADMIN_PASS, "FLEETQ_SRC": SRC})
    notify(f"BUILT in {int(time.time() - t0)}s")
    for name, cmd in [("horizon", "php artisan horizon"),
                      ("scheduler", "while true; do php artisan schedule:run --no-interaction; sleep 60; done"),
                      ("reverb", "php artisan reverb:start --host=127.0.0.1 --port=8081")]:
        p = subprocess.Popen(["su", "-s", "/bin/bash", "www-data", "-c", f"cd {SRC} && {cmd}"],
                             stdout=open(f"/tmp/{name}.log", "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        procs.append(p)
    tok = open("/opt/browserless/token").read().strip()
    for name, cmd in [("mjml", "cd /opt/mjml && exec node server.js"),
                      ("searxng", "cd /opt/searxng && SEARXNG_SETTINGS_PATH=/opt/searxng/settings.yml exec venv/bin/python -m searx.webapp"),
                      ("browserless", f"BROWSERLESS_TOKEN={tok} exec /opt/browserless/bin/python /tmp/browserless_shim.py 3000")]:
        p = subprocess.Popen(["bash", "-c", cmd], stdout=open(f"/tmp/{name}.log", "w"), stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL)
        procs.append(p)
    names = ["horizon", "scheduler", "reverb", "mjml", "searxng", "browserless"]
    time.sleep(20)
    notify("WORKERS " + " ".join(f"{n}:{'up' if p.poll() is None else 'DIED ' + open(f'/tmp/{n}.log').read()[-200:]}"
                                 for n, p in zip(names, procs[-6:])))
    checks = {"mjml": "curl -s -m 10 http://127.0.0.1:15500/healthcheck",
              "searxng": "curl -s -m 30 'http://127.0.0.1:8888/search?q=autosar&format=json' | head -c 80",
              "browserless": f"curl -s -m 60 -X POST -H 'Authorization: Token {tok}' http://127.0.0.1:3000/content "
                             "-d '{\"url\":\"https://example.com\"}'" " | head -c 80"}
    notify("SIDECARS " + " | ".join(f"{k}: {sh(v + ' || true').strip()[:90]}" for k, v in checks.items()))
    notify("CHECK login " + sh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/login").strip()
           + " register " + sh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/register").strip())
    notify(f"APP_URL {app_url}")
    notify("READY fleetq")
    connect_qwen()
    log, pos = f"{SRC}/storage/logs/laravel.log", 0
    while True:                                  # forward each new Laravel error entry (header line only)
        time.sleep(30)
        try:
            with open(log, errors="replace") as f:
                f.seek(pos); chunk = f.read(); pos = f.tell()
        except FileNotFoundError:
            continue
        for line in chunk.splitlines():
            if re.match(r"^\[[^\]]+\] \w+\.(ERROR|CRITICAL|ALERT|EMERGENCY):", line):
                notify("LARAVEL " + line[:700])

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: shutdown("SIGTERM"))
    try:
        main()
    except Exception as e:
        shutdown(f"{type(e).__name__}: {e}"[:1500], error=True)
