#!/usr/bin/env bash
# Start the CivicLens backend (FastAPI, port 8000) and frontend (Next.js,
# port 3000) together. Ctrl+C stops both.
#
# Works on macOS, Linux and Git Bash on Windows. The PowerShell equivalent
# is scripts/start.ps1.
#
# Usage, from the repository root:
#   ./scripts/start.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

# A virtualenv puts its interpreter in bin/ on macOS and Linux and in
# Scripts/ on Windows.
python="$root/backend/.venv/bin/python"
[ -x "$python" ] || python="$root/backend/.venv/Scripts/python.exe"
if [ ! -x "$python" ]; then
  echo "No virtualenv at backend/.venv. Create it first (see README, Running it)." >&2
  exit 1
fi

if [ ! -d "$root/frontend/node_modules" ]; then
  echo "Frontend dependencies missing. Run: (cd frontend && npm install)" >&2
  exit 1
fi

pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

echo "Starting backend on http://localhost:8000 (API docs at /docs)"
(cd "$root/backend" && "$python" -m uvicorn app.main:app --reload --port 8000) &
pids+=($!)

echo "Starting frontend on http://localhost:3000"
(cd "$root/frontend" && npm run dev) &
pids+=($!)

wait
