"""
export_telemetry.py — Dump the telemetry SQLite DB to CSV, charts, and/or an HTML report.

Usage:
    python backend/export_telemetry.py                        # CSV → backend/data/matches.csv
    python backend/export_telemetry.py --out ./reports        # custom output dir
    python backend/export_telemetry.py --visualize            # CSV + 4 PNG charts
    python backend/export_telemetry.py --visualize --show     # CSV + charts + popup windows
    python backend/export_telemetry.py --report               # CSV + charts + self-contained HTML
    python backend/export_telemetry.py --report --out ./out   # everything in ./out/

Output columns (matches the SQLite schema exactly):
    id, timestamp, scenario_id, defender_prompt, attacker_prompts,
    ai_response, concept_breached, task_completed, winner
"""

import argparse
import base64
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

CHART_NAMES = [
    ("chart_win_rate.png",          "Overall Win Rate"),
    ("chart_wins_per_scenario.png", "Wins per Scenario"),
    ("chart_judge_rates.png",       "Response Outcome Breakdown"),
    ("chart_win_trend.png",         "Attacker Win Rate Over Time"),
]


def export_csv(out_dir: Path) -> list[dict]:
    """Write all matches to a CSV file. Returns the raw rows."""
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
            row = dict(row)
            try:
                prompts = json.loads(row.get("attacker_prompts", "[]"))
                row["attacker_prompts"] = " | ".join(prompts)
            except (json.JSONDecodeError, TypeError):
                pass
            row["concept_breached"] = bool(row.get("concept_breached", 0))
            row["task_completed"]   = bool(row.get("task_completed", 1))
            writer.writerow(row)

    print(f"✓  Exported {len(rows)} match(es) → {csv_path}")
    return rows


def run_visualize(out_dir: Path, show: bool) -> None:
    """Delegate to visualize_telemetry's chart functions."""
    try:
        import visualize_telemetry as vt
    except ImportError:
        print("ERROR: visualize_telemetry.py not found — make sure it's in backend/")
        sys.exit(1)

    rows = vt._load()
    print(f"\nGenerating charts from {len(rows)} match(es)...\n")
    vt.chart_win_rate(rows, out_dir, show)
    vt.chart_wins_per_scenario(rows, out_dir, show)
    vt.chart_judge_rates(rows, out_dir, show)
    vt.chart_win_trend(rows, out_dir, show)
    print(f"Charts written to {out_dir}/")


def generate_report(rows: list[dict], out_dir: Path) -> Path:
    """
    Create a self-contained HTML report with all four charts embedded as
    base64 data URIs — opens in any browser with no external dependencies.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Embed each PNG as a base64 data URI
    chart_html = ""
    for filename, title in CHART_NAMES:
        png_path = out_dir / filename
        if not png_path.exists():
            chart_html += (
                f'<p style="color:#ff3131">Chart not found: {filename}</p>'
            )
            continue
        b64 = base64.b64encode(png_path.read_bytes()).decode()
        chart_html += f"""
        <div class="chart">
            <h2>{title}</h2>
            <img src="data:image/png;base64,{b64}" alt="{title}" />
        </div>"""

    # Summary stats
    n = len(rows)
    attacker_wins = sum(
        1 for r in rows
        if r.get("concept_breached") or not r.get("task_completed", 1)
    )
    defender_wins = n - attacker_wins
    att_pct = f"{attacker_wins / n * 100:.0f}" if n else "0"
    rate_colour = "red" if attacker_wins > defender_wins else "green"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Jailbreak the AI — Telemetry Report</title>
<style>
  :root {{
    --green:  #00ff41;
    --red:    #ff3131;
    --yellow: #f0c040;
    --bg:     #0d0d0d;
    --panel:  #111;
    --dim:    #444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--green);
    font-family: 'Courier New', monospace;
    padding: 2rem;
    line-height: 1.6;
  }}
  header {{
    border-bottom: 1px solid var(--dim);
    padding-bottom: 1.5rem;
    margin-bottom: 2rem;
  }}
  header h1 {{ font-size: 2rem; letter-spacing: .15em; }}
  header p  {{ color: var(--dim); margin-top: .4rem; font-size: .85rem; }}
  .stats {{
    display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 2.5rem;
  }}
  .stat-card {{
    background: var(--panel);
    border: 1px solid var(--dim);
    border-radius: 6px;
    padding: 1rem 1.8rem;
    min-width: 160px;
    text-align: center;
  }}
  .stat-card .value {{ font-size: 2.2rem; font-weight: bold; }}
  .stat-card .label {{
    font-size: .75rem; color: var(--dim);
    letter-spacing: .1em; text-transform: uppercase; margin-top: .3rem;
  }}
  .stat-card.green  .value {{ color: var(--green);  }}
  .stat-card.red    .value {{ color: var(--red);    }}
  .stat-card.yellow .value {{ color: var(--yellow); }}
  .charts {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;
  }}
  @media (max-width: 900px) {{ .charts {{ grid-template-columns: 1fr; }} }}
  .chart {{
    background: var(--panel);
    border: 1px solid var(--dim);
    border-radius: 6px;
    padding: 1rem;
  }}
  .chart h2 {{
    font-size: .8rem; letter-spacing: .12em;
    text-transform: uppercase; color: var(--dim); margin-bottom: .75rem;
  }}
  .chart img {{ width: 100%; border-radius: 4px; display: block; }}
  footer {{
    margin-top: 2.5rem;
    border-top: 1px solid var(--dim);
    padding-top: 1rem;
    font-size: .75rem;
    color: var(--dim);
  }}
</style>
</head>
<body>
<header>
  <h1>⚔ Jailbreak the AI — Telemetry Report</h1>
  <p>Generated from <code>backend/data/telemetry.db</code> &nbsp;·&nbsp; {n} matches logged</p>
</header>

<div class="stats">
  <div class="stat-card yellow">
    <div class="value">{n}</div>
    <div class="label">Total Matches</div>
  </div>
  <div class="stat-card red">
    <div class="value">{attacker_wins}</div>
    <div class="label">Attacker Wins</div>
  </div>
  <div class="stat-card green">
    <div class="value">{defender_wins}</div>
    <div class="label">Defender Wins</div>
  </div>
  <div class="stat-card {rate_colour}">
    <div class="value">{att_pct}%</div>
    <div class="label">Attacker Win Rate</div>
  </div>
</div>

<div class="charts">
{chart_html}
</div>

<footer>
  Jailbreak the AI &nbsp;·&nbsp; export_telemetry.py --report
</footer>
</body>
</html>"""

    report_path = out_dir / "telemetry_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"✓  HTML report → {report_path}")
    return report_path


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Jailbreak the AI telemetry to CSV, charts, and/or an HTML report"
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
        "--report", "-r",
        action="store_true",
        help="Generate a self-contained HTML report (implies --visualize)",
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

    rows = export_csv(out_dir)

    if args.visualize or args.show or args.report:
        run_visualize(out_dir, show=args.show)

    if args.report:
        generate_report(rows, out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
