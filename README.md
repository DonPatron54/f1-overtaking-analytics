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
| [OpenF1](https://openf1.org/) *(optional, under review)* | high-resolution positions, from 2023 | REST API |

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

## Pipeline

Run the notebooks in this order (each runs top to bottom with *Restart & Run All*):

| Notebook | Step | Output |
| --- | --- | --- |
| `00_setup_check` | environment, database connection | – |
| `01_data_collection` | FastF1, Jolpica-F1, Wikipedia, GeoJSON | `data/raw/`, `reports/logs/collection_fastf1.csv` |
| `02_integration` | keys, joins, integration log | `data/interim/`, `reports/logs/integration_log.csv` |
| `03_database_postgres` | load PostgreSQL, SQL queries | database tables |
| `04_pairs_and_target` | pair-laps, target `overtake`, exclusions | table `pairs`, `data/processed/pairs.parquet` |

Scope: all main races 2018–2026 (2026 up to the latest race; the remaining
races are added after the season ends).

Raw data is committed in `data/raw/`, so the notebooks run without calling the
APIs again. This matters because data access has become restricted:

- Since October 2026 the F1 live-timing server requires an **F1 TV account**
  (Access plan or higher). FastF1's public mirror only holds 2021 and 2022.
- The server blocks cloud networks (HTTP 403 from GitHub Actions and
  Codespaces, even with an account), so a collection with account has to run
  on a regular home or university network.
- FastF1 allows 500 API calls per hour (Jolpica: 200). The collector paces
  itself to at most 40 uncached races per rolling hour, also across restarts,
  so a full collection takes about four to five hours.

```bash
python -m src.collect_jolpica 2018 2019 2020 2021 2022 2023 2024 2025 2026
python -m src.collect_fastf1 --check 2018 2023         # access status per season
python -m src.collect_fastf1 --login 2018 2019 2020 2023 2024 2025 2026
python -m src.scrape_wikipedia
python -m src.collect_geo
python -m pytest                                        # unit tests
```

With `--login`, FastF1 asks for the F1 TV e-mail and password in the terminal;
they are not stored in the project.

## Repository structure

```text
├── .devcontainer/      # Codespace: Python 3.11 + PostgreSQL 16 (Docker Compose)
├── data/
│   ├── raw/            # unmodified API / scraping responses
│   ├── interim/        # parsed and integrated tables (Parquet)
│   └── processed/      # analysis datasets (pairs.parquet)
├── notebooks/          # numbered in pipeline order (00_, 01_, ...)
├── reports/
│   ├── figures/        # figures for the slides (PNG, 300 dpi)
│   └── logs/           # collection, integration and exclusion logs
├── sql/schema.sql      # database schema
├── src/                # collectors, integration, pair construction, database
├── tests/              # unit tests
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
