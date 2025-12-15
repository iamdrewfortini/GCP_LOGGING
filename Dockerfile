# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python API
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies if needed (e.g. for some python packages)
# RUN apt-get update && apt-get install -y gcc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY config/ config/

# Copy built frontend from builder stage
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# Environment variables should be injected at runtime, but we can set defaults
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Command to run the application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
