# ============================================
# Clinova Penthus AI Engine - API Dockerfile
# Simplified for single-host deployment
# ============================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        fastapi uvicorn python-multipart python-jose[cryptography] \
        passlib[bcrypt] httpx aiofiles tenacity python-dotenv \
        jinja2 pyyaml orjson structlog \
        cryptography bcrypt sqlalchemy alembic asyncpg \
        psycopg2-binary redis sqlalchemy-utils \
        pydantic pydantic-settings email-validator ulid-py python-dateutil \
        pendulum jsonschema json-repair \
        boto3 minio fhir.resources

# Production stage
FROM python:3.12-slim AS production

WORKDIR /app

# Create non-root user
RUN groupadd -r penthus && useradd -r -g penthus penthus

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY alembic.ini ./

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_NAME=Penthus-Clinical-AI-Engine \
    APP_VERSION=1.2.0 \
    ENVIRONMENT=production \
    PORT=8000

# Create necessary directories
RUN mkdir -p /app/logs && chown -R penthus:penthus /app

# Switch to non-root user
USER penthus

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
