FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[api]"

# Copy application code
COPY src/ src/
COPY app_platform/ app_platform/
COPY config/ config/
COPY prompts/ prompts/
COPY deploy/__init__.py deploy/__init__.py
COPY deploy/db/ deploy/db/
COPY scripts/ scripts/
COPY deploy/entrypoint.sh deploy/entrypoint.sh
RUN chmod +x deploy/entrypoint.sh

# Run as non-root user
RUN useradd -r appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["deploy/entrypoint.sh"]
