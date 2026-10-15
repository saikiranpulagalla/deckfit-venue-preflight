FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp/venue-home \
    PATH=/opt/venue-venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv libreoffice-impress fonts-dejavu-core \
    && python3 -m venv /opt/venue-venv \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /tmp/venue-home venueagent

# Ubuntu USN-8868-1 (2026-10-05): fail the image build if apt resolves
# a LibreOffice package older than the security-fixed Ubuntu 24.04 build.
RUN dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libreoffice-impress)" ge '4:24.2.7-0ubuntu0.24.04.7' \
    && dpkg-query -W -f='Verified LibreOffice Ubuntu package: ${Package} ${Version}\n' libreoffice-impress

WORKDIR /app
COPY backend /app/backend
COPY reference /app/reference
COPY demo /app/demo
COPY frontend/static /app/frontend/static
COPY Dockerfile railway.json /app/
RUN /opt/venue-venv/bin/pip install --no-cache-dir -e '/app/backend[agent]' \
    && chown -R venueagent:venueagent /tmp/venue-home

WORKDIR /app/backend
USER venueagent
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=15s --start-period=15s --retries=3 \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health/deep-readiness',timeout=12)); raise SystemExit(0 if d.get('status')=='ready' else 1)"

CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
