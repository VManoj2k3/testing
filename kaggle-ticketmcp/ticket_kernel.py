# Runs INSIDE a Kaggle CPU session: serves the fake ticket-desk MCP server (tests/ticket_mcp.py)
# behind a Cloudflare quick tunnel so a RAGFlow agent can call it (RAGFlow refuses MCP servers on
# non-public addresses). Bearer-key protected; every tool call is posted to ntfy; stops itself
# after MAX_RUNTIME_MIN. __PLACEHOLDERS__ are filled by launch.sh.
import base64, re, subprocess, time, urllib.request

KEY, TOPIC, MAX_MIN = "__KEY__", "__NTFY_TOPIC__", int("__MAX_RUNTIME_MIN__")
open("/tmp/ticket_mcp.py", "w").write(base64.b64decode("__SERVER_B64__").decode())

def notify(m):
    print(m, flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=m.encode(), method="POST"), timeout=10)
    except Exception as e:
        print("ntfy failed", e)

subprocess.Popen(["python3", "/tmp/ticket_mcp.py", "8765", "/tmp/calls.jsonl", KEY, TOPIC])
subprocess.run("curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared", shell=True, check=True)
p = subprocess.Popen(["/tmp/cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8765"], stderr=subprocess.PIPE, text=True)
for line in p.stderr:
    m = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", line)
    if m:
        notify(f"MCP_URL {m.group(0)}/mcp")
        break
deadline = time.time() + MAX_MIN * 60
while time.time() < deadline and p.poll() is None:
    p.stderr.readline()
notify("STOPPED")
