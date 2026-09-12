FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-websockets \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py db.py totp.py docker.py ./

ENV CONTROL_DB=/data/control.db \
    SNAP_DIR=/snapshots \
    DOCKER_SOCK=/var/run/docker.sock \
    PORT=8080 \
    COMPUTER_IMAGE=yourdaas/computer:local \
    HELPER_IMAGE=yourdaas/computer:local \
    NET_NAME=your-daas_default \
    IDLE_MINUTES=30 \
    SESSION_HOURS=24 \
    SWEEP_SEC=60

EXPOSE 8080
CMD ["python3", "/app/server.py"]
