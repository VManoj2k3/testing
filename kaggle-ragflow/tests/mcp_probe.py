"""Minimal MCP streamable-HTTP client: initialize, tools/list, optional tools/call.
Usage: python3 mcp_probe.py <url> [api key] [tool name] [json args]"""
import json, sys, urllib.error, urllib.request

url = sys.argv[1]; key = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
sid = None

def rpc(method, params=None, rid=1):
    global sid
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if key: h["Authorization"] = f"Bearer {key}"
    if sid: h["Mcp-Session-Id"] = sid
    body = {"jsonrpc": "2.0", "method": method, **({"id": rid} if rid else {}), **({"params": params} if params is not None else {})}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            sid = r.headers.get("Mcp-Session-Id") or sid
            raw = r.read().decode()
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read(300).decode(errors="replace")}
    for line in raw.splitlines():  # SSE framing or plain JSON
        if line.startswith("data:"):
            raw = line[5:]
    return json.loads(raw) if raw.strip() else {}

init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}})
print("initialize:", json.dumps(init)[:300])
if "result" in init:
    rpc("notifications/initialized", rid=None)
    tools = rpc("tools/list", {}, 2)
    for t in tools.get("result", {}).get("tools", []):
        print(f"tool: {t['name']}: {t.get('description', '')[:110]}")
    if len(sys.argv) > 3:
        res = rpc("tools/call", {"name": sys.argv[3], "arguments": json.loads(sys.argv[4] if len(sys.argv) > 4 else "{}")}, 3)
        print("call:", json.dumps(res)[:1200])
