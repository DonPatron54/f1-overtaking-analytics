"""Shared figure style: one look for all notebook and slide figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

from src.config import FIGURES_DIR

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"


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
