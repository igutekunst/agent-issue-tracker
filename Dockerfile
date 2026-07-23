# --- Stage 1: build the web UI ---------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
# vite writes the built SPA into ../src/issue_tracker/static
RUN mkdir -p src/issue_tracker && cd frontend && npm run build

# --- Stage 2: python runtime ------------------------------------------------
FROM python:3.11-slim
WORKDIR /app

# Install the package (with its built frontend).
COPY pyproject.toml README.md ./
COPY src ./src
# Overwrite any committed static with the freshly built bundle.
COPY --from=frontend /app/src/issue_tracker/static ./src/issue_tracker/static
RUN pip install --no-cache-dir .

# SQLite database + secret + bootstrap token live here (mount a volume).
ENV ISSUE_TRACKER_DB=/data/tracker.db
VOLUME /data
EXPOSE 8000

CMD ["uvicorn", "issue_tracker.app:app", "--host", "0.0.0.0", "--port", "8000"]
