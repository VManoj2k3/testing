"""Small, checkable RAG evaluation against a live RAGFlow: ask questions about one parsed
document through a chat assistant and score answers by expected keywords.

Usage: python3 eval_rag.py <ragflow base url> <email> <password> <dataset id> [label]
Answers come from "Attention Is All You Need" (arXiv 1706.03762v7); expected values are
the paper's own numbers. Unanswerable questions should get RAGFlow's "not found" reply.
"""
import base64, json, re, subprocess, sys, time, urllib.request
from pathlib import Path

BASE, EMAIL, PW, DATASET = sys.argv[1:5]
LABEL = sys.argv[5] if len(sys.argv) > 5 else "chat"
API = BASE.rstrip("/") + "/api/v1"
PEM = Path(__file__).with_name("public.pem")

QUESTIONS = [
    # (question, any-of expected substrings (case-insensitive); None = should be "not found")
    ("How many attention heads does the base Transformer model use?", ["8", "eight"]),
    ("What is the model dimension d_model of the base model?", ["512"]),
    ("How many layers are in the encoder stack?", ["6", "six"]),
    ("What BLEU score did the big Transformer get on WMT 2014 English-to-German?", ["28.4"]),
    ("How long was the base model trained and on what hardware?", ["12 hours", "8 P100", "eight P100"]),
    ("What label smoothing value was used during training?", ["0.1"]),
    ("What is the capital city of Australia according to this paper?", None),
    ("What GPU price per hour did the authors pay for training?", None),
]
NOT_FOUND = re.compile(r"not found in the (dataset|knowledge)|no relevant|cannot find|not (mentioned|provided|stated|specified)|does not (mention|provide|specify|state|contain)", re.I)


def enc(pw):
    b64 = base64.b64encode(pw.encode()).decode()
    out = subprocess.run(["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", str(PEM),
                          "-pkeyopt", "rsa_padding_mode:pkcs1"], input=b64.encode(), capture_output=True, check=True)
    return base64.b64encode(out.stdout).decode()


def call(method, path, body=None, token=None, timeout=900):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers.get("Authorization"), json.loads(r.read())


def main():
    token, _ = call("POST", "/auth/login", {"email": EMAIL, "password": enc(PW)})
    _, chat = call("POST", "/chats", {"name": f"eval-{LABEL}-{int(time.time())}", "dataset_ids": [DATASET]}, token)
    chat_id = chat["data"]["id"]
    _, sess = call("POST", f"/chats/{chat_id}/sessions", {"name": "eval"}, token)
    session_id = sess["data"]["id"]
    score, rows = 0, []
    for q, expected in QUESTIONS:
        t0 = time.time()
        try:
            _, r = call("POST", "/chat/completions", {"chat_id": chat_id, "session_id": session_id,
                                                      "question": q, "stream": False}, token)
            data = r.get("data") or {}
            answer = (data.get("answer") or "").strip()
            refs = (data.get("reference") or {}).get("chunks") or []
        except Exception as e:
            answer, refs = f"<error {type(e).__name__}: {e}>", []
        dt = time.time() - t0
        clean = re.sub(r"<think>.*?</think>", "", answer, flags=re.S)
        if expected is None:
            ok = bool(NOT_FOUND.search(clean))
        else:
            ok = any(e.lower() in clean.lower() for e in expected)
        score += ok
        rows.append((ok, round(dt), len(refs), q, clean.replace("\n", " ")[:220]))
        print(f"{'PASS' if ok else 'FAIL'} {dt:5.0f}s refs={len(refs):2d} | {q}\n      -> {clean[:220]!r}", flush=True)
        # Each question in its own session so earlier answers can't leak into later ones.
        _, sess = call("POST", f"/chats/{chat_id}/sessions", {"name": "eval"}, token)
        session_id = sess["data"]["id"]
    print(f"\n{LABEL}: {score}/{len(QUESTIONS)} correct; "
          f"median latency {sorted(r[1] for r in rows)[len(rows) // 2]}s", flush=True)


if __name__ == "__main__":
    main()
