"""Shared figure style: one look for all notebook and slide figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from src.config import FIGURES_DIR

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"

# Circuit types (colour-blind safe pair, always with legend or labels)
CIRCUIT_TYPE_COLORS = {"race": "#6250d6", "street": "#eda100"}

# Sequential: one hue (blue), light -> dark, for magnitudes such as rates
SEQUENTIAL = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf",
                 "#184f95", "#0d366b"])
# Diverging: blue <-> neutral grey <-> red, for signed values such as correlations
DIVERGING = LinearSegmentedColormap.from_list(
    "div_blue_red", ["#184f95", "#6da7ec", "#f0efec", "#ee8e8d", "#b52d2d"])


def set_style() -> None:
    """Apply the project style to matplotlib (thin marks, recessive grid)."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "figure.dpi": 110,
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.labelsize": 10,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_SECONDARY,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID,
        "grid.linewidth": 0.8, "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY, "text.color": TEXT_PRIMARY,
        "lines.linewidth": 2, "lines.markersize": 6, "legend.frameon": False,
    })


def wilson_ci(successes, n, z: float = 1.96):
    """95 % Wilson confidence interval of a proportion (vectorised).

    Args:
        successes: Number of successes.
        n: Number of trials.
        z: Normal quantile (1.96 for 95 %).

    Returns:
        (low, high) as arrays of proportions.
    """
    import numpy as np

    successes, n = np.asarray(successes, float), np.asarray(n, float)
    p = successes / n
    centre = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return centre - half, centre + half


def add_source(fig: plt.Figure, text: str) -> None:
    """Add a source note at the bottom left of a figure."""
    fig.text(0.01, 0.005, f"Source: {text}", fontsize=8, color=TEXT_SECONDARY,
             ha="left", va="bottom")


def save(fig: plt.Figure, name: str) -> Path:
    """Save a figure as 300 dpi PNG to reports/figures/ and return the path."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / f"{name}.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    return path
