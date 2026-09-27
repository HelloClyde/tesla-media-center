#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/amap-app/release_assets.py
docker build -f docker_build/Dockerfile . -t registry.cn-hangzhou.aliyuncs.com/helloclyde/tesla-media-center:latest
docker push registry.cn-hangzhou.aliyuncs.com/helloclyde/tesla-media-center:latest
echo 'build success'
