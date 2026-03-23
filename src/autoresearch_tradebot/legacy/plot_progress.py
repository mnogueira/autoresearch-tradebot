"""
Generate a Karpathy-style autoresearch progress chart.

Reads experiment results from research/legacy/results.tsv and produces a PNG chart showing
the progression of experiments with kept improvements highlighted.

Usage:
    python -m autoresearch_tradebot.legacy.plot_progress --input research/legacy/results.tsv --output artifacts/legacy/progress.png

Module usage:
    from autoresearch_tradebot.legacy.plot_progress import generate_progress_chart
    path = generate_progress_chart()
"""

import argparse
import csv
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from ..common.paths import LEGACY_PROGRESS_PATH, LEGACY_RESULTS_PATH, ensure_parent


def generate_progress_chart(
    input_path: str | Path = LEGACY_RESULTS_PATH,
    output_path: str | Path = LEGACY_PROGRESS_PATH,
) -> str:
    """Generate a Karpathy-style progress chart and save it as PNG.

    Args:
        input_path: Path to the tab-separated results file.
        output_path: Where to write the PNG chart.

    Returns:
        The absolute path to the saved chart.
    """
    # ------------------------------------------------------------------
    # 1. Read data
    # ------------------------------------------------------------------
    input_path = Path(input_path)
    output_path = Path(output_path)

    rows = []
    with input_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError(f"No data rows found in {input_path}")

    # Parse into lists
    experiment_nums = []
    sharpe_values = []
    statuses = []
    descriptions = []

    for i, row in enumerate(rows, start=1):
        experiment_nums.append(i)
        sharpe_values.append(float(row["test_sharpe"]))
        statuses.append(row["status"].strip().lower())
        descriptions.append(row["description"].strip())

    # Separate kept vs discarded
    kept_x = []
    kept_y = []
    kept_desc = []
    discarded_x = []
    discarded_y = []

    for x, y, s, d in zip(experiment_nums, sharpe_values, statuses, descriptions):
        if s == "improved":
            kept_x.append(x)
            kept_y.append(y)
            kept_desc.append(d)
        else:
            discarded_x.append(x)
            discarded_y.append(y)

    total_experiments = len(experiment_nums)
    total_kept = len(kept_x)

    # ------------------------------------------------------------------
    # 2. Build chart  (dark theme, Karpathy style)
    # ------------------------------------------------------------------
    bg_color = "#1a1a2e"
    grid_color = "#2a2a4a"
    text_color = "#c8c8d8"
    kept_color = "#4ade80"       # green-400
    discard_color = "#6b7280"    # gray-500
    line_color = "#22c55e"       # green-500

    dpi = 120
    fig, ax = plt.subplots(figsize=(2400 / dpi, 1200 / dpi), dpi=dpi)
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    # Grid
    ax.grid(True, color=grid_color, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    # Discarded dots (draw first so kept dots sit on top)
    if discarded_x:
        ax.scatter(
            discarded_x, discarded_y,
            c=discard_color, s=50, alpha=0.5,
            edgecolors="none", zorder=2,
            label="Discarded",
        )

    # Kept dots + connecting line
    if kept_x:
        ax.plot(
            kept_x, kept_y,
            color=line_color, linewidth=2, alpha=0.7, zorder=3,
            label="Running best",
        )
        ax.scatter(
            kept_x, kept_y,
            c=kept_color, s=80, edgecolors="white", linewidths=0.7,
            zorder=4, label="Kept",
        )

        # Labels on kept experiments
        for x, y, desc in zip(kept_x, kept_y, kept_desc):
            short = textwrap.shorten(desc, width=38, placeholder="...")
            ax.annotate(
                short,
                xy=(x, y),
                xytext=(6, 10),
                textcoords="offset points",
                fontsize=6.5,
                color=kept_color,
                alpha=0.9,
                ha="left",
                va="bottom",
                rotation=30,
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor=bg_color,
                    edgecolor=kept_color,
                    alpha=0.6,
                    linewidth=0.5,
                ),
            )

    # Axes labels & title
    ax.set_xlabel("Experiment #", color=text_color, fontsize=13, labelpad=10)
    ax.set_ylabel("Test Sharpe Ratio", color=text_color, fontsize=13, labelpad=10)
    ax.set_title(
        f"Autoresearch Progress: {total_experiments} Experiments, "
        f"{total_kept} Kept Improvements",
        color="white", fontsize=16, fontweight="bold", pad=18,
    )

    # Tick styling
    ax.tick_params(colors=text_color, labelsize=10)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    for spine in ax.spines.values():
        spine.set_color(grid_color)

    # Legend
    legend = ax.legend(
        loc="upper left", framealpha=0.3, fontsize=10,
        facecolor=bg_color, edgecolor=grid_color,
    )
    for t in legend.get_texts():
        t.set_color(text_color)

    # X-axis starts at 1
    if experiment_nums:
        ax.set_xlim(0.5, max(experiment_nums) + 0.5)

    plt.tight_layout()
    ensure_parent(output_path)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), dpi=dpi)
    plt.close(fig)

    abs_path = str(output_path.resolve())
    print(f"Chart saved to {abs_path}")
    return abs_path


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a Karpathy-style autoresearch progress chart."
    )
    parser.add_argument(
        "--input", default=str(LEGACY_RESULTS_PATH),
        help=f"Path to the TSV results file (default: {LEGACY_RESULTS_PATH})",
    )
    parser.add_argument(
        "--output", default=str(LEGACY_PROGRESS_PATH),
        help=f"Output PNG path (default: {LEGACY_PROGRESS_PATH})",
    )
    args = parser.parse_args()
    generate_progress_chart(input_path=args.input, output_path=args.output)
