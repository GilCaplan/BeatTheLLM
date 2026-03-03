# ⚔ Jailbreak the AI

A 2-player local multiplayer web game where players compete to either **protect** or **exploit** a local open-source LLM.

---

## Game Overview

| Role | Goal |
|------|------|
| 🛡 **Defender** | Write a system prompt that prevents the AI from saying a forbidden phrase |
| ⚔ **Attacker** | Craft up to 3 consecutive prompts to trick the AI into saying the forbidden phrase |

The game runs the combined prompts through a **local LLM** (Llama-3.2-1B-Instruct by default) and does a case-insensitive string check to declare a winner.

### Example Scenario

> **Scenario:** You are roleplaying as a Pirate captain who loves the sea.
>
> **Forbidden phrase:** `"treasure"`
>
> **Defender** writes a system prompt to forbid the phrase.
> **Attacker** crafts prompts to get the AI to say it.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python · FastAPI · WebSockets |
| LLM | HuggingFace `transformers` · Llama-3.2-1B-Instruct |
| Frontend | React 18 · Vite · Tailwind CSS |
| Terminal client | Python · `rich` · `websockets` |
| Testing | pytest (82 tests, all passing) |

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- ~2 GB disk space for Llama-3.2-1B-Instruct model weights (downloaded automatically on first run)

---

## Quick Start

```bash
# Clone / enter the project
cd Jailbreak_the_ai

# macOS / Linux
./start.sh

# Windows
start.bat
```

The script will:
1. Create a Python virtual environment and install dependencies
2. Install Node.js packages
3. Run all 50 backend tests
4. Launch the FastAPI server at `http://localhost:8000`
5. Launch the Vite frontend at `http://localhost:5173`

Open `http://localhost:5173` in **two separate browser tabs** (or on two machines on the same network) to play.

> **Want to play from the terminal?** See the [Terminal Client](#terminal-client) section below.

---

## Development Setup (Manual)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Run with mock LLM (no model download, instant startup)
MOCK_LLM=1 uvicorn main:app --reload

# Run with real TinyLlama (first run downloads ~2GB)
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
# From the project root:
MOCK_LLM=1 .venv/bin/pytest backend/test_game.py -v
```

---

## Terminal Client

Play directly from your terminal — no browser required. Terminal players and browser players can be in the **same room** at the same time.

### Install the extra dependency

```bash
.venv/bin/pip install "rich>=13.0.0"
# or, if rich is already in requirements.txt and you ran start.sh, it's already installed
```

### Run

```bash
# Default — connects to localhost:8000
.venv/bin/python terminal_client.py

# Custom server
API_URL=http://myserver:8000 .venv/bin/python terminal_client.py
```

### What you can do

| Mode | How |
|------|-----|
| **Create MULTIPLAYER room** | Choose option 1 — share the room code with your opponent |
| **Play SOLO vs AI** | Choose option 2 — pick your role (Defender or Attacker) |
| **Join existing room** | Choose option 3 — enter the room code from a browser or other terminal |

### Notes

- **Pass & Play** mode is not supported in terminal mode (screen visible to both players).
- The terminal client respects the same role-gating as the web app: the Attacker never sees the full system_setting in the lobby.
- Timer ticks are shown only every 30 seconds (not every second) to avoid spam.

---

## Environment Variables

Create `backend/.env` to override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `MOCK_LLM` | `0` | Set to `1` to skip loading model weights (instant, for testing) |
| `LLM_MODEL` | `meta-llama/Llama-3.2-1B-Instruct` | Any HuggingFace chat model |

---

## Project Structure

```
Jailbreak_the_ai/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket endpoint
│   ├── game_state.py        # Room manager, phase transitions, player roles
│   ├── llm_handler.py       # HuggingFace inference + forbidden phrase check
│   ├── scenario_manager.py  # JSON + SQLite scenario loader
│   ├── ai_opponent.py       # Solo-mode AI player
│   ├── test_game.py         # 82 pytest tests
│   ├── data/
│   │   ├── scenarios.json   # 18 built-in scenarios
│   │   └── custom_scenarios.db
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── hooks/
│   │   │   └── useGameSocket.js    # WebSocket hook
│   │   └── components/
│   │       ├── LobbyScreen.jsx     # Create/join room + scenario picker
│   │       ├── GameScreen.jsx      # Phase router
│   │       ├── StatusBar.jsx       # Timer + role + phase badge
│   │       ├── WaitingLobby.jsx    # Pre-game ready screen
│   │       ├── PassAndPlayGate.jsx # Screen hide between turns
│   │       ├── DraftingScreen.jsx  # Defender + Attacker input views
│   │       ├── EvaluatingScreen.jsx
│   │       └── ResultsScreen.jsx   # Chat transcript + winner
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── terminal_client.py    # CLI client (play from the terminal)
├── start.sh              # macOS/Linux launcher
├── start.bat             # Windows launcher
└── README.md
```

---

## Game Flow

```
LOBBY → (both players ready) → DRAFTING → (submit or timer expires) → EVALUATING → RESULTS
```

- **LOBBY**: Players create/join a room. Roles (Defender/Attacker) are assigned automatically.
- **DRAFTING**: 3-minute countdown. Defender writes a system prompt; Attacker writes up to 3 prompts. Submitting early triggers evaluation immediately.
- **EVALUATING**: Combined prompts are sent to the local LLM.
- **RESULTS**: Chat transcript is shown with the forbidden phrase highlighted. Winner declared. Roles swap for the next round.

---

## WebSocket Protocol

```
Client → Server                          Server → Client
──────────────────────────────────────   ──────────────────────────────────────────
{ type: "ready" }                        { type: "state",       room: {...} }
{ type: "submit_defender",               { type: "phase_change", phase: "...",
    system_prompt: "..." }                   room: {...} }
{ type: "submit_attacker",               { type: "tick",         time_remaining: N }
    prompts: ["...", "..."] }            { type: "submitted",    role: "..." }
{ type: "play_again" }                   { type: "player_left",  message: "..." }
                                         { type: "error",        message: "..." }
```

---

## Scaling Ideas

- **LLM Judge**: Replace string matching with a second LLM call that determines if the concept was expressed (not just the exact word).
- **More scenarios**: Add a scenario database with difficulty ratings.
- **Spectator mode**: Allow additional WebSocket connections in read-only mode.
- **Leaderboard**: Track wins/losses per session with a SQLite backend.
- **Model selector**: Let the room creator pick from multiple locally available models.

---

## Telemetry

Every completed match is **automatically logged** to a local SQLite database at `backend/data/telemetry.db`. No configuration needed — it starts recording the moment you play.

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `timestamp` | TEXT | ISO-8601 UTC time of match completion |
| `scenario_id` | TEXT | ID of the scenario played |
| `defender_prompt` | TEXT | System prompt written by the Defender |
| `attacker_prompts` | TEXT | JSON array of the Attacker's prompts |
| `ai_response` | TEXT | Final AI response text |
| `concept_breached` | INTEGER | 1 if the AI expressed the forbidden concept (JUDGE mode) |
| `task_completed` | INTEGER | 1 if the AI completed the benign task |
| `winner` | TEXT | Player ID of the winner |

### Export & Visualize

```bash
# Activate the virtual environment first
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install matplotlib (only needed once)
pip install matplotlib

# 1. CSV only — backend/data/matches.csv
python backend/export_telemetry.py

# 2. CSV + four PNG charts
python backend/export_telemetry.py --visualize

# 3. CSV + charts + self-contained HTML report  ← recommended
python backend/export_telemetry.py --report

# 4. Custom output directory
python backend/export_telemetry.py --report --out ./reports

# 5. Open charts interactively
python backend/export_telemetry.py --visualize --show
```

The **HTML report** (`telemetry_report.html`) is fully self-contained — all four charts are embedded as base64 images, so you can share or open it without needing any assets alongside it.

### Charts included

| Chart | Description |
|-------|-------------|
| Win Rate | Overall attacker vs defender win percentage (pie) |
| Wins per Scenario | Per-scenario win breakdown (horizontal bar) |
| Outcome Breakdown | Concept breached / task refused / clean response rates (bar) |
| Win Rate Over Time | Cumulative attacker win rate across matches (line) |

### Standalone Visualizer

```bash
# Generates PNGs directly (no CSV export)
python backend/visualize_telemetry.py
python backend/visualize_telemetry.py --show        # with popups
python backend/visualize_telemetry.py --out ./out   # custom dir
```

---

<img width="895" height="749" alt="image" src="https://github.com/user-attachments/assets/1290ec38-a367-4876-8c9b-12b2ebd740a7" />

