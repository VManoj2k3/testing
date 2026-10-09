"""pytest plugin: run RAGFlow's upstream HTTP API suite (test/testcases) against our own models.

The suite hard-codes two paid cloud providers: ZHIPU-AI (chat, glm-4-flash@CI@ZHIPU-AI, ~64
references) and SILICONFLOW (embedding BAAI/bge-m3 + rerank, instance "CI"). Instead of editing
the tests, this plugin registers those same providers/instances with their base_url pointed at
our OpenAI-compatible llama-servers (Qwen for chat, bge-m3 for embeddings). RAGFlow resolves an
instance's base_url before the provider default (internal/entity/models/base_model.go
GetBaseURL), and llama-server serves its loaded model whatever model name is sent, so the
suite's own model IDs route to our models. No RAGFlow code is changed.

There is no reranker: tests that need one fail and are classified as "environment".

Env: QWEN_URL, EMBED_URL (both .../v1), MODEL_KEY (the llama-server API key), HOST_ADDRESS.
Usage (from the ragflow checkout):
  ZHIPU_AI_API_KEY=$MODEL_KEY SILICONFLOW_API_KEY=$MODEL_KEY \
  .venv/bin/pytest -p qwen_override test/testcases/restful_api --level=p2   (with this dir on PYTHONPATH)
"""
import os

import pytest
import requests

QWEN_URL = os.environ["QWEN_URL"].rstrip("/")
EMBED_URL = os.environ["EMBED_URL"].rstrip("/")
KEY = os.environ["MODEL_KEY"]

INSTANCES = {
    "ZHIPU-AI": {"base_url": QWEN_URL, "model_info": [
        {"model_type": ["chat"], "model_name": "glm-4-flash", "max_tokens": 32768}]},
    "SILICONFLOW": {"base_url": EMBED_URL, "model_info": [
        {"model_type": ["embedding"], "model_name": "BAAI/bge-m3", "max_tokens": 8192},
        {"model_type": ["embedding"], "model_name": "BAAI/bge-large-en-v1.5", "max_tokens": 512},
        {"model_type": ["embedding"], "model_name": "BAAI/bge-large-zh-v1.5", "max_tokens": 512}]},
}


def _add_model_instance(host):
    def add_model_instance(auth):
        h = {"Authorization": auth}
        for provider, inst in INSTANCES.items():
            requests.put(f"{host}/api/v1/providers", headers=h, json={"provider_name": provider}, timeout=60)
            body = {"instance_name": "CI", "api_key": KEY, "region": "default", **inst}
            r = requests.post(f"{host}/api/v1/providers/{provider}/instances", headers=h, json=body, timeout=120).json()
            if r.get("code") != 0 and "exist" in str(r.get("message", "")).lower():
                # Re-point an instance left over from an earlier run (URLs change per Kaggle launch).
                r = requests.put(f"{host}/api/v1/providers/{provider}/instances/CI", headers=h, json=body, timeout=120).json()
            print(f"[qwen_override] {provider}/CI -> {inst['base_url']}: code={r.get('code')} {r.get('message')}")
        tid = requests.get(f"{host}/api/v1/users/me", headers=h, timeout=60).json().get("data", {}).get("id", "")
        r = requests.patch(f"{host}/api/v1/users/me/models", headers=h, timeout=60, json={
            "tenant_id": tid, "llm_id": "glm-4-flash@CI@ZHIPU-AI", "embd_id": "BAAI/bge-m3@CI@SILICONFLOW",
            "asr_id": "", "img2txt_id": "", "rerank_id": "", "tts_id": ""}).json()
        print(f"[qwen_override] tenant defaults: code={r.get('code')} {r.get('message')}")
    return add_model_instance


def pytest_configure(config):
    import test.testcases.conftest as c  # noqa: E402  (imported after env is set)
    c.add_model_instance = _add_model_instance(c.HOST_ADDRESS)
    original = c.get_added_models
    done = {"x": False}

    def get_added_models(auth, factory_name):
        # Force one (re)registration per session so instances always point at the current URLs.
        if not done["x"]:
            done["x"] = True
            return False
        return original(auth, factory_name)
    c.get_added_models = get_added_models

    class _Requests:
        """requests shim: redirect the suite's 'Builtin/Local bge-small' embedding default (not
        available natively) to our bge-m3 instance; everything else passes through."""
        def __getattr__(self, name):
            return getattr(requests, name)

        def patch(self, url, **kw):
            j = kw.get("json") or {}
            if url.endswith("/api/v1/models/default") and j.get("model_type") == "embedding":
                kw["json"] = {"model_provider": "SILICONFLOW", "model_instance": "CI",
                              "model_type": "embedding", "model_name": "BAAI/bge-m3"}
            return requests.patch(url, **kw)
    c.requests = _Requests()
