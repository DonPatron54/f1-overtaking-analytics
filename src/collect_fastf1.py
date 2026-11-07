"""Collect lap, result and weather data of all Grand Prix races via FastF1.

FastF1 reads the official F1 live-timing API. Its HTTP cache (data/cache/)
keeps the original API responses; the tables FastF1 builds from them are
stored unchanged as Parquet in data/raw/fastf1/<season>/. Only main races
(session 'R') are collected, no sprints and no testing.

Command line:
    python -m src.collect_fastf1 2021 2022
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import fastf1
import pandas as pd

from src.config import CACHE_DIR, LOGS_DIR, PILOT_SEASONS, RAW_DIR

RAW_FASTF1 = RAW_DIR / "fastf1"
TABLES = ("laps", "results", "weather", "track_status")


def _paths(season: int, rnd: int) -> dict[str, Path]:
    """File paths of the raw tables (Parquet) and metadata (JSON) of one race."""
    base = RAW_FASTF1 / str(season)
    paths = {t: base / f"{rnd:02d}_{t}.parquet" for t in TABLES}
    paths["meta"] = base / f"{rnd:02d}_meta.json"
    return paths


def setup_fastf1(log_level: str = "WARNING") -> None:
    """Enable the FastF1 HTTP cache and reduce its log output.

    Since FastF1 3.9, requests to the live-timing API try to sign in to a
    Formula 1 account. Historical race data is still served without one, so
    the sign-in is skipped: without F1_USERNAME/F1_PASSWORD, stdin is detached
    so FastF1 never waits for an interactive credential prompt.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.configure(cache_dir=str(CACHE_DIR))
    fastf1.set_log_level(log_level)
    if not os.environ.get("F1_USERNAME"):
        sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115
        # one warning per request would flood the output
        logging.getLogger("fastf1.fastf1.internals.f1account.transport").setLevel(
            logging.ERROR)


def load_schedule(season: int) -> pd.DataFrame:
    """Event schedule of a season without testing, stored as raw Parquet.

    Args:
        season: Championship year.

    Returns:
        FastF1 event schedule as plain DataFrame.
    """
    schedule = pd.DataFrame(fastf1.get_event_schedule(season, include_testing=False))
    out = RAW_FASTF1 / str(season)
    out.mkdir(parents=True, exist_ok=True)
    schedule.to_parquet(out / "schedule.parquet", index=False)
    return schedule


def collect_race(season: int, rnd: int, refresh: bool = False) -> dict:
    """Load one race session and store its raw tables.

    Args:
        season: Championship year.
        rnd: Round number in the season.
        refresh: Reload even if all tables already exist locally.

    Returns:
        One log record (season, round, status, row counts, total laps, error).
    """
    paths = _paths(season, rnd)
    record = {"season": season, "round": rnd}
    if not refresh and all(p.exists() for p in paths.values()):
        record["status"] = "cached"
        for t in TABLES:
            record[f"n_{t}"] = len(pd.read_parquet(paths[t]))
        record.update(json.loads(paths["meta"].read_text(encoding="utf-8")))
        return record

    try:
        session = fastf1.get_session(season, rnd, "R")
        session.load(laps=True, telemetry=False, weather=True, messages=False)
        tables = {
            "laps": pd.DataFrame(session.laps),
            "results": pd.DataFrame(session.results),
            "weather": pd.DataFrame(session.weather_data),
            "track_status": pd.DataFrame(session.track_status),
        }
    except Exception as exc:  # noqa: BLE001 - log every failure and continue
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        return record

    if tables["laps"].empty:
        record.update(status="failed", error="no lap data")
        return record

    paths["meta"].parent.mkdir(parents=True, exist_ok=True)
    for t, df in tables.items():
        df.to_parquet(paths[t], index=False)
        record[f"n_{t}"] = len(df)
    total_laps = getattr(session, "total_laps", None)
    meta = {
        "total_laps": int(total_laps) if pd.notna(total_laps) else None,
        "session_start_utc": str(session.date),
    }
    paths["meta"].write_text(json.dumps(meta), encoding="utf-8")
    record.update(meta, status="loaded")
    return record


def collect(seasons, refresh: bool = False) -> pd.DataFrame:
    """Collect all main races of the given seasons.

    Races that have not taken place yet are skipped. Failures are logged and
    do not stop the run.

    Args:
        seasons: Iterable of championship years.
        refresh: Reload races that already exist locally.

    Returns:
        Collection log, one row per race (also stored in reports/logs/).
    """
    setup_fastf1()
    records = []
    for season in seasons:
        schedule = load_schedule(season)
        for _, ev in schedule.iterrows():
            rnd = int(ev["RoundNumber"])
            if pd.Timestamp(ev["EventDate"]) > pd.Timestamp.now():
                records.append({"season": season, "round": rnd, "status": "future"})
                continue
            rec = collect_race(season, rnd, refresh)
            rec["event_name"] = ev["EventName"]
            rec["event_format"] = ev["EventFormat"]
            records.append(rec)
            print(f"{season} R{rnd:02d} {ev['EventName']:<28} {rec['status']}")
    log = pd.DataFrame(records)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log.to_csv(LOGS_DIR / "collection_fastf1.csv", index=False)
    return log


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    years = [int(a) for a in sys.argv[1:]] or list(PILOT_SEASONS)
    result = collect(years)
    print(result["status"].value_counts().to_string())
