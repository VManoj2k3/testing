"""CPU vs GPU DeepDoc ingestion on the kaggle-ragflow-gpu notebook, driven from outside.

For each device (cuda first, then cpu) it switches the ingestor through the notebook's control endpoint,
parses the same PDF into a fresh dataset, and records wall time, chunk count and GPU memory sampled during
the parse. Chunk texts must be identical across devices. Then one chat question is timed with the
ingestor idle and again while a GPU parse is running (contention).

Usage: python3 gpu_bench.py <app url> <email> <pw> <control url> <secret> <pdf> [question]
"""
import json, sys, threading, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
APP, EMAIL, PW, CTRL, SECRET, PDF, *Q = sys.argv[1:]
QUESTION = Q[0] if Q else "What dropout rate did the base Transformer model use?"
sys.argv = [sys.argv[0], "x", APP, EMAIL, PW]
import feature_matrix as fm  # noqa: E402


def control(method, path):
    req = urllib.request.Request(CTRL + path, method=method, headers={"X-Kill-Secret": SECRET})
    return urllib.request.urlopen(req, timeout=180).read().decode()


def chunks(ds, doc):
    out, page = [], 1
    while True:
        r = (fm.api("GET", f"/datasets/{ds}/documents/{doc}/chunks?page={page}&page_size=100").get("data") or {})
        got = r.get("chunks") or []
        out += [c.get("content") or c.get("content_with_weight") or "" for c in got]
        if len(got) < 100:
            return sorted(out)
        page += 1


def parse_on(device):
    print(f"\n## ingestor -> {device}\n" + control("POST", f"/ingestor/{device}").strip())
    ds = fm.new_dataset(f"gpubench-{device}", "naive")
    d = fm.upload(ds, PDF)["data"]
    doc = (d[0] if isinstance(d, list) else d)["id"]
    mem, done = [], threading.Event()

    def sample():
        while not done.is_set():
            try:
                mem.append(control("GET", "/gpu").strip())
            except Exception as e:
                mem.append(f"err {e}")
            done.wait(15)
    threading.Thread(target=sample, daemon=True).start()
    docs, secs = fm.parse_and_wait(ds, [doc], limit=2400)
    done.set()
    st = [(x.get("ingestion_status"), x.get("chunk_count")) for x in docs]
    print(f"{device}: {secs:.0f}s {st}")
    print(f"{device}: GPU memory samples (first, peak-ish last): {mem[:1]} ... {mem[-2:]}")
    return ds, doc, secs, st


def timed_chat(ds, label):
    t = time.time()
    a = fm.ask(ds, QUESTION)
    secs = time.time() - t
    if a.startswith("**ERROR**"):  # RAGFlow returns model errors as answer text
        print(f"chat [{label}] FAILED after {secs:.0f}s: {a[:200]!r}")
        return None
    print(f"chat [{label}] {secs:.0f}s: {a[:160]!r}")
    return secs


if __name__ == "__main__":
    print("GPU at start:", control("GET", "/gpu").strip())
    res = {dev: parse_on(dev) for dev in ("cuda", "cpu")}
    bad = [d for d, r in res.items() if not r[3] or r[3][0][0] != "COMPLETED" or not r[3][0][1]]
    if bad:  # a failed or empty parse makes every comparison below meaningless
        sys.exit(f"parse FAILED on {bad}: {[res[d][3] for d in bad]} - no comparison reported")
    a, b = chunks(*res["cuda"][:2]), chunks(*res["cpu"][:2])
    print(f"\nchunks cuda={len(a)} cpu={len(b)} text {'IDENTICAL' if a == b else 'DIFFERENT'}")
    if a != b:
        sa, sb = set(a), set(b)
        print(f"  only cuda: {len(sa - sb)}, only cpu: {len(sb - sa)}")
        for x in sorted(sa - sb)[:2]:
            print("  cuda>", x[:160].replace("\n", " "))
        for x in sorted(sb - sa)[:2]:
            print("  cpu> ", x[:160].replace("\n", " "))
    print(f"speed-up cuda vs cpu: {res['cpu'][2] / max(res['cuda'][2], 1):.2f}x")

    # Contention: chat while idle vs while a GPU parse runs.
    print("\n## contention\n" + control("POST", "/ingestor/cuda").strip().splitlines()[-1])
    idle = timed_chat(res["cuda"][0], "ingestor idle")
    bg_ds = fm.new_dataset("gpubench-bg", "naive")
    d = fm.upload(bg_ds, PDF)["data"]
    bg_doc = (d[0] if isinstance(d, list) else d)["id"]
    fm.api("POST", f"/datasets/{bg_ds}/documents/parse", {"document_ids": [bg_doc]})
    time.sleep(20)
    busy = timed_chat(res["cuda"][0], "during GPU parse")
    if idle and busy:
        print(f"chat slowdown during GPU parse: {busy / max(idle, 1):.2f}x")
    print(json.dumps({"cuda_s": round(res["cuda"][2]), "cpu_s": round(res["cpu"][2]), "chunks_identical": a == b,
                      "chat_idle_s": idle and round(idle), "chat_busy_s": busy and round(busy)}))
