#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: build-mnn-web.sh MNN_3_1_1_SOURCE OUTPUT_DIR" >&2
  exit 2
fi

mnn_source=$(realpath "$1")
output_dir=$(realpath -m "$2")
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$output_dir"

emcmake cmake -S "$mnn_source" -B "$mnn_source/buildweb" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DMNN_BUILD_SHARED_LIBS=OFF -DMNN_SEP_BUILD=OFF \
  -DMNN_BUILD_TOOLS=OFF -DMNN_BUILD_TEST=OFF \
  -DMNN_FORBID_MULTI_THREAD=ON -DMNN_USE_THREAD_POOL=OFF -DMNN_USE_SSE=OFF
cmake --build "$mnn_source/buildweb" --target MNN -j 8

em++ "$script_dir/mnn_bridge.cpp" -I"$mnn_source/include" \
  -Wl,--whole-archive "$mnn_source/buildweb/libMNN.a" -Wl,--no-whole-archive \
  -O3 -s MODULARIZE=1 -s EXPORT_NAME=createAmapMnn \
  -s ALLOW_MEMORY_GROWTH=1 -s ENVIRONMENT=web,worker,node \
  -s 'EXPORTED_FUNCTIONS=["_amap_mnn_load_f0","_amap_mnn_run_f0","_amap_mnn_f0_data","_amap_mnn_clear","_amap_mnn_load","_amap_mnn_prepare_input","_amap_mnn_input_elements","_amap_mnn_run","_amap_mnn_output_data","_amap_mnn_output_elements","_amap_mnn_output_dimension","_amap_mnn_unload","_malloc","_free"]' \
  -o "$output_dir/amap-mnn.js"
