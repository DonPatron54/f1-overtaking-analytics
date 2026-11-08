"""Figures for the concept presentation, sized for a 1920 x 1080 slide.

Each figure is drawn at its slot size on the slide (1 inch = 100 slide px) and
saved at 2x, so every label is at least 24 px on the slide. Run from the
repository root after notebook 04:

    python -m src.concept_figures
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

from src.config import (ERA_COLORS, FIGURES_DIR, GAP_MAX, LOGS_DIR,
                        PROCESSED_DIR, RAW_DIR, era_for_season)
from src.viz import GRID, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, wilson_ci

OUT_DIR = FIGURES_DIR / "slides"
SLIDE_DPI = 100   # layout resolution: 1 inch = 100 slide pixels
SAVE_DPI = 200    # saved at 2x for sharp projection
ERA_SHORT = {"E1": "E1 2018–21", "E2": "E2 2022–25", "E3": "E3 2026"}
INTER_DIR = Path("/usr/share/fonts/opentype/inter")


def set_slide_style() -> None:
    """Project style with slide-sized type (18 pt = 25 px at 100 dpi)."""
    for name in ("Regular", "Medium", "SemiBold", "Bold"):
        path = INTER_DIR / f"Inter-{name}.otf"
        if path.exists():
            font_manager.fontManager.addfont(str(path))
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "DejaVu Sans"],
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "figure.dpi": SLIDE_DPI,
        "font.size": 18, "axes.labelsize": 18, "xtick.labelsize": 18,
        "ytick.labelsize": 18, "legend.fontsize": 18,
        "axes.titlesize": 18, "axes.titleweight": "semibold",
        "axes.titlelocation": "left", "axes.titlepad": 12,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_SECONDARY,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID,
        "grid.linewidth": 1.0, "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY, "text.color": TEXT_PRIMARY,
        "lines.linewidth": 3, "lines.markersize": 9, "legend.frameon": False,
        "xtick.major.size": 0, "ytick.major.size": 0,
        "xtick.major.pad": 8, "ytick.major.pad": 8,
    })


def load_pairs() -> pd.DataFrame:
    """Pair-laps with season and era."""
    pairs = pd.read_parquet(PROCESSED_DIR / "pairs.parquet")
    pairs["season"] = pairs["race_id"] // 100
    pairs["era"] = pairs["season"].map(era_for_season)
    return pairs


def slot(width_px: int, height_px: int) -> plt.Figure:
    """A figure of exactly the slot size on the slide."""
    return plt.figure(figsize=(width_px / SLIDE_DPI, height_px / SLIDE_DPI))


def save(fig: plt.Figure, name: str) -> Path:
    """Save at 2x without trimming, so the slot size stays exact."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=SAVE_DPI)
    plt.close(fig)
    return path


def gap_by_era(pairs: pd.DataFrame, n_bins: int = 8) -> pd.DataFrame:
    """Overtake rate per 0.25 s gap class and era, with 95 % Wilson CI."""
    width = GAP_MAX / n_bins
    bins = np.minimum((pairs["gap_s"] // width).astype(int), n_bins - 1)
    table = (pairs.assign(bin=bins)
             .groupby(["era", "bin"])["overtake"].agg(["sum", "size"])
             .reset_index())
    table["gap_mid_s"] = (table["bin"] + 0.5) * width
    table["rate"] = table["sum"] / table["size"]
    table["ci_low"], table["ci_high"] = wilson_ci(table["sum"], table["size"])
    return table


def fig_gap_era(pairs: pd.DataFrame, size=(980, 480)) -> pd.DataFrame:
    """Overtake rate by gap at lap start, one line per era."""
    table = gap_by_era(pairs)
    fig = slot(*size)
    ax = fig.add_axes((0.10, 0.17, 0.86, 0.80))
    for era, g in table.groupby("era"):
        color = ERA_COLORS[era]
        ax.fill_between(g["gap_mid_s"], 100 * g["ci_low"], 100 * g["ci_high"],
                        color=color, alpha=0.15, linewidth=0)
        ax.plot(g["gap_mid_s"], 100 * g["rate"], marker="o", color=color,
                label=ERA_SHORT[era])
    ax.set_xlim(0, GAP_MAX)
    ax.set_ylim(0, None)
    ax.set_xticks(np.arange(0, GAP_MAX + 0.01, 0.5))
    ax.set_xlabel("Gap to the car ahead at lap start (s)")
    ax.set_ylabel("Overtake rate (%)")
    ax.legend(loc="upper right", handlelength=1.4)
    save(fig, "concept_gap_era")
    return table


def fig_closer_not_more(pairs: pd.DataFrame, size=(620, 480)) -> pd.DataFrame:
    """Two panels: share of close situations and overtake rate per era."""
    by_era = pairs.groupby("era").agg(
        n=("overtake", "size"), overtakes=("overtake", "sum"),
        close=("gap_s", lambda s: (s < 0.5).mean()))
    by_era["rate"] = by_era["overtakes"] / by_era["n"]
    by_era["ci_low"], by_era["ci_high"] = wilson_ci(by_era["overtakes"], by_era["n"])

    fig = slot(*size)
    panels = [
        ("Pair-laps starting < 0.5 s behind (%)", 100 * by_era["close"], None),
        ("Overtake rate (%)", 100 * by_era["rate"],
         (100 * by_era["ci_low"], 100 * by_era["ci_high"])),
    ]
    eras = list(by_era.index)
    y = np.arange(len(eras))[::-1]
    for i, (title, values, ci) in enumerate(panels):
        ax = fig.add_axes((0.17, 0.585 - i * 0.50, 0.70, 0.29))
        ax.barh(y, values, color=[ERA_COLORS[e] for e in eras], height=0.68)
        if ci is not None:
            ax.errorbar(values.to_numpy(), y,
                        xerr=[(values - ci[0]).to_numpy(), (ci[1] - values).to_numpy()],
                        fmt="none", ecolor=TEXT_PRIMARY, elinewidth=1.5, capsize=4)
        ends = values if ci is None else ci[1]
        for yi, v, end in zip(y, values, ends):
            ax.text(end + 0.6, yi, f"{v:.1f}", va="center", ha="left",
                    color=TEXT_PRIMARY, fontsize=18)
        ax.set_yticks(y, eras)
        ax.set_xlim(0, 20)
        ax.set_xticks([])
        ax.grid(False)
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_color(GRID)
        ax.set_title(title, color=TEXT_PRIMARY, x=-0.22, ha="left")
    save(fig, "concept_closer_not_more")
    return by_era


def fig_waterfall(size=(900, 600)) -> pd.DataFrame:
    """From candidate pair-laps to analysed pair-laps (floating bars)."""
    log = pd.read_csv(LOGS_DIR / "pairs_waterfall.csv")
    short = {
        "candidate": "Candidate pairs",
        "no lap-n data": "No lap data",
        "pit stop": "Pit stop A or B",
        "lap n neutralised": "SC / VSC / red flag",
        "restart lap": "Restart lap",
        "gap > 2.0 s": "Gap > 2.0 s",
    }
    rows = []
    for _, r in log.iterrows():
        label = next((v for k, v in short.items() if r["rule"].startswith(k)), None)
        if label is None or (r["removed"] == 0 and label != "Candidate pairs"):
            continue
        if label == "Candidate pairs":
            rows.append((label, 0, r["remaining"], "start"))
        else:
            rows.append((label, r["remaining"], r["remaining"] + r["removed"], "removed"))
    rows.append(("Analysed pair-laps", 0, log["remaining"].iloc[-1], "end"))
    table = pd.DataFrame(rows, columns=["step", "left", "right", "kind"])

    colors = {"start": "#8a8984", "removed": "#e8b7b2", "end": TEXT_PRIMARY}
    fig = slot(*size)
    ax = fig.add_axes((0.30, 0.15, 0.66, 0.83))
    y = np.arange(len(table))[::-1]
    for yi, (_, r) in zip(y, table.iterrows()):
        ax.barh(yi, r["right"] - r["left"], left=r["left"], height=0.62,
                color=colors[r["kind"]])
        value = r["right"] - r["left"]
        if r["kind"] == "removed":   # label left of the floating bar
            ax.text(r["left"] - 3000, yi, f"−{value:,.0f}", va="center",
                    ha="right", fontsize=18, color=TEXT_PRIMARY)
        else:                        # label inside the bar end
            ax.text(r["right"] - 3000, yi, f"{value:,.0f}", va="center",
                    ha="right", fontsize=18, color=SURFACE)
    ax.set_yticks(y, table["step"])
    ax.set_axisbelow(True)
    ax.set_xlim(0, 205_000)
    ax.set_xticks(range(0, 200_001, 50_000))
    ax.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k" if v else "0"))
    ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Pair-laps")
    save(fig, "concept_waterfall")
    return table


def circuit_svg(geojson_id: str = "mc-1929", box=(500, 640),
                track: str = "#f3f2ee", asphalt: str = "#2c2f37") -> Path:
    """Track map of one circuit from the GeoJSON layouts as a small SVG.

    The layout keeps its true shape (equirectangular projection) and is scaled
    to fit into ``box`` (width, height in px). It is drawn as a wide dark
    asphalt band with a light track line on top, like a broadcast track map.
    """
    layouts = json.loads((RAW_DIR / "geo" / "f1-circuits.geojson").read_text())
    feature = next(f for f in layouts["features"]
                   if f["properties"]["id"] == geojson_id)
    lon, lat = np.array(feature["geometry"]["coordinates"]).T
    x = (lon - lon.min()) * math.cos(math.radians(lat.mean()))
    y = lat.max() - lat
    pad = 20
    scale = min((box[0] - 2 * pad) / x.max(), (box[1] - 2 * pad) / y.max())
    width = int(round(x.max() * scale + 2 * pad))
    height = int(round(y.max() * scale + 2 * pad))
    pts = " ".join(f"{pad + a * scale:.1f},{pad + b * scale:.1f}"
                   for a, b in zip(x, y))
    line = ('<polygon points="{pts}" fill="none" stroke="{color}" '
            'stroke-width="{width}" stroke-linejoin="round"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
           f'height="{height}" viewBox="0 0 {width} {height}">'
           + line.format(pts=pts, color=asphalt, width=30)
           + line.format(pts=pts, color=track, width=10)
           + '</svg>')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"circuit_{geojson_id}.svg"
    path.write_text(svg)
    return path


def main() -> None:
    set_slide_style()
    pairs = load_pairs()
    gap = fig_gap_era(pairs)
    by_era = fig_closer_not_more(pairs)
    steps = fig_waterfall()
    svg = circuit_svg()
    pd.set_option("display.width", 140)
    print(gap.pivot(index="gap_mid_s", columns="era", values="rate").mul(100).round(1))
    print(by_era.assign(close=by_era["close"] * 100, rate=by_era["rate"] * 100).round(2))
    print(steps)
    print(f"pairs {len(pairs):,}, overtakes {pairs['overtake'].sum():,}, "
          f"races {pairs['race_id'].nunique()}, svg {svg.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
