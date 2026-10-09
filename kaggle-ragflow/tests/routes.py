"""Extract (method, path) for every route registered in RAGFlow's Go router.

Tracks `x := y.Group("/p")` prefixes and `x.METHOD("/p", ...)` calls across router/*.go,
including the Register*Routes(group, handler) helpers. Static analysis, so it can miss routes
built dynamically; good enough for an unauthenticated-access sweep.
Usage: python3 routes.py <ragflow src dir>  -> prints "METHOD path auth-group" lines.
"""
import re, sys
from pathlib import Path

src = Path(sys.argv[1]) / "internal" / "router"
text = {p.name: p.read_text() for p in src.glob("*.go") if not p.name.endswith("_test.go")}
group_re = re.compile(r'(\w+)\s*:?=\s*(\w+)\.Group\("([^"]*)"')
route_re = re.compile(r'\b(\w+)\.(GET|POST|PUT|PATCH|DELETE)\("([^"]*)"')
call_re = re.compile(r'Register(\w+)Routes\((\w+)(?:\.Group\("([^"]*)"\))?')
func_re = re.compile(r'func Register(\w+)Routes\((\w+) ')

def walk(body, prefixes, out):
    for line in body.splitlines():
        if m := group_re.search(line):
            var, parent, p = m.groups()
            prefixes[var] = prefixes.get(parent, "") + p
        for var, meth, p in route_re.findall(line):
            if var in prefixes:
                out.append((meth, prefixes[var] + p, var))
        if m := call_re.search(line):
            name, var, extra = m.groups()
            for fn in funcs.get(name, []):
                walk(fn[1], {fn[0]: prefixes.get(var, "") + (extra or "")}, out)

funcs = {}
for t in text.values():
    for m in func_re.finditer(t):
        start = m.end(); depth = 0; i = t.index("{", start)
        for j in range(i, len(t)):
            depth += {"{": 1, "}": -1}.get(t[j], 0)
            if depth == 0:
                funcs.setdefault(m.group(1), []).append((m.group(2), t[i:j]))
                break

out = []
body = text["router.go"]
walk(body, {"r.engine": "", "engine": ""}, out)
for meth, path, var in sorted(set(out), key=lambda x: (x[1], x[0])):
    print(meth, re.sub(r"/+", "/", path), var)
