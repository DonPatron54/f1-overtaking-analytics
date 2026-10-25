"""Central project constants and paths.

All paths are resolved relative to the repository root, so notebooks and
scripts behave the same regardless of the current working directory.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"  # FastF1 cache, not committed
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
SQL_DIR = PROJECT_ROOT / "sql"

# Analysis parameters
SEASONS = range(2018, 2027)
GAP_MAX = 2.0  # max gap (s) at lap start for a pair to be included
RANDOM_STATE = 42

# Regulation eras
ERAS = {
    "E1": range(2018, 2022),  # classic aero
    "E2": range(2022, 2026),  # ground effect
    "E3": range(2026, 2027),  # active aero, override mode
}

# Consistent era colours for all figures
ERA_COLORS = {"E1": "#1f77b4", "E2": "#d62728", "E3": "#2ca02c"}


def era_for_season(season: int) -> str:
    """Return the regulation era label ('E1', 'E2', 'E3') for a season.

    Args:
        season: Championship year, e.g. 2023.

    Returns:
        Era label.

    Raises:
        ValueError: If the season lies outside the study period.
    """
    for era, years in ERAS.items():
        if season in years:
            return era
    raise ValueError(f"Season {season} is outside the study period {SEASONS}")
