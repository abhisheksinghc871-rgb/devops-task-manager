# Small, currently supported Python base image.
FROM python:3.12-slim

# No .pyc files, unbuffered logs (so `docker logs` shows output immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Unprivileged user to run the app.
RUN groupadd --system app \
 && useradd --system --gid app --no-create-home --shell /usr/sbin/nologin app

# Install dependencies first so Docker caches this layer until requirements change.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy only what the app needs at runtime.
COPY app.py .
COPY templates/ templates/
COPY static/ static/

USER app

EXPOSE 8000

# python:slim has no curl, so use Python for the health probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# One worker on purpose: tasks live in process memory, so several workers
# would each hold a different task list. Threads give concurrency instead.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
