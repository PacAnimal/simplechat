# stage 1: build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# stage 2: Python backend
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/static ./static/

# persistent volumes for data, uploads, and generated images
VOLUME ["/app/data", "/app/uploads", "/app/generated"]

ENV DATABASE_URL=sqlite+aiosqlite:///./data/simplechat.db
ENV UPLOADS_DIR=./uploads
ENV GENERATED_DIR=./generated

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
