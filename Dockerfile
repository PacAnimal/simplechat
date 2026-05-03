# stage 1: build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
RUN npm install -g npm@11.13.0
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# stage 2: Python backend
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY --from=frontend-build /app/static ./static/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/data"]

ENV DATABASE_URL=sqlite+aiosqlite:////data/data/simplechat.db
ENV UPLOADS_DIR=/data/uploads
ENV GENERATED_DIR=/data/generated
ENV LOCAL_PORT=8080

EXPOSE ${LOCAL_PORT}

ENTRYPOINT ["/entrypoint.sh"]
