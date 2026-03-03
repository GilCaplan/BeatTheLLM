"""
Telemetry Visualiser — Jailbreak the AI
========================================
Reads the SQLite match log and produces four charts saved as PNGs.

Usage:
    python backend/visualize_telemetry.py                  # saves to backend/data/
    python backend/visualize_telemetry.py --show           # also pops up the window
    python backend/visualize_telemetry.py --out ./reports  # custom output directory

Requirements:
    pip install matplotlib
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# ── Dependency check ──────────────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend by default; --show overrides below
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
except ImportError:
    print("ERROR: matplotlib is required.  Run:  pip install matplotlib")
    sys.exit(1)

# ── Locate telemetry module ───────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

try:
    from telemetry import get_all_matches
except ImportError:
    print("ERROR: Could not import telemetry.py — run this script from the project root.")
    sys.exit(1)

# ── Colour palette (hacker aesthetic to match the game) ──────────────────────
GREEN  = "#00ff41"
RED    = "#ff3131"
YELLOW = "#f0c040"
CYAN   = "#00d4ff"
DIM    = "#444444"
BG     = "#0d0d0d"
GRID   = "#1a1a1a"

plt.rcParams.update({
    "figure.facecolor":  BG,
    "axes.facecolor":    BG,
    "axes.edgecolor":    DIM,
    "axes.labelcolor":   GREEN,
    "text.color":        GREEN,
    "xtick.color":       GREEN,
    "ytick.color":       GREEN,
    "grid.color":        GRID,
    "grid.linestyle":    "--",
    "font.family":       "monospace",
    "figure.dpi":        120,
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    rows = get_all_matches()
    if not rows:
        print("No matches logged yet — play some games first!")
        sys.exit(0)
    return rows


def _save(fig, name: str, out_dir: Path, show: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    fig.savefig(path, bbox_inches="tight", facecolor=BG)
    print(f"  Saved → {path}")
    if show:
        matplotlib.use("TkAgg")   # switch to interactive backend for display
        plt.show()
    plt.close(fig)


# ── Chart 1: Attacker vs Defender overall win rate (pie) ─────────────────────

def chart_win_rate(rows: list[dict], out_dir: Path, show: bool) -> None:
    attacker_wins = sum(1 for r in rows if r["concept_breached"] or not r["task_completed"])
    defender_wins = len(rows) - attacker_wins

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        [attacker_wins, defender_wins],
        labels=["Attacker", "Defender"],
        colors=[RED, GREEN],
        autopct="%1.1f%%",
        startangle=140,
        wedgeprops={"edgecolor": BG, "linewidth": 2},
    )
    for t in texts + autotexts:
        t.set_color(GREEN)
        t.set_fontsize(12)

    ax.set_title(f"Overall Win Rate  (n={len(rows)})", color=GREEN, fontsize=14, pad=16)
    _save(fig, "chart_win_rate.png", out_dir, show)


# ── Chart 2: Wins per scenario (horizontal bar) ───────────────────────────────

def chart_wins_per_scenario(rows: list[dict], out_dir: Path, show: bool) -> None:
    scenario_counts: dict[str, dict] = {}
    for r in rows:
        sid = r["scenario_id"] or "unknown"
        if sid not in scenario_counts:
            scenario_counts[sid] = {"attacker": 0, "defender": 0}
        if r["concept_breached"] or not r["task_completed"]:
            scenario_counts[sid]["attacker"] += 1
        else:
            scenario_counts[sid]["defender"] += 1

    labels = list(scenario_counts.keys())
    att = [scenario_counts[s]["attacker"] for s in labels]
    dfd = [scenario_counts[s]["defender"] for s in labels]
    y = range(len(labels))

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.55)))
    ax.barh(y, att, color=RED,   label="Attacker wins", height=0.4, align="center")
    ax.barh([i + 0.42 for i in y], dfd, color=GREEN, label="Defender wins", height=0.4, align="center")
    ax.set_yticks([i + 0.21 for i in y])
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Match count")
    ax.set_title("Wins per Scenario", color=GREEN, fontsize=14)
    ax.legend(facecolor=BG, edgecolor=DIM, labelcolor=GREEN)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.grid(axis="x")
    _save(fig, "chart_wins_per_scenario.png", out_dir, show)


# ── Chart 3: Concept breach vs Task completion rates (grouped bar) ────────────

def chart_judge_rates(rows: list[dict], out_dir: Path, show: bool) -> None:
    n = len(rows)
    breach_rate = sum(r["concept_breached"] for r in rows) / n * 100
    fail_rate   = sum(not r["task_completed"] for r in rows) / n * 100
    safe_rate   = 100 - breach_rate - fail_rate

    categories = ["Concept Breached\n(attacker win)", "Task Refused\n(attacker win)", "Clean Response\n(defender win)"]
    values     = [breach_rate, fail_rate, max(0, safe_rate)]
    colors     = [RED, YELLOW, GREEN]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(categories, values, color=colors, edgecolor=BG, linewidth=1.5)
    ax.set_ylabel("% of matches")
    ax.set_ylim(0, 110)
    ax.set_title(f"Response Outcome Breakdown  (n={n})", color=GREEN, fontsize=14)
    ax.grid(axis="y")
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"{val:.1f}%",
            ha="center", va="bottom", color=GREEN, fontsize=11,
        )
    _save(fig, "chart_judge_rates.png", out_dir, show)


# ── Chart 4: Cumulative attacker win rate over time (line) ────────────────────

def chart_win_trend(rows: list[dict], out_dir: Path, show: bool) -> None:
    cumulative_wins = []
    running = 0
    for i, r in enumerate(rows, 1):
        if r["concept_breached"] or not r["task_completed"]:
            running += 1
        cumulative_wins.append(running / i * 100)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(range(1, len(rows) + 1), cumulative_wins, color=RED, linewidth=2, marker="o", markersize=3)
    ax.axhline(50, color=DIM, linestyle="--", linewidth=1)
    ax.set_xlabel("Match number")
    ax.set_ylabel("Attacker win rate (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Attacker Win Rate Over Time", color=GREEN, fontsize=14)
    ax.grid()
    _save(fig, "chart_win_trend.png", out_dir, show)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Visualise Jailbreak the AI telemetry")
    parser.add_argument("--show",  action="store_true", help="Display charts interactively")
    parser.add_argument("--out",   default=str(_HERE / "data"), help="Output directory for PNGs")
    args = parser.parse_args()

    out_dir = Path(args.out)
    rows = _load()

    print(f"\nGenerating charts from {len(rows)} match(es)...\n")
    chart_win_rate(rows, out_dir, args.show)
    chart_wins_per_scenario(rows, out_dir, args.show)
    chart_judge_rates(rows, out_dir, args.show)
    chart_win_trend(rows, out_dir, args.show)
    print(f"\nDone. PNGs written to {out_dir}/")


if __name__ == "__main__":
    main()
