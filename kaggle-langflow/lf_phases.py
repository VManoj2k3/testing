"""Langflow phases for the Kaggle demo (also runnable locally to rehearse against any local model).

Phase A (internal, before any URL exists): start Langflow with the build-from-description workaround,
which needs RESTRICT_LOCAL_FILE_ACCESS=false, and ask the assistant to build an agent.
Phase B (what the user gets): restart with the restriction back on, register the local model, create a
template agent and a from-scratch agent, and run each once.

CLI: python lf_phases.py <venv> <home> <model_url> <model_name> <admin_password> [A|B|AB]
"""
import glob, json, os, secrets, subprocess, sys, time, urllib.parse, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "langflow-offline"  # in the repo; on Kaggle both files are copied next to this one
ENV_EXAMPLE = next(p for p in (HERE / "langflow.env.example", SHARED / "langflow.env.example") if p.exists())
sys.path[:0] = [str(HERE), str(SHARED)]


def site_packages(venv):
    return Path(glob.glob(f"{venv}/lib/python3*/site-packages")[0])


def write_env(venv, home, password, restrict, model_host="127.0.0.1"):
    comps = site_packages(venv) / "lfx" / "components"
    lines = []
    for line in ENV_EXAMPLE.read_text().splitlines():
        if line.startswith("LANGFLOW_SUPERUSER_PASSWORD="):
            line = f"LANGFLOW_SUPERUSER_PASSWORD={password}"
        elif line.startswith("LANGFLOW_CONFIG_DIR="):
            line = f"LANGFLOW_CONFIG_DIR={home}/lfdata"
        elif line.startswith("LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS="):
            line = f"LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS={'true' if restrict else 'false'}"
        elif line.startswith("LANGFLOW_SSRF_ALLOWED_HOSTS="):
            line = f"LANGFLOW_SSRF_ALLOWED_HOSTS={model_host}"
        lines.append(line)
    lines += [f"LANGFLOW_DATABASE_URL=sqlite:///{home}/lfdata/langflow.db",
              f"LANGFLOW_DIRECTORY_COMPONENT_ALLOWED_ROOTS={comps}"]
    # The assistant reads component sources from this git-checkout path; point it at the installed ones.
    link = Path(home) / "src/lfx/src/lfx/components"
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(comps)
    (Path(home) / "lfdata").mkdir(exist_ok=True)
    env_file = Path(home) / "langflow.env"
    env_file.write_text("\n".join(lines) + "\n")
    env_file.chmod(0o600)
    return env_file


def wait_health(p, log, tries=300):
    for _ in range(tries):
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://127.0.0.1:7860/health", timeout=5)
            return
        except Exception:
            if p.poll() is not None:
                raise RuntimeError("langflow exited: " + Path(log).read_text(errors="replace")[-1200:])
            time.sleep(3)
    raise RuntimeError("langflow never became healthy")


def start(venv, home, password, restrict, model_url):
    # Langflow rewrites localhost/127.0.0.1 to the Docker host when it detects a container (Kaggle is one),
    # so the model is served on another loopback address and that host is the only SSRF exception.
    env_file = write_env(venv, home, password, restrict, urllib.parse.urlparse(model_url).hostname)
    log = f"{home}/langflow.log"
    # Values the env file can't carry reliably are passed in the environment too.
    # OPENAI_* in Langflow's own environment: imported as variables for every user (new ones too), so
    # copies of shared templates run for everyone. As per-user variables only the admin could run them.
    env = {"HOME": home, "PATH": f"{venv}/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
           "LITELLM_LOCAL_MODEL_COST_MAP": "True", "LANGFLOW_MODELS_DEV_REFRESH": "false",
           "OPENAI_BASE_URL": model_url, "OPENAI_API_KEY": "local-no-key"}
    p = subprocess.Popen([f"{venv}/bin/langflow", "run", "--env-file", str(env_file)], cwd=home, env=env,
                         stdout=open(log, "w"), stderr=subprocess.STDOUT, start_new_session=True)
    wait_health(p, log)
    return p


def stop(p):
    p.terminate()
    try:
        p.wait(30)
    except subprocess.TimeoutExpired:
        p.kill()


def drive_env(venv, home, model_url, model, password):
    os.environ.update({"LF_PASSWORD": password, "LF_MODEL": model, "LF_MODEL_URL": model_url,
                       "LF_STATE": f"{home}/.lfstate",
                       "LF_TPL_DIR": str(site_packages(venv) / "langflow/initial_setup/starter_projects")})
    import lf_drive
    return lf_drive


def assist_probe(d, model, ask):
    """Ask the build-from-description assistant for an agent; return (node types, seconds, reply)."""
    tok = d.login()
    fid = d.call("POST", "/flows/", {"name": "Built by assistant", "data": {"nodes": [], "edges": []}}, token=tok)["id"]
    body = json.dumps({"flow_id": fid, "input_value": ask, "provider": "OpenAI", "model_name": model,
                       "iterations_limit": 40}).encode()
    req = urllib.request.Request(d.BASE + "/agentic/assist/stream", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
    t, reply = time.time(), ""
    for raw in d.opener.open(req, timeout=1800):
        line = raw.decode(errors="replace").strip()
        if line.startswith("data:"):
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if ev.get("event") == "complete":
                reply = json.dumps(ev.get("data", {}).get("result", ev))[:400]
    flow = d.call("GET", f"/flows/{fid}", token=tok)
    nodes = [n["data"].get("type") for n in (flow.get("data") or {}).get("nodes", [])]
    return nodes, time.time() - t, reply


ASK = ("Build a flow: Chat Input connected to an Agent, Agent connected to Chat Output. The agent reads meeting "
       "notes the user pastes and returns every action item with its owner and due date.")
QUESTIONS = [("template", "What is 17.5% of 2340? Use the calculator tool.", "409.5"),
             ("triage", "Excel crashes every time I open a file with macros.", "SOFTWARE")]


def phase_a(venv, home, model_url, model, password, report=print):
    p = start(venv, home, password, restrict=False, model_url=model_url)
    try:
        d = drive_env(venv, home, model_url, model, password)
        d.setup(d.login())
        nodes, secs, reply = assist_probe(d, model, ASK)
        report(f"ASSIST built {len(nodes)} nodes {nodes} in {secs:.0f}s" if nodes
               else f"ASSIST built nothing in {secs:.0f}s; reply: {reply}")
    except SystemExit as e:  # lf_drive exits on HTTP errors (CLI behaviour); report it here
        raise RuntimeError(f"phase A: {e}") from None
    finally:
        stop(p)


COMPANY_TEMPLATE = "Helpdesk Triage (company)"


def publish_template(venv, d, tok, flow_name, tpl_name):
    """Admin route: export a flow into Langflow's starter_projects folder (shown under Templates after restart)."""
    src = next(f for f in d.call("GET", "/flows/?get_all=true&header_flows=false", token=tok) if f["name"] == flow_name)
    tpl = {"data": src["data"], "description": f"{flow_name}, published by the admin", "endpoint_name": None,
           "id": str(uuid.uuid4()), "is_component": False, "last_tested_version": "1.12.5", "locked": False,
           "name": tpl_name, "tags": ["agents"]}
    path = site_packages(venv) / "langflow/initial_setup/starter_projects" / f"{tpl_name}.json"
    path.write_text(json.dumps(tpl, indent=2), encoding="utf-8")


def check_second_user(d, admin_tok, question, expect):
    """A throwaway non-admin user copies the company template and runs it; the user is deleted afterwards."""
    name, pw = "check-" + secrets.token_hex(3), secrets.token_urlsafe(12)
    uid = d.call("POST", "/users/", {"username": name, "password": pw})["id"]
    try:
        d.call("PATCH", f"/users/{uid}", {"is_active": True}, token=admin_tok)
        tok = d.call("POST", "/login", {"username": name, "password": pw}, form=True)["access_token"]
        tpls = d.call("GET", "/flows/basic_examples/", token=tok)
        tpl = next((t for t in tpls if t["name"] == COMPANY_TEMPLATE), None)
        if not tpl:
            return f"SHARED template not visible to a second user ({len(tpls)} templates)"
        leaked = [f["name"] for f in d.call("GET", "/flows/?get_all=true&header_flows=true", token=tok)]
        mine = d.call("POST", "/flows/", {"name": "copy", "data": tpl["data"]}, token=tok)
        key = d.call("POST", "/api_key/", {"name": "check"}, token=tok)["api_key"]
        out = d.call("POST", f"/run/{mine['id']}?stream=false",
                     {"input_value": question, "input_type": "chat", "output_type": "chat"}, token=key)
        text = out["outputs"][0]["outputs"][0]["results"]["message"]["text"]
        ok = expect.lower() in text.lower()
        return (f"SHARED second user: sees {len(tpls)} templates incl. company one, admin flows visible: "
                f"{leaked or 'none'}, ran copy: {'PASS' if ok else 'CHECK'} {text[:160]!r}")
    finally:
        d.call("DELETE", f"/users/{uid}", token=admin_tok)


def phase_b(venv, home, model_url, model, password, report=print):
    p = start(venv, home, password, restrict=True, model_url=model_url)
    try:
        d = drive_env(venv, home, model_url, model, password)
        tok = d.login()
        d.setup(tok)
        ids = {"template": d.template(tok), "triage": d.scratch(tok)}
        d.bugfinder(tok)  # Code Bug Finder (streaming on); not run here, reviews take 20-100 s
        for key, q, expect in QUESTIONS:
            text = d.run(tok, ids[key], q)
            ok = expect.lower() in (text or "").lower()
            report(f"AGENT {key}: {'PASS' if ok else 'CHECK'} {text[:200]!r}")
        publish_template(venv, d, tok, "Helpdesk Triage", COMPANY_TEMPLATE)
        stop(p)
        p = start(venv, home, password, restrict=True, model_url=model_url)  # templates reload on start
        report(check_second_user(d, d.login(), "I forgot my password and I am locked out of email.", "ACCOUNT"))
    except SystemExit as e:
        stop(p)
        raise RuntimeError(f"phase B: {e}") from None
    return p


if __name__ == "__main__":
    venv, home, model_url, model, pw, *ph = sys.argv[1:]
    ph = ph[0] if ph else "AB"
    if "A" in ph:
        phase_a(venv, home, model_url, model, pw)
    if "B" in ph:
        p = phase_b(venv, home, model_url, model, pw)
        print("Langflow left running on 127.0.0.1:7860, pid", p.pid)
