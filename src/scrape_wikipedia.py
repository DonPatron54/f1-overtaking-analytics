"""Scrape circuit characteristics from the Wikipedia list of F1 circuits.

The page HTML is downloaded once and stored unchanged in data/raw/wikipedia/;
parsing always works on that stored copy.

Command line:
    python -m src.scrape_wikipedia
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.config import INTERIM_DIR, RAW_DIR, WIKIPEDIA_CIRCUITS_URL
from src.web import PoliteSession

RAW_WIKI = RAW_DIR / "wikipedia"
HTML_FILE = RAW_WIKI / "list_of_formula_one_circuits.html"
META_FILE = RAW_WIKI / "list_of_formula_one_circuits.meta.json"


def download(refresh: bool = False) -> str:
    """Download the page HTML unless a stored copy exists.

    Args:
        refresh: Download again even if the file exists.

    Returns:
        'downloaded' or 'cached'.
    """
    if HTML_FILE.exists() and not refresh:
        return "cached"
    RAW_WIKI.mkdir(parents=True, exist_ok=True)
    resp = PoliteSession().get(WIKIPEDIA_CIRCUITS_URL)
    HTML_FILE.write_bytes(resp.content)
    META_FILE.write_text(json.dumps({
        "url": WIKIPEDIA_CIRCUITS_URL,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }), encoding="utf-8")
    return "downloaded"


def _clean(value) -> str | None:
    """Remove footnote markers like '[a]' or '[12]' and surrounding spaces."""
    if pd.isna(value):
        return None
    return re.sub(r"\[[^\]]*\]", "", str(value)).strip() or None


def parse() -> pd.DataFrame:
    """Parse the circuits table from the stored HTML.

    Returns:
        One row per circuit with the columns of the Wikipedia table
        (footnotes removed), stored as data/interim/wikipedia_circuits.parquet.
    """
    html = HTML_FILE.read_text(encoding="utf-8")
    tables = pd.read_html(StringIO(html))
    candidates = [t for t in tables
                  if {"Circuit", "Type"}.issubset({_clean(c) for c in t.columns})]
    if not candidates:
        raise ValueError("Circuit table not found - page structure has changed")
    df = max(candidates, key=len)
    df.columns = [_clean(c) for c in df.columns]
    df = df.apply(lambda col: col.map(_clean))
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM_DIR / "wikipedia_circuits.parquet", index=False)
    return df


if __name__ == "__main__":
    print(download())
    table = parse()
    print(f"{len(table)} circuits, columns: {list(table.columns)}")
