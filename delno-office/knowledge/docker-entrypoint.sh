#!/bin/sh
set -e

echo "==> delno-knowledge: init-db"
python -m brain_platform init-db

echo "==> delno-knowledge: seed-demo (idempotent)"
python -m brain_platform seed-demo

exec uvicorn main:app --host 0.0.0.0 --port 8021
