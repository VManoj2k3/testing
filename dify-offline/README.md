# Dify without outbound calls: setup for your own hardware (written from the code, NOT run)

Dify (commit 7b69dea2, 2026-10-12) was not installed here: its Docker stack (~16 containers by
default) needs more disk than this test container has. Everything below is read from the repo and
is **unverified until you run it with a firewall**, the way `langflow-offline/` was verified.

Platforms: Linux (Docker Engine) or Windows/macOS (Docker Desktop). Docs state at least 2 CPU cores
and 4 GiB RAM, plus your local model server.

## Outbound calls Dify makes by default, and the switch

| Call | Default | Switch | Where to set it |
|---|---|---|---|
| Anonymous telemetry to otel.dify.ai (otel.dify.cn fallback) | **on** | `DISABLE_TELEMETRY=true` | `docker/envs/core-services/shared.env` (read by api and worker); not in the shipped examples |
| Update check to updates.dify.ai | on | `CHECK_UPDATE_URL=` (empty) | `docker/.env` and `shared.env` |
| App templates from tmpl.dify.ai | remote | `HOSTED_FETCH_APP_TEMPLATES_MODE=builtin` | `shared.env` (falls back to built-in if remote fails) |
| Plugin marketplace (marketplace.dify.ai) | on | `MARKETPLACE_ENABLED=false` | `docker/.env`, `shared.env`, `middleware.env` |
| Plugin Python dependencies from PyPI | on (when a plugin is installed) | `PIP_MIRROR_URL=<internal mirror>`, or install plugins once while connected | `docker/.env` |
| Next.js telemetry (web container) | `NEXT_TELEMETRY_DISABLED=0` | `NEXT_TELEMETRY_DISABLED=1` | `docker/.env` |
| Weaviate telemetry | on | `WEAVIATE_DISABLE_TELEMETRY=true` | `docker/.env` |
| Sentry | off (DSNs empty) | keep empty | — |

## Local models are plugins

Dify has no built-in OpenAI-compatible or Ollama provider; both are plugins. Offline install:
1. On a connected machine, download the signed `.difypkg` for the OpenAI-API-compatible (or Ollama)
   provider from the marketplace.
2. Upload it in Dify: Plugins → Install from local package. Signature checking
   (`FORCE_VERIFYING_SIGNATURE=true`) stays on, since marketplace packages are signed.
3. The plugin daemon then pip-installs the plugin's dependencies. **Fully offline, that fails** unless
   `PIP_MIRROR_URL` points at an internal PyPI mirror, or the plugin was installed once while connected.
4. Add the provider with base URL `http://<host>:<port>/v1`. From inside Docker, the host is not `127.0.0.1`.

## Licence conditions (LICENSE)

Apache 2.0 plus: no multi-tenant service (one tenant = one workspace) and no removing or changing the
Dify logo or copyright in the console/web app without a commercial licence. One company running it
internally in one workspace fits; check with legal for anything else.

## To verify on your machine

1. Apply the settings above, then `docker compose up -d`.
2. Block outbound traffic for the Docker network (host firewall or `internal: true` networks), leaving
   only the model server reachable. Log what is blocked.
3. Create one agent from a template and one from scratch with the form builder; run both.
4. Anything in the block log is a call this table missed.
