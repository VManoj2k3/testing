"""Agent evaluation against a live RAGFlow: build agents from the built-in "Your starter
dataset chatbot" template, point them at one parsed dataset, run questions through the
agent run API (SSE) and score answers by expected keywords.

Usage: python3 eval_agent.py <ragflow base url> <email> <password> <dataset id> [llm_id]
Answers come from "Attention Is All You Need" (arXiv 1706.03762v7).

Agent A = the template as shipped (single retrieval, Docs QA prompt), same 8 questions as
eval_rag.py. Agent B = same flow with a prompt that asks for several retrievals, on
questions that need two facts combined.
"""
import copy, json, re, sys, time, urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from eval_rag import QUESTIONS, NOT_FOUND, enc  # noqa: E402  (same questions + password encryption)

BASE, EMAIL, PW, DATASET = sys.argv[1:5]
LLM_ID = sys.argv[5] if len(sys.argv) > 5 else "qwen3.8-27b@kaggle-qwen@OpenAI-API-Compatible"
API = BASE.rstrip("/") + "/api/v1"
TEMPLATE_TITLE = "Your starter dataset chatbot"

# Each expected entry is a list of groups; every group must match (any-of inside a group).
MULTI_STEP = [
    ("How much higher is the big Transformer's BLEU on WMT 2014 English-to-German than the base model's?",
     [["1.1"]]),
    ("How many attention heads does the big model use, and how many does the base model use?",
     [["16"], ["8", "eight"]]),
    ("For how many steps were the base and the big models trained?",
     [["100,000", "100000", "100k", "100 000"], ["300,000", "300000", "300k", "300 000"]]),
    ("What is d_ff in the base model, and how many times larger is it than d_model?",
     [["2048"], ["4", "four"]]),
]
MULTI_STEP_PROMPT = (
    "\n\n# Multi-step questions\nIf the question needs more than one fact, call the retrieval tool "
    "separately for each fact before answering. Show the facts you found, then compute or compare. "
    "Give the final answer in one sentence.")


def call(method, path, body=None, token=None, timeout=120):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers.get("Authorization"), json.loads(r.read())


def run_agent(token, agent_id, question, timeout=900):
    """POST /agents/:id/run and collect the SSE stream. Returns (answer, events, error)."""
    req = urllib.request.Request(f"{API}/agents/{agent_id}/run", method="POST",
                                 data=json.dumps({"question": question}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": token})
    parts, events, error = [], [], None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                ev = json.loads(payload)
            except ValueError:
                continue
            events.append(ev)
            if ev.get("code") == 500:
                error = ev.get("message")
            data = ev.get("data")
            if ev.get("event") == "message" and isinstance(data, dict) and isinstance(data.get("content"), str):
                parts.append(data["content"])
    return "".join(parts).strip(), events, error


def make_agent(token, template, title, extra_prompt=""):
    dsl = copy.deepcopy(template["dsl"])
    for comp in dsl["components"].values():
        obj = comp["obj"]
        if obj["component_name"] != "Agent":
            continue
        obj["params"]["llm_id"] = LLM_ID
        obj["params"]["sys_prompt"] += extra_prompt
        for tool in obj["params"].get("tools", []):
            if tool.get("component_name") == "Retrieval":
                tool["params"]["dataset_ids"] = [DATASET]
    _, r = call("POST", "/agents", {"title": f"{title}-{int(time.time())}", "dsl": dsl,
                                    "canvas_category": "agent_canvas", "permission": "me"}, token)
    if r.get("code") not in (0, None):
        raise RuntimeError(f"create agent failed: {r}")
    data = r.get("data") or {}
    return data.get("id") or data.get("canvas_id")


def evaluate(token, agent_id, label, questions):
    score, lat = 0, []
    for q, expected in questions:
        t0 = time.time()
        try:
            answer, events, error = run_agent(token, agent_id, q)
        except Exception as e:
            answer, events, error = "", [], f"{type(e).__name__}: {e}"
        dt = time.time() - t0
        lat.append(dt)
        clean = re.sub(r"<think>.*?</think>", "", answer, flags=re.S)
        if expected is None:
            ok = bool(NOT_FOUND.search(clean))
        else:
            groups = expected if isinstance(expected[0], list) else [expected]
            ok = all(any(e.lower() in clean.lower() for e in g) for g in groups)
        score += ok
        kinds = sorted({e.get("event", "?") for e in events})
        print(f"{'PASS' if ok else 'FAIL'} {dt:5.0f}s events={len(events):3d} {kinds} | {q}", flush=True)
        print(f"      -> {(error and '<error ' + error + '> ') or ''}{clean.replace(chr(10), ' ')[:300]!r}", flush=True)
    print(f"\n{label}: {score}/{len(questions)} correct; median latency {sorted(lat)[len(lat) // 2]:.0f}s\n", flush=True)
    return score


def main():
    token, _ = call("POST", "/auth/login", {"email": EMAIL, "password": enc(PW)})
    _, t = call("GET", "/agents/templates", token=token)
    items = t.get("data") or []
    items = items if isinstance(items, list) else items.get("templates") or items.get("items") or []
    template = next(x for x in items if TEMPLATE_TITLE.lower() in json.dumps(x.get("title", "")).lower())
    a = make_agent(token, template, "eval-agentA")
    print(f"Agent A (template as shipped): {a}", flush=True)
    evaluate(token, a, "Agent A, single-fact + not-found", QUESTIONS)
    b = make_agent(token, template, "eval-agentB", MULTI_STEP_PROMPT)
    print(f"Agent B (multi-step prompt): {b}", flush=True)
    evaluate(token, b, "Agent B, multi-step", MULTI_STEP)


if __name__ == "__main__":
    main()
