FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm test -- --run --no-file-parallelism --maxWorkers=1 && npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANNOTATE_TOOL_FRONTEND_DIST=/app/frontend/dist \
    ANNOTATE_TOOL_DATA_DIR=/data \
    PORT=8000
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY annotate_tool/ ./annotate_tool/
COPY app.py ./
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN mkdir -p /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/v1/health', timeout=4)"
CMD ["sh", "-c", "uvicorn annotate_tool.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
