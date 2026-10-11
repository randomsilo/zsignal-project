# Build from the repo root: `docker compose build zsignal-receiver` (see ../docker-compose.yml).
# Must run on the Orange Pi's arm64 -- python:3-slim is published multi-arch, so
# building this natively on the Pi itself produces an arm64 image with no buildx/
# cross-compilation needed.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY zsignal/ ./zsignal/
COPY zsignal-receiver/ ./zsignal-receiver/

RUN pip install --no-cache-dir pyserial

WORKDIR /app/zsignal-receiver
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
