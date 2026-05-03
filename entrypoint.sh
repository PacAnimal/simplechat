#!/bin/sh
set -e

mkdir -p /data/data /data/uploads /data/generated
chown appuser:appuser /data /data/data /data/uploads /data/generated
chmod 755 /data /data/data /data/uploads /data/generated

exec gosu appuser uvicorn backend.main:app --host 0.0.0.0 --port "${LOCAL_PORT:-8080}"
