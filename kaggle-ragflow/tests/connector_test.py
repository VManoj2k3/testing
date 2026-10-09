"""End-to-end connector check: create an RSS data source, link it to a new dataset, wait for the
syncer to pull items and the ingestor to parse them, then ask a question about one synced item.

Usage: python3 connector_test.py <base> <email> <pw> <feed url>
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE, EMAIL, PW, FEED = sys.argv[1:5]
sys.argv = [sys.argv[0], "connector", BASE, EMAIL, PW]  # feature_matrix reads MODE, BASE, EMAIL, PW
import feature_matrix as fm  # noqa: E402  (login + api/ask helpers)

r = fm.api("POST", "/connectors", {"name": f"rss-{int(time.time())}", "source": "rss",
                                   "config": {"feed_url": FEED, "batch_size": 5}, "refresh_freq": 30})
print("create connector:", r.get("code"), r.get("message"))
cid = (r.get("data") or {}).get("id")
print("test connector:", fm.api("POST", f"/connectors/{cid}/test", {}).get("code"))
ds = fm.new_dataset("rss")
u = fm.api("PUT", f"/datasets/{ds}", {"connectors": [{"id": cid, "auto_parse": "1"}]})
print("link to dataset:", u.get("code"), u.get("message"))
t0, docs = time.time(), []
while time.time() - t0 < 1500:
    time.sleep(15)
    docs = (fm.api("GET", f"/datasets/{ds}/documents?page=1&page_size=50").get("data") or {}).get("docs") or []
    done = [d for d in docs if str(d.get("ingestion_status")).upper() == "COMPLETED"]
    print(f"{time.time() - t0:5.0f}s synced={len(docs)} parsed={len(done)}", flush=True)
    if done and len(done) == len(docs):
        break
    if docs and not done and time.time() - t0 > 300:  # synced but nothing parsing: kick the parse ourselves
        fm.api("POST", f"/datasets/{ds}/documents/parse", {"document_ids": [d["id"] for d in docs]})
logs = fm.api("GET", f"/connectors/{cid}/logs")
print("sync log:", str(logs.get("data"))[:400])
if docs:
    title = docs[0]["name"].rsplit(".", 1)[0]
    q = f"Summarise in one sentence what the post titled '{title}' is about."
    print("Q:", q)
    print("A:", fm.ask(ds, q)[:400])
