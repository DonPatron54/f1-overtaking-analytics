"""Collect lap, result and weather data of all Grand Prix races via FastF1.

FastF1 reads the F1 live-timing data. Its HTTP cache (data/cache/) keeps the
original API responses; the tables FastF1 builds from them are stored
unchanged as Parquet in data/raw/fastf1/<season>/. Only main races
(session 'R') are collected, no sprints and no testing.

API etiquette: FastF1 limits itself to 500 calls per hour on any API and
200 per hour on Jolpica. This module stays below both limits on its own
(at most MAX_RACES_PER_HOUR uncached races per rolling hour, tracked in a
file so that restarts do not reset the count) and never bypasses them.

Access: since October 2026 the official live-timing server requires an
F1 TV account (Access plan or higher). Without an account FastF1 uses its
public mirror, which only holds some seasons (2021 and 2022 at the time of
writing). With an account, set F1_USERNAME and F1_PASSWORD as environment
variables (e.g. as Codespaces secrets) or pass --login to sign in
interactively; credentials are handled by FastF1 only.

Command line:
    python -m src.collect_fastf1 2021 2022
    python -m src.collect_fastf1 --login 2018 2019 2020
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import fastf1
import fastf1.req
import fastf1._api as ff1_api  # private module; behaviour checked for FastF1 3.9.0
import pandas as pd
from fastf1.exceptions import RateLimitExceededError

from src.config import CACHE_DIR, LOGS_DIR, PILOT_SEASONS, RAW_DIR

RAW_FASTF1 = RAW_DIR / "fastf1"
TABLES = ("laps", "results", "weather", "track_status")
# Pacing: an uncached race needs about 10 calls (8 live-timing files, 2 Jolpica
# requests), so 40 races per hour stay below 500 (any API) and 200 (Jolpica).
MAX_RACES_PER_HOUR = 40
LOAD_LOG = CACHE_DIR / "race_loads.json"  # timestamps of uncached race loads
# Safety net if FastF1's own limiter still triggers: wait and retry.
RATE_LIMIT_WAIT_S = 300
RATE_LIMIT_MAX_WAITS = 15


def _paths(season: int, rnd: int) -> dict[str, Path]:
    """File paths of the raw tables (Parquet) and metadata (JSON) of one race."""
    base = RAW_FASTF1 / str(season)
    paths = {t: base / f"{rnd:02d}_{t}.parquet" for t in TABLES}
    paths["meta"] = base / f"{rnd:02d}_meta.json"
    return paths


def setup_fastf1(log_level: str = "WARNING", login: bool = False) -> None:
    """Enable the FastF1 HTTP cache and reduce its log output.

    With an account (F1_USERNAME/F1_PASSWORD or login=True) the sign-in is
    checked once up front. Without one, stdin is detached so FastF1 never waits
    for an interactive credential prompt, and requests go to the public mirror.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.configure(cache_dir=str(CACHE_DIR))
    fastf1.set_log_level(log_level)
    if not (login or os.environ.get("F1_USERNAME")):
        sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115
        # one warning per request would flood the output
        logging.getLogger("fastf1.fastf1.internals.f1account.transport").setLevel(
            logging.ERROR)
        # Without an account the official server answers every request with
        # HTTP 401 and FastF1 then repeats it on its public mirror; both
        # attempts count towards the hourly limit. Asking the mirror directly
        # skips the request that is certain to fail - the mirror receives
        # exactly the same requests as before.
        ff1_api.base_url = ff1_api.base_url_mirror
    else:
        _check_account_login()
    _install_call_counter()


def _check_account_login() -> None:
    """Sign in once before collecting; abort on failure.

    Without this check FastF1 would retry the sign-in on every request and
    continue without authentication, i.e. many failed sign-ins in a row,
    which can lock the account.
    """
    from fastf1.exceptions import F1AuthError
    from fastf1.internals import f1account

    try:
        token = f1account.get_token()
    except F1AuthError as exc:
        raise SystemExit(f"F1 account sign-in failed, nothing collected: {exc}") from None
    print(f"F1 account sign-in ok (token valid: {token.is_valid()})", flush=True)


_NETWORK_URLS: list[str] = []


def _count_network_call(response, *args, **kwargs):
    """requests hook: record URLs that were not served from the cache.

    The cached session can run response hooks more than once per request,
    so calls are counted as distinct URLs per race (see collect_race).
    """
    if not getattr(response, "from_cache", False):
        _NETWORK_URLS.append(response.url)


def _install_call_counter() -> None:
    """Attach the counter to FastF1's HTTP session (for the collection log)."""
    session = (fastf1.req.Cache._requests_session_cached
               or fastf1.req.Cache._requests_session)
    if _count_network_call not in session.hooks["response"]:
        session.hooks["response"].append(_count_network_call)


def _wait_for_hourly_budget() -> None:
    """Sleep until fewer than MAX_RACES_PER_HOUR races were loaded in the last hour.

    The load times are stored in LOAD_LOG, so the budget also holds across
    interrupted and restarted runs.
    """
    now = time.time()
    loads = json.loads(LOAD_LOG.read_text()) if LOAD_LOG.exists() else []
    loads = [t for t in loads if now - t < 3600]
    if len(loads) >= MAX_RACES_PER_HOUR:
        wait = 3600 - (now - min(loads)) + 5
        print(f"hourly budget of {MAX_RACES_PER_HOUR} races used; "
              f"waiting {wait / 60:.0f} min ...", flush=True)
        time.sleep(wait)
        loads = [t for t in loads if time.time() - t < 3600]
    LOAD_LOG.write_text(json.dumps(loads + [time.time()]))


def _is_cached(season: int, rnd: int) -> bool:
    """True if all raw files of a race exist."""
    return all(p.exists() for p in _paths(season, rnd).values())


def load_schedule(season: int, refresh: bool = False) -> pd.DataFrame:
    """Event schedule of a season without testing, stored as raw Parquet.

    Args:
        season: Championship year.
        refresh: Download again even if a stored schedule exists.

    Returns:
        FastF1 event schedule as plain DataFrame.
    """
    path = RAW_FASTF1 / str(season) / "schedule.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    schedule = pd.DataFrame(fastf1.get_event_schedule(season, include_testing=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    schedule.to_parquet(path, index=False)
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

    calls_before = len(_NETWORK_URLS)
    try:
        session = fastf1.get_session(season, rnd, "R")
        session.load(laps=True, telemetry=False, weather=True, messages=False)
        tables = {
            "laps": pd.DataFrame(session.laps),
            "results": pd.DataFrame(session.results),
            "weather": pd.DataFrame(session.weather_data),
            "track_status": pd.DataFrame(session.track_status),
        }
    except RateLimitExceededError:
        raise  # handled by collect(): wait and retry
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
    record.update(meta, status="loaded",
                  api_calls=len(set(_NETWORK_URLS[calls_before:])))
    return record


def collect(seasons, refresh: bool = False, login: bool = False) -> pd.DataFrame:
    """Collect all main races of the given seasons.

    Races that have not taken place yet are skipped. Failures are logged and
    do not stop the run. Uncached races are paced to MAX_RACES_PER_HOUR, so a
    full collection (about 200 races) takes several hours.

    Args:
        seasons: Iterable of championship years.
        refresh: Reload races that already exist locally.
        login: Sign in to an F1 TV account interactively (see module docstring).

    Returns:
        Collection log, one row per race (also stored in reports/logs/).
    """
    setup_fastf1(login=login)
    records = []
    for season in seasons:
        schedule = load_schedule(season, refresh)
        for _, ev in schedule.iterrows():
            rnd = int(ev["RoundNumber"])
            if pd.Timestamp(ev["EventDate"]) > pd.Timestamp.now():
                records.append({"season": season, "round": rnd, "status": "future"})
                continue
            if refresh or not _is_cached(season, rnd):
                _wait_for_hourly_budget()
            for attempt in range(RATE_LIMIT_MAX_WAITS + 1):
                try:
                    rec = collect_race(season, rnd, refresh)
                    break
                except RateLimitExceededError as exc:
                    if attempt == RATE_LIMIT_MAX_WAITS:
                        rec = {"season": season, "round": rnd, "status": "failed",
                               "error": f"RateLimitExceededError: {exc}"}
                        break
                    print(f"API rate limit reached ({exc}); waiting "
                          f"{RATE_LIMIT_WAIT_S // 60} min before retrying ...", flush=True)
                    time.sleep(RATE_LIMIT_WAIT_S)
            rec["event_name"] = ev["EventName"]
            rec["event_format"] = ev["EventFormat"]
            records.append(rec)
            print(f"{season} R{rnd:02d} {ev['EventName']:<28} {rec['status']}", flush=True)
    log = pd.DataFrame(records)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "collection_fastf1.csv"
    if log_file.exists():
        # keep the entries of seasons that were not part of this run
        old = pd.read_csv(log_file)
        old = old.loc[~old["season"].isin(log["season"].unique())]
        full = pd.concat([old, log], ignore_index=True)
    else:
        full = log
    full.sort_values(["season", "round"]).to_csv(log_file, index=False)
    return log


def check_access(seasons, login: bool = False) -> pd.DataFrame:
    """Request one live-timing file of the first race per season (no cache).

    Prints the HTTP status per season and host, to diagnose access problems
    without collecting anything. The token is never printed.

    Args:
        seasons: Championship years to check.
        login: Sign in interactively (see module docstring).

    Returns:
        One row per season and host with the HTTP status code.
    """
    setup_fastf1(login=login)
    session_http = fastf1.req.Cache._requests_session  # uncached, token adapter mounted
    rows = []
    for season in seasons:
        path = fastf1.get_session(season, 1, "R").api_path
        for host in ("https://livetiming.formula1.com", ff1_api.base_url_mirror):
            url = f"{host}{path}SessionInfo.jsonStream"
            try:
                status = session_http.get(url, timeout=30).status_code
            except Exception as exc:  # noqa: BLE001
                status = type(exc).__name__
            rows.append({"season": season, "host": host, "status": status})
            print(f"{season} {host:<38} {status}", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    args = sys.argv[1:]
    use_login = "--login" in args
    years = [int(a) for a in args if a.isdigit()] or list(PILOT_SEASONS)
    if "--check" in args:
        check_access(years, login=use_login)
        sys.exit(0)
    result = collect(years, login=use_login)
    print(result["status"].value_counts().to_string())
