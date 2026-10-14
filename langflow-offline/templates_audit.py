"""Audit: do Langflow's 27 bundled templates work on our setup (local Qwen via the OpenAI provider)?

For each template: import it as a flow, point every language-model field at the local model, run it once
with a fitting sample input (fresh session, streamed) and record the result as JSONL.
Nothing else is changed, so this is the "as shipped" baseline.

Usage: LF_URL=... LF_PASSWORD=... LF_STATE=... LF_TPL_DIR=... python templates_audit.py <out.jsonl> [name ...]
"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import lf_drive as d

SAMPLES = {
    "Basic Prompting": "Write a two-line welcome message for new employees.",
    "Blog Writer": "Write a short blog post about https://www.python.org/about/",
    "Content Aggregator": "Latest news about open-source AI models",
    "Custom Component Generator": "Create a component that counts the words in a text input.",
    "Deep Research Agent": "What are the main differences between SQLite and PostgreSQL?",
    "Document Q&A": "What is this document about?",
    "Financial Report Parser": "Summarise the key figures.",
    "Hybrid Search RAG": "What does the document say about pricing?",
    "Image Sentiment Analysis": "Describe the sentiment of this image.",
    "Instagram Copywriter": "A new coffee shop opening in Bangalore",
    "Knowledge Retrieval": "What is our refund policy?",
    "Market Research": "Electric scooters in India",
    "Meeting Summary": "Summarise the meeting.",
    "Memory Chatbot": "Hi, my name is Manoj. Please remember it.",
    "Multi Agent Flow": "Plan a one-day team offsite agenda.",
    "Portfolio Website Code Generator": "Create a portfolio site.",
    "Price Deal Finder": "Best price for a Logitech MX Master 3S mouse",
    "Research Translation Loop": "large language model agents",
    "SEO Keyword Generator": "Keywords for a self-hosted AI agent platform",
    "SaaS Pricing": "What should we charge for a team plan?",
    "Sequential Tasks Agents": "Write a short market overview of AI code review tools.",
    "Simple Agent": "What is 17.5% of 2340?",
    "Social Media Agent": "Write a LinkedIn post about our new AI agent platform.",
    "Text Sentiment Analysis": "Analyse the sentiment.",
    "Travel Planning Agents": "Plan a 2-day trip to Mysore from Bangalore.",
    "Twitter Thread Generator": "A thread about why teams should self-host AI.",
    "Vector Store RAG": "What is in the knowledge base?",
}


def adapt(flow):
    """Only change: every language-model field -> local model (embedding fields untouched)."""
    for n in flow["data"]["nodes"]:
        t = n["data"].get("node", {}).get("template", {})
        if isinstance(t.get("model"), dict) and t["model"].get("_input_type") == "ModelInput":
            t["model"]["value"] = d.MODEL
        if isinstance(t.get("stream"), dict):
            t["stream"]["value"] = True


def audit_one(tok, name, out):
    flow = json.loads((d.tpl_dir() / f"{name}.json").read_text(encoding="utf-8"))
    adapt(flow)
    t0 = time.time()
    try:
        fid = d.call("POST", "/flows/", {"name": f"[audit] {name}", "description": flow.get("description", ""),
                                          "data": flow["data"]}, token=tok)["id"]
        text = d.run_stream(tok, fid, SAMPLES.get(name, "Hello"))
        err = "" if text else "empty answer (tunnel idle limit or no chat output)"
    except (Exception, SystemExit) as e:
        text, err = "", f"{type(e).__name__}: {e}"[:600]
    row = {"template": name, "secs": round(time.time() - t0), "error": err, "answer": text}
    with open(out, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"{name:<34} {row['secs']:4}s {'OK ' if text else 'ERR'} {(err or text)[:110]!r}", flush=True)


if __name__ == "__main__":
    out, names = sys.argv[1], sys.argv[2:] or sorted(SAMPLES)
    tok = d.login()
    d.api_key(tok)
    with ThreadPoolExecutor(2) as ex:  # the model has 2 slots
        list(ex.map(lambda n: audit_one(tok, n, out), names))
