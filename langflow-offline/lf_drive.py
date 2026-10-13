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
import gzip, importlib.util, json, os, sys, time, urllib.error, urllib.parse, urllib.request
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
        raw = opener.open(req, timeout=timeout).read()
        if raw[:2] == b"\x1f\x8b":  # some list endpoints return gzip without Content-Encoding
            raw = gzip.decompress(raw)
        return json.loads(raw or b"null")
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


BUGFINDER_PROMPT = """You are a senior code reviewer. Find BUGS in the code the user pastes: logic errors, off-by-one,
null/None handling, resource leaks, injection, race conditions, missing await, wrong error handling, memory
safety. Do not comment on style, naming or formatting.

For each bug, output exactly:
LINE: <line number or "unsure">
SEVERITY: high | medium | low
BUG: <one sentence>
WHY: <what goes wrong at runtime>
FIX: <corrected code>

If you find no real bug, output exactly: NO BUGS FOUND
Never invent line numbers or bugs you are not confident about."""


def bugfinder(tok):
    """Code Bug Finder: the Agent with a reviewer prompt and no tools (no code execution on a shared server)."""
    flow = load_template("Simple Agent")
    flow["data"]["nodes"] = [n for n in flow["data"]["nodes"] if n["data"].get("type") != "note"]
    for n in flow["data"]["nodes"]:
        if n["data"].get("type") == "Agent":
            t = n["data"]["node"]["template"]
            t["system_prompt"]["value"] = BUGFINDER_PROMPT
            t["add_current_date_tool"]["value"] = False
            t["add_calculator_tool"]["value"] = False
            t["stream"]["value"] = True  # long reviews: keep the connection busy (tunnels cut idle requests at 100 s)
    return create(tok, "Code Bug Finder", flow)


AGENTS = {
    "Meeting → Action Items": """You turn messy meeting notes into a clear action list.
Output:
1. A markdown table with columns: # | Action | Owner | Due date | Notes. Use "unassigned" or "not set" when
   the notes don't say; never invent names or dates.
2. "Decisions made:" as bullets.
3. "Open questions:" as bullets (things nobody answered or owned).
Keep it short. No introduction.""",
    "Email Writer": """You write professional emails. The user gives the situation and optionally a tone
(formal, friendly, firm, apologetic; default: friendly-professional) and maybe an email to reply to.
Output exactly:
Subject: <subject line>

<email body, under 150 words, with greeting and sign-off "[Your name]">
Do not add facts the user did not give; use [placeholders] for missing details like dates or numbers.""",
    "Bug Report → Jira Ticket": """You turn a rough bug complaint into a well-formed ticket.
Output exactly these fields:
Title: <short, specific>
Component: <best guess, or "unknown">
Priority: <Highest/High/Medium/Low> - <one-line reason based on user impact>
Environment: <from the report, or "not given">
Steps to reproduce:
1. ...
Expected result: ...
Actual result: ...
Missing information: <questions to ask the reporter>
Never invent details that are not in the report; put guesses under Missing information.""",
    "SQL Helper": """You write SQL from plain English. The user gives a question and (ideally) the table schema.
Output:
1. The SQL in a ```sql block (standard SQL; mention the dialect if it matters).
2. "How it works:" 2-4 bullets.
3. "Assumptions:" anything you guessed about the schema.
If no schema is given, ask for it in one line and show a best-guess query with clearly named assumed columns.
Never write UPDATE/DELETE/DROP unless explicitly asked, and then warn about it. You never execute queries.""",
    "Unit Test Generator": """You are a test generator. Whatever the user sends is source code to be tested.
NEVER explain the code. ALWAYS answer with tests, in this exact structure:

```<language>
<complete test file: imports, then one test per case, each with a one-line comment>
```
Possible bugs:
- <behaviour the tests expose as wrong, or "none found">

Framework: pytest for Python, Jest for JavaScript/TypeScript, JUnit 5 for Java, unless the user names another.
Write AT MOST 6 tests and keep the file under 40 lines: pick the most valuable normal, edge (empty, zero,
negative, boundaries, None/null) and error cases.""",
    "Release Notes Writer": """You turn a list of commit messages or changes into release notes for users.
Output markdown with sections (omit empty ones): ## New features, ## Improvements, ## Bug fixes,
## Breaking changes (with what users must do), ## Internal (one line, optional).
Rewrite developer jargon into plain language, merge duplicates, drop noise like "fix typo" or "merge branch".
Do not invent changes that are not in the list.""",
}

CHAIN_STEPS = [
    ("Drafter", """You are the DRAFTER. Write a first version of what the user asks for (a pitch, plan, announcement,
idea, etc.). Be concrete. Output only the draft."""),
    ("Critic", """You are the CRITIC. You receive a draft. Reply in exactly this format:
DRAFT:
<the draft, copied unchanged>

CRITIQUE:
- <3-5 specific weaknesses: unclear points, missing facts, weak arguments, tone problems>"""),
    ("Improver", """You are the IMPROVER. You receive a DRAFT and a CRITIQUE. Rewrite the draft so every critique point
is fixed. Output only:
FINAL VERSION:
<improved text>

WHAT CHANGED:
- <one bullet per critique point>"""),
]


def _agent_flow(prompt):
    """Simple Agent template without internet tools or notes; the given instructions; no tools; streaming on."""
    flow = load_template("Simple Agent")
    flow["data"]["nodes"] = [n for n in flow["data"]["nodes"] if n["data"].get("type") != "note"]
    for n in flow["data"]["nodes"]:
        if n["data"].get("type") == "Agent":
            t = n["data"]["node"]["template"]
            t["system_prompt"]["value"] = prompt
            t["add_current_date_tool"]["value"] = False
            t["add_calculator_tool"]["value"] = False
            t["stream"]["value"] = True
    return flow


def build_agent(tok, name, prompt):
    return create(tok, name, _agent_flow(prompt))


def _handle(d):
    return json.dumps(d).replace('"', "œ")


def _edge(src, src_type, tgt, tgt_input_types, tgt_field_type):
    sh = {"dataType": src_type, "id": src, "name": "message" if src_type == "ChatInput" else "response",
          "output_types": ["Message"]}
    th = {"fieldName": "input_value", "id": tgt, "inputTypes": tgt_input_types, "type": tgt_field_type}
    compact = lambda h: json.dumps(h, separators=(",", ":")).replace('"', "œ")
    return {"source": src, "target": tgt, "sourceHandle": _handle(sh), "targetHandle": _handle(th),
            "id": f"reactflow__edge-{src}{compact(sh)}-{tgt}{compact(th)}",
            "data": {"sourceHandle": sh, "targetHandle": th}, "className": "", "animated": False}


def build_chain(tok, name="Idea → Critic → Improver"):
    """Multi-agent flow: Chat Input -> Drafter -> Critic -> Improver -> Chat Output (three Agent nodes)."""
    flow = _agent_flow(CHAIN_STEPS[0][1])
    nodes = flow["data"]["nodes"]
    agent = next(n for n in nodes if n["data"]["type"] == "Agent")
    chat_in = next(n for n in nodes if n["data"]["type"] == "ChatInput")
    chat_out = next(n for n in nodes if n["data"]["type"] == "ChatOutput")
    agents = [agent]
    for i, (_, prompt) in enumerate(CHAIN_STEPS[1:], start=1):
        clone = json.loads(json.dumps(agent))
        clone["id"] = clone["data"]["id"] = f"Agent-chain{i}"
        clone["position"] = {"x": agent["position"]["x"] + 450 * i, "y": agent["position"]["y"]}
        clone["data"]["node"]["template"]["system_prompt"]["value"] = prompt
        nodes.append(clone)
        agents.append(clone)
    for a, (label, _) in zip(agents, CHAIN_STEPS):
        a["data"]["node"]["display_name"] = f"Agent: {label}"
    chat_out["position"] = {"x": agents[-1]["position"]["x"] + 450, "y": chat_out["position"]["y"]}
    edges = [_edge(chat_in["id"], "ChatInput", agents[0]["id"], ["Message"], "str")]
    edges += [_edge(a["id"], "Agent", b["id"], ["Message"], "str") for a, b in zip(agents, agents[1:])]
    edges.append(_edge(agents[-1]["id"], "Agent", chat_out["id"], ["Data", "JSON", "DataFrame", "Table", "Message"], "other"))
    flow["data"]["edges"] = edges
    return create(tok, name, flow)


def build_all(tok):
    ids = {name: build_agent(tok, name, prompt) for name, prompt in AGENTS.items()}
    ids["Idea → Critic → Improver"] = build_chain(tok)
    return ids


def run_stream(tok, flow_id, question, session_id=None):
    """Like run(), but streamed: events arrive while the model writes, so proxies don't time out."""
    t = time.time()
    req = urllib.request.Request(BASE + f"/run/{flow_id}?stream=true", method="POST",
                                 data=json.dumps({"input_value": question, "input_type": "chat", "output_type": "chat",
                                                  # a fresh session per call, so earlier chats don't grow the prompt
                                                  "session_id": session_id or f"lfdrive-{time.time_ns()}"}).encode(),
                                 headers={"Content-Type": "application/json", "x-api-key": api_key(tok)})
    chunks, final = [], ""
    for raw in opener.open(req, timeout=1800):
        line = raw.decode(errors="replace").strip()
        if not line:
            continue
        try:
            ev = json.loads(line[5:] if line.startswith("data:") else line)
        except ValueError:
            continue
        kind, data = ev.get("event"), ev.get("data") or {}
        if kind == "token":
            chunks.append(data.get("chunk", ""))
        elif kind == "end":
            try:
                final = data["result"]["outputs"][0]["outputs"][0]["results"]["message"]["text"]
            except (KeyError, IndexError, TypeError):
                pass
        elif kind == "error":
            sys.exit(f"run failed: {json.dumps(data)[:600]}")
    text = final or "".join(chunks)
    print(f"[{time.time() - t:.0f}s] Q: {question}\nA: {text}")
    return text


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
    elif cmd == "bugfinder":
        bugfinder(tok)
    elif cmd == "agents":
        for name, fid in build_all(tok).items():
            print(f"{fid}\t{name}")
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
