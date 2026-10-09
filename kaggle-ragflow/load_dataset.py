"""Create a dataset, upload files, parse them and wait; prints parse time and chunk counts.

Usage: python3 load_dataset.py <ragflow base url> <email> <password> <dataset name> <file>...
Prints `DATASET_ID=<id>` on success. Uses the tenant's default embedding model.
"""
import json, mimetypes, sys, time, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
BASE, EMAIL, PW, NAME, *FILES = sys.argv[1:]
sys.argv = sys.argv[:5]  # eval_rag reads argv[1:5] at import
from eval_rag import call, enc  # noqa: E402

API = BASE.rstrip("/") + "/api/v1"


def upload(token, ds, path):
    boundary = uuid.uuid4().hex
    p = Path(path)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{p.name}\"\r\n"
            f"Content-Type: {mimetypes.guess_type(p.name)[0] or 'application/octet-stream'}\r\n\r\n").encode() \
        + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{API}/datasets/{ds}/documents", data=body, method="POST",
                                 headers={"Authorization": token, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    if out.get("code") != 0:
        raise RuntimeError(f"upload {p.name}: {out}")
    data = out["data"]
    return [d["id"] for d in (data if isinstance(data, list) else [data])]


def main():
    token, _ = call("POST", "/auth/login", {"email": EMAIL, "password": enc(PW)})
    _, r = call("POST", "/datasets", {"name": NAME}, token)
    if r.get("code") != 0:
        raise RuntimeError(f"create dataset: {r}")
    ds = r["data"]["id"]
    ids = [i for f in FILES for i in upload(token, ds, f)]
    t0 = time.time()
    _, r = call("POST", f"/datasets/{ds}/documents/parse", {"document_ids": ids}, token)
    print("parse started:", r.get("code"), r.get("message"), flush=True)
    while True:
        time.sleep(5)
        _, r = call("GET", f"/datasets/{ds}/documents?page=1&page_size=100", token=token)
        docs = (r.get("data") or {}).get("docs") or (r.get("data") or {}).get("documents") or []
        states = [(d.get("name"), d.get("ingestion_status"), round(float(d.get("progress") or 0), 2), d.get("chunk_count")) for d in docs]
        print(f"{time.time() - t0:5.0f}s", states, flush=True)
        # ingestion_status is the source of truth (e.g. RUNNING, DONE, FAILED); progress can sit at 0.8 after a failure.
        if docs and all(str(d.get("ingestion_status")).upper() in ("DONE", "SUCCESS", "FAILED", "CANCELLED", "CANCELED") for d in docs):
            break
        if time.time() - t0 > 1800:
            raise RuntimeError("parse did not finish in 30 min")
    for d in docs:
        if str(d.get("ingestion_status")).upper() not in ("DONE", "SUCCESS"):
            print("FAILED:", d.get("name"), json.dumps(d.get("latest_ingestion_event"))[:800], flush=True)
    print(f"parsed in {time.time() - t0:.0f}s; chunks:", sum(int(d.get("chunk_count") or 0) for d in docs))
    print(f"DATASET_ID={ds}")


if __name__ == "__main__":
    main()
