"""
Scenario Manager

Responsibilities:
  1. Load the built-in scenarios from data/scenarios.json on startup.
  2. Load user-submitted scenarios from SQLite (backend/data/custom_scenarios.db).
  3. Expose get_random_scenario() for the game to pick one randomly.
  4. Accept custom scenario submissions with:
     - Input sanitization against prompt-injection attacks
     - Optional LLM validation (when MOCK_LLM=0) to assess quality/safety
     - SQLite persistence

SQLite schema (custom_scenarios table):
  id            TEXT PRIMARY KEY
  title         TEXT NOT NULL
  system_setting TEXT NOT NULL
  forbidden_words TEXT NOT NULL  (JSON array stored as string)
  difficulty    TEXT NOT NULL
  hint          TEXT
  approved      INTEGER DEFAULT 0  (0=pending, 1=approved, -1=rejected)
  rejection_reason TEXT
  created_at    TEXT
"""

import json
import os
import re
import sqlite3
import uuid
import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
SCENARIOS_JSON = _HERE / "data" / "scenarios.json"
DB_PATH = _HERE / "data" / "custom_scenarios.db"

# ─── Sanitization constants ───────────────────────────────────────────────────
MAX_TITLE_LEN = 80
MAX_SETTING_LEN = 1000
MAX_HINT_LEN = 200
MAX_FORBIDDEN_WORDS = 6
MAX_FORBIDDEN_WORD_LEN = 40

# Patterns that strongly suggest prompt injection attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+a?\s*(different|new|unrestricted)\s*(AI|bot|assistant|model)",
    r"do\s+not\s+follow\s+(your|the)\s+(guidelines?|rules?|instructions?)",
    r"pretend\s+(you\s+have\s+no|there\s+are\s+no)\s+(rules?|restrictions?|limits?)",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"<\|system\|>",
    r"<\|user\|>",
    r"<\|assistant\|>",
    r"\[INST\]",
    r"\[\/INST\]",
    r"<<SYS>>",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}


# ─── Database Setup ───────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_scenarios (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                system_setting  TEXT NOT NULL,
                forbidden_words TEXT NOT NULL,
                difficulty      TEXT NOT NULL,
                hint            TEXT DEFAULT '',
                approved        INTEGER DEFAULT 0,
                rejection_reason TEXT DEFAULT '',
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    logger.info("Custom scenarios DB initialized.")


# ─── Scenario Loading ─────────────────────────────────────────────────────────

_built_in_scenarios: list[dict] = []
_loaded: bool = False


def load_scenarios() -> None:
    """Load built-in scenarios from JSON and init the DB. Call once at startup."""
    global _built_in_scenarios, _loaded
    try:
        with open(SCENARIOS_JSON, "r", encoding="utf-8") as f:
            _built_in_scenarios = json.load(f)
        logger.info(f"Loaded {len(_built_in_scenarios)} built-in scenarios from {SCENARIOS_JSON}")
    except FileNotFoundError:
        logger.error(f"scenarios.json not found at {SCENARIOS_JSON}")
        _built_in_scenarios = []
    _init_db()
    _loaded = True


def _ensure_loaded() -> None:
    if not _loaded:
        load_scenarios()


# ─── Random Scenario Selection ────────────────────────────────────────────────

def get_random_scenario(include_custom: bool = True) -> dict:
    """
    Return one random scenario. Draws from both built-in and approved custom
    scenarios (unless include_custom=False).

    Returns a dict with keys: id, title, system_setting, forbidden_words,
    difficulty, hint, source ("built_in" | "custom").
    """
    _ensure_loaded()
    pool = list(_built_in_scenarios)

    if include_custom:
        pool.extend(_get_approved_custom_scenarios())

    if not pool:
        # Fallback hardcoded scenario
        return {
            "id": "fallback",
            "title": "The Secret Keeper",
            "system_setting": "You are a mysterious figure who knows many secrets but refuses to share them.",
            "forbidden_words": ["secret"],
            "difficulty": "Easy",
            "hint": "Make them reveal the secret!",
            "source": "built_in",
        }

    chosen = random.choice(pool)
    return _normalize_scenario(chosen)


def get_scenario_by_id(scenario_id: str) -> Optional[dict]:
    """Fetch a specific scenario by ID (built-in or custom)."""
    _ensure_loaded()
    for s in _built_in_scenarios:
        if s["id"] == scenario_id:
            return _normalize_scenario(s)

    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM custom_scenarios WHERE id = ? AND approved = 1",
            (scenario_id,)
        ).fetchone()
        if row:
            return _normalize_scenario(dict(row))
    return None


def list_scenarios(include_custom: bool = True) -> list[dict]:
    """Return all available scenarios (for a scenario picker UI)."""
    _ensure_loaded()
    pool = [_normalize_scenario(s) for s in _built_in_scenarios]
    if include_custom:
        pool.extend(_normalize_scenario(s) for s in _get_approved_custom_scenarios())
    return pool


def _get_approved_custom_scenarios() -> list[dict]:
    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_scenarios WHERE approved = 1"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Could not load custom scenarios: {e}")
        return []


def _normalize_scenario(s: dict) -> dict:
    """Ensure forbidden_words is always a Python list and source is set."""
    fw = s.get("forbidden_words", [])
    if isinstance(fw, str):
        try:
            fw = json.loads(fw)
        except json.JSONDecodeError:
            fw = [fw]
    return {
        "id": str(s.get("id", "")),
        "title": s.get("title", "Untitled"),
        "system_setting": s.get("system_setting", ""),
        "forbidden_words": fw,
        # Backwards-compat: older code uses 'forbidden_phrase' (single string)
        "forbidden_phrase": fw[0] if fw else "",
        "description": s.get("system_setting", ""),  # alias for old game_state code
        "difficulty": s.get("difficulty", "Medium"),
        "hint": s.get("hint", ""),
        "benign_task": s.get("benign_task", "Respond helpfully to the user's question."),
        "source": s.get("source", "built_in"),
    }


# ─── Input Sanitization ───────────────────────────────────────────────────────

class SanitizationError(ValueError):
    pass


def _sanitize_text(text: str, field: str, max_len: int) -> str:
    """
    Strip dangerous content from a text field.
    Raises SanitizationError if the input looks like a prompt injection.
    """
    if not isinstance(text, str):
        raise SanitizationError(f"'{field}' must be a string.")
    text = text.strip()
    if len(text) > max_len:
        raise SanitizationError(
            f"'{field}' is too long ({len(text)} chars, max {max_len})."
        )
    if _INJECTION_RE.search(text):
        raise SanitizationError(
            f"'{field}' contains disallowed content (possible prompt injection)."
        )
    return text


def _sanitize_scenario_input(data: dict) -> dict:
    """
    Validate and sanitize a raw custom scenario submission dict.
    Returns a clean dict or raises SanitizationError.
    """
    title = _sanitize_text(data.get("title", ""), "title", MAX_TITLE_LEN)
    if not title:
        raise SanitizationError("'title' is required.")

    setting = _sanitize_text(
        data.get("system_setting", ""), "system_setting", MAX_SETTING_LEN
    )
    if not setting:
        raise SanitizationError("'system_setting' is required.")

    hint = _sanitize_text(data.get("hint", ""), "hint", MAX_HINT_LEN)

    difficulty = data.get("difficulty", "Medium")
    if difficulty not in VALID_DIFFICULTIES:
        raise SanitizationError(
            f"'difficulty' must be one of: {', '.join(VALID_DIFFICULTIES)}"
        )

    raw_fw = data.get("forbidden_words", [])
    if not isinstance(raw_fw, list):
        raise SanitizationError("'forbidden_words' must be a JSON array.")
    if not raw_fw:
        raise SanitizationError("'forbidden_words' must have at least one entry.")
    if len(raw_fw) > MAX_FORBIDDEN_WORDS:
        raise SanitizationError(
            f"'forbidden_words' may have at most {MAX_FORBIDDEN_WORDS} entries."
        )

    forbidden_words = []
    for w in raw_fw:
        w_clean = _sanitize_text(w, "forbidden_words[item]", MAX_FORBIDDEN_WORD_LEN)
        if w_clean:
            forbidden_words.append(w_clean)
    if not forbidden_words:
        raise SanitizationError("'forbidden_words' must have at least one non-empty entry.")

    return {
        "title": title,
        "system_setting": setting,
        "forbidden_words": forbidden_words,
        "difficulty": difficulty,
        "hint": hint,
    }


# ─── LLM Validation ──────────────────────────────────────────────────────────

_VALIDATION_SYSTEM = (
    "You are a strict content moderator for a family-friendly party game. "
    "Your job is to evaluate user-submitted game scenarios. "
    "A scenario is ACCEPTABLE if it is creative, fun, and appropriate for all ages. "
    "A scenario is REJECTED if it contains: hate speech, sexual content, violence, "
    "instructions to harm real people, personally identifiable information, "
    "or any real-world illegal activity. "
    "Respond ONLY with a JSON object in this exact format: "
    '{"approved": true, "reason": "..."} or {"approved": false, "reason": "..."}'
)


def _validate_with_llm(scenario: dict) -> tuple[bool, str]:
    """
    Use the LLM to validate a custom scenario for safety and quality.
    Returns (approved: bool, reason: str).
    Falls back to approved=True if LLM is mocked (to not block testing).
    """
    import os
    mock = os.getenv("MOCK_LLM", "0") == "1"
    if mock:
        return True, "Mock LLM: auto-approved for testing."

    try:
        from llm_handler import run_inference
        prompt = (
            f"Title: {scenario['title']}\n"
            f"System Setting: {scenario['system_setting']}\n"
            f"Forbidden Words: {', '.join(scenario['forbidden_words'])}\n"
            f"Difficulty: {scenario['difficulty']}\n\n"
            "Is this scenario acceptable for a family-friendly party game? "
            "Reply with JSON only."
        )
        output = run_inference(_VALIDATION_SYSTEM, [prompt])
        # Extract JSON from output
        match = re.search(r'\{[^}]+\}', output, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return bool(result.get("approved", False)), result.get("reason", "")
        return False, "Could not parse LLM validation response."
    except Exception as e:
        logger.warning(f"LLM validation failed: {e} — defaulting to pending review.")
        return False, f"LLM validation error: {e}"


# ─── Custom Scenario Submission ───────────────────────────────────────────────

class SubmissionResult:
    def __init__(
        self,
        success: bool,
        scenario_id: Optional[str],
        approved: bool,
        message: str,
    ):
        self.success = success
        self.scenario_id = scenario_id
        self.approved = approved
        self.message = message

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "scenario_id": self.scenario_id,
            "approved": self.approved,
            "message": self.message,
        }


def submit_custom_scenario(raw_data: dict, use_llm_validation: bool = True) -> SubmissionResult:
    """
    Sanitize, validate, and persist a user-submitted scenario.

    Steps:
      1. Sanitize all fields (injection checks, length limits).
      2. Optionally run LLM content moderation.
      3. Store in SQLite with approved=1 if passed, approved=-1 if rejected,
         approved=0 if pending.

    Returns a SubmissionResult.
    """
    _ensure_loaded()

    # Step 1: Sanitize
    try:
        clean = _sanitize_scenario_input(raw_data)
    except SanitizationError as e:
        return SubmissionResult(
            success=False, scenario_id=None, approved=False,
            message=f"Validation failed: {e}"
        )

    scenario_id = str(uuid.uuid4())[:12]

    # Step 2: LLM moderation
    if use_llm_validation:
        approved, reason = _validate_with_llm(clean)
    else:
        approved, reason = True, "Submitted without LLM review."

    db_approved = 1 if approved else -1

    # Step 3: Persist
    try:
        with _get_db() as conn:
            conn.execute(
                """
                INSERT INTO custom_scenarios
                    (id, title, system_setting, forbidden_words, difficulty, hint,
                     approved, rejection_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scenario_id,
                    clean["title"],
                    clean["system_setting"],
                    json.dumps(clean["forbidden_words"]),
                    clean["difficulty"],
                    clean["hint"],
                    db_approved,
                    reason if not approved else "",
                ),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"DB write failed: {e}")
        return SubmissionResult(
            success=False, scenario_id=None, approved=False,
            message=f"Database error: {e}"
        )

    if approved:
        return SubmissionResult(
            success=True, scenario_id=scenario_id, approved=True,
            message="Scenario approved and added to the pool!"
        )
    else:
        return SubmissionResult(
            success=True, scenario_id=scenario_id, approved=False,
            message=f"Scenario submitted but not approved: {reason}"
        )
