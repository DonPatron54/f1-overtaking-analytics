"""Build the analysis table: pairs of consecutive cars x lap, target `overtake`.

Definition (project description, section 6.1):
    For every lap n >= 2, car A on position p and car B on position p+1 at the
    end of lap n-1 (= start of lap n) form a pair. `overtake` = 1 if B is ahead
    of A at the end of lap n. Only pairs with a gap <= GAP_MAX seconds at the
    start of lap n are kept.

Exclusion rules are applied in a fixed order; every rule records how many
pair-laps it removes (waterfall), which feeds the integration documentation.

All features use information available at the start of lap n only, to avoid
leakage (positions/times at the end of lap n-1, tyres fitted for lap n, pace
of laps n-3..n-1, qualifying, weather at lap start).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import COMPOUND_RANK, GAP_MAX, NEUTRALISED_STATUS, WET_COMPOUNDS

LAP_KEY = ["race_id", "driver_id", "lap_number"]
_NEUTRAL_PATTERN = "[" + "".join(NEUTRALISED_STATUS) + "]"


def is_neutralised(track_status: pd.Series) -> pd.Series:
    """True where the lap's track status string contains SC, VSC or red flag."""
    return track_status.fillna("").astype(str).str.contains(_NEUTRAL_PATTERN, regex=True)


def add_recent_pace(laps: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """Add `pace_prev` = mean clean lap time of the previous `window` laps.

    Clean laps exclude lap 1, pit-in and pit-out laps and neutralised laps.
    At least two clean laps are required, otherwise the value is NaN.

    Args:
        laps: Lap table with lap_time_s, pit_in, pit_out, track_status.
        window: Number of previous laps.

    Returns:
        Copy of `laps` with an additional column `pace_prev` (seconds).
    """
    laps = laps.sort_values(LAP_KEY).copy()
    clean = (
        laps["lap_time_s"].notna()
        & (laps["lap_number"] > 1)
        & ~laps["pit_in"].eq(True)
        & ~laps["pit_out"].eq(True)
        & ~is_neutralised(laps["track_status"])
    )
    clean_time = laps["lap_time_s"].where(clean)
    laps["pace_prev"] = (
        clean_time.groupby([laps["race_id"], laps["driver_id"]])
        .transform(lambda s: s.shift(1).rolling(window, min_periods=2).mean())
    )
    return laps


def build_pairs(laps: pd.DataFrame, race_drivers: pd.DataFrame, races: pd.DataFrame,
                weather: pd.DataFrame | None = None, gap_max: float = GAP_MAX
                ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build pair-laps with features and target.

    Args:
        laps: One row per race_id, driver_id, lap_number with lap_time_s,
            time_end_s (session time at lap end, s), position (at lap end),
            compound, tyre_life, pit_in, pit_out (bool), track_status (str).
        race_drivers: One row per race_id, driver_id with team and quali_pos.
        races: One row per race_id with total_laps.
        weather: Optional rows race_id, time_s, air_temp, track_temp, rainfall.
        gap_max: Maximum gap (s) at the start of lap n.

    Returns:
        (pairs, waterfall): the analysis table and the exclusion log with
        columns rule, removed, remaining.
    """
    laps = add_recent_pace(laps)
    laps["neutral"] = is_neutralised(laps["track_status"])
    laps["pit_in"] = laps["pit_in"].eq(True)
    laps["pit_out"] = laps["pit_out"].eq(True)

    # --- candidate pairs: adjacent cars in the order at the end of lap n-1 ---
    start = laps.loc[laps["position"].notna()].sort_values(
        ["race_id", "lap_number", "position"])
    grp = start.groupby(["race_id", "lap_number"], sort=False)
    cand = pd.DataFrame({
        "race_id": start["race_id"],
        "lap_number": start["lap_number"] + 1,          # lap n
        "driver_behind": start["driver_id"],
        "driver_ahead": grp["driver_id"].shift(1),
        "pos_b_start": start["position"],
        "pos_a_start": grp["position"].shift(1),
        "t_b_start": start["time_end_s"],
        "t_a_start": grp["time_end_s"].shift(1),
        "neutral_b_prev": start["neutral"],
        "neutral_a_prev": grp["neutral"].shift(1),
        "pit_in_b_prev": start["pit_in"],
        "pit_in_a_prev": grp["pit_in"].shift(1),
    }).dropna(subset=["driver_ahead"])
    cand = cand.merge(races[["race_id", "total_laps"]], on="race_id", how="left")
    cand = cand.loc[cand["lap_number"] <= cand["total_laps"]].reset_index(drop=True)

    # --- state at the end of lap n (and tyres/pace valid for lap n) ---
    cols = ["position", "pit_in", "pit_out", "neutral", "compound", "tyre_life", "pace_prev"]
    cur = laps[LAP_KEY + cols].rename(columns={"position": "pos_end"})
    cols[0] = "pos_end"
    for side, drv in (("a", "driver_ahead"), ("b", "driver_behind")):
        cand = cand.merge(
            cur.rename(columns={"driver_id": drv, **{c: f"{c}_{side}" for c in cols}}),
            on=["race_id", drv, "lap_number"], how="left", indicator=f"has_{side}")
        cand[f"has_{side}"] = cand[f"has_{side}"].eq("both")

    cand["gap_s"] = cand["t_b_start"] - cand["t_a_start"]
    pit = cand[["pit_in_a", "pit_out_a", "pit_in_b", "pit_out_b",
                "pit_in_a_prev", "pit_in_b_prev"]].eq(True).any(axis=1)

    rules = [
        ("no lap-n data for A or B (retirement, race end or missing timing)",
         ~(cand["has_a"] & cand["has_b"])
         | cand["pos_end_a"].isna() | cand["pos_end_b"].isna()),
        ("positions not consecutive at lap start (car missing in data)",
         (cand["pos_b_start"] - cand["pos_a_start"]) != 1),
        ("pit stop of A or B in lap n", pit),
        ("lap n neutralised (SC, VSC, red flag)",
         cand[["neutral_a", "neutral_b"]].eq(True).any(axis=1)),
        ("restart lap (lap n-1 neutralised)",
         cand[["neutral_a_prev", "neutral_b_prev"]].eq(True).any(axis=1)),
        ("missing timing at lap start", cand["gap_s"].isna()),
        ("negative gap (inconsistent timing)", cand["gap_s"] < 0),
        (f"gap > {gap_max:.1f} s at lap start", cand["gap_s"] > gap_max),
    ]
    keep = pd.Series(True, index=cand.index)
    waterfall = [{"rule": "candidate pair-laps (adjacent cars, laps 2..N)",
                  "removed": 0, "remaining": len(cand)}]
    for name, mask in rules:
        hit = keep & mask.fillna(True).astype(bool)
        keep &= ~hit
        waterfall.append({"rule": name, "removed": int(hit.sum()),
                          "remaining": int(keep.sum())})
    p = cand.loc[keep].copy()

    # --- features (all known at the start of lap n) ---
    rank_a = p["compound_a"].map(COMPOUND_RANK)
    rank_b = p["compound_b"].map(COMPOUND_RANK)
    p["compound_adv"] = rank_b - rank_a
    p["wet_tyres"] = p["compound_a"].isin(WET_COMPOUNDS) | p["compound_b"].isin(WET_COMPOUNDS)
    p["tyre_age_diff"] = p["tyre_life_b"] - p["tyre_life_a"]
    p["pace_diff"] = p["pace_prev_b"] - p["pace_prev_a"]
    p["position_a"] = p["pos_a_start"].astype(int)
    p["lap_frac"] = p["lap_number"] / p["total_laps"]

    rd = race_drivers[["race_id", "driver_id", "team", "quali_pos"]]
    for side, drv in (("a", "driver_ahead"), ("b", "driver_behind")):
        p = p.merge(rd.rename(columns={"driver_id": drv, "team": f"team_{side}",
                                       "quali_pos": f"quali_{side}"}),
                    on=["race_id", drv], how="left")
    p["quali_gap"] = p["quali_b"] - p["quali_a"]
    p["same_team"] = p["team_a"].eq(p["team_b"]) & p["team_a"].notna()

    if weather is not None and not weather.empty:
        w = weather[["race_id", "time_s", "air_temp", "track_temp", "rainfall"]]
        p = pd.merge_asof(
            p.sort_values("t_a_start"), w.sort_values("time_s"),
            left_on="t_a_start", right_on="time_s", by="race_id",
            direction="backward").drop(columns="time_s")
    else:
        p[["air_temp", "track_temp", "rainfall"]] = np.nan

    # target: B ahead of A at the end of lap n
    p["overtake"] = (p["pos_end_b"] < p["pos_end_a"]).astype("int8")
    return p.sort_values(["race_id", "lap_number", "position_a"]).reset_index(drop=True), \
        pd.DataFrame(waterfall)


# --------------------------------------------------------------------------
# Database round trip: read laps etc. with SQL, write pairs back
# --------------------------------------------------------------------------

PAIR_DB_COLUMNS = ["race_id", "lap_number", "driver_ahead", "driver_behind", "position_a",
                   "gap_s", "tyre_age_diff", "compound_adv", "wet_tyres", "pace_diff",
                   "quali_gap", "lap_frac", "same_team", "air_temp", "track_temp",
                   "rainfall", "overtake"]


def run_from_db(engine, gap_max: float = GAP_MAX) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the integrated tables from PostgreSQL, build pairs, store them.

    The pairs are written to the `pairs` table (replacing its content), to
    data/processed/pairs.parquet (all columns incl. helper columns) and the
    exclusion waterfall to reports/logs/pairs_waterfall.csv.

    Args:
        engine: SQLAlchemy engine of the project database.
        gap_max: Maximum gap (s) at lap start.

    Returns:
        (pairs, waterfall)
    """
    from src.config import LOGS_DIR, PROCESSED_DIR

    laps = pd.read_sql("""
        SELECT race_id, driver_id, lap_number, lap_time_s, time_end_s, position,
               compound, tyre_life, pit_in, pit_out, track_status
        FROM laps
    """, engine)
    race_drivers = pd.read_sql(
        "SELECT race_id, driver_id, team, quali_pos FROM results", engine)
    races = pd.read_sql("SELECT race_id, total_laps FROM races", engine)
    weather = pd.read_sql(
        "SELECT race_id, time_s, air_temp, track_temp, rainfall FROM weather", engine)

    pairs, waterfall = build_pairs(laps, race_drivers, races, weather, gap_max)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    pairs.to_parquet(PROCESSED_DIR / "pairs.parquet", index=False)
    waterfall.to_csv(LOGS_DIR / "pairs_waterfall.csv", index=False)

    from src.db import load_tables
    load_tables(engine, {"pairs": pairs[PAIR_DB_COLUMNS]})
    return pairs, waterfall
