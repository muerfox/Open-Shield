FROM python:3.12-slim

WORKDIR /app

# All Python dependencies are vendored as wheels (see
# vendor/wheels/VERSIONS.md), so pip never reaches PyPI. openssl is the one
# apt-get step needed (to generate the self-signed TLS cert below) — see
# README's "Offline builds" section for why OS packages aren't vendored.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY vendor/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Self-signed cert so the panel serves HTTPS by default — plain HTTP on an
# admin login page (even on localhost/LAN) means credentials and the
# session cookie travel in cleartext. 100-year validity since there's no
# real CA chain to renew against anyway; regenerated fresh (unique key)
# on every image build, never committed to the repo.
RUN mkdir -p /etc/ssl/panel \
    && openssl req -new -newkey rsa:2048 -days 36500 -nodes -x509 \
        -subj '/CN=open-shield-panel' \
        -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' \
        -keyout /etc/ssl/panel/panel.key \
        -out /etc/ssl/panel/panel.crt

COPY app ./app

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD python -c "import ssl,urllib.request,sys; ctx=ssl._create_unverified_context(); sys.exit(0 if urllib.request.urlopen('https://localhost:8080/login', timeout=3, context=ctx).status < 500 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--ssl-keyfile", "/etc/ssl/panel/panel.key", "--ssl-certfile", "/etc/ssl/panel/panel.crt"]
