"""Unit tests for the pair-lap construction on a hand-made mini race."""

import pandas as pd
import pytest

from src.build_pairs import build_pairs, is_neutralised


def _lap(drv, n, pos, t, status="1", pit_in=False, pit_out=False,
         compound="MEDIUM", tyre=None):
    return {"race_id": 1, "driver_id": drv, "lap_number": n, "position": pos,
            "time_end_s": t, "lap_time_s": 90.0, "track_status": status,
            "pit_in": pit_in, "pit_out": pit_out, "compound": compound,
            "tyre_life": tyre if tyre is not None else n}


@pytest.fixture
def mini_race():
    """Three cars, five laps.

    lap 1: X, Y (+0.8 s), Z (+5 s)
    lap 2: unchanged
    lap 3: Y passes X
    lap 4: Z pits (pit in), Y leads X
    lap 5: safety car, Z leaves the pits
    """
    rows = [
        _lap("X", 1, 1, 100.0), _lap("Y", 1, 2, 100.8), _lap("Z", 1, 3, 105.0),
        _lap("X", 2, 1, 190.0), _lap("Y", 2, 2, 190.5), _lap("Z", 2, 3, 196.0),
        _lap("Y", 3, 1, 279.8), _lap("X", 3, 2, 280.2), _lap("Z", 3, 3, 286.0),
        _lap("Y", 4, 1, 369.5), _lap("X", 4, 2, 369.9), _lap("Z", 4, 3, 390.0, pit_in=True),
        _lap("Y", 5, 1, 470.0, "14"), _lap("X", 5, 2, 470.5, "14"),
        _lap("Z", 5, 3, 480.0, "14", pit_out=True, compound="HARD", tyre=1),
    ]
    laps = pd.DataFrame(rows)
    drivers = pd.DataFrame({"race_id": 1, "driver_id": ["X", "Y", "Z"],
                            "team": ["T1", "T2", "T2"], "quali_pos": [1, 3, 2]})
    races = pd.DataFrame({"race_id": [1], "total_laps": [5]})
    return laps, drivers, races


def test_pairs_and_target(mini_race):
    pairs, _ = build_pairs(*mini_race)
    got = pairs[["lap_number", "driver_ahead", "driver_behind", "overtake"]]
    expected = pd.DataFrame({"lap_number": [2, 3, 4],
                             "driver_ahead": ["X", "X", "Y"],
                             "driver_behind": ["Y", "Y", "X"],
                             "overtake": [0, 1, 0]})
    pd.testing.assert_frame_equal(got.reset_index(drop=True), expected,
                                  check_dtype=False)


def test_features_use_lap_start(mini_race):
    pairs, _ = build_pairs(*mini_race)
    lap3 = pairs.loc[pairs["lap_number"] == 3].iloc[0]
    assert lap3["gap_s"] == pytest.approx(0.5)      # end of lap 2, not lap 3
    assert lap3["position_a"] == 1                  # X led at the start of lap 3
    assert lap3["quali_gap"] == 2                   # Y (3) - X (1)
    assert not lap3["same_team"]
    assert lap3["lap_frac"] == pytest.approx(3 / 5)


def test_waterfall_counts(mini_race):
    _, wf = build_pairs(*mini_race)
    removed = dict(zip(wf["rule"], wf["removed"]))
    assert wf["remaining"].iloc[0] == 8             # 4 laps x 2 adjacent pairs
    assert removed["pit stop of A or B in lap n"] == 2
    assert removed["lap n neutralised (SC, VSC, red flag)"] == 1
    assert removed["gap > 2.0 s at lap start"] == 2
    assert wf["remaining"].iloc[-1] == 3


def test_retirement_and_restart():
    rows = [
        _lap("X", 1, 1, 100.0), _lap("Y", 1, 2, 100.5), _lap("Z", 1, 3, 101.0),
        _lap("X", 2, 1, 190.0, "4"), _lap("Y", 2, 2, 190.4, "4"), _lap("Z", 2, 3, 190.9, "4"),
        _lap("X", 3, 1, 280.0), _lap("Y", 3, 2, 280.4),           # Z retires in lap 3
    ]
    laps = pd.DataFrame(rows)
    drivers = pd.DataFrame({"race_id": 1, "driver_id": ["X", "Y", "Z"],
                            "team": ["A", "B", "C"], "quali_pos": [1, 2, 3]})
    races = pd.DataFrame({"race_id": [1], "total_laps": [3]})
    pairs, wf = build_pairs(laps, drivers, races)
    removed = dict(zip(wf["rule"], wf["removed"]))
    assert pairs.empty
    assert removed["no lap-n data for A or B (retirement, race end or missing timing)"] == 1
    assert removed["lap n neutralised (SC, VSC, red flag)"] == 2
    assert removed["restart lap (lap n-1 neutralised)"] == 1


def test_is_neutralised():
    s = pd.Series(["1", "12", "14", "167", None, "2"])
    assert is_neutralised(s).tolist() == [False, False, True, True, False, False]
