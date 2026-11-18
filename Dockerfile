# syntax=docker/dockerfile:1
# Multi-stage build: dependencies in a builder, slim non-root runtime. Image bundles homematicip (GPL-3.0-or-later):
# licence files are shipped in /licenses (see THIRD_PARTY_NOTICES.md and docs/sbom/components.md).
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runner
LABEL org.opencontainers.image.title="homematic-exporter" \
      org.opencontainers.image.description="Prometheus exporter for Homematic IP heating" \
      org.opencontainers.image.licenses="MIT AND GPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/zbitmanis/homematic_exporter"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATE_DIR=/state
RUN useradd --system --uid 10001 --no-create-home exporter \
 && mkdir -p /state && chown exporter /state && chmod 700 /state
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY src/ /app/src/
COPY LICENSE THIRD_PARTY_NOTICES.md LICENSES/ /licenses/
USER exporter
VOLUME /state
EXPOSE 9100
# Ignored by podman for OCI-format builds; the Quadlet unit defines the real health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9100/health', timeout=3).status == 200 else 1)"]
CMD ["uvicorn", "homematic_exporter.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "9100"]
