"""Unit tests for integration helpers."""

import pandas as pd
import pytest

from src.integrate import IntegrationLog, _haversine_km, clean_wikipedia


def test_haversine_known_distance():
    # Monza -> Imola is about 235 km as the crow flies
    d = _haversine_km(45.6156, 9.28111, 44.3439, 11.7167)
    assert d == pytest.approx(235, abs=10)
    assert _haversine_km(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0)


def test_clean_wikipedia_parses_numbers_and_markers():
    raw = pd.DataFrame({
        "Circuit": ["Circuit de Monaco *", "Jeddah Corniche Circuit †"],
        "Location": ["Monte Carlo", "Jeddah"],
        "Country": ["Monaco", "Saudi Arabia"],
        "Type": ["Street circuit", "Street circuit"],
        "Last length used": ["3.337 km (2.074 mi)", "6.174 km (3.836 mi)"],
        "Turns": ["19", "27"],
    })
    out = clean_wikipedia(raw)
    assert out["wiki_name"].tolist() == ["Circuit de Monaco", "Jeddah Corniche Circuit"]
    assert out["circuit_type"].tolist() == ["street", "street"]
    assert out["length_km"].tolist() == [3.337, 6.174]
    assert out["turns"].tolist() == [19, 27]


def test_integration_log_change():
    log = IntegrationLog()
    log.add("step", 10, 7, "reason")
    row = log.to_frame().iloc[0]
    assert row["change"] == -3 and row["note"] == "reason"


def test_relative_compounds_2018_and_later():
    from src.integrate import relative_compounds

    laps = pd.DataFrame({
        "season": [2018] * 5 + [2019] * 3,
        "round": [3] * 5 + [1] * 3,
        "Compound": ["ULTRASOFT", "SOFT", "MEDIUM", "INTERMEDIATE", None,
                     "MEDIUM", "HARD", "UNKNOWN"],
    })
    out = relative_compounds(laps, IntegrationLog()).tolist()
    # 2018: ultrasoft/soft/medium nominated -> SOFT/MEDIUM/HARD; wet unchanged
    assert out[:4] == ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE"]
    assert pd.isna(out[4])
    # 2019+: relative names stay, unknown becomes missing
    assert out[5:7] == ["MEDIUM", "HARD"] and pd.isna(out[7])
