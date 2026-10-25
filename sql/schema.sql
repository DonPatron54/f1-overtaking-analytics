-- F1 Overtaking Analytics: database schema (PostgreSQL 16).
-- Idempotent: safe to run repeatedly (python -m src.db init).
-- Grain of the analysis table `pairs`: one pair of consecutive cars x one lap.

CREATE TABLE IF NOT EXISTS circuits (
    circuit_id          TEXT PRIMARY KEY,            -- Jolpica circuitId
    name                TEXT NOT NULL,
    locality            TEXT,
    country             TEXT,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    circuit_type        TEXT,                        -- Wikipedia: street / race / road
    length_km           NUMERIC(6, 3),
    turns               INT,
    longest_straight_m  NUMERIC(8, 1),               -- computed from GeoJSON
    geojson_id          TEXT                         -- id in bacinger/f1-circuits
);

CREATE TABLE IF NOT EXISTS races (
    race_id     SERIAL PRIMARY KEY,
    season      INT  NOT NULL,
    round       INT  NOT NULL,
    race_name   TEXT,
    circuit_id  TEXT NOT NULL REFERENCES circuits (circuit_id),
    race_date   DATE,
    era         TEXT NOT NULL CHECK (era IN ('E1', 'E2', 'E3')),
    total_laps  INT,
    UNIQUE (season, round)
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id    TEXT PRIMARY KEY,                   -- Jolpica driverId
    code         TEXT,
    given_name   TEXT,
    family_name  TEXT,
    nationality  TEXT
);

-- Maps FastF1 identifiers (abbreviation, car number) to Jolpica driverId per season.
CREATE TABLE IF NOT EXISTS driver_map (
    season         INT  NOT NULL,
    abbreviation   TEXT NOT NULL,
    driver_number  INT,
    driver_id      TEXT NOT NULL REFERENCES drivers (driver_id),
    PRIMARY KEY (season, abbreviation)
);

CREATE TABLE IF NOT EXISTS results (
    race_id     INT  NOT NULL REFERENCES races (race_id),
    driver_id   TEXT NOT NULL REFERENCES drivers (driver_id),
    team        TEXT,
    grid        INT,
    quali_pos   INT,
    finish_pos  INT,
    status      TEXT,
    PRIMARY KEY (race_id, driver_id)
);

CREATE TABLE IF NOT EXISTS laps (
    race_id       INT  NOT NULL REFERENCES races (race_id),
    driver_id     TEXT NOT NULL REFERENCES drivers (driver_id),
    lap_number    INT  NOT NULL,
    lap_time_s    NUMERIC(8, 3),
    time_end_s    NUMERIC(10, 3),                    -- session time at lap end (s)
    position      INT,
    stint         INT,
    compound      TEXT,
    tyre_life     INT,
    pit_in        BOOLEAN,
    pit_out       BOOLEAN,
    track_status  TEXT,                              -- FastF1 code string, e.g. '14'
    is_accurate   BOOLEAN,
    PRIMARY KEY (race_id, driver_id, lap_number)
);

CREATE TABLE IF NOT EXISTS weather (
    race_id     INT NOT NULL REFERENCES races (race_id),
    time_s      NUMERIC(10, 3) NOT NULL,             -- session time (s)
    air_temp    NUMERIC(5, 2),
    track_temp  NUMERIC(5, 2),
    humidity    NUMERIC(5, 2),
    pressure    NUMERIC(7, 2),
    rainfall    BOOLEAN,
    wind_speed  NUMERIC(5, 2),
    PRIMARY KEY (race_id, time_s)
);

-- Analysis table: only information known at the start of the lap (no leakage).
CREATE TABLE IF NOT EXISTS pairs (
    pair_id        SERIAL PRIMARY KEY,
    race_id        INT  NOT NULL REFERENCES races (race_id),
    lap_number     INT  NOT NULL,
    driver_ahead   TEXT NOT NULL REFERENCES drivers (driver_id),
    driver_behind  TEXT NOT NULL REFERENCES drivers (driver_id),
    position_a     INT,
    gap_s          NUMERIC(6, 3),
    tyre_age_diff  INT,
    compound_adv   INT,
    pace_diff      NUMERIC(6, 3),
    quali_gap      INT,
    lap_frac       NUMERIC(5, 4),
    same_team      BOOLEAN,
    air_temp       NUMERIC(5, 2),
    track_temp     NUMERIC(5, 2),
    rainfall       BOOLEAN,
    overtake       SMALLINT NOT NULL CHECK (overtake IN (0, 1)),
    UNIQUE (race_id, lap_number, driver_ahead, driver_behind)
);

CREATE INDEX IF NOT EXISTS idx_races_season   ON races (season);
CREATE INDEX IF NOT EXISTS idx_laps_race_lap  ON laps (race_id, lap_number);
CREATE INDEX IF NOT EXISTS idx_pairs_race     ON pairs (race_id);
