"""
RouteX Data Warehouse & OLAP Cube Builder
Builds the multidimensional Star Schema database (routex_olap.db)
and materializes OLAP analytical cubes in 'final dataset/'.
"""

import os
import csv
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FINAL_DIR = BASE_DIR / "final dataset"
DB_PATH = FINAL_DIR / "routex_olap.db"

REGION_MAP = {
    # North
    'Jammu and Kashmir': 'North', 'Himachal Pradesh': 'North', 'Punjab': 'North',
    'Chandigarh': 'North', 'Uttarakhand': 'North', 'Haryana': 'North',
    'Delhi': 'North', 'Rajasthan': 'North', 'Ladakh': 'North',
    # Central
    'Uttar Pradesh': 'Central', 'Madhya Pradesh': 'Central', 'Chhattisgarh': 'Central',
    # East
    'Bihar': 'East', 'Jharkhand': 'East', 'Odisha': 'East', 'West Bengal': 'East',
    # West
    'Gujarat': 'West', 'Maharashtra': 'West', 'Goa': 'West',
    'Dadra and Nagar Haveli and Daman and Diu': 'West',
    # South
    'Andhra Pradesh': 'South', 'Karnataka': 'South', 'Kerala': 'South',
    'Tamil Nadu': 'South', 'Telangana': 'South', 'Puducherry': 'South',
    'Lakshadweep': 'South', 'Andaman and Nicobar Islands': 'South',
    # North-East
    'Assam': 'North-East', 'Arunachal Pradesh': 'North-East', 'Manipur': 'North-East',
    'Meghalaya': 'North-East', 'Mizoram': 'North-East', 'Nagaland': 'North-East',
    'Sikkim': 'North-East', 'Tripura': 'North-East'
}

def get_density_tier(density: float) -> str:
    if density >= 1000.0:
        return 'Ultra-High Density'
    elif density >= 500.0:
        return 'High Density'
    elif density >= 200.0:
        return 'Moderate Density'
    else:
        return 'Low Density'

def build_olap():
    print("=" * 65)
    print("RouteX OLAP Cube Builder: Constructing Star Schema & Cubes")
    print("=" * 65)

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f" -> Removed old database at {DB_PATH.name}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # ---------------------------------------------------------
    # 1. CREATE DIMENSION TABLES
    # ---------------------------------------------------------
    print("\n[1/6] Creating Star Schema Dimension Tables...")

    cursor.execute("""
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
    """)

    cursor.execute("""
    CREATE TABLE dim_time (
        time_key INTEGER PRIMARY KEY,
        year INTEGER NOT NULL,
        quarter TEXT NOT NULL,
        month_number INTEGER NOT NULL,
        month_name TEXT NOT NULL,
        season TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE dim_diurnal (
        diurnal_key INTEGER PRIMARY KEY,
        time_slot TEXT UNIQUE NOT NULL,
        period TEXT NOT NULL,
        start_hour INTEGER NOT NULL,
        end_hour INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE dim_highway (
        highway_key INTEGER PRIMARY KEY AUTOINCREMENT,
        highway_name TEXT UNIQUE NOT NULL,
        road_type TEXT NOT NULL,
        segment_count INTEGER NOT NULL,
        total_length_km REAL NOT NULL,
        corridor_tier TEXT NOT NULL
    );
    """)

    # ---------------------------------------------------------
    # 2. CREATE FACT TABLES
    # ---------------------------------------------------------
    print("\n[2/6] Creating Fact Tables...")

    cursor.execute("""
    CREATE TABLE fact_monthly_accidents (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        geography_key INTEGER NOT NULL,
        time_key INTEGER NOT NULL,
        accidents_count INTEGER NOT NULL,
        FOREIGN KEY (geography_key) REFERENCES dim_geography(geography_key),
        FOREIGN KEY (time_key) REFERENCES dim_time(time_key)
    );
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    # ---------------------------------------------------------
    # 3. POPULATE DIMENSIONS
    # ---------------------------------------------------------
    print("\n[3/6] Loading Dimensions...")

    # Load dim_geography
    state_key_map = {}
    with open(FINAL_DIR / "dim_state.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            st = r['state_name']
            reg = REGION_MAP.get(st, 'Other')
            pop = int(r['population'])
            area = float(r['area_sq_km'])
            dens = float(r['population_density_per_sq_km'])
            tier = get_density_tier(dens)

            cursor.execute("""
            INSERT INTO dim_geography (
                state_id, state_code, state_name, region, population, area_sq_km,
                population_density, density_tier, districts_count, centroid_latitude, centroid_longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(r['state_id']), r['state_code'], st, reg, pop, area, dens, tier,
                int(r['districts_count']), float(r['centroid_latitude']), float(r['centroid_longitude'])
            ))
            state_key_map[st] = cursor.lastrowid
    print(f" -> dim_geography loaded ({len(state_key_map)} states)")

    # Load dim_time (for years 2001 to 2014, months 1 to 12)
    month_meta = [
        (1, 'January', 'Q1', 'Winter'),
        (2, 'February', 'Q1', 'Winter'),
        (3, 'March', 'Q1', 'Pre-Monsoon/Summer'),
        (4, 'April', 'Q2', 'Pre-Monsoon/Summer'),
        (5, 'May', 'Q2', 'Pre-Monsoon/Summer'),
        (6, 'June', 'Q2', 'Monsoon'),
        (7, 'July', 'Q3', 'Monsoon'),
        (8, 'August', 'Q3', 'Monsoon'),
        (9, 'September', 'Q3', 'Monsoon'),
        (10, 'October', 'Q4', 'Post-Monsoon'),
        (11, 'November', 'Q4', 'Post-Monsoon'),
        (12, 'December', 'Q4', 'Winter')
    ]
    time_key_map = {}
    for yr in range(2001, 2015):
        for m_num, m_name, q, s in month_meta:
            t_key = yr * 100 + m_num
            cursor.execute("""
            INSERT INTO dim_time (time_key, year, quarter, month_number, month_name, season)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (t_key, yr, q, m_num, m_name, s))
            time_key_map[(yr, m_num)] = t_key
    print(f" -> dim_time loaded ({len(time_key_map)} periods)")

    # Load dim_diurnal
    diurnal_slots = [
        (1, '00:00 - 03:00', 'Night', 0, 3),
        (2, '03:00 - 06:00', 'Night', 3, 6),
        (3, '06:00 - 09:00', 'Day', 6, 9),
        (4, '09:00 - 12:00', 'Day', 9, 12),
        (5, '12:00 - 15:00', 'Day', 12, 15),
        (6, '15:00 - 18:00', 'Day', 15, 18),
        (7, '18:00 - 21:00', 'Night', 18, 21),
        (8, '21:00 - 24:00', 'Night', 21, 24)
    ]
    diurnal_key_map = {}
    for d_key, slot, per, sh, eh in diurnal_slots:
        cursor.execute("""
        INSERT INTO dim_diurnal (diurnal_key, time_slot, period, start_hour, end_hour)
        VALUES (?, ?, ?, ?, ?)
        """, (d_key, slot, per, sh, eh))
        diurnal_key_map[slot] = d_key
    print(f" -> dim_diurnal loaded ({len(diurnal_slots)} time slots)")

    # Load dim_highway
    hw_rows = 0
    with open(FINAL_DIR / "dim_national_highways.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cursor.execute("""
            INSERT INTO dim_highway (highway_name, road_type, segment_count, total_length_km, corridor_tier)
            VALUES (?, ?, ?, ?, ?)
            """, (
                r['highway_name'], r['road_type'], int(r['segment_count']),
                float(r['total_length_km']), r['corridor_tier']
            ))
            hw_rows += 1
    print(f" -> dim_highway loaded ({hw_rows} highways)")

    # ---------------------------------------------------------
    # 4. POPULATE FACTS
    # ---------------------------------------------------------
    print("\n[4/6] Loading Fact Tables...")

    # Load fact_monthly_accidents
    m_fact_rows = 0
    with open(FINAL_DIR / "fact_accidents_monthly_trend_long.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        batch = []
        for r in reader:
            geo_key = state_key_map.get(r['state_name'])
            t_key = time_key_map.get((int(r['year']), int(r['month_number'])))
            if geo_key and t_key:
                batch.append((geo_key, t_key, int(r['accidents_count'])))
                m_fact_rows += 1
        cursor.executemany("""
        INSERT INTO fact_monthly_accidents (geography_key, time_key, accidents_count)
        VALUES (?, ?, ?)
        """, batch)
    print(f" -> fact_monthly_accidents loaded ({m_fact_rows} rows)")

    # Load fact_diurnal_accidents
    d_fact_rows = 0
    with open(FINAL_DIR / "fact_accidents_time_of_day_long.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        batch = []
        for r in reader:
            geo_key = state_key_map.get(r['state_name'])
            d_key = diurnal_key_map.get(r['time_slot'])
            if geo_key and d_key:
                batch.append((
                    geo_key, int(r['year']), d_key,
                    int(r['accidents_count']),
                    float(r['share_of_annual_total_pct']) if r['share_of_annual_total_pct'] else None
                ))
                d_fact_rows += 1
        cursor.executemany("""
        INSERT INTO fact_diurnal_accidents (geography_key, year, diurnal_key, accidents_count, share_of_annual_total_pct)
        VALUES (?, ?, ?, ?, ?)
        """, batch)
    print(f" -> fact_diurnal_accidents loaded ({d_fact_rows} rows)")

    # Load fact_annual_safety (2020-2024 from fact_state_safety_recent)
    safety_fact_rows = 0
    with open(FINAL_DIR / "fact_state_safety_recent.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        batch = []
        for r in reader:
            geo_key = state_key_map.get(r['state_name'])
            if not geo_key: continue
            
            risk_tier = r['safety_risk_tier']
            pop = int(r['population'])

            # Years 2020 to 2024
            for yr in [2020, 2021, 2022, 2023, 2024]:
                k_val = int(r[f'fatalities_{yr}']) if r.get(f'fatalities_{yr}') else None
                acc_val = int(r[f'total_accidents_{yr}']) if yr <= 2022 and r.get(f'total_accidents_{yr}') else None
                per_lakh = round((k_val / pop) * 100000.0, 2) if (k_val and pop > 0) else None
                sev = round((k_val / acc_val) * 100.0, 2) if (k_val and acc_val and acc_val > 0) else None
                rnk = int(r['fatality_rank_2024']) if yr == 2024 and r.get('fatality_rank_2024') else None

                batch.append((geo_key, yr, k_val, acc_val, per_lakh, sev, rnk, risk_tier))
                safety_fact_rows += 1

        cursor.executemany("""
        INSERT INTO fact_annual_safety (
            geography_key, year, fatalities, total_accidents, fatalities_per_lakh,
            severity_index, fatality_rank, safety_risk_tier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
    print(f" -> fact_annual_safety loaded ({safety_fact_rows} rows)")

    # Build Indices for lightning-fast OLAP queries
    print(" -> Creating star schema indexes...")
    cursor.execute("CREATE INDEX idx_fma_geo_time ON fact_monthly_accidents(geography_key, time_key);")
    cursor.execute("CREATE INDEX idx_fda_geo_yr_diurn ON fact_diurnal_accidents(geography_key, year, diurnal_key);")
    cursor.execute("CREATE INDEX idx_fas_geo_yr ON fact_annual_safety(geography_key, year);")

    # ---------------------------------------------------------
    # 5. MATERIALIZE OLAP CUBES (Views & Tables)
    # ---------------------------------------------------------
    print("\n[5/6] Materializing Multidimensional OLAP Cubes...")

    # Cube 1: Temporal & Seasonality Cube
    cursor.execute("""
    CREATE TABLE cube_temporal_seasonality AS
    SELECT 
        g.region,
        g.state_name,
        t.year,
        t.season,
        t.quarter,
        SUM(f.accidents_count) AS total_accidents,
        ROUND(AVG(f.accidents_count), 2) AS avg_monthly_accidents,
        MIN(f.accidents_count) AS min_monthly_accidents,
        MAX(f.accidents_count) AS max_monthly_accidents
    FROM fact_monthly_accidents f
    JOIN dim_geography g ON f.geography_key = g.geography_key
    JOIN dim_time t ON f.time_key = t.time_key
    GROUP BY g.region, g.state_name, t.year, t.season, t.quarter;
    """)

    # Cube 2: Diurnal Risk Cube (Day vs Night & 3-Hour Slot)
    cursor.execute("""
    CREATE TABLE cube_diurnal_risk AS
    SELECT 
        g.region,
        g.state_name,
        f.year,
        d.period AS day_or_night,
        d.time_slot,
        SUM(f.accidents_count) AS total_accidents,
        ROUND(AVG(f.share_of_annual_total_pct), 2) AS avg_time_slot_share_pct
    FROM fact_diurnal_accidents f
    JOIN dim_geography g ON f.geography_key = g.geography_key
    JOIN dim_diurnal d ON f.diurnal_key = d.diurnal_key
    GROUP BY g.region, g.state_name, f.year, d.period, d.time_slot;
    """)

    # Cube 3: State Safety & Fatality Cube (Recent 2020-2024)
    cursor.execute("""
    CREATE TABLE cube_state_safety_measures AS
    SELECT 
        g.region,
        g.state_name,
        g.population,
        g.density_tier,
        s.safety_risk_tier,
        s.year,
        s.fatalities,
        s.total_accidents,
        s.fatalities_per_lakh,
        s.severity_index,
        s.fatality_rank
    FROM fact_annual_safety s
    JOIN dim_geography g ON s.geography_key = g.geography_key;
    """)

    # Cube 4: Regional Demographic & Accident Summary
    cursor.execute("""
    CREATE TABLE cube_regional_demographics AS
    SELECT 
        g.region,
        COUNT(DISTINCT g.state_name) AS states_count,
        SUM(g.population) AS total_population,
        ROUND(SUM(g.area_sq_km), 2) AS total_area_sq_km,
        ROUND(SUM(g.population) / SUM(g.area_sq_km), 2) AS regional_population_density,
        SUM(CASE WHEN s.year = 2024 THEN s.fatalities ELSE 0 END) AS total_fatalities_2024,
        ROUND((SUM(CASE WHEN s.year = 2024 THEN s.fatalities ELSE 0 END) * 100000.0) / SUM(g.population), 2) AS fatalities_per_lakh_2024
    FROM dim_geography g
    LEFT JOIN fact_annual_safety s ON g.geography_key = s.geography_key AND s.year = 2024
    GROUP BY g.region;
    """)

    conn.commit()
    print(" -> All 4 OLAP Cubes materialized in routex_olap.db")

    # ---------------------------------------------------------
    # 6. EXPORT CUBES TO CSV IN 'final dataset/'
    # ---------------------------------------------------------
    print("\n[6/6] Exporting OLAP Cubes to CSV...")

    cube_exports = [
        ("cube_temporal_seasonality", "olap_cube_temporal_seasonality.csv"),
        ("cube_diurnal_risk", "olap_cube_diurnal_risk.csv"),
        ("cube_state_safety_measures", "olap_cube_state_safety_measures.csv"),
        ("cube_regional_demographics", "olap_cube_regional_demographics.csv")
    ]

    for table_name, out_csv in cube_exports:
        cursor.execute(f"SELECT * FROM {table_name}")
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        out_path = FINAL_DIR / out_csv
        with open(out_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            writer.writerows(rows)
        print(f" -> Exported {out_csv} ({len(rows)} rows)")

    conn.close()

    print("\n" + "=" * 65)
    print("OLAP Cube Construction Completed Successfully!")
    print(f"Database location: {DB_PATH}")
    print("=" * 65)

if __name__ == "__main__":
    build_olap()
