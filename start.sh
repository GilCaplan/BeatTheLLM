#!/usr/bin/env bash
# ============================================================
# Jailbreak the AI — Start Script (macOS / Linux)
# ============================================================
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$ROOT/.venv"

# ── Colors ──────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[JAILBREAK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Python venv setup ───────────────────────────────────────
log "Setting up Python virtual environment..."
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV" || err "Failed to create venv. Is python3 installed?"
fi

log "Installing Python dependencies..."
"$VENV/bin/pip" install --upgrade pip --quiet
"$VENV/bin/pip" install -r "$BACKEND/requirements.txt" --quiet

# ── Node.js setup ───────────────────────────────────────────
log "Installing Node.js dependencies..."
if ! command -v node &>/dev/null; then
  err "Node.js not found. Please install Node.js (https://nodejs.org) and re-run."
fi

cd "$FRONTEND"
if [ ! -d "node_modules" ]; then
  npm install --legacy-peer-deps
fi
cd "$ROOT"

# ── .env setup ──────────────────────────────────────────────
if [ ! -f "$BACKEND/.env" ]; then
  log "Creating default .env in backend/..."
  cat > "$BACKEND/.env" <<EOF
# Set MOCK_LLM=1 to skip loading model weights (instant testing)
MOCK_LLM=0

# Change to override the default TinyLlama model
LLM_MODEL=TinyLlama/TinyLlama-1.1B-Chat-v1.0
EOF
fi

# ── Run tests ───────────────────────────────────────────────
log "Running backend tests (MOCK_LLM=1)..."
MOCK_LLM=1 "$VENV/bin/pytest" "$BACKEND/test_game.py" -v --tb=short
log "All tests passed!"

# ── Launch servers ──────────────────────────────────────────
log "Starting servers..."
echo ""
echo -e "  ${GREEN}Backend${NC}  → http://localhost:8000"
echo -e "  ${GREEN}Frontend${NC} → http://localhost:5173"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo ""

# Kill background processes on exit
cleanup() {
  log "Shutting down..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start backend
cd "$BACKEND"
"$VENV/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Small delay so backend has time to start
sleep 1

# Start frontend
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# Wait for both
wait "$BACKEND_PID" "$FRONTEND_PID"
