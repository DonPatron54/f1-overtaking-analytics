"""Integrate FastF1, Jolpica, GeoJSON (and Wikipedia) into the database tables.

Every step records rows before/after and the reason for lost rows in an
IntegrationLog, which is the basis for the integration documentation (P2).

Keys:
    race      FastF1 (season, RoundNumber)   <-> Jolpica (season, round)
    driver    FastF1 DriverNumber per race   <-> Jolpica number per race -> driverId
    circuit   Jolpica circuitId (lat/lon)    <-> GeoJSON location (nearest point)
    weather   lap start session time         <-> weather session time (asof, backward)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from src.collect_fastf1 import RAW_FASTF1
from src.collect_geo import load_locations
from src.config import INTERIM_DIR, LOGS_DIR, era_for_season

GEO_MAX_DISTANCE_KM = 5.0
WIKI_NAME_THRESHOLD = 85        # accept a fuzzy name match from this score
WIKI_NAME_LOCATION_THRESHOLD = 50  # lower bar if the town also matches exactly
# Manual corrections where names and towns differ too much for fuzzy matching
# (Jolpica circuitId -> Wikipedia circuit name)
MANUAL_WIKI_MATCH = {
    "hungaroring": "Hungaroring",  # Jolpica town Budapest, Wikipedia town Mogyoród
}


@dataclass
class IntegrationLog:
    """Collects one record per integration step."""

    rows: list[dict] = field(default_factory=list)

    def add(self, step: str, before: int, after: int, note: str = "") -> None:
        """Record a step.

        Args:
            step: Short description of the step.
            before: Rows before the step.
            after: Rows after the step.
            note: Reason for lost/gained rows or key used.
        """
        self.rows.append({"step": step, "rows_before": before, "rows_after": after,
                          "change": after - before, "note": note})

    def to_frame(self) -> pd.DataFrame:
        """Log as DataFrame."""
        return pd.DataFrame(self.rows)


# --------------------------------------------------------------------------
# Loading raw FastF1 tables
# --------------------------------------------------------------------------

def load_fastf1_raw(seasons) -> dict[str, pd.DataFrame]:
    """Read the raw FastF1 Parquet/JSON files of all collected races.

    Args:
        seasons: Iterable of championship years.

    Returns:
        Dict with 'events', 'laps', 'results', 'weather' (season/round added).
    """
    parts: dict[str, list[pd.DataFrame]] = {"laps": [], "results": [], "weather": []}
    events = []
    for season in seasons:
        base = RAW_FASTF1 / str(season)
        schedule = pd.read_parquet(base / "schedule.parquet")
        for meta_file in sorted(base.glob("*_meta.json")):
            rnd = int(meta_file.name[:2])
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            ev = schedule.loc[schedule["RoundNumber"] == rnd].iloc[0]
            events.append({"season": season, "round": rnd, "event_name": ev["EventName"],
                           "event_format": ev["EventFormat"], **meta})
            for t in parts:
                df = pd.read_parquet(base / f"{rnd:02d}_{t}.parquet")
                df.insert(0, "round", rnd)
                df.insert(0, "season", season)
                parts[t].append(df)
    out = {t: pd.concat(dfs, ignore_index=True) for t, dfs in parts.items()}
    out["events"] = pd.DataFrame(events)
    return out


def _seconds(td: pd.Series) -> pd.Series:
    """Timedelta -> float seconds (NaT -> NaN)."""
    return pd.to_timedelta(td).dt.total_seconds()


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (vectorised)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


# --------------------------------------------------------------------------
# Integration steps
# --------------------------------------------------------------------------

def integrate_races(jol_races: pd.DataFrame, events: pd.DataFrame,
                    log: IntegrationLog) -> pd.DataFrame:
    """Step 1: match FastF1 sessions to Jolpica races on (season, round)."""
    m = jol_races.merge(events, on=["season", "round"], how="outer", indicator=True)
    only_jol = m.loc[m["_merge"] == "left_only", ["season", "round", "race_name"]]
    only_ff1 = m.loc[m["_merge"] == "right_only", ["season", "round", "event_name"]]
    races = m.loc[m["_merge"] == "both"].drop(columns="_merge").copy()

    # consistency checks on the matched races
    races["name_similarity"] = [
        fuzz.token_set_ratio(a, b) for a, b in zip(races["race_name"], races["event_name"])]
    session_date = pd.to_datetime(races["session_start_utc"], errors="coerce").dt.normalize()
    races["date_diff_days"] = (session_date - pd.to_datetime(races["race_date"])).dt.days

    def _fmt(df: pd.DataFrame, name_col: str) -> str:
        return ", ".join(f"{r.season} R{r.round} {getattr(r, name_col)}"
                         for r in df.itertuples())

    note = "key (season, round)"
    if len(only_jol):
        note += f"; only Jolpica (no FastF1 race data): {_fmt(only_jol, 'race_name')}"
    if len(only_ff1):
        note += f"; only FastF1: {_fmt(only_ff1, 'event_name')}"
    log.add("1 races: FastF1 sessions <-> Jolpica calendar", len(jol_races), len(races), note)
    bad = races.loc[(races["name_similarity"] < 80) | (races["date_diff_days"].abs() > 1)]
    log.add("1b races: consistency check name/date", len(races), len(races),
            f"{len(bad)} races with name similarity < 80 or date difference > 1 day"
            + (f": {bad[['season', 'round', 'race_name', 'event_name']].to_dict('records')}"
               if len(bad) else ""))

    races["race_date"] = pd.to_datetime(races["race_date"]).dt.date
    races["race_id"] = races["season"] * 100 + races["round"]
    races["era"] = races["season"].map(era_for_season)
    return races


def clean_wikipedia(wiki: pd.DataFrame) -> pd.DataFrame:
    """Normalise the scraped Wikipedia circuit table.

    Removes status markers (*, †) from names and converts length and number
    of turns to numbers.
    """
    out = pd.DataFrame({
        "wiki_name": wiki["Circuit"].str.replace(r"[*†‡§#]+", "", regex=True).str.strip(),
        "wiki_location": wiki["Location"],
        "wiki_country": wiki["Country"],
        "circuit_type": wiki["Type"].str.replace(" circuit", "", regex=False).str.lower(),
        "length_km": pd.to_numeric(
            wiki["Last length used"].str.extract(r"([\d.]+)\s*km")[0], errors="coerce"),
        "turns": pd.to_numeric(wiki["Turns"], errors="coerce").astype("Int64"),
    })
    return out


def match_wikipedia(circuits: pd.DataFrame, wiki: pd.DataFrame,
                    log: IntegrationLog) -> pd.DataFrame:
    """Step 2b: add Wikipedia attributes by fuzzy name (+ town) matching."""
    w = clean_wikipedia(wiki)
    rows = []
    for _, c in circuits.iterrows():
        name_score = np.array([fuzz.token_set_ratio(c["circuit_name"], n)
                               for n in w["wiki_name"]])
        same_town = (w["wiki_location"].fillna("").str.casefold()
                     == str(c["locality"]).casefold()).to_numpy()
        best = int(np.argmax(name_score + 20 * same_town))
        score, town = name_score[best], same_town[best]
        if score >= WIKI_NAME_THRESHOLD:
            method = "fuzzy name"
        elif town and score >= WIKI_NAME_LOCATION_THRESHOLD:
            method = "fuzzy name + town"
        elif c["circuit_id"] in MANUAL_WIKI_MATCH:
            best = int(np.flatnonzero(w["wiki_name"] == MANUAL_WIKI_MATCH[c["circuit_id"]])[0])
            score, method = name_score[best], "manual correction"
        else:
            best, method = None, "unmatched"
        rec = {"circuit_id": c["circuit_id"], "wiki_match": method,
               "wiki_score": float(score)}
        if best is not None:
            rec.update(w.iloc[best].to_dict())
        rows.append(rec)
    m = pd.DataFrame(rows)
    counts = m["wiki_match"].value_counts().to_dict()
    log.add("2b circuits: Jolpica circuit name <-> Wikipedia list (fuzzy)",
            len(circuits), int((m["wiki_match"] != "unmatched").sum()),
            f"rapidfuzz token_set_ratio >= {WIKI_NAME_THRESHOLD}, or >= "
            f"{WIKI_NAME_LOCATION_THRESHOLD} with identical town, else manual table; "
            f"{counts}")
    return circuits.merge(m, on="circuit_id", how="left")


def integrate_circuits(races: pd.DataFrame, log: IntegrationLog) -> pd.DataFrame:
    """Step 2: circuits from Jolpica, matched to GeoJSON by nearest location."""
    circuits = (races[["circuit_id", "circuit_name", "locality", "country", "lat", "lon"]]
                .drop_duplicates("circuit_id").reset_index(drop=True))
    geo = load_locations()
    dist = _haversine_km(circuits["lat"].to_numpy()[:, None], circuits["lon"].to_numpy()[:, None],
                         geo["lat"].to_numpy()[None, :], geo["lon"].to_numpy()[None, :])
    nearest = dist.argmin(axis=1)
    circuits["geojson_id"] = geo["id"].to_numpy()[nearest]
    circuits["geojson_name"] = geo["name"].to_numpy()[nearest]
    circuits["geo_distance_km"] = dist[np.arange(len(circuits)), nearest].round(2)
    too_far = circuits["geo_distance_km"] > GEO_MAX_DISTANCE_KM
    circuits.loc[too_far, ["geojson_id", "geojson_name"]] = None
    log.add("2 circuits: Jolpica circuitId <-> GeoJSON location (nearest point)",
            len(circuits), int((~too_far).sum()),
            f"matched if distance <= {GEO_MAX_DISTANCE_KM} km; unmatched: "
            f"{circuits.loc[too_far, 'circuit_id'].tolist()}; "
            f"max matched distance {circuits.loc[~too_far, 'geo_distance_km'].max()} km")
    return circuits


def integrate_drivers(ff1_results: pd.DataFrame, jol_results: pd.DataFrame,
                      races: pd.DataFrame, log: IntegrationLog
                      ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Step 3: map FastF1 drivers (number per race) to Jolpica driverId.

    Returns:
        (race_driver_key, driver_map, drivers)
    """
    ff1 = ff1_results[["season", "round", "DriverNumber", "Abbreviation", "DriverId"]].copy()
    ff1["number"] = pd.to_numeric(ff1["DriverNumber"], errors="coerce").astype("Int64")
    ff1 = ff1.merge(races[["season", "round"]], on=["season", "round"])
    jol = jol_results[["season", "round", "number", "driver_id", "code"]].copy()
    jol["number"] = jol["number"].astype("Int64")

    m = ff1.merge(jol, on=["season", "round", "number"], how="left", indicator=True)
    unmatched = m.loc[m["_merge"] == "left_only"]
    id_conflict = m.loc[(m["_merge"] == "both") & (m["DriverId"] != m["driver_id"])]
    code_conflict = m.loc[(m["_merge"] == "both") & (m["Abbreviation"] != m["code"])]
    key = m.loc[m["_merge"] == "both",
                ["season", "round", "DriverNumber", "Abbreviation", "number", "driver_id"]]
    log.add("3 drivers: FastF1 car number per race <-> Jolpica driverId", len(ff1), len(key),
            f"key (season, round, number); unmatched {len(unmatched)}; "
            f"driverId differs from FastF1 DriverId: {len(id_conflict)}; "
            f"abbreviation differs from Jolpica code: {len(code_conflict)}"
            + (f" {code_conflict[['season', 'round', 'Abbreviation', 'code']].to_dict('records')}"
               if len(code_conflict) else ""))

    driver_map = (key.rename(columns={"Abbreviation": "abbreviation",
                                      "number": "driver_number"})
                  [["season", "abbreviation", "driver_number", "driver_id"]]
                  .drop_duplicates())
    dup = driver_map.duplicated(["season", "abbreviation"], keep=False)
    conflicts = driver_map.loc[dup]
    n_before = len(driver_map)
    driver_map = driver_map.drop_duplicates(["season", "abbreviation"], keep="first")
    log.add("3b driver_map: unique (season, abbreviation)", n_before, len(driver_map),
            f"abbreviations with several numbers/drivers in a season (first kept): "
            f"{conflicts.to_dict('records')}" if len(conflicts) else "no conflicts")

    drivers = (jol_results[["driver_id", "code", "given_name", "family_name", "nationality"]]
               .drop_duplicates("driver_id").reset_index(drop=True))
    return key, driver_map, drivers


def integrate_results(jol_results: pd.DataFrame, jol_quali: pd.DataFrame,
                      races: pd.DataFrame, log: IntegrationLog) -> pd.DataFrame:
    """Step 4: race results + qualifying position (Jolpica)."""
    res = jol_results.merge(races[["season", "round", "race_id"]], on=["season", "round"])
    out = res.merge(jol_quali, on=["season", "round", "driver_id"], how="left")
    missing = out.loc[out["quali_pos"].isna(), ["season", "round", "driver_id"]]
    log.add("4 results: race result + qualifying position", len(res), len(out),
            f"left join on (season, round, driverId); {len(missing)} drivers without "
            f"qualifying position (quali_gap will be missing for them)")
    out = out.rename(columns={"constructor_name": "team"})
    return out[["race_id", "driver_id", "team", "grid", "quali_pos", "finish_pos", "status"]]


def integrate_laps(ff1_laps: pd.DataFrame, key: pd.DataFrame, races: pd.DataFrame,
                   log: IntegrationLog) -> pd.DataFrame:
    """Step 5: FastF1 laps with driver_id, times in seconds."""
    laps = ff1_laps.merge(races[["season", "round", "race_id"]], on=["season", "round"])
    n0 = len(laps)
    laps = laps.merge(key[["season", "round", "DriverNumber", "driver_id"]],
                      on=["season", "round", "DriverNumber"], how="left")
    unmapped = laps["driver_id"].isna()
    no_lapnum = laps["LapNumber"].isna()
    laps = laps.loc[~unmapped & ~no_lapnum].copy()
    out = pd.DataFrame({
        "race_id": laps["race_id"],
        "driver_id": laps["driver_id"],
        "lap_number": laps["LapNumber"].astype(int),
        "lap_time_s": _seconds(laps["LapTime"]),
        "time_end_s": _seconds(laps["Time"]),
        "position": laps["Position"],
        "stint": laps["Stint"],
        "compound": laps["Compound"],
        "tyre_life": laps["TyreLife"],
        "pit_in": laps["PitInTime"].notna(),
        "pit_out": laps["PitOutTime"].notna(),
        "track_status": laps["TrackStatus"],
        "is_accurate": laps["IsAccurate"],
    })
    dup = out.duplicated(["race_id", "driver_id", "lap_number"])
    out = out.loc[~dup]
    log.add("5 laps: FastF1 laps -> driver_id, seconds", n0, len(out),
            f"driver not mapped: {int(unmapped.sum())}; lap number missing: "
            f"{int(no_lapnum.sum())}; duplicate (race, driver, lap): {int(dup.sum())}; "
            f"info: position missing {int(out['position'].isna().sum())}, "
            f"IsAccurate=False {int((~out['is_accurate'].astype(bool)).sum())}")
    return out


def integrate_weather(ff1_weather: pd.DataFrame, races: pd.DataFrame,
                      log: IntegrationLog) -> pd.DataFrame:
    """Step 6: weather samples (about once per minute) in session seconds."""
    w = ff1_weather.merge(races[["season", "round", "race_id"]], on=["season", "round"])
    out = pd.DataFrame({
        "race_id": w["race_id"], "time_s": _seconds(w["Time"]),
        "air_temp": w["AirTemp"], "track_temp": w["TrackTemp"], "humidity": w["Humidity"],
        "pressure": w["Pressure"], "rainfall": w["Rainfall"].astype("boolean"),
        "wind_speed": w["WindSpeed"],
    }).dropna(subset=["time_s"]).drop_duplicates(["race_id", "time_s"])
    log.add("6 weather: FastF1 weather samples", len(w), len(out),
            "rows without time or duplicate (race, time) removed; joined to pairs "
            "later with merge_asof (backward) on lap start time")
    return out


def integrate(seasons, jolpica: dict[str, pd.DataFrame],
              wiki: pd.DataFrame | None = None) -> tuple[dict, pd.DataFrame]:
    """Run all integration steps.

    Args:
        seasons: Championship years to integrate.
        jolpica: Output of collect_jolpica.collect (races, results, qualifying).
        wiki: Output of scrape_wikipedia.parse (optional).

    Returns:
        (tables, log): dict of DataFrames ready for the database, integration log.
    """
    log = IntegrationLog()
    ff1 = load_fastf1_raw(seasons)
    jol = {k: v.loc[v["season"].isin(list(seasons))] for k, v in jolpica.items()}

    races = integrate_races(jol["races"], ff1["events"], log)
    max_lap = (ff1["laps"].groupby(["season", "round"])["LapNumber"].max()
               .rename("max_lap").reset_index())
    races = races.merge(max_lap, on=["season", "round"], how="left")
    races["total_laps"] = races["total_laps"].fillna(races["max_lap"]).astype(int)

    circuits = integrate_circuits(races, log)
    if wiki is not None:
        circuits = match_wikipedia(circuits, wiki, log)
    else:
        circuits[["circuit_type", "length_km", "turns"]] = None
    key, driver_map, drivers = integrate_drivers(ff1["results"], jol["results"], races, log)
    results = integrate_results(jol["results"], jol["qualifying"], races, log)
    laps = integrate_laps(ff1["laps"], key, races, log)
    weather = integrate_weather(ff1["weather"], races, log)

    tables = {
        "circuits": circuits[["circuit_id", "circuit_name", "locality", "country", "lat",
                              "lon", "circuit_type", "length_km", "turns", "geojson_id"]]
        .rename(columns={"circuit_name": "name"}),
        "races": races[["race_id", "season", "round", "race_name", "circuit_id",
                        "race_date", "era", "total_laps"]],
        "drivers": drivers,
        "driver_map": driver_map,
        "results": results,
        "laps": laps,
        "weather": weather,
    }
    # matching details (not a database table, used for documentation)
    tables["circuit_matching"] = circuits.drop(columns=["lat", "lon"], errors="ignore")
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(INTERIM_DIR / f"{name}.parquet", index=False)
    log_df = log.to_frame()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(LOGS_DIR / "integration_log.csv", index=False)
    return tables, log_df
