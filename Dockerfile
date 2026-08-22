# Multi-stage build for MediNote
# Stage 1: Backend - Python/FastAPI
FROM python:3.11-slim as backend-builder

WORKDIR /app/backend

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Frontend - static browser assets
FROM node:20-alpine as frontend-builder

WORKDIR /app/frontend
COPY frontend/ .
RUN npm install

# Stage 3: Runtime - FastAPI serves the API and frontend from one public port
FROM python:3.11-slim as runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin
COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend /app/frontend

EXPOSE 8000

# Render provides PORT dynamically; local Docker falls back to 8000.
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
