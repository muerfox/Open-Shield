FROM python:3.12-slim

WORKDIR /app

# All dependencies are vendored as wheels (see vendor/wheels/VERSIONS.md),
# so this never reaches PyPI. pip itself ships inside the base image, and
# the healthcheck below uses Python's stdlib instead of curl, so this build
# needs no apt-get/network access at all beyond pulling the base image.
COPY requirements.txt .
COPY vendor/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app ./app

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/login', timeout=3).status < 500 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
