#!/usr/bin/env bash
# One-command start: builds the interface if needed, then serves app + API on http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install && npm run build)
fi
cd backend
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
