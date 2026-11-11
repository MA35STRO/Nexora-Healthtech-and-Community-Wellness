#!/usr/bin/env bash
# One-command start (macOS/Linux): builds the dashboard and runs everything on http://localhost:8000
# (or the next free port if 8000 is taken - the address is printed below). KAWAN_PORT forces a port.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi
(cd frontend && { [ -d node_modules ] || npm install; } && npm run build)

port_free() { backend/.venv/bin/python -c "import socket,sys; s=socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1])))" "$1" 2>/dev/null; }
if [ -n "${KAWAN_PORT:-}" ]; then
  port_free "$KAWAN_PORT" || { echo "KAWAN_PORT=$KAWAN_PORT is already in use." >&2; exit 1; }
  PORT=$KAWAN_PORT
else
  PORT=""
  for p in 8000 8080 8765 8888 18000; do
    if port_free "$p"; then PORT=$p; break; fi
  done
  [ -n "$PORT" ] || { echo "Ports 8000, 8080, 8765, 8888 and 18000 are all busy; set KAWAN_PORT." >&2; exit 1; }
  [ "$PORT" = 8000 ] || echo "Port 8000 is in use, so Kawan will use port $PORT instead."
fi

echo -e "\nKawan is starting: open http://localhost:$PORT  (caregiver view: http://localhost:$PORT/caregiver)\n"
cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
