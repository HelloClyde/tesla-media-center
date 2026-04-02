FROM node:20-bookworm-slim AS web-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.10-slim

EXPOSE 8080

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /root/tesla-media-center

COPY requirement.txt ./
RUN python -m pip install --no-cache-dir --upgrade -r requirement.txt

COPY *.py ./
COPY ffvideo ./ffvideo
COPY video ./video
COPY web/public ./web/public
COPY --from=web-builder /build/web/dist ./web/dist

CMD ["python", "/root/tesla-media-center/flask_app.py"]
