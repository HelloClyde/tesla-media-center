# syntax=docker/dockerfile:1
# Compress each large asset family independently from application source.
FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS asset-compressor
COPY web/scripts/precompress-dist.mjs /precompress-dist.mjs

FROM asset-compressor AS model-assets
COPY web/public/models/ /assets/
RUN node /precompress-dist.mjs /assets

FROM asset-compressor AS texture-assets
COPY web/public/textures/ /assets/
RUN node /precompress-dist.mjs /assets

FROM asset-compressor AS public-assets
COPY web/public/*.* /assets/
COPY web/public/catalogs/ /assets/catalogs/
COPY web/public/gam4980/ /assets/gam4980/
COPY web/public/icon/ /assets/icon/
COPY web/public/vendor/ /assets/vendor/
RUN node /precompress-dist.mjs /assets

FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS web-builder
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/*.json web/*.ts web/*.html ./
COPY web/src/ ./src/
COPY web/scripts/ ./scripts/
# Vite resolves these root assets while compiling; the remaining public
# directories are copied later as independent runtime layers.
COPY web/public/*.js ./public/
COPY web/public/tmc-mark.svg web/public/screen-cap.jpg ./public/
COPY web/public/icon/ ./public/icon/
RUN TMC_SEPARATE_PUBLIC=1 npm run build

FROM asset-compressor AS tts-assets
COPY web/public/tts/ /assets/
COPY --from=web-builder /build/web/public/tts/amap-1.0/amap-core.js /assets/amap-1.0/amap-core.js
RUN test -s /assets/amap-1.0/am_encoder.mnn && \
    test -s /assets/amap-1.0/am_decoder.mnn && \
    test -s /assets/amap-1.0/ddspganV2_f0.mnn && \
    test -s /assets/amap-1.0/ddspganV2_ctrl.mnn && \
    test -s /assets/amap-1.0/amap-mnn.wasm && \
    test -s /assets/amap-1.0/amap-core.js && \
    node /precompress-dist.mjs /assets

FROM python:3.11-slim
EXPOSE 8080
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMC_DATA_DIR=/data \
    TMC_AMAP_APP_ASSETS=/opt/tmc/amap-app
WORKDIR /root/tesla-media-center
COPY requirement.txt ./
COPY tools/amap-app/requirements.txt ./amap-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade -r requirement.txt -r amap-requirements.txt
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/tmc/ms-playwright
RUN python -m playwright install --with-deps --no-shell chromium

# Linked COPY layers do not depend on earlier code/dependency layers.
COPY --link docker_build/amap-assets/ /opt/tmc/amap-app/
COPY --link --from=tts-assets /assets/ ./web/dist/tts/
COPY --link --from=model-assets /assets/ ./web/dist/models/
COPY --link --from=texture-assets /assets/ ./web/dist/textures/
COPY --link --from=public-assets /assets/ ./web/dist/
COPY --link video/ ./video/
# Keep the backend catalog path compatible without duplicating public assets.
RUN ln -s dist web/public

COPY --link *.py ./
COPY --link ffvideo/ ./ffvideo/
COPY --link tools/amap-app/ ./tools/amap-app/
RUN python tools/amap-app/release_assets.py --verify-only --directory /opt/tmc/amap-app && \
    python -c "import sys; sys.path.insert(0, 'tools/amap-app'); import tmc_map_helper, tmc_route_helper, tmc_lane_helper"
COPY --link --from=web-builder /build/web/dist/ ./web/dist/
CMD ["python", "/root/tesla-media-center/flask_app.py"]
