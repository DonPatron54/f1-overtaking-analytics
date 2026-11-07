"""Download circuit layouts and locations (GeoJSON) from bacinger/f1-circuits.

Files are fetched from a pinned commit (see config.GEOJSON_COMMIT) so the
download is reproducible, and stored unchanged in data/raw/geo/.

Command line:
    python -m src.collect_geo
"""

from __future__ import annotations

import geopandas as gpd

from src.config import GEOJSON_BASE_URL, RAW_DIR
from src.web import PoliteSession

RAW_GEO = RAW_DIR / "geo"
FILES = ("f1-circuits.geojson", "f1-locations.geojson")


def download(refresh: bool = False) -> dict[str, str]:
    """Download the GeoJSON files unless they already exist.

    Args:
        refresh: Download again even if the files exist.

    Returns:
        Mapping file name -> 'downloaded' or 'cached'.
    """
    RAW_GEO.mkdir(parents=True, exist_ok=True)
    session = PoliteSession(min_interval_s=0.2)
    status = {}
    for name in FILES:
        target = RAW_GEO / name
        if target.exists() and not refresh:
            status[name] = "cached"
            continue
        target.write_bytes(session.get(f"{GEOJSON_BASE_URL}/{name}").content)
        status[name] = "downloaded"
    return status


def load_layouts() -> gpd.GeoDataFrame:
    """Circuit layouts as LineStrings (WGS84), one row per circuit."""
    return gpd.read_file(RAW_GEO / "f1-circuits.geojson")


def load_locations() -> gpd.GeoDataFrame:
    """Circuit locations as Points (WGS84), one row per circuit."""
    return gpd.read_file(RAW_GEO / "f1-locations.geojson")


if __name__ == "__main__":
    print(download())
    print(f"layouts: {len(load_layouts())}, locations: {len(load_locations())}")
