"""RAGFlow feature matrix: per-format upload, parse and answer checks, chunking methods, agent templates.

Usage:
  python3 feature_matrix.py formats   <base> <email> <pw> <samples dir>        # upload+parse+ask per file
  python3 feature_matrix.py chunking  <base> <email> <pw> <file> <method>...   # one dataset per method
  python3 feature_matrix.py templates <base> <email> <pw> <dataset id> <llm_id> # run every agent template once
Reuses the login/encryption helpers of eval_rag.py and the agent helpers of eval_agent.py.
"""
import json, re, sys, time, urllib.error, urllib.request, uuid, mimetypes
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
MODE, BASE, EMAIL, PW, *REST = sys.argv[1:]
sys.argv = [sys.argv[0], BASE, EMAIL, PW, "x"]  # eval_rag / eval_agent read argv at import
from eval_rag import call, enc  # noqa: E402

API = BASE.rstrip("/") + "/api/v1"
TOKEN, _ = call("POST", "/auth/login", {"email": EMAIL, "password": enc(PW)})


def api(method, path, body=None, timeout=120):
    try:
        return call(method, path, body, TOKEN, timeout=timeout)[1]
    except urllib.error.HTTPError as e:
        return {"code": e.code, "message": e.read(300).decode(errors="replace")}


def upload(ds, path):
    b = uuid.uuid4().hex; p = Path(path)
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{p.name}\"\r\n"
            f"Content-Type: {mimetypes.guess_type(p.name)[0] or 'application/octet-stream'}\r\n\r\n").encode() + p.read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(f"{API}/datasets/{ds}/documents", data=body, method="POST",
                                 headers={"Authorization": TOKEN, "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"code": e.code, "message": e.read(300).decode(errors="replace")}


def new_dataset(name, chunk_method=None):
    body = {"name": f"{name}-{int(time.time())}"}
    if chunk_method:
        body["parser_id"] = chunk_method  # the API field is parser_id
    r = api("POST", "/datasets", body)
    if r.get("code") != 0:
        raise RuntimeError(f"create dataset {body}: {r}")
    return r["data"]["id"]


def parse_and_wait(ds, ids, limit=900):
    t0 = time.time()
    api("POST", f"/datasets/{ds}/documents/parse", {"document_ids": ids})
    while time.time() - t0 < limit:
        time.sleep(4)
        docs = (api("GET", f"/datasets/{ds}/documents?page=1&page_size=100").get("data") or {}).get("docs") or []
        docs = [d for d in docs if d["id"] in ids]
        if docs and all(str(d.get("ingestion_status")).upper() in ("COMPLETED", "DONE", "FAILED", "CANCELLED") for d in docs):
            return docs, time.time() - t0
    return docs, time.time() - t0


def ask(ds, question):
    chat = api("POST", "/chats", {"name": f"fm-{uuid.uuid4().hex[:8]}", "dataset_ids": [ds]})["data"]["id"]
    sess = api("POST", f"/chats/{chat}/sessions", {"name": "fm"})["data"]["id"]
    r = api("POST", "/chat/completions", {"chat_id": chat, "session_id": sess, "question": question, "stream": False}, timeout=900)
    return re.sub(r"<think>.*?</think>", "", ((r.get("data") or {}).get("answer") or str(r.get("message"))), flags=re.S).strip()


def formats(samples):
    facts = json.loads((Path(samples) / "facts.json").read_text())
    print("| File | Upload | Parse | Chunks | Parse s | Answer correct | Answer |\n|---|---|---|---|---|---|---|", flush=True)
    for name, (q, exp) in facts.items():
        ds = new_dataset(f"fmt-{Path(name).suffix[1:]}")
        up = upload(ds, Path(samples) / name)
        if up.get("code") != 0:
            print(f"| {name} | REJECTED: {str(up.get('message'))[:80]} | - | - | - | - | - |", flush=True)
            continue
        ids = [d["id"] for d in (up["data"] if isinstance(up["data"], list) else [up["data"]])]
        docs, secs = parse_and_wait(ds, ids)
        st = ",".join(str(d.get("ingestion_status")) for d in docs)
        chunks = sum(int(d.get("chunk_count") or 0) for d in docs)
        if not docs or "COMPLETED" not in st.upper():
            err = json.dumps((docs[0].get("latest_ingestion_event") or {}).get("message", ""))[:120] if docs else "no doc"
            print(f"| {name} | ok | {st} {err} | {chunks} | {secs:.0f} | - | - |", flush=True)
            continue
        ans = ask(ds, q)
        ok = any(e.lower() in ans.lower() for e in exp)
        print(f"| {name} | ok | {st} | {chunks} | {secs:.0f} | {'YES' if ok else 'NO'} | {ans[:110].replace('|', '/').replace(chr(10), ' ')} |", flush=True)


def chunking(path, methods):
    print("| Method | Status | Chunks | Parse s | First chunk |\n|---|---|---|---|---|", flush=True)
    for m in methods:
        try:
            ds = new_dataset(f"chunk-{m}", m)
        except RuntimeError as e:
            print(f"| {m} | dataset rejected: {str(e)[:100]} | - | - | - |", flush=True)
            continue
        up = upload(ds, path)
        if up.get("code") != 0:
            print(f"| {m} | upload rejected: {str(up.get('message'))[:80]} | - | - | - |", flush=True)
            continue
        ids = [d["id"] for d in (up["data"] if isinstance(up["data"], list) else [up["data"]])]
        docs, secs = parse_and_wait(ds, ids)
        chunks = sum(int(d.get("chunk_count") or 0) for d in docs)
        first = ""
        if chunks:
            c = api("GET", f"/datasets/{ds}/documents/{ids[0]}/chunks?page=1&page_size=1")
            items = (c.get("data") or {}).get("chunks") or []
            first = (items[0].get("content") if items else "")[:90].replace("\n", " ").replace("|", "/")
        st = ",".join(str(d.get("ingestion_status")) for d in docs)
        print(f"| {m} | {st} | {chunks} | {secs:.0f} | {first} |", flush=True)


def templates(ds, llm_id):
    import copy
    tl = api("GET", "/agents/templates").get("data") or []
    tl = tl if isinstance(tl, list) else tl.get("templates") or []
    print(f"{len(tl)} templates\n| Template | Type | Result | Seconds | Output / error |\n|---|---|---|---|---|", flush=True)
    for t in tl:
        title = t.get("title") if isinstance(t.get("title"), str) else json.dumps(t.get("title"))
        ctype = t.get("canvas_type") or ""
        dsl = copy.deepcopy(t.get("dsl") or {})
        comps = dsl.get("components") or {}
        for comp in comps.values():
            p = comp.get("obj", {}).get("params", {})
            if "llm_id" in p:
                p["llm_id"] = llm_id
            for tool in p.get("tools", []) or []:
                tp = tool.get("params", {})
                if "dataset_ids" in tp:
                    tp["dataset_ids"] = [ds]
                if "llm_id" in tp:
                    tp["llm_id"] = llm_id
            if "dataset_ids" in p:
                p["dataset_ids"] = [ds]
        names = sorted({c.get("obj", {}).get("component_name") for c in comps.values()})
        if "File" in names or "Parser" in names:
            print(f"| {title} | ingestion pipeline | not run (pipeline, not an agent) | - | components: {', '.join(names)} |", flush=True)
            continue
        r = api("POST", "/agents", {"title": f"tpl-{uuid.uuid4().hex[:6]}", "dsl": dsl, "canvas_category": "agent_canvas", "permission": "me"})
        aid = (r.get("data") or {}).get("id")
        if not aid:
            print(f"| {title} | {ctype} | CREATE FAILED | - | {str(r.get('message'))[:100]} |", flush=True)
            continue
        t0 = time.time()
        q = "What does the Transformer use instead of recurrence? Answer in two sentences."
        parts, err, waiting = [], None, False
        try:
            req = urllib.request.Request(f"{API}/agents/{aid}/run", method="POST", data=json.dumps({"question": q}).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": TOKEN})
            with urllib.request.urlopen(req, timeout=900) as resp:
                for raw in resp:
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                        continue
                    ev = json.loads(line[5:])
                    if ev.get("code") == 500:
                        err = ev.get("message")
                    if ev.get("event") == "waiting_for_user":
                        waiting = True
                    d = ev.get("data")
                    if ev.get("event") == "message" and isinstance(d, dict) and isinstance(d.get("content"), str):
                        parts.append(d["content"])
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        out = "".join(parts).strip()
        res = "ERROR" if err else ("WAITS FOR USER INPUT" if waiting and not out else ("OK" if out else "EMPTY"))
        print(f"| {title} | {ctype} | {res} | {time.time() - t0:.0f} | {(err or out)[:120].replace('|', '/').replace(chr(10), ' ')} |", flush=True)


if __name__ == "__main__":
    {"formats": lambda: formats(REST[0]), "chunking": lambda: chunking(REST[0], REST[1:]),
     "templates": lambda: templates(REST[0], REST[1])}[MODE]()
