# F1 Overtaking Analytics

**Did the regulations make Formula 1 more exciting? Overtaking across three regulation eras (2018–2026)**

Group project, Data Analytics, ZHAW School of Management and Law, HS 2026
Mahdi Mohamed Zahir · Chris Zimmermann · Maksim Knezevic

## Research question

Which factors determine whether a driver overtakes the car ahead within a lap
(gap, tyre advantage, circuit, weather), and has their influence changed across
three regulation eras?

| Era | Seasons | Regulations |
| --- | --- | --- |
| E1 | 2018–2021 | classic wing-based aerodynamics, DRS |
| E2 | 2022–2025 | ground effect, DRS |
| E3 | 2026 | new cars and power units, active aerodynamics, override mode |

Unit of analysis: one pair of consecutive cars (gap ≤ 2.0 s at lap start) × one lap.
Target: `overtake` (1 if the car behind is ahead at the end of the lap).

## Data sources

| Source | Content | Access |
| --- | --- | --- |
| [FastF1](https://docs.fastf1.dev/) | laps, positions, tyres, track status, weather | Python package (F1 live timing) |
| [Jolpica-F1](https://github.com/jolpica/jolpica-f1) | results, grid, drivers, circuits | REST API |
| Wikipedia | circuit characteristics | web scraping |
| [bacinger/f1-circuits](https://github.com/bacinger/f1-circuits) | circuit layouts (GeoJSON) | file download |
| [OpenF1](https://openf1.org/) *(optional)* | high-resolution positions, from 2023 | REST API |

## Quick start (GitHub Codespaces)

1. On GitHub: **Code → Codespaces → Create codespace on main**.
2. Wait for the setup to finish (first start takes a few minutes). It
   - starts PostgreSQL 16 in its own container (data persists in a Docker volume),
   - installs all Python packages from `requirements.txt`,
   - creates the database schema (`sql/schema.sql`).
3. Verify: open `notebooks/00_setup_check.ipynb` and run all cells, or in the terminal:

   ```bash
   python -m src.db check
   ```

The database is reachable at `localhost:5432` (database `f1`, user `f1`).
The password is generated on first start and stored in `.devcontainer/.env`
(not committed); inside the Codespace it is available as `$PGPASSWORD`.

```python
from src.db import get_engine
import pandas as pd

engine = get_engine()
pd.read_sql("SELECT * FROM races LIMIT 5", engine)
```

For ad-hoc SQL, run `psql` in the Codespace terminal (no arguments needed).

## Repository structure

```text
├── .devcontainer/      # Codespace: Python 3.11 + PostgreSQL 16 (Docker Compose)
├── data/
│   ├── raw/            # unmodified API / scraping responses (not committed)
│   ├── interim/        # cleaned intermediate files (not committed)
│   └── processed/      # final analysis datasets
├── notebooks/          # numbered in pipeline order (00_, 01_, ...)
├── reports/figures/    # figures for the slides
├── sql/schema.sql      # database schema
├── src/                # reusable code (config, db, collectors, features)
└── requirements.txt    # pinned dependencies (generated from requirements.in)
```

## Conventions

- Code, comments and docstrings in English, `snake_case`.
- Fixed seeds (`RANDOM_STATE = 42`) and all constants in `src/config.py`.
- Raw data is never overwritten; every step is a notebook or script.
- Every notebook runs top to bottom with *Restart & Run All*.

## Dependencies

`requirements.txt` is a pinned lock file for Python 3.11. To add a package,
add it to `requirements.in` and regenerate:

```bash
pip install uv
uv pip compile requirements.in --python-version 3.11 -o requirements.txt
```
