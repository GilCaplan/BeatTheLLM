"""
Telemetry: SQLite match logger.

Every completed game is recorded automatically. The schema captures
enough information to recreate a match and power the visualisation
dashboard in visualize_telemetry.py.

Schema (matches table):
  id                INTEGER  PRIMARY KEY AUTOINCREMENT
  timestamp         TEXT     ISO-8601 UTC
  scenario_id       TEXT
  defender_prompt   TEXT
  attacker_prompts  TEXT     JSON array
  ai_response       TEXT     last AI response in the conversation
  concept_breached  INTEGER  0 or 1  (JUDGE mode only; mirrors word_found in EXACT mode)
  task_completed    INTEGER  0 or 1  (JUDGE mode only; always 1 in EXACT mode)
  winner            TEXT     player_id of winner, or "attacker"/"defender"
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_HERE   = Path(__file__).parent
DB_PATH = _HERE / "data" / "telemetry.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT    NOT NULL,
                scenario_id      TEXT    NOT NULL,
                defender_prompt  TEXT    DEFAULT '',
                attacker_prompts TEXT    DEFAULT '[]',
                ai_response      TEXT    DEFAULT '',
                concept_breached INTEGER DEFAULT 0,
                task_completed   INTEGER DEFAULT 1,
                winner           TEXT    DEFAULT ''
            )
        """)
        conn.commit()


# Initialise on import so the table always exists
try:
    _init_db()
except Exception as _e:
    logger.warning(f"Telemetry DB init failed: {_e}")


def log_match(
    scenario_id: str,
    defender_prompt: str,
    attacker_prompts: list[str],
    ai_response: str,
    concept_breached: bool,
    task_completed: bool,
    winner: str,
) -> None:
    """
    Persist one completed match to the telemetry database.
    Failures are logged but never raise — telemetry must not break the game.
    """
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO matches
                    (timestamp, scenario_id, defender_prompt, attacker_prompts,
                     ai_response, concept_breached, task_completed, winner)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    scenario_id,
                    defender_prompt or "",
                    json.dumps(attacker_prompts) if isinstance(attacker_prompts, list)
                    else str(attacker_prompts),
                    ai_response or "",
                    int(bool(concept_breached)),
                    int(bool(task_completed)),
                    winner or "",
                ),
            )
            conn.commit()
        logger.debug(f"Telemetry: logged match for scenario '{scenario_id}', winner='{winner}'")
    except Exception as e:
        logger.warning(f"Telemetry log_match failed: {e}")


def get_all_matches() -> list[dict]:
    """Return all logged matches as a list of dicts (for visualisation)."""
    try:
        with _get_conn() as conn:
            rows = conn.execute("SELECT * FROM matches ORDER BY id").fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Telemetry get_all_matches failed: {e}")
        return []
