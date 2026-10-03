"""Natural-language -> KiCad schematic agent.

An OpenAI-compatible LLM (Qwen on llama-server) drives a curated subset of the
mcp-server-kicad tools over MCP streamable HTTP. Stdlib only, so it runs
anywhere. Paths are injected server-side; the model only sees design arguments.
"""
import json
import urllib.request

# Path arguments the server fills in for the current design; the model never sees them.
INJECTED_ARGS = ("schematic_path", "project_path")

SYSTEM = """You are a KiCad schematic designer. Turn the user's request into a schematic by calling tools.
Rules:
- Standard symbols: Device:R, Device:C, Device:C_Polarized, Device:L, Device:LED, Device:D,
  Device:Q_NPN_BEC, Device:Q_PNP_BEC, Switch:SW_Push, Connector:Conn_01x02_Pin.
  Power: power:+5V, power:+3V3, power:+12V, power:VCC, power:GND (references #PWR01, #PWR02, ...).
- Two-pin parts (R, C, L, LED, D) have pins "1" and "2". For LED/D, pin "1" is the cathode (K), "2" the anode (A).
  Power symbols have a single pin "1".
- Coordinates are in mm on a 2.54 mm grid; keep parts 15-25 mm apart, start near x=100, y=80.
- Place every part first, then connect pins with connect_pins (or wire_pins_to_net for shared nets).
- Finish with run_erc. Fix real errors if you can. Then reply with a short summary of the circuit.
- Never invent tool names. One step at a time; read each tool result before the next call."""


class MCPClient:
    def __init__(self, url, key):
        self.url, self.key, self.sid = url, key, None
        self._id = 0

    def _post(self, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": f"Bearer {self.key}", "MCP-Protocol-Version": "2025-06-18"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            self.sid = r.headers.get("Mcp-Session-Id") or self.sid
            data = [l[6:] for l in r.read().decode().splitlines() if l.startswith("data: ")]
            return json.loads(data[-1]) if data else None

    def _rpc(self, method, params=None):
        self._id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg["result"]

    def connect(self):
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "kicad-ui", "version": "0"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self._rpc("tools/list")["tools"]

    def call(self, name, args):
        r = self._rpc("tools/call", {"name": name, "arguments": args})
        payload = r.get("structuredContent") or [c.get("text") for c in r.get("content", [])]
        return {"isError": bool(r.get("isError")), "result": payload}


def openai_tools(mcp_tools):
    """All server tools as OpenAI functions, minus the injected path arguments.

    Returns (tools, injectable) where injectable maps tool name -> the injected
    args that tool actually accepts.
    """
    out, injectable = [], {}
    for t in mcp_tools:
        schema = json.loads(json.dumps(t["inputSchema"]))
        props = schema.get("properties", {})
        injectable[t["name"]] = [k for k in INJECTED_ARGS if k in props]
        for k in injectable[t["name"]]:
            props.pop(k)
        if "required" in schema:
            schema["required"] = [r for r in schema["required"] if r not in INJECTED_ARGS]
        out.append({"type": "function", "function": {
            "name": t["name"], "description": t.get("description", "").strip(), "parameters": schema}})
    return out, injectable


def chat(llm_url, llm_key, model, messages, tools):
    body = {"model": model, "messages": messages, "tools": tools, "temperature": 0.2, "max_tokens": 2048}
    req = urllib.request.Request(f"{llm_url}/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {llm_key}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())


def run(prompt, *, llm_url, llm_key, model, mcp, tools, injectable, schematic_path, project_path="",
        history=None, max_steps=40, on_event=print):
    """Run one user request to completion. Yields events via on_event; returns updated history."""
    messages = history or [{"role": "system", "content": SYSTEM}]
    messages.append({"role": "user", "content": prompt})
    for _ in range(max_steps):
        resp = chat(llm_url, llm_key, model, messages, tools)
        msg = resp["choices"][0]["message"]
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        calls = msg.get("tool_calls") or []
        if not calls:
            on_event({"type": "answer", "text": msg.get("content") or ""})
            return messages
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError as e:
                result = {"isError": True, "result": f"arguments were not valid JSON: {e}"}
            else:
                if name not in injectable:
                    result = {"isError": True, "result": f"unknown tool {name}"}
                else:
                    paths = {"schematic_path": schematic_path, "project_path": project_path}
                    result = mcp.call(name, {**args, **{k: paths[k] for k in injectable[name] if paths[k]}})
            on_event({"type": "tool", "name": name, "args": args, **result})
            messages.append({"role": "tool", "tool_call_id": c.get("id", name),
                             "content": json.dumps(result["result"])[:4000]})
    on_event({"type": "answer", "text": f"Stopped after {max_steps} steps without finishing."})
    return messages
