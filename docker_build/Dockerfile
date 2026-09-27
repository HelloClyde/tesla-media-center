FROM node:20-bookworm-slim AS web-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

EXPOSE 8080

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /root/tesla-media-center

COPY requirement.txt ./
COPY tools/amap-app/requirements.txt ./amap-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade -r requirement.txt -r amap-requirements.txt

COPY *.py ./
COPY ffvideo ./ffvideo
COPY tools/amap-app ./tools/amap-app
RUN python -c "import sys; sys.path.insert(0, 'tools/amap-app'); import tmc_map_helper, tmc_route_helper"
COPY video ./video
COPY web/public ./web/public
COPY --from=web-builder /build/web/dist ./web/dist

CMD ["python", "/root/tesla-media-center/flask_app.py"]
