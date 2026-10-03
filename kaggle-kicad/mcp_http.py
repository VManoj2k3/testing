"""Serve the unified mcp-server-kicad over streamable HTTP with bearer-token auth.

The upstream entry point (mcp_server_kicad.server:main) is stdio-only; this
reuses its tool merge and exposes the same server at /mcp.
Env: MCP_TOKEN (required), PORT (default 8090), MCP_CWD (KiCad project dir).
"""
import hmac
import json
import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware

from mcp_server_kicad import footprint, pcb, project, schematic, symbol
from mcp_server_kicad import server as unified

TOKEN = os.environ["MCP_TOKEN"]


class BearerAuth:
    """Reject HTTP requests without the token; CORS preflight passes through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] != "OPTIONS":
            got = dict(scope["headers"]).get(b"authorization", b"").decode()
            if not hmac.compare_digest(got, f"Bearer {TOKEN}"):
                body = json.dumps({"error": "missing or invalid bearer token"}).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def build_app():
    for mod in [schematic, pcb, symbol, footprint, project]:
        unified._copy_tools(mod.mcp, unified.mcp)
    # The tunnel's Host header is not localhost; the bearer token is the guard instead.
    app = unified.mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return CORSMiddleware(BearerAuth(app), allow_origins=["*"], allow_methods=["*"],
                          allow_headers=["*"], expose_headers=["Mcp-Session-Id"])


if __name__ == "__main__":
    if os.environ.get("MCP_CWD"):
        os.chdir(os.environ["MCP_CWD"])
    uvicorn.run(build_app(), host="127.0.0.1", port=int(os.environ.get("PORT", "8090")),
                log_level="warning")
