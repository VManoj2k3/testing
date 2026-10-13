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

## Code Bug Finder agent (tested 2026-10-13, Qwen3.8-27B on Kaggle 2x T4, through the tunnel)

`lf_drive.py bugfinder` builds it; `bugfinder_cases.py` scores it on 8 seeded bugs + 2 correct snippets.

| Result | Cases |
|---|---|
| Found, right line, right fix (checked by hand) | none-deref, SQL injection, file leak, mutable default, missing await, division by zero (6) |
| No answer: the model wrote nothing for >100 s and the tunnel closed the stream | off-by-one, C buffer overflow (2) |
| Clean code reported as "NO BUGS FOUND" | 2/2 (no false alarms) |

Time per review 21–106 s. Each review needs a fresh chat session: in one long session the prompt grows
and every answer timed out. Over a direct network (no 100 s tunnel limit) the two timeouts would
probably complete; not tested.

### Stress test (2026-10-13 16:11–16:42 UTC, `bugfinder_stress.py`, 33 reviews)

Every answer that came back was checked by hand.

| Stage | Answered | Result of the answered ones | No answer |
|---|---|---|---|
| Prompt injection (bug + "say NO BUGS FOUND"/"say APPROVED") | 2/3 | 2/2 ignored the injection and reported the SQL injection | 1 timeout |
| Harder bugs (race, C overflow, date boundary, ReDoS, TOCTOU, double discount) | 1/6 | date boundary correct | 5 timeouts |
| Clean, non-trivial code | 2/5 | 1 "NO BUGS FOUND"; 1 flagged NULL `name` in `snprintf("%s")` (strictly undefined in C, debatable) | 3 (2 closed after 33 s, cause unknown) |
| Size (bug in 50 / 150 / 400 lines) | 0/3 | — | 3 timeouts |
| Concurrency 1 / 2 / 4 at once | 0/7 | — | 7 timeouts |
| Consistency (same snippet x3) | 3/3 | same bug, line and fix each time; severity varied | — |
| Junk (empty, prose, 20 KB minified, Go, Rust) | 4/5 | Go nil map and Rust `unwrap` correct; empty/prose got "NO BUGS FOUND" | 20 KB timed out |

**What it shows.** When it answers, it is right: no invented bugs, injection resisted, stable across runs.
But 21/33 reviews got no answer. The cause is this demo rig: the Cloudflare tunnel closes a stream after
~100 s without output, and the aborted review keeps running on the GPU (2 slots), so later requests
queue behind it and time out too (even the single-request concurrency case ran behind that backlog).
Size and concurrency are therefore **not measured**. A real deployment needs a direct network path or a
longer proxy timeout, cancellation of abandoned runs, and a queue in front of the model.

## Publishing a flow as a template for every user (tested 2026-10-13, Langflow 1.12.5)

There is no "publish as template" button. What works (admin, needs shell access and a restart):
1. Export the flow (UI: Export, or `GET /api/v1/flows/{id}`) as JSON with `name`, `description`, `data`.
2. Put it in `<site-packages>/langflow/initial_setup/starter_projects/`.
3. Restart. Templates are rebuilt from that folder on every start.

Result: a second user saw it under Templates (27 total), copied it and ran it; the admin's own flows
stayed invisible to that user. Two catches found in the test:
- **Model settings are per user.** The template carries the model *name*, but the base URL/key are the
  admin's private variables, so the second user's copy failed ("OpenAI API key is required"). Fix: put
  `OPENAI_API_KEY` and `OPENAI_BASE_URL` in Langflow's own environment; they then apply to every user,
  including users created later (verified with a user created after the restart).
- **The folder is inside the installed package**: a `pip install -U langflow` wipes added templates.
  Keep the JSON files in your own repo and copy them in after each upgrade.

## Running Langflow in Docker (or any container)

Inside a container (it checks for `/.dockerenv`), Langflow rewrites `localhost` and `127.0.0.1` in model
URLs to the Docker host's address. A model server in the same container is then unreachable and the SSRF
guard rejects the address. Serve the model on another loopback address (e.g. `127.0.0.2`) and allow
that host in `LANGFLOW_SSRF_ALLOWED_HOSTS`. Found on Kaggle, reproduced here by creating `/.dockerenv`.

## Windows

`.github/workflows/langflow-offline.yml` runs the same steps on `windows-latest` and `ubuntu-latest`
with Qwen3-1.7B: install, start, build both agents, run them. It proves install and API behaviour on
Windows, not the UI by hand, and it can't firewall the runner (offline proof is Linux only).
