"""PostgreSQL helpers: engine creation, schema setup and a health check.

Connection settings are read from environment variables (PGHOST, PGPORT,
PGUSER, PGPASSWORD, PGDATABASE). In the Codespace these are set by the dev
container. Outside of it, put them into a `.env` file in the repository root
(see `.env.example`).

Command line:
    python -m src.db init    # create all tables (idempotent)
    python -m src.db check   # print server version and table row counts
"""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv
from sqlalchemy import URL, Engine, create_engine, inspect, text
from sqlalchemy.exc import OperationalError

from src.config import PROJECT_ROOT, SQL_DIR

load_dotenv(PROJECT_ROOT / ".env")


def get_engine(echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the project database.

    Args:
        echo: Log every SQL statement (useful for debugging).

    Returns:
        SQLAlchemy Engine using the psycopg 3 driver.

    Raises:
        KeyError: If PGPASSWORD is not set.
    """
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("PGUSER", "f1"),
        password=os.environ["PGPASSWORD"],
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "f1"),
    )
    return create_engine(url, echo=echo, pool_pre_ping=True)


def wait_for_db(engine: Engine, timeout_s: int = 60) -> None:
    """Block until the database accepts connections.

    Args:
        engine: Engine to test.
        timeout_s: Give up after this many seconds.

    Raises:
        OperationalError: If the database is still unreachable after timeout_s.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


def run_sql_file(engine: Engine, filename: str) -> None:
    """Execute a SQL file from the sql/ directory in one transaction.

    Args:
        engine: Target database.
        filename: File name inside sql/, e.g. 'schema.sql'.
    """
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


def init_schema(engine: Engine) -> list[str]:
    """Create all project tables (idempotent).

    Args:
        engine: Target database.

    Returns:
        Sorted list of table names after setup.
    """
    run_sql_file(engine, "schema.sql")
    return sorted(inspect(engine).get_table_names())


def table_counts(engine: Engine) -> dict[str, int]:
    """Count rows per table in the public schema.

    Args:
        engine: Target database.

    Returns:
        Mapping table name -> row count.
    """
    counts = {}
    with engine.connect() as conn:
        for table in sorted(inspect(engine).get_table_names()):
            counts[table] = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one()
    return counts


def main(argv: list[str]) -> int:
    """Command line entry point (see module docstring)."""
    command = argv[1] if len(argv) > 1 else "check"
    engine = get_engine()
    wait_for_db(engine)

    if command == "init":
        tables = init_schema(engine)
        print(f"Schema ready: {len(tables)} tables -> {', '.join(tables)}")
    elif command == "check":
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
        print(f"PostgreSQL {version} reachable at "
              f"{engine.url.host}:{engine.url.port}/{engine.url.database}")
        counts = table_counts(engine)
        if not counts:
            print("No tables yet. Run: python -m src.db init")
        for table, n in counts.items():
            print(f"  {table:<12} {n:>10,} rows")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
