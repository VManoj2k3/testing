"""Build and test customized agents through RAGFlow's API, the way a non-coder's tooling would.

1. questionnaire  - plain answers -> template + datasets + LLM-written instructions -> agent -> auto-test
2. triage         - Categorize branches: paper expert / Go expert / out-of-scope (template rewired)
3. confirm        - draft -> pause for the user's yes/no (UserFillUp) -> only then call create_ticket (MCP)

Usage:
  python3 custom_agents.py <base> <email> <pw> <llm_id> <qwen /v1 url> <qwen key> <paper ds> <go ds> \
      [<mcp server id> <ntfy topic>]          # last two enable the confirm agent test
"""
import copy, json, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
BASE, EMAIL, PW, LLM_ID, QWEN_URL, QWEN_KEY, PAPER_DS, GO_DS, *OPT = sys.argv[1:]
sys.argv = [sys.argv[0], "x", BASE, EMAIL, PW]
import feature_matrix as fm  # noqa: E402

TEMPLATES = None


def template(title_part):
    global TEMPLATES
    if TEMPLATES is None:
        t = fm.api("GET", "/agents/templates")["data"]
        TEMPLATES = t if isinstance(t, list) else t.get("templates", [])
    return copy.deepcopy(next(t for t in TEMPLATES if title_part.lower() in json.dumps(t.get("title")).lower())["dsl"])


def create(dsl, title):
    r = fm.api("POST", "/agents", {"title": f"{title}-{int(time.time())}", "dsl": dsl, "canvas_category": "agent_canvas", "permission": "me"})
    return r["data"]["id"]


def run(aid, question, session_id=None):
    """Returns (answer text, waiting_for_user?, session_id)."""
    url = f"{fm.API}/agents/{aid}/run" + (f"?session_id={session_id}" if session_id else "")
    req = urllib.request.Request(url, method="POST", data=json.dumps({"question": question}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": fm.TOKEN})
    parts, waiting, sid = [], False, session_id
    with urllib.request.urlopen(req, timeout=900) as resp:
        for raw in resp:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            ev = json.loads(line[5:])
            sid = ev.get("session_id") or sid
            if ev.get("code") == 500:
                parts.append(f"<error {ev.get('message')}>")
            if ev.get("event") == "waiting_for_user":
                waiting = True
            d = ev.get("data")
            if ev.get("event") == "message" and isinstance(d, dict) and isinstance(d.get("content"), str):
                parts.append(d["content"])
    return re.sub(r"<think>.*?</think>", "", "".join(parts), flags=re.S).strip(), waiting, sid


def qwen(prompt):
    req = urllib.request.Request(QWEN_URL.rstrip("/") + "/chat/completions", method="POST",
                                 data=json.dumps({"model": "q", "messages": [{"role": "user", "content": prompt}], "max_tokens": 900,
                                                  "chat_template_kwargs": {"enable_thinking": False}}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {QWEN_KEY}"})
    return json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"].strip()


def score(answer, expect):
    if expect is None:
        return bool(re.search(r"not (found|available|in the|mentioned|covered|provided|stated)|cannot find|can't find|no information|outside|out of scope|doesn't (contain|cover)|does not (contain|cover)|unable to", answer, re.I))
    return all(any(e.lower() in answer.lower() for e in g) for g in expect)


# 1. Questionnaire -> agent ----------------------------------------------------------------------
def questionnaire():
    answers = {
        "purpose": "Help our ML reading group answer questions about the Transformer paper we are studying.",
        "users": "Engineers new to deep learning.",
        "data": [PAPER_DS],
        "must_not": "Guess numbers, or answer questions unrelated to the paper.",
        "format": "Short answers (max 3 sentences) with the exact number from the paper and a citation.",
        "examples": [
            {"q": "What dropout rate did the base model use?", "expect": [["0.1"]]},
            {"q": "How many layers does the decoder have?", "expect": [["6", "six"]]},
            {"q": "Which optimizer was used for training?", "expect": [["Adam"]]},
            {"q": "What is the recommended pizza topping for training runs?", "expect": None},
        ],
    }
    t0 = time.time()
    sys_prompt = qwen(
        "Write the system prompt for a retrieval-augmented assistant from this questionnaire. Use sections: Role, "
        "Rules, Answer format, When you don't know. The assistant has a retrieval tool over the user's documents and "
        "must answer only from retrieved content and say clearly when the answer is not in the documents.\n\n"
        + json.dumps({k: v for k, v in answers.items() if k != "examples"}, indent=1)
        + "\n\nReturn only the system prompt text.")
    gen_s = time.time() - t0
    dsl = template("starter dataset chatbot")
    for comp in dsl["components"].values():
        o = comp["obj"]
        if o["component_name"] == "Agent":
            o["params"].update({"llm_id": LLM_ID, "sys_prompt": sys_prompt})
            for t in o["params"].get("tools", []):
                if t.get("component_name") == "Retrieval":
                    t["params"]["dataset_ids"] = answers["data"]
    aid = create(dsl, "questionnaire-paper-helper")
    print(f"\n## 1. Questionnaire-built agent ({aid}); instructions generated in {gen_s:.0f}s, {len(sys_prompt)} chars")
    print("   generated prompt (start):", sys_prompt[:240].replace("\n", " / "))
    ok = 0
    for ex in answers["examples"]:
        t1 = time.time(); a, _, _ = run(aid, ex["q"]); good = score(a, ex["expect"]); ok += good
        print(f"   {'PASS' if good else 'FAIL'} {time.time() - t1:4.0f}s | {ex['q']}\n        -> {a[:200]!r}")
    print(f"   auto-test: {ok}/{len(answers['examples'])}")


# 2. Triage with Categorize ------------------------------------------------------------------------
def triage():
    dsl = template("smart customer service")
    comps = dsl["components"]
    cat = next(k for k, v in comps.items() if v["obj"]["component_name"] == "Categorize")
    old = comps[cat]["obj"]["params"]["category_description"]
    by_target = {v["to"][0]: k for k, v in old.items()}
    retr = [k for k, v in comps.items() if v["obj"]["component_name"] == "Retrieval"]
    direct_agent = next(t for t in by_target if t.startswith("Agent:"))
    paper_r, go_r = retr[0], retr[1]
    comps[cat]["obj"]["params"]["llm_id"] = LLM_ID
    comps[cat]["obj"]["params"]["category_description"] = {
        "Transformer paper": {"description": "Questions about the Transformer / 'Attention Is All You Need' paper: architecture, training, results.",
                              "examples": ["How many heads does the model use?\nWhat BLEU score did it get?"], "to": [paper_r]},
        "Go programming": {"description": "Questions about the Go programming language, its runtime, tooling or Go blog posts.",
                           "examples": ["What is a goroutine leak?\nHow does Go allocate on the stack?"], "to": [go_r]},
        "Out of scope": {"description": "Anything else (personal, travel, cooking, other technologies).",
                         "examples": ["Book me a flight\nWhat's a good pasta recipe?"], "to": [direct_agent]},
    }
    comps[paper_r]["obj"]["params"]["dataset_ids"] = [PAPER_DS]
    comps[go_r]["obj"]["params"]["dataset_ids"] = [GO_DS]
    for k, v in comps.items():
        o = v["obj"]
        if o["component_name"] == "Agent":
            o["params"]["llm_id"] = LLM_ID
            o["params"]["tools"] = []
            if k == direct_agent:
                o["params"]["sys_prompt"] = "Politely tell the user this assistant only covers the Transformer paper and the Go programming language, in one sentence."
            else:
                o["params"]["sys_prompt"] = "Answer the user's question in at most 3 sentences using only the retrieved content provided in the user message. If it is not there, say it is not in the documents."
    aid = create(dsl, "triage-paper-go")
    print(f"\n## 2. Triage agent with branching ({aid})")
    tests = [("What label smoothing value was used in training the Transformer?", [["0.1"]], "paper"),
             ("According to the Go blog, what problem do goroutine leak profiles help with?", [["leak"]], "go"),
             ("Can you recommend a good pasta recipe?", [["only", "Transformer", "Go"]], "out of scope")]
    ok = 0
    for q, exp, route in tests:
        t1 = time.time(); a, _, _ = run(aid, q); good = score(a, exp); ok += good
        print(f"   {'PASS' if good else 'FAIL'} {time.time() - t1:4.0f}s [{route}] {q}\n        -> {a[:200]!r}")
    print(f"   triage: {ok}/{len(tests)}")


# 3. Confirm before action -----------------------------------------------------------------------
def confirm(mcp_id, topic):
    def calls_since(t0):
        raw = urllib.request.urlopen(f"https://ntfy.sh/{topic}/json?poll=1&since=all", timeout=30).read().decode()
        out = []
        for line in raw.splitlines():
            ev = json.loads(line)
            if ev.get("event") == "message" and ev["message"].startswith("CALL "):
                c = json.loads(ev["message"][5:])
                if c["t"] >= t0 - 3 and c["tool"] == "create_ticket":
                    out.append(c)
        return out

    tools = (fm.api("GET", f"/mcp/servers/{mcp_id}")["data"].get("variables") or {}).get("tools") or {}
    dsl = template("interactive agent")
    comps = dsl["components"]
    agents = [k for k, v in comps.items() if v["obj"]["component_name"] == "Agent"]
    fill = next(k for k, v in comps.items() if v["obj"]["component_name"] == "UserFillUp")
    first = next(a for a in agents if comps[a]["downstream"] == [fill])
    second = next(a for a in agents if a != first)
    comps[first]["obj"]["params"].update({"llm_id": LLM_ID, "tools": [], "max_tokens": 300,
        "sys_prompt": "Draft a ticket for the user's request: one line 'Title: ...' and one line 'Body: ...'. Do not do anything else."})
    comps[fill]["obj"]["params"]["tips"] = f"Here is the draft ticket:\n{{{first}@content}}\nReply yes to create it, or no to cancel."
    comps[second]["obj"]["params"].update({"llm_id": LLM_ID, "tools": [], "max_rounds": 3, "max_tokens": 300,
        "mcp": [{"mcp_id": mcp_id, "tools": tools}],
        "sys_prompt": "You receive a draft ticket and the user's confirmation. If the confirmation is clearly yes, call create_ticket with the draft's title and body and report the ticket id. Otherwise do NOT call any tool and reply 'Cancelled, no ticket created.'"})
    aid = create(dsl, "confirm-before-ticket")
    print(f"\n## 3. Confirm-before-action agent ({aid})")
    for reply in ("no", "yes"):
        t0 = time.time()
        a1, waiting, sid = run(aid, "Our CI runner ci-07 has been offline since this morning; please open a ticket.")
        before = calls_since(t0)
        print(f"   step 1: paused for user={waiting}; tickets created before confirm={len(before)}; draft -> {a1[:150]!r}")
        a2, _, _ = run(aid, reply, session_id=sid)
        time.sleep(5)
        after = calls_since(t0)
        want = 1 if reply == "yes" else 0
        good = waiting and not before and len(after) == want
        print(f"   {'PASS' if good else 'FAIL'} reply={reply!r}: tickets created={len(after)} (expected {want}) -> {a2[:160]!r}")


if __name__ == "__main__":
    questionnaire()
    triage()
    if len(OPT) >= 2:
        confirm(OPT[0], OPT[1])
