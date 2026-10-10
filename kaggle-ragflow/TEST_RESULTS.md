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

## Stress checks (2026-10-10, one at a time, 4-CPU box, CPU embedder)

### 1. Search and API under load (`ab`, one shared login)

| Endpoint | 1 user | 5 users | 10 users | 25 users | Failures |
|---|---|---|---|---|---|
| Search (`POST /retrieval`), req/s | 4.7 | 5.6 | 6.8 | 6.5 | 0 |
| Search median / slowest | 0.2 / 0.35 s | 0.8 / 1.3 s | 1.5 / 2.5 s | 3.8 / 4.9 s | |
| List datasets, req/s | 181 | 629 | 431 | 557 | 0 |
| Health check, req/s | 290 | 811 | 908 | 1353 | 39–56% non-200 |

- **Search plateaus at about 6–7 req/s** and waits grow linearly. The bottleneck is the CPU embedder embedding each question: this box's limit, not RAGFlow's. No errors up to 25 concurrent users.
- **RAGFlow bug: the health check reports false failures under concurrency.** With 25 parallel calls, 36 of 200 returned HTTP 500 "storage is not healthy" while MinIO was fine. Cause: `internal/storage/minio.go` `Health()` calls `client.HealthCheck()` on the shared MinIO client every time. That call fails with "health check is running" when another check is in flight (846 such warnings in `api.log`). Load balancers or Kubernetes probes would mark a busy instance unhealthy.
- A first run seemed to show mixed or empty response bodies. That was my test (parallel curls sharing one stdout); with per-request files, all 200 bodies were valid. Retracted.

### 2. Bulk ingestion (100 small text files, uploaded and parsed at once)

| Ingestor workers | Parsed | Failed | Time | Docs/min | Chunks |
|---|---|---|---|---|---|
| 1 (RAGFlow default) | 100 | 0 | 317 s | ~19 | 299 |
| 4 (`RAGFLOW_INGESTOR_MAX_CONCURRENT_WORKERS=4`) | 100 | 0 | 260 s | ~23 | 299 |

- **RAGFlow parses one document at a time by default** (`max_concurrent_workers: 1` in `conf/service_conf.yaml`). A company rollout should raise it.
- With 4 workers only 18% faster here, because the single-slot CPU embedder becomes the bottleneck. This box's limit; a GPU embedder should scale better (not measured).
- Peak memory: ingestor 448 MB, embedder 1.8 GB, Elasticsearch 2.6 GB, API 607 MB. Nothing failed or leaked over the run.

### 3. One large PDF (220 generated pages: headings, text, a table every 10 pages)

- **Parsed successfully:** 205 chunks in 653 s (~3 s/page, default single worker, CPU only). No errors.
- **Memory:** the ingestor peaked at 3.2 GB (vs 448 MB for plain text), because PDF layout analysis dominates. Embedder 1.9 GB, Elasticsearch 2.6 GB. Box total about 6.4 GB used of 16.
- **Whole file searchable:** table rows from page 190 are retrievable.
- **Quality notes:**
  - Adjacent table cells can merge in the extracted text (`P190-4 | 806 | ms` → `P190-4806ms`), which can mislead number lookups.
  - Search is semantic, so an exact label query ("Chapter 197") returned the neighbouring chapter's chunk.

### 4. Upload limits and filenames

| Upload | Via nginx (:80) | Via API (:9380) |
|---|---|---|
| 50 MB | accepted (0.6 s) | accepted (0.4 s) |
| 1.1 GB | **HTTP 413** immediately (`client_max_body_size 1024M`) | uploaded fully, then refused: "file exceeds the maximum allowed size of 134217728 bytes" |

- **The real per-file limit is 128 MB**, not the 1 GB that nginx and Docker's `MAX_CONTENT_LENGTH` suggest. Files between 128 MB and 1 GB upload completely and are then refused. Temporary disk space was released afterwards (checked); no leak.
- **Error codes:** validation failures (too large, unsupported type, bad name) come back as **HTTP 200 with `code: 500`**, which monitoring and clients will read as server crashes.
- **Filenames:**
  - 300 chars: rejected (255-byte limit).
  - Unicode and emoji: stored correctly.
  - `../../etc/passwd.txt`: sanitized to `passwd.txt`, stored inside the dataset's bucket; no path escape.
  - `..\..\win.txt`: not sanitized by RAGFlow, but rejected by MinIO (as code 500).
  - `<script>…</script>.txt`: stored as `script>.txt`.
  - No extension: rejected.
  - A text file renamed `.pdf`: accepted at upload.

### 5. Malformed input (21 requests to datasets, retrieval, chats, agents)

- **Robust:** every request got a clean validation message in under 0.02 s. There were no crashes, hangs, panics or API restarts, and health stayed OK afterwards.
- Inputs tried:
  - empty and broken JSON,
  - wrong types and nulls,
  - a 1 MB name (rejected: limit 128),
  - negative or huge paging and top_k (range-checked),
  - fake and SQL-like IDs (permission error),
  - a SQL-injection-style dataset name (stored literally; database intact).
- **Weak spot: agent graphs are not validated at save time.**
  - An agent whose Begin block points to itself was accepted on create (code 0).
  - It fails only when run, with a misleading "Internal storage error while accessing the agent". The real cause is in `api.log`: `self-edge on "begin"`. No hang or CPU spin.

### 6. Service failure: Elasticsearch killed mid-ingestion (20 docs, 16 done / 4 running)

- The 4 in-flight documents **failed fast with a clear error** ("insert chunk batch … after 3 attempts … connection refused", with partial-write compensation). The 16 completed ones were unaffected.
- The health check correctly showed `doc_engine: nok` during the 1-minute outage.
- **No automatic retry after recovery:** the 4 stayed FAILED once Elasticsearch was back. A manual re-parse completed them in 20 s.
- **No data loss or duplicates:** exactly 60 chunks for 20 docs, and search works afterwards.
- For a rollout, failed documents need monitoring and a re-parse job, or an operator.

### 7. Chat and agents under concurrent load (Qwen3.8-27B, 2×T4, 4 parallel slots, 65k context)

| Chat, users at once | 8 answers took | Typical / slowest answer | Errors | Correct |
|---|---|---|---|---|
| 1 | 146 s | 18 / 23 s | 0 | 7/8 |
| 2 | 43 s | 6 / 17 s | 0 | 8/8 |
| 4 | 39 s | 12 / 31 s | 0 | 7/8 |
| 8 (more than the 4 slots) | 41 s | 23 / 41 s | 0 | 7/8 |

| Agent (starter template), runs at once | 8 runs took | Typical / slowest | Correct |
|---|---|---|---|
| 1 | 162 s | 19 / 43 s | 4/8 |
| 2 | 164 s | 35 / 87 s | 4/8 |
| 4 | 146 s | 46 / 115 s | 4/8 |

- **Chat holds up:** no errors and stable accuracy up to 8 concurrent users. Beyond the 4 slots, requests queue (slowest 41 s) rather than fail. The same 8 questions were reused per level, so llama.cpp's prompt cache flatters the later levels' speed.
- **Agents hit a context limit, not a load limit.** The 4/8 is the same at 1, 2 and 4 runs at once. 3 of the 4 misses were Qwen rejecting the request: "request (~17,000 tokens) exceeds the context". Four parallel slots split the 65k context into about 16k per request, and one agent run (instructions, tool schemas, retrieved chunks) needs about 17k. **Parallel slots and context size must be sized together:** fewer slots, a bigger context, or fewer retrieved chunks.
- **RAGFlow returns that model error as the answer text** ("**ERROR**: [GraphRunError] … status 400 …") rather than as an error event, so users would see raw errors as replies.
- 1 genuine wrong answer: asked about the big model's heads, the agent quoted the base model's 8. The correct answer is 16.

## Not covered

- Oversized-upload limits (default `MAX_CONTENT_LENGTH` is 1 GB).
- GitHub (blocked here) and GitLab (needs a token) connectors.
- Answer quality on real company documents (the 30–50 question gold set is still needed).
- Load and concurrency.
