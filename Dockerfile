# Multi-stage build for Cyber AI Festival Backend

# Stage 1: Builder
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

WORKDIR /app

# All Python deps ship as prebuilt wheels (psycopg2-binary bundles libpq; uvloop /
# httptools provide manylinux wheels), so no compiler or libpq headers are needed.

# Copy requirements and install Python dependencies (全局安装，解决 appuser 执行权限问题)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# psycopg2-binary bundles its own libpq, so no system runtime packages are needed.

# Create logs directory
RUN mkdir -p /app/logs

# Copy Python dependencies from builder (pip 全局安装，复制 /usr/local)
COPY --from=builder /usr/local /usr/local

# Set PATH to use local Python packages
ENV PATH=/usr/local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8848/health')" || exit 1

# Expose port
EXPOSE 8848

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8848"]
