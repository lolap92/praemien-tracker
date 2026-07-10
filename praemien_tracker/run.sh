#!/bin/sh
set -e

cd /app
exec python3 -m uvicorn praemien_tracker.main:app --host 0.0.0.0 --port "${PORT:-8000}"
