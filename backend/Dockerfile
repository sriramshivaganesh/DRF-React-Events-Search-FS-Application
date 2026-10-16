FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data

WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt

# Unprivileged user; /data is created owned by it so a fresh named volume inherits the ownership.
RUN useradd --system --uid 10001 --no-create-home app && mkdir -p /data/uploads && chown -R app /data
COPY --chown=app . .
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/', timeout=4).status == 200 else 1)"

# Long timeout: importing a large archive happens inside the upload request.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "900", "--access-logfile", "-"]
