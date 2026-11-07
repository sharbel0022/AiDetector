FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json vite.config.js ./
COPY sites ./sites
RUN npm ci && npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TEXTLAB_ENV=production TEXTLAB_STATE_DB=/state/textlab.sqlite3
WORKDIR /app
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt && useradd --uid 10001 --create-home textlab && mkdir /state && chown textlab:textlab /state
COPY backend ./backend
COPY ai ./ai
COPY --from=frontend /build/dist ./dist
USER textlab
EXPOSE 8767
VOLUME ["/state"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8767/api/health',timeout=3)"
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8767", "--workers", "2", "--no-access-log", "--no-proxy-headers"]
