#!/usr/bin/env bash
# Build bin/ragflow_server_gpu: build.sh's server binary built without the Go "static" tag, so DeepDoc loads
# Microsoft's GPU libonnxruntime.so (CUDA execution provider) instead of the linked-in CPU-only ORT.
# Needs the RAGFlow tree patched with ragflow_deepdoc_gpu.patch and a normal build.sh run done once.
# Usage: RAGFLOW_SRC=/path/to/ragflow build_gpu_server.sh
# Run with: RAGFLOW_DEEPDOC_DEVICE=cuda RAGFLOW_ORT_LIBRARY_PATH=<ort-gpu>/lib/libonnxruntime.so
set -eu   # no pipefail: build.sh checks use `strings | grep -q`, which pipefail turns into failures
cd "${RAGFLOW_SRC:?set RAGFLOW_SRC}"
export CC=${CC:-clang-20} CXX=${CXX:-clang++-20}   # as setup_ragflow.sh; gcc mixes C++ runtimes and the binary segfaults at start
source ./build.sh            # defines functions only (main runs only when executed directly)
setup_cgo_env
# Drop the static CPU-only ORT (archives, forced OrtGetApiBase pull, dynamic-list export) so the process
# holds one ORT: without the "static" tag the binding dlopen()s RAGFLOW_ORT_LIBRARY_PATH instead.
CGO_LDFLAGS=$(printf '%s' "$CGO_LDFLAGS" | tr -s ' \n' '\n\n' \
  | grep -v -e 'libonnxruntime' -e 'OrtGetApiBase' -e 'ort_dynamic_list' | tr '\n' ' ')
export CGO_LDFLAGS
CGO_ENABLED=1 go build -tags cgo,sonic -o bin/ragflow_server_gpu cmd/ragflow_server.go cmd/deepdoc_server_ee.go
echo "built $(pwd)/bin/ragflow_server_gpu"
