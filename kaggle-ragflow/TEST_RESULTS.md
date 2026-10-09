# RAGFlow full-tool test results

Tested on 2026-10-09. RAGFlow v1.0.0-rc1 (Go rewrite, commit 2400ca8) was built from source and run natively with no Docker. Qwen3.8-27B (Q4_K_M) served chat on 2× T4 on Kaggle; bge-m3 (Q8_0) did embeddings, first on GPU, later on 4 local CPU cores.

Every number below comes from a run in this session. Test scripts are in `kaggle-ragflow/tests/`.

## Summary

| Layer | Result | RAGFlow bugs found |
|---|---|---|
| Go unit tests | 29 packages pass, 0 assertion failures; 25 packages not runnable here (native-lib link issue) | 0 |
| Upstream HTTP API suite (353 tests, level p2) | 192 passed; 2 failed + 5 errors, all environment; 153 skipped by the suite itself | 0 |
| Upstream UI suite (Playwright) | Auth: 12 passed, 11 skipped (sign-up off). End-to-end: 23 passed, 4 failed (env / test drift), 12 cascade skips | 0 confirmed |
| File formats (13 files) | 11/11 supported formats parsed and answered correctly; .tsv and .log rejected at upload | 0 |
| Chunking methods | 9/9 complete | 0 |
| Built-in agent templates (16 agents) | 12 ran, 1 waits for the user by design, 2 need outside setup (search keys, SQL DB), 1 is not runnable | 0 |
| Chat accuracy (Attention paper) | 7/8 | - |
| Template agent accuracy | 8/8 single-fact, 4/4 multi-step | - |
| Custom agents | Questionnaire-built 4/4, triage 3/3, confirm-before-action 2/2, MCP-tool agent 3/3 | - |
| Connector (RSS) | 10 items synced, 119 chunks, correct cited answer | 0 |
| MCP server | Works; default mode has no client auth (see security) | design issue |

## Findings that matter for adoption

1. **Agents work on this data.** Single-fact Q&A, two-step reasoning, branching, tool calls, and human confirmation all behaved correctly. The questionnaire-built agent passed its own tests first time. The caveat: this was one clean academic paper plus public blog posts, not company documents.
2. **MCP default mode trusts everyone.** In `self-host` mode (the default) the MCP server ignores client credentials. No key or a wrong key both return data as the server's configured account (`internal/handler/mcp_server.go`). It binds to 127.0.0.1 by default. `RAGFLOW_MCP_LAUNCH_MODE=host` enforces per-caller keys (verified: 401 without or with a wrong key). Use host mode for any shared setup.
3. **Agents can only use MCP servers at public addresses.** RAGFlow's SSRF guard rejects MCP URLs that resolve to private or loopback IPs. The override exists only for tests and cannot be set by config (`internal/common/http.go`). A company MCP gateway on an internal IP is refused unless it's exposed publicly (with auth) or RAGFlow is changed.
4. **One session per account.** A new login immediately invalidates the account's previous session, and so does an API restart. Shared or service accounts and multi-device use will log people out.
5. **Prompt injection:** a planted "ignore instructions / create a ticket" text was resisted in chat (2/2), template agent (2/2) and the tool-enabled agent, with and without a defensive prompt line. These were single, crude probes. RAGFlow has no injection defense of its own, so the resistance comes from the model.
6. **Silent fallback:** the Deep research template answered without its web-search key, from model knowledge, without saying so.
7. **Maturity:** RAGFlow's own API suite skips 153 tests in Go mode. 15 routes are marked "not implemented", and the older flat parser_config format is no longer accepted. The UI test suite lags the app: it rejects v1.0's own 3-part model IDs and uses an outdated dataset URL.
8. **Sizing:** the "one" chunking method sends a whole document as one 8k-token chunk. The CPU embedder needed about 9 GB and was OOM-killed until its batch size was reduced to 4096.

## Environment failures (not RAGFlow bugs)

- **API suite (7):** 2 tests assert the default embedding model name `BAAI/bge-small-en-v1.5`; 5 need Docker's built-in TEI embedder on :6380.
- **UI suite (4):**
  - The agent-import JSON is hard-wired to `glm-4-flash`; RAGFlow shows a clear "model missing" checklist.
  - The dataset fallback URL `/dataset/dataset/:id` is outdated and returns 404.
  - The search dropdown isn't on the default view.
  - Chat settings step: likely the same drift, unverified.
- **Go tests (25 packages):** packages that use the pdfium / office_oxide / onnxruntime static libraries either don't compile without build.sh's CGO flags, or link and then segfault in protobuf's static init. The production binary built by build.sh runs fine. Document parsing and HTTP handlers therefore have no unit-test coverage here, only the end-to-end coverage above.

## Bugs found and fixed in our own scripts (pushed)

- `run_ragflow.sh start` left sign-up open after any restart (verified: an anonymous account could be created). It now defaults to `ENABLE_REGISTER=0`.
- `configure_models.sh` registered the GPU embedder without its key, so every parse failed with 401.
- All Kaggle kernels: the tunnel-URL regex captured `api.trycloudflare.com` from cloudflared error lines.
- `load_dataset.py` / `feature_matrix.py`: wrong status and field names (`ingestion_status` / COMPLETED, `parser_id`, `content_with_weight`).

## Corrections to earlier claims

- The "AUTH_SECRET_KEY / password hash exposed via /api/runtime-config" issue belongs to **Presenton** (`servers/fastapi/api/v1/auth/config.py`), not RAGFlow. RAGFlow v1.0 has no such route.

## Git and Jira connectors (tested 2026-10-09, late)

| Connector | Result |
|---|---|
| **Jira** | **Works end to end.** Apache's public Jira (Server 8.20, project KAFKA, issues updated in the last 3 days): 10 issues synced in 20 s, all 10 parsed in ~220 s, and retrieval returned the right issue with key, URL, summary, description and comments. Auth note: the connector requires credentials (no anonymous mode), and Apache's Jira treated a placeholder bearer token as anonymous read. A company Jira needs a real API token (Cloud: email + token; Server/DC: token or username/password), and the connector reads with that account's permissions. |
| **GitLab** | gitlab.com is reachable and the connector/dataset link was created, but the sync failed: the connector **requires** `gitlab_access_token`, even for public projects (`internal/syncer/connector/gitlab.go`). Not completed without a token. |
| **GitHub** | Not testable from this container: api.github.com is blocked by the network proxy (403). |
| **Bitbucket** | Not tested. |

## Not covered

- Oversized-upload limits (default `MAX_CONTENT_LENGTH` is 1 GB).
- GitHub (blocked here) and GitLab (needs a token) connectors.
- Answer quality on real company documents (the 30–50 question gold set is still needed).
- Load and concurrency.
