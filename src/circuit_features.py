"""Geometric circuit features computed from the GeoJSON layouts.

The layouts are LineStrings in WGS84. They are projected to the local UTM
zone (metres) and analysed as a closed loop:

- layout_length_m: length of the line (validated against Wikipedia)
- longest_straight_m: longest run of consecutive segments whose direction
  stays within MAX_TURN_DEG of the run's mean direction
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

MAX_TURN_DEG = 10.0


def _angle_diff(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray | float:
    """Smallest absolute difference between two headings in degrees."""
    return np.abs((np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0)


def straight_lengths(coords: np.ndarray, max_turn_deg: float = MAX_TURN_DEG) -> list[float]:
    """Lengths (m) of all straights of a closed circuit line.

    Args:
        coords: Array (n, 2) of projected coordinates in metres; the line is
            treated as a closed loop.
        max_turn_deg: Maximum deviation of a segment from the running mean
            direction of the current straight.

    Returns:
        Length of every straight, in order along the loop.
    """
    if not np.allclose(coords[0], coords[-1]):
        coords = np.vstack([coords, coords[:1]])
    seg = np.diff(coords, axis=0)
    seg = seg[np.hypot(seg[:, 0], seg[:, 1]) > 0]
    length = np.hypot(seg[:, 0], seg[:, 1])
    heading = np.degrees(np.arctan2(seg[:, 1], seg[:, 0]))

    # start the walk after the sharpest turn, so no straight is split at the
    # arbitrary first point of the file (e.g. the start/finish straight)
    turn = _angle_diff(heading, np.roll(heading, 1))
    start = int(np.argmax(turn))
    seg, length, heading = (np.roll(a, -start, axis=0) for a in (seg, length, heading))

    runs, run_vec, run_len = [], seg[0].astype(float), length[0]
    for vec, seg_len, seg_heading in zip(seg[1:], length[1:], heading[1:]):
        run_heading = np.degrees(np.arctan2(run_vec[1], run_vec[0]))
        if _angle_diff(seg_heading, run_heading) <= max_turn_deg:
            run_vec = run_vec + vec
            run_len += seg_len
        else:
            runs.append(float(run_len))
            run_vec, run_len = vec.astype(float), seg_len
    runs.append(float(run_len))
    return runs


def geometry_features(layouts: gpd.GeoDataFrame) -> pd.DataFrame:
    """Layout length and longest straight per GeoJSON circuit.

    Args:
        layouts: GeoDataFrame with columns id and geometry (LineString, WGS84).

    Returns:
        One row per circuit: geojson_id, layout_length_m, longest_straight_m.
    """
    rows = []
    for _, row in layouts.iterrows():
        single = gpd.GeoSeries([row.geometry], crs=layouts.crs)
        line = single.to_crs(single.estimate_utm_crs()).iloc[0]
        coords = np.asarray(line.coords)[:, :2]
        rows.append({
            "geojson_id": row["id"],
            "layout_length_m": round(float(line.length), 1),
            "longest_straight_m": round(max(straight_lengths(coords)), 1),
        })
    return pd.DataFrame(rows)
