"""Upload format_cases.py output to RAGFlow, parse, and check by search (no LLM).
A case passes when its expected text is in one of the top-3 chunks retrieved from that file only
(document_ids filter, re-checked on each chunk's document_id), so cases sharing a code can't pass on each other's chunks.

Usage: python3 format_run.py <base> <email> <pw> <cases dir> <group> <chunk method>
       group: sweep | csv | tsv | xlsx; chunk method: naive | table | ...
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE, EMAIL, PW, DIR, GROUP, METHOD = sys.argv[1:7]
sys.argv = [sys.argv[0], "x", BASE, EMAIL, PW]
import feature_matrix as fm  # noqa: E402

cases = {k: v for k, v in json.loads((Path(DIR) / "cases.json").read_text()).items() if v["group"] == GROUP}
ds = fm.new_dataset(f"fmt-{GROUP}-{METHOD}", METHOD)
ids, rows = {}, {}
for name, c in cases.items():
    r = fm.upload(ds, Path(DIR) / name)
    d = r.get("data")
    if r.get("code") == 0 and d:
        c["doc_id"] = (d[0] if isinstance(d, list) else d)["id"]
        ids[c["doc_id"]] = name
        rows[name] = ["accepted"]
    else:
        rows[name] = ["REJECTED: " + str(r.get("message"))[:60]]
docs, secs = fm.parse_and_wait(ds, list(ids)) if ids else ([], 0)
for d in docs:
    rows[ids[d["id"]]] += [str(d.get("ingestion_status")), d.get("chunk_count", d.get("chunk_num"))]
for name, c in cases.items():
    if rows[name][0] != "accepted":
        continue
    r = fm.api("POST", "/retrieval", {"question": c["code"], "dataset_ids": [ds], "document_ids": [c["doc_id"]], "top_k": 3, "page_size": 3})
    chunks = [ch for ch in ((r.get("data") or {}).get("chunks") or []) if ch.get("document_id", c["doc_id"]) == c["doc_id"]][:3]
    texts = [ch.get("content_with_weight") or ch.get("content") or "" for ch in chunks]
    hit = next((i + 1 for i, t in enumerate(texts) if c["expect"].lower() in t.lower()), None)
    shown = texts[hit - 1] if hit else (texts[0] if texts else "<no chunks>")
    at = max(0, shown.lower().find(c["expect"].lower()) - 70) if hit else 0
    rows[name] += [f"PASS (rank {hit})" if hit else "FAIL", shown[at:at + 170].replace("\n", " | ")]
print(f"dataset {ds} method={METHOD} group={GROUP} parse wall {secs:.0f}s")
for name, r in rows.items():
    print(f"  {name:22} " + " ; ".join(str(x) for x in r))
