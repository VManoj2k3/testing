"""Drive a local Langflow over its REST API: register a local model, build agents, run them.

Works on Linux and Windows (stdlib only). Talks to localhost only and never uses a proxy.

Environment:
  LF_URL        Langflow base URL (default http://127.0.0.1:7860)
  LF_USER       admin user (default admin)
  LF_PASSWORD   admin password (required)
  LF_MODEL      model name served by the local OpenAI-compatible server (default qwen3-4b)
  LF_MODEL_URL  local OpenAI-compatible base URL (default http://127.0.0.1:8095/v1)
  LF_TPL_DIR    Langflow starter_projects dir (default: located from the installed langflow package)
  LF_STATE      dir for the cached login token and API key (default ./.lfstate)

Usage:
  python lf_drive.py setup                       register the local model as the OpenAI provider
  python lf_drive.py template                    create an agent from the "Simple Agent" template
  python lf_drive.py scratch                     create a helpdesk triage agent with its own instructions
  python lf_drive.py run <flow_id> <question>    run a flow and print the answer
  python lf_drive.py check <flow_id> <question> <expected>   like run, exits 1 if <expected> is missing
"""
import importlib.util, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BASE = os.environ.get("LF_URL", "http://127.0.0.1:7860").rstrip("/") + "/api/v1"
MODEL_NAME = os.environ.get("LF_MODEL", "qwen3-4b")
MODEL_URL = os.environ.get("LF_MODEL_URL", "http://127.0.0.1:8095/v1")
STATE = Path(os.environ.get("LF_STATE", ".lfstate"))
MODEL = [{"name": MODEL_NAME, "provider": "OpenAI", "metadata": {}}]
INTERNET_ONLY = {"UnifiedWebSearch", "URLComponent"}  # template tools that need the internet
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def tpl_dir():
    if os.environ.get("LF_TPL_DIR"):
        return Path(os.environ["LF_TPL_DIR"])
    spec = importlib.util.find_spec("langflow")
    if not spec or not spec.submodule_search_locations:
        sys.exit("set LF_TPL_DIR or run with the Python that has langflow installed")
    return Path(list(spec.submodule_search_locations)[0]) / "initial_setup" / "starter_projects"


def call(method, path, body=None, form=False, token=None, timeout=900):
    data, headers = None, {}
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    if token and token.startswith("sk-"):
        headers["x-api-key"] = token
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        return json.loads(opener.open(req, timeout=timeout).read() or b"null")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read()[:600].decode(errors='replace')}")


def cached(name, make, max_age=None):
    """Login is rate limited, so the token and API key are cached between calls."""
    STATE.mkdir(exist_ok=True)
    p = STATE / name
    if p.exists() and (max_age is None or time.time() - p.stat().st_mtime < max_age):
        return p.read_text().strip()
    value = make()
    p.write_text(value)
    os.chmod(p, 0o600)
    return value


def login():
    def fresh():
        pw = os.environ.get("LF_PASSWORD") or sys.exit("LF_PASSWORD is required")
        user = os.environ.get("LF_USER", "admin")
        return call("POST", "/login", {"username": user, "password": pw}, form=True)["access_token"]
    return cached("token", fresh, max_age=3000)


def api_key(tok):
    return cached("api_key", lambda: call("POST", "/api_key/", {"name": "lf_drive"}, token=tok)["api_key"])


def setup(tok):
    have = {v["name"]: v for v in call("GET", "/variables/", token=tok)}
    # Base URL first: saving OPENAI_API_KEY triggers a validation call, which goes to
    # api.openai.com when no base URL is set yet.
    for name, value in (("OPENAI_BASE_URL", MODEL_URL), ("OPENAI_API_KEY", "local-no-key")):
        if name in have:
            call("PATCH", f"/variables/{have[name]['id']}", {"id": have[name]["id"], "name": name, "value": value}, token=tok)
        else:
            call("POST", "/variables/", {"name": name, "value": value, "type": "Credential", "default_fields": []}, token=tok)
    print("local model registered:", MODEL_URL, MODEL_NAME)


def load_template(name):
    flow = json.loads((tpl_dir() / f"{name}.json").read_text(encoding="utf-8"))
    gone = {n["id"] for n in flow["data"]["nodes"] if n["data"].get("type") in INTERNET_ONLY}
    flow["data"]["nodes"] = [n for n in flow["data"]["nodes"] if n["id"] not in gone]
    flow["data"]["edges"] = [e for e in flow["data"]["edges"] if e["source"] not in gone and e["target"] not in gone]
    for n in flow["data"]["nodes"]:
        t = n["data"].get("node", {}).get("template", {})
        if isinstance(t.get("model"), dict):
            t["model"]["value"] = MODEL
    return flow


def create(tok, name, flow):
    f = call("POST", "/flows/", {"name": name, "description": flow.get("description", ""), "data": flow["data"]}, token=tok)
    print(f["id"])
    return f["id"]


def template(tok):
    return create(tok, "Simple Agent (local model)", load_template("Simple Agent"))


def scratch(tok):
    flow = load_template("Simple Agent")
    flow["data"]["nodes"] = [n for n in flow["data"]["nodes"] if n["data"].get("type") != "note"]
    for n in flow["data"]["nodes"]:
        if n["data"].get("type") == "Agent":
            t = n["data"]["node"]["template"]
            t["system_prompt"]["value"] = (
                "You are an IT helpdesk triage agent. Classify the user's problem as one of: "
                "NETWORK, ACCOUNT, HARDWARE, SOFTWARE. Reply with exactly two lines:\n"
                "CATEGORY: <one of the four>\nNEXT STEP: <one concrete first step>")
            t["add_current_date_tool"]["value"] = False
    return create(tok, "Helpdesk Triage", flow)


def run(tok, flow_id, question):
    t = time.time()
    r = call("POST", f"/run/{flow_id}?stream=false",
             {"input_value": question, "input_type": "chat", "output_type": "chat"}, token=api_key(tok))
    try:
        text = r["outputs"][0]["outputs"][0]["results"]["message"]["text"]
    except (KeyError, IndexError, TypeError):
        text = ""
    print(f"[{time.time() - t:.0f}s] Q: {question}\nA: {text or json.dumps(r)[:800]}")
    return text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tok, cmd = login(), sys.argv[1]
    if cmd == "setup":
        setup(tok)
    elif cmd == "template":
        template(tok)
    elif cmd == "scratch":
        scratch(tok)
    elif cmd == "run":
        if not run(tok, sys.argv[2], sys.argv[3]):
            sys.exit("FAIL: empty answer")
    elif cmd == "check":
        text = run(tok, sys.argv[2], sys.argv[3])
        if sys.argv[4].lower() not in text.lower():
            sys.exit(f"FAIL: expected {sys.argv[4]!r} in the answer")
        print("PASS")
    else:
        sys.exit(__doc__)
