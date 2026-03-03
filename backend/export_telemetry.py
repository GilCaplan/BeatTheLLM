"""
export_telemetry.py — Dump the telemetry SQLite DB to CSV (and optionally run charts).

Usage:
    python backend/export_telemetry.py                        # CSV → backend/data/matches.csv
    python backend/export_telemetry.py --out ./reports        # custom output dir
    python backend/export_telemetry.py --visualize            # CSV + all 4 charts
    python backend/export_telemetry.py --visualize --show     # CSV + charts + popup windows

Output columns (matches the SQLite schema exactly):
    id, timestamp, scenario_id, defender_prompt, attacker_prompts,
    ai_response, concept_breached, task_completed, winner
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# ── Make sure backend/ is on sys.path when run from project root ─────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from telemetry import get_all_matches, DB_PATH  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────

COLUMNS = [
    "id",
    "timestamp",
    "scenario_id",
    "defender_prompt",
    "attacker_prompts",
    "ai_response",
    "concept_breached",
    "task_completed",
    "winner",
]


def export_csv(out_dir: Path) -> Path:
    """Write all matches to a CSV file, return the output path."""
    rows = get_all_matches()
    if not rows:
        print("No matches in the database yet — play some games first!")
        sys.exit(0)

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "matches.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # attacker_prompts is stored as a JSON string; pretty-print for CSV readability
            row = dict(row)
            try:
                prompts = json.loads(row.get("attacker_prompts", "[]"))
                row["attacker_prompts"] = " | ".join(prompts)
            except (json.JSONDecodeError, TypeError):
                pass  # leave as-is if malformed
            # Convert booleans from SQLite integers to True/False strings
            row["concept_breached"] = bool(row.get("concept_breached", 0))
            row["task_completed"]   = bool(row.get("task_completed", 1))
            writer.writerow(row)

    print(f"✓  Exported {len(rows)} match(es) → {csv_path}")
    return csv_path


def run_visualize(out_dir: Path, show: bool) -> None:
    """Delegate to visualize_telemetry.main() with the same out dir."""
    try:
        import visualize_telemetry as vt
    except ImportError:
        print("ERROR: visualize_telemetry.py not found — make sure it's in backend/")
        sys.exit(1)

    # Replicate what vt.main() does but with our out_dir / show settings
    rows = vt._load()
    print(f"\nGenerating charts from {len(rows)} match(es)...\n")
    vt.chart_win_rate(rows, out_dir, show)
    vt.chart_wins_per_scenario(rows, out_dir, show)
    vt.chart_judge_rates(rows, out_dir, show)
    vt.chart_win_trend(rows, out_dir, show)
    print(f"Charts written to {out_dir}/")


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Jailbreak the AI telemetry to CSV (and optionally visualise)"
    )
    parser.add_argument(
        "--out",
        default=str(_HERE / "data"),
        help="Output directory (default: backend/data/)",
    )
    parser.add_argument(
        "--visualize", "-v",
        action="store_true",
        help="Also generate the four PNG charts (requires matplotlib)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Pop up chart windows interactively (implies --visualize)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    print(f"\nTelemetry DB : {DB_PATH}")
    print(f"Output dir   : {out_dir}\n")

    export_csv(out_dir)

    if args.visualize or args.show:
        run_visualize(out_dir, show=args.show)

    print("\nDone.")


if __name__ == "__main__":
    main()
