"""Call every RAGFlow route without credentials and report which ones do NOT reject.

Usage: python3 unauth_sweep.py <api base, e.g. http://127.0.0.1:9380> <routes.txt from routes.py>
A route counts as protected if it returns HTTP 401/403 or a JSON body with code 401/403/109
(RAGFlow's auth codes). Everything else is printed for review: public by design, or a gap.
"""
import json, re, sys, urllib.error, urllib.request

base, routes_file = sys.argv[1].rstrip("/"), sys.argv[2]
DUMMY = "0" * 32
rows = []
for line in open(routes_file):
    meth, path, group = line.split()
    url = base + re.sub(r":\w+|\*\w+", DUMMY, path)
    req = urllib.request.Request(url, method=meth, data=b"{}" if meth != "GET" else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, body = r.status, r.read(400)
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read(400)
    except Exception as e:
        status, body = 0, str(e).encode()
    try:
        code = json.loads(body).get("code")
    except Exception:
        code = None
    protected = status in (401, 403) or code in (401, 403, 109, 102)  # 102 = "Authorization is not valid" (API-key routes)
    rows.append((protected, meth, path, group, status, code, body[:140].decode(errors="replace").replace("\n", " ")))
prot = sum(r[0] for r in rows)
print(f"{prot}/{len(rows)} routes reject unauthenticated calls\n\nNOT rejected:")
for p, meth, path, group, status, code, body in rows:
    if not p:
        print(f"{meth:6} {path:70} [{group}] http={status} code={code} {body}")
