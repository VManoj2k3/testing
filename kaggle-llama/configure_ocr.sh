#!/usr/bin/env bash
# Points ocr at the Kaggle-hosted llama-server.
set -euo pipefail
cd "$(dirname "$0")"
URL=${1:-$(cat .state/llm_url)}
ocr config set provider                         kaggle-qwen
ocr config set custom_providers.kaggle-qwen.url        "$URL"
ocr config set custom_providers.kaggle-qwen.protocol   openai
ocr config set custom_providers.kaggle-qwen.model      qwen3-8b
ocr config set custom_providers.kaggle-qwen.api_key    "$(cat .state/secret)"
ocr config set custom_providers.kaggle-qwen.timeout_sec 900
