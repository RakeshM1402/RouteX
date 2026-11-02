CREATE TABLE dim_diurnal (
        diurnal_key INTEGER PRIMARY KEY,
        time_slot TEXT UNIQUE NOT NULL,
        period TEXT NOT NULL,
        start_hour INTEGER NOT NULL,
        end_hour INTEGER NOT NULL
    );

CREATE TABLE dim_geography (
        geography_key INTEGER PRIMARY KEY AUTOINCREMENT,
        state_id INTEGER,
        state_code TEXT NOT NULL,
        state_name TEXT UNIQUE NOT NULL,
        region TEXT NOT NULL,
        population INTEGER NOT NULL,
        area_sq_km REAL NOT NULL,
        population_density REAL NOT NULL,
        density_tier TEXT NOT NULL,
        districts_count INTEGER NOT NULL,
        centroid_latitude REAL,
        centroid_longitude REAL
    );

CREATE TABLE dim_highway (
        highway_key INTEGER PRIMARY KEY AUTOINCREMENT,
        highway_name TEXT UNIQUE NOT NULL,
        road_type TEXT NOT NULL,
        segment_count INTEGER NOT NULL,
        total_length_km REAL NOT NULL,
        corridor_tier TEXT NOT NULL
    );

CREATE TABLE dim_time (
        time_key INTEGER PRIMARY KEY,
        year INTEGER NOT NULL,
        quarter TEXT NOT NULL,
        month_number INTEGER NOT NULL,
        month_name TEXT NOT NULL,
        season TEXT NOT NULL
    );

CREATE TABLE fact_annual_safety (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        geography_key INTEGER NOT NULL,
        year INTEGER NOT NULL,
        fatalities INTEGER,
        total_accidents INTEGER,
        fatalities_per_lakh REAL,
        severity_index REAL,
        fatality_rank INTEGER,
        safety_risk_tier TEXT,
        FOREIGN KEY (geography_key) REFERENCES dim_geography(geography_key)
    );

CREATE TABLE fact_diurnal_accidents (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        geography_key INTEGER NOT NULL,
        year INTEGER NOT NULL,
        diurnal_key INTEGER NOT NULL,
        accidents_count INTEGER NOT NULL,
        share_of_annual_total_pct REAL,
        FOREIGN KEY (geography_key) REFERENCES dim_geography(geography_key),
        FOREIGN KEY (diurnal_key) REFERENCES dim_diurnal(diurnal_key)
    );

CREATE TABLE fact_monthly_accidents (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        geography_key INTEGER NOT NULL,
        time_key INTEGER NOT NULL,
        accidents_count INTEGER NOT NULL,
        FOREIGN KEY (geography_key) REFERENCES dim_geography(geography_key),
        FOREIGN KEY (time_key) REFERENCES dim_time(time_key)
    );

CREATE TABLE sqlite_sequence(name,seq);
