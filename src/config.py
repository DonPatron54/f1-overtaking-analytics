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

LOGS_DIR = PROJECT_ROOT / "reports" / "logs"  # collection and integration logs

# Analysis parameters
SEASONS = range(2018, 2027)
PILOT_SEASONS = (2021, 2022)  # E1 -> E2 transition, used for the pilot run
GAP_MAX = 2.0  # max gap (s) at lap start for a pair to be included
RANDOM_STATE = 42

# Track status codes (FastF1): 1 green, 2 yellow, 4 safety car, 5 red flag,
# 6 VSC deployed, 7 VSC ending. Laps containing these are neutralised.
NEUTRALISED_STATUS = ("4", "5", "6", "7")

# Tyre compound ranking for compound_adv (higher = softer = faster)
COMPOUND_RANK = {"SOFT": 3, "MEDIUM": 2, "HARD": 1}
WET_COMPOUNDS = ("INTERMEDIATE", "WET")
# Until 2018 Pirelli used absolute compound names; three of them were
# nominated per race. Ordered from softest to hardest.
ABSOLUTE_COMPOUNDS_2018 = ("HYPERSOFT", "ULTRASOFT", "SUPERSOFT", "SOFT",
                           "MEDIUM", "HARD", "SUPERHARD")

# Web access
USER_AGENT = "f1-overtaking-analytics/0.1 (student research project; python-requests)"
JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"
WIKIPEDIA_CIRCUITS_URL = "https://en.wikipedia.org/wiki/List_of_Formula_One_circuits"
# Pinned commit of bacinger/f1-circuits for reproducible downloads
GEOJSON_COMMIT = "8094e957b8d6aa8b9f4510c93968556cccd30e02"
GEOJSON_BASE_URL = (
    f"https://raw.githubusercontent.com/bacinger/f1-circuits/{GEOJSON_COMMIT}"
)

# Regulation eras
ERAS = {
    "E1": range(2018, 2022),  # classic aero
    "E2": range(2022, 2026),  # ground effect
    "E3": range(2026, 2027),  # active aero, override mode
}

# Consistent era colours for all figures (colour-blind safe set, validated
# for deutan/protan/tritan separation; always add direct labels or a legend)
ERA_COLORS = {"E1": "#2a78d6", "E2": "#eb6834", "E3": "#1baf7a"}
ERA_LABELS = {"E1": "E1 2018–2021 (classic aero)",
              "E2": "E2 2022–2025 (ground effect)",
              "E3": "E3 2026 (active aero)"}


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
