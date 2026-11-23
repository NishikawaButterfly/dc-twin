# syntax=docker/dockerfile:1.9
FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY examples ./examples
COPY web ./web
RUN python -m pip install .

FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DC_TWIN_HOST=0.0.0.0 \
    DC_TWIN_PORT=8000

RUN groupadd --gid 10001 dc-twin \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/dc-twin dc-twin

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).read()"]

ENTRYPOINT ["python", "-m", "dc_twin.server"]
