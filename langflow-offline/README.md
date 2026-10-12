# Langflow fully offline: results and setup

Goal: an agent builder with ready-made templates, a simple UI, and agents built from scratch, where
**no data leaves the machine**, on **Linux and Windows**. Langflow 1.12.5 (MIT), tested 2026-10-12.

## Why Langflow (desk check of 5 tools, read from each repo)

| | Langflow | Dify | AnythingLLM | n8n | Flowise |
|---|---|---|---|---|---|
| Licence | MIT | Apache 2.0 + conditions (no multi-tenant service, keep logo) | MIT | Sustainable Use (not open source) | Apache 2.0 + commercial `enterprise/` |
| Templates bundled | 27 | 22 (3 agents) | none (online hub) | ~4 (gallery online) | 64 |
| Builder | canvas + build-from-description | form agent + canvas + build-from-description | block-list form | canvas (AI builder: paid licence + cloud/Anthropic) | canvas |
| Windows without Docker | yes (pip / desktop app) | no (Docker Desktop, ~16 containers) | desktop app | npm (undocumented) | npm |
| Status | active | active | active | active | **archived 2026-08-13** |

Dify comes second: it is the closest to a form-style builder, but heavy and with more default
outbound calls (telemetry, update check, remote templates, marketplace plugins for local models).

## Offline proof (Linux, this container)

Langflow and the model server ran as user `lfoffline`, with `offline_firewall.sh`: only
`127.0.0.1:7860` (Langflow) and `127.0.0.1:8095` (model) reachable; everything else rejected and
logged. (Allowing all of loopback would not be enough: a local HTTP proxy on 127.0.0.1 is a way out.)

What Langflow tried to reach, and the fix:

| Destination | Cause | Fix |
|---|---|---|
| raw.githubusercontent.com | LiteLLM (dependency) model price list at startup | `LITELLM_LOCAL_MODEL_COST_MAP=True` |
| models.dev | model catalog refresh | `LANGFLOW_MODELS_DEV_REFRESH=false` |
| pypi.org | version check in the startup banner, sends only the package name | **no switch**: block with a firewall |
| api.openai.com | saving `OPENAI_API_KEY` validates it; went to OpenAI because the base URL was saved *after* the key | save `OPENAI_BASE_URL` **first** (lf_drive.py does) |

Telemetry (Scarf) and the legacy store were off via `LANGFLOW_DO_NOT_TRACK`/`DO_NOT_TRACK`/`LANGFLOW_STORE=false`
and never appeared. During all agent runs, no outbound attempt was logged.

## Agents with a local model (Qwen3-4B Q4, llama.cpp, 4 CPU cores, ~8 tokens/s)

| Test | Result |
|---|---|
| "Simple Agent" template (web-search/URL tools removed, calculator kept): 17.5% of 2340 | 409.5, correct, 12–21 s |
| From-scratch helpdesk triage agent (own instructions): 6 tickets | 6/6 categories correct, 4–9 s each |
| Build-from-description assistant | **does not work** with a 4B model: it chats instead of building (0 nodes). On a pip install it also needs a path workaround and `LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false` (a security trade-off), see below. Not tested with a larger model. |

The quality limit is the model, not Langflow: a 27B-class model needs a GPU.

## Setup

1. Install: `pip install langflow==1.12.5` (Python 3.10–3.13) in a venv. Windows: same, or Langflow Desktop.
2. Local model: any OpenAI-compatible server, e.g. llama.cpp `llama-server -m model.gguf --port 8095 --jinja`.
3. `cp langflow.env.example langflow.env`, set the password, then `langflow run --env-file langflow.env`.
4. Point Langflow at the model: `LF_PASSWORD=... python lf_drive.py setup` (or in the UI: set the
   OpenAI provider's **base URL first**, then any API key).
5. Linux, optional proof: `sudo ./offline_firewall.sh on`, run Langflow and the model as `lfoffline`,
   then `sudo ./offline_firewall.sh log`. pypi.org will appear (banner check, no switch).

Build-from-description on a pip install: it reads component sources from `./src/lfx/src/lfx/components/`
(a git-checkout path). Workaround: symlink that path to the installed `lfx/components`, set
`LANGFLOW_DIRECTORY_COMPONENT_ALLOWED_ROOTS=<installed lfx/components>` and
`LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false`. The last one lets users' flows read server files,
so only do this on a single-user machine.

## Running Langflow in Docker (or any container)

Inside a container (it checks for `/.dockerenv`), Langflow rewrites `localhost` and `127.0.0.1` in model
URLs to the Docker host's address. A model server in the same container is then unreachable and the SSRF
guard rejects the address. Serve the model on another loopback address (e.g. `127.0.0.2`) and allow
that host in `LANGFLOW_SSRF_ALLOWED_HOSTS`. Found on Kaggle, reproduced here by creating `/.dockerenv`.

## Windows

`.github/workflows/langflow-offline.yml` runs the same steps on `windows-latest` and `ubuntu-latest`
with Qwen3-1.7B: install, start, build both agents, run them. It proves install and API behaviour on
Windows, not the UI by hand, and it can't firewall the runner (offline proof is Linux only).
