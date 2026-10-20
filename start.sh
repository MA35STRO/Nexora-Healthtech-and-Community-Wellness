#!/usr/bin/env bash
# One-command start (macOS/Linux): builds the dashboard and runs everything on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi
(cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
echo -e "\nBAYMAX is starting: open http://localhost:8000  (caregiver view: /caregiver)\n"
cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
