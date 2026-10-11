# Build from the repo root: `docker compose build zsignal-web` (see ../docker-compose.yml).
# python:3-slim is published multi-arch (amd64/arm64), so this Dockerfile needs no
# cross-compilation -- each host builds its own native image locally.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY zsignal/ ./zsignal/
COPY zsignal-web/ ./zsignal-web/

RUN pip install --no-cache-dir -r zsignal-web/requirements.txt

WORKDIR /app/zsignal-web
ENV ZSIGNAL_WEB_HOST=0.0.0.0
ENV ZSIGNAL_WEB_DATA_DIR=/data
EXPOSE 5055

CMD ["python", "app.py"]
