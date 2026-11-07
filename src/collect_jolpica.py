"""Collect race calendar, results and qualifying from the Jolpica-F1 REST API.

Jolpica (https://github.com/jolpica/jolpica-f1) is the maintained successor of
the Ergast API and uses the same paths. Every API page is stored unchanged as
JSON in data/raw/jolpica/<season>/ before anything is parsed, so the raw data
can always be re-parsed without new requests.

Command line:
    python -m src.collect_jolpica 2021 2022
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from src.config import INTERIM_DIR, JOLPICA_BASE_URL, PILOT_SEASONS, RAW_DIR
from src.web import PoliteSession

RAW_JOLPICA = RAW_DIR / "jolpica"
PAGE_LIMIT = 100  # maximum page size of the API


def fetch_paginated(path: str, raw_dir: Path, session: PoliteSession,
                    refresh: bool = False) -> list[dict]:
    """Fetch all pages of an endpoint and store each page unchanged.

    Args:
        path: Endpoint path without extension, e.g. '2021/results'.
        raw_dir: Directory for the raw JSON pages.
        session: HTTP session (throttled).
        refresh: Download again even if a page already exists locally.

    Returns:
        List of parsed JSON pages.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = path.replace("/", "_")
    pages, offset = [], 0
    while True:
        file = raw_dir / f"{stem}_offset{offset:05d}.json"
        if file.exists() and not refresh:
            data = json.loads(file.read_text(encoding="utf-8"))
        else:
            resp = session.get(f"{JOLPICA_BASE_URL}/{path}.json",
                               params={"limit": PAGE_LIMIT, "offset": offset})
            file.write_bytes(resp.content)
            data = resp.json()
        pages.append(data)
        mr = data["MRData"]
        offset = int(mr["offset"]) + int(mr["limit"])
        if offset >= int(mr["total"]):
            return pages


def _races(pages: list[dict]) -> list[dict]:
    """Flatten the Races lists of all pages."""
    return [race for p in pages for race in p["MRData"]["RaceTable"]["Races"]]


def parse_races(pages: list[dict]) -> pd.DataFrame:
    """Race calendar: one row per race with circuit and location."""
    rows = []
    for r in _races(pages):
        c = r["Circuit"]
        loc = c.get("Location", {})
        rows.append({
            "season": int(r["season"]), "round": int(r["round"]),
            "race_name": r.get("raceName"), "race_date": r.get("date"),
            "circuit_id": c["circuitId"], "circuit_name": c.get("circuitName"),
            "locality": loc.get("locality"), "country": loc.get("country"),
            "lat": float(loc["lat"]) if loc.get("lat") else None,
            "lon": float(loc["long"]) if loc.get("long") else None,
        })
    return pd.DataFrame(rows)


def parse_results(pages: list[dict]) -> pd.DataFrame:
    """Race results: one row per driver and race.

    A race can be split across two API pages; parsing per result row makes the
    page boundaries irrelevant.
    """
    rows = []
    for r in _races(pages):
        for res in r.get("Results", []):
            d, k = res["Driver"], res["Constructor"]
            rows.append({
                "season": int(r["season"]), "round": int(r["round"]),
                "driver_id": d["driverId"], "code": d.get("code"),
                "number": int(res["number"]) if res.get("number") else None,
                "given_name": d.get("givenName"), "family_name": d.get("familyName"),
                "nationality": d.get("nationality"),
                "constructor_id": k["constructorId"], "constructor_name": k.get("name"),
                "grid": int(res["grid"]) if res.get("grid") else None,
                "finish_pos": int(res["position"]) if res.get("position") else None,
                "position_text": res.get("positionText"),
                "laps": int(res["laps"]) if res.get("laps") else None,
                "status": res.get("status"),
            })
    return pd.DataFrame(rows)


def parse_qualifying(pages: list[dict]) -> pd.DataFrame:
    """Qualifying classification: one row per driver and race."""
    rows = []
    for r in _races(pages):
        for q in r.get("QualifyingResults", []):
            rows.append({
                "season": int(r["season"]), "round": int(r["round"]),
                "driver_id": q["Driver"]["driverId"],
                "quali_pos": int(q["position"]) if q.get("position") else None,
            })
    return pd.DataFrame(rows)


def collect_season(season: int, session: PoliteSession | None = None,
                   refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Download and parse calendar, results and qualifying of one season.

    Args:
        season: Championship year.
        session: Optional shared HTTP session.
        refresh: Re-download pages that already exist locally.

    Returns:
        Dict with DataFrames 'races', 'results', 'qualifying'.
    """
    session = session or PoliteSession()
    raw_dir = RAW_JOLPICA / str(season)
    return {
        "races": parse_races(fetch_paginated(f"{season}", raw_dir, session, refresh)),
        "results": parse_results(
            fetch_paginated(f"{season}/results", raw_dir, session, refresh)),
        "qualifying": parse_qualifying(
            fetch_paginated(f"{season}/qualifying", raw_dir, session, refresh)),
    }


def collect(seasons, refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Collect several seasons and store the parsed tables as Parquet.

    Args:
        seasons: Iterable of championship years.
        refresh: Re-download pages that already exist locally (the current
            season is always downloaded again).

    Returns:
        Dict with the concatenated DataFrames 'races', 'results', 'qualifying'.
    """
    session = PoliteSession()
    parts: dict[str, list[pd.DataFrame]] = {"races": [], "results": [], "qualifying": []}
    current_year = pd.Timestamp.now().year
    for season in seasons:
        # the running season changes after every race: always fetch it again
        season_refresh = refresh or season >= current_year
        for name, df in collect_season(season, session, season_refresh).items():
            parts[name].append(df)
    out = {name: pd.concat(dfs, ignore_index=True) for name, dfs in parts.items()}
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in out.items():
        df.to_parquet(INTERIM_DIR / f"jolpica_{name}.parquet", index=False)
    return out


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:]] or list(PILOT_SEASONS)
    tables = collect(years)
    for name, df in tables.items():
        print(f"{name:<11} {len(df):>6} rows")
