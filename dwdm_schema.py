"""
RouteX Data Warehousing & Data Mining (DWDM) - Star Schema DDL & Introspector
Defines FACT_TRIP_ANALYTICS and the 5 Dimension tables:
- DIM_DATE
- DIM_LOCATION
- DIM_TRAFFIC
- DIM_ACCIDENT
- DIM_SERVICE
Plus ETL_AUDIT_LOG for tracking ETL pipeline executions.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"

DDL_STATEMENTS = [
    # 1. DIM_DATE
    """
    CREATE TABLE IF NOT EXISTS DIM_DATE (
        Date_ID INTEGER PRIMARY KEY,
        Full_Date TEXT NOT NULL UNIQUE,
        Day INTEGER NOT NULL,
        Month INTEGER NOT NULL,
        Quarter TEXT NOT NULL,
        Year INTEGER NOT NULL,
        Weekday TEXT NOT NULL,
        Weekend_Status TEXT NOT NULL
    );
    """,
    # 2. DIM_LOCATION
    """
    CREATE TABLE IF NOT EXISTS DIM_LOCATION (
        Location_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Location_Name TEXT NOT NULL,
        City TEXT NOT NULL,
        State TEXT NOT NULL,
        Country TEXT NOT NULL DEFAULT 'India',
        Latitude REAL NOT NULL,
        Longitude REAL NOT NULL,
        Location_Type TEXT NOT NULL
    );
    """,
    # 3. DIM_TRAFFIC
    """
    CREATE TABLE IF NOT EXISTS DIM_TRAFFIC (
        Traffic_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Congestion_Level TEXT NOT NULL,
        Vehicle_Count INTEGER NOT NULL,
        Average_Speed REAL NOT NULL,
        Waiting_Time REAL NOT NULL,
        Traffic_Status TEXT NOT NULL
    );
    """,
    # 4. DIM_ACCIDENT
    """
    CREATE TABLE IF NOT EXISTS DIM_ACCIDENT (
        Accident_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Accident_Type TEXT NOT NULL,
        Accident_Severity TEXT NOT NULL,
        Accident_Zone TEXT NOT NULL,
        Accident_Count INTEGER NOT NULL,
        Accident_Date TEXT NOT NULL
    );
    """,
    # 5. DIM_SERVICE
    """
    CREATE TABLE IF NOT EXISTS DIM_SERVICE (
        Service_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Service_Name TEXT NOT NULL,
        Service_Type TEXT NOT NULL,
        Contact_Number TEXT NOT NULL,
        Latitude REAL NOT NULL,
        Longitude REAL NOT NULL,
        Availability_Status TEXT NOT NULL
    );
    """,
    # 6. Central Fact Table: FACT_TRIP_ANALYTICS
    """
    CREATE TABLE IF NOT EXISTS FACT_TRIP_ANALYTICS (
        Trip_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Date_ID INTEGER NOT NULL,
        Location_ID INTEGER NOT NULL,
        Traffic_ID INTEGER NOT NULL,
        Accident_ID INTEGER NOT NULL,
        Service_ID INTEGER NOT NULL,
        Distance_KM REAL NOT NULL,
        Travel_Time_Minutes REAL NOT NULL,
        Waiting_Time_Minutes REAL NOT NULL,
        Accident_Count INTEGER NOT NULL,
        Average_Speed REAL NOT NULL,
        FOREIGN KEY (Date_ID) REFERENCES DIM_DATE(Date_ID) ON DELETE RESTRICT,
        FOREIGN KEY (Location_ID) REFERENCES DIM_LOCATION(Location_ID) ON DELETE RESTRICT,
        FOREIGN KEY (Traffic_ID) REFERENCES DIM_TRAFFIC(Traffic_ID) ON DELETE RESTRICT,
        FOREIGN KEY (Accident_ID) REFERENCES DIM_ACCIDENT(Accident_ID) ON DELETE RESTRICT,
        FOREIGN KEY (Service_ID) REFERENCES DIM_SERVICE(Service_ID) ON DELETE RESTRICT
    );
    """,
    # 7. ETL_AUDIT_LOG
    """
    CREATE TABLE IF NOT EXISTS ETL_AUDIT_LOG (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT NOT NULL,
        extracted_records INTEGER DEFAULT 0,
        transformed_records INTEGER DEFAULT 0,
        loaded_records INTEGER DEFAULT 0,
        rejected_records INTEGER DEFAULT 0,
        duration_seconds REAL DEFAULT 0.0,
        notes TEXT
    );
    """
]

# Indexes for high-performance OLAP querying
INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_fact_trip_date ON FACT_TRIP_ANALYTICS(Date_ID);",
    "CREATE INDEX IF NOT EXISTS idx_fact_trip_location ON FACT_TRIP_ANALYTICS(Location_ID);",
    "CREATE INDEX IF NOT EXISTS idx_fact_trip_traffic ON FACT_TRIP_ANALYTICS(Traffic_ID);",
    "CREATE INDEX IF NOT EXISTS idx_fact_trip_accident ON FACT_TRIP_ANALYTICS(Accident_ID);",
    "CREATE INDEX IF NOT EXISTS idx_fact_trip_service ON FACT_TRIP_ANALYTICS(Service_ID);",
    "CREATE INDEX IF NOT EXISTS idx_dim_location_city ON DIM_LOCATION(City);",
    "CREATE INDEX IF NOT EXISTS idx_dim_location_state ON DIM_LOCATION(State);",
    "CREATE INDEX IF NOT EXISTS idx_dim_date_year_month ON DIM_DATE(Year, Month);",
    "CREATE INDEX IF NOT EXISTS idx_dim_traffic_congestion ON DIM_TRAFFIC(Congestion_Level);",
    "CREATE INDEX IF NOT EXISTS idx_dim_accident_severity ON DIM_ACCIDENT(Accident_Severity);",
    "CREATE INDEX IF NOT EXISTS idx_dim_service_type ON DIM_SERVICE(Service_Type);"
]


def init_star_schema(db_path: Optional[Path] = None):
    """Initializes the Star Schema tables and indexes in the SQLite warehouse."""
    target_db = db_path or DEFAULT_DB_PATH
    target_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    for stmt in DDL_STATEMENTS:
        cur.execute(stmt)

    for idx in INDEX_STATEMENTS:
        cur.execute(idx)

    conn.commit()
    conn.close()
    return True


def get_star_schema_metadata(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Dynamically inspects the SQLite database using PRAGMA commands
    to generate the metadata required for the Star Schema Architecture Visualizer.
    """
    target_db = db_path or DEFAULT_DB_PATH
    if not target_db.exists():
        init_star_schema(target_db)

    conn = sqlite3.connect(target_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    star_tables = [
        "FACT_TRIP_ANALYTICS",
        "DIM_DATE",
        "DIM_LOCATION",
        "DIM_TRAFFIC",
        "DIM_ACCIDENT",
        "DIM_SERVICE"
    ]

    table_descriptions = {
        "FACT_TRIP_ANALYTICS": "Central Fact Table storing quantitative measurements of travel distance, journey duration, signal wait times, speed, and accident occurrences across dimensions.",
        "DIM_DATE": "Temporal dimension tracking calendar dates, quarters, months, days, weekdays, and weekend classifications for seasonal & periodic trend slicing.",
        "DIM_LOCATION": "Spatial dimension capturing geographical hierarchy (Country -> State -> City -> Location), coordinates, and road corridor classifications.",
        "DIM_TRAFFIC": "Traffic condition dimension representing congestion intensity, vehicle volume metrics, speed categories, and road flow status.",
        "DIM_ACCIDENT": "Safety dimension detailing accident events, impact severity (Fatal, Grievous, Minor), collision types, and high-risk blackspot zones.",
        "DIM_SERVICE": "Points of Interest & Emergency infrastructure dimension detailing hospitals, EV charging points, fuel stations, vehicle repair, and amenities."
    }

    table_icons = {
        "FACT_TRIP_ANALYTICS": "📊",
        "DIM_DATE": "📅",
        "DIM_LOCATION": "📍",
        "DIM_TRAFFIC": "🚦",
        "DIM_ACCIDENT": "⚠️",
        "DIM_SERVICE": "🏥"
    }

    tables_meta = []
    relationships = []

    for tbl_name in star_tables:
        # Check if table exists
        exists = cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl_name,)).fetchone()
        if not exists:
            continue

        # Get row count
        count = cur.execute(f"SELECT COUNT(*) FROM [{tbl_name}]").fetchone()[0]

        # Get columns via PRAGMA table_info
        cols_info = cur.execute(f"PRAGMA table_info([{tbl_name}])").fetchall()
        columns = []
        for col in cols_info:
            is_pk = bool(col["pk"])
            columns.append({
                "cid": col["cid"],
                "name": col["name"],
                "type": col["type"],
                "notnull": bool(col["notnull"]),
                "dflt_value": col["dflt_value"],
                "pk": is_pk,
                "is_fk": False  # will be updated below
            })

        # Get Foreign Keys via PRAGMA foreign_key_list
        fks_info = cur.execute(f"PRAGMA foreign_key_list([{tbl_name}])").fetchall()
        fks = []
        for fk in fks_info:
            from_col = fk["from"]
            to_table = fk["table"]
            to_col = fk["to"]
            fks.append({
                "from_column": from_col,
                "to_table": to_table,
                "to_column": to_col
            })
            # Mark column as FK
            for col in columns:
                if col["name"] == from_col:
                    col["is_fk"] = True

            # Register relationship edge
            relationships.append({
                "from_table": tbl_name,
                "from_column": from_col,
                "to_table": to_table,
                "to_column": to_col,
                "cardinality": "N:1",
                "label": f"{tbl_name}.{from_col} ➔ {to_table}.{to_col}"
            })

        # Get sample rows (up to 5)
        cur.row_factory = sqlite3.Row
        sample_rows = [dict(r) for r in cur.execute(f"SELECT * FROM [{tbl_name}] LIMIT 5").fetchall()]

        tables_meta.append({
            "name": tbl_name,
            "is_fact": tbl_name.startswith("FACT_"),
            "description": table_descriptions.get(tbl_name, ""),
            "icon": table_icons.get(tbl_name, "📁"),
            "row_count": count,
            "columns": columns,
            "foreign_keys": fks,
            "sample_rows": sample_rows
        })

    conn.close()

    return {
        "status": "success",
        "schema_name": "RouteX DWDM Star Schema",
        "fact_table": "FACT_TRIP_ANALYTICS",
        "tables": tables_meta,
        "relationships": relationships
    }


if __name__ == "__main__":
    print(f"Initializing RouteX Star Schema in {DEFAULT_DB_PATH}...")
    init_star_schema()
    meta = get_star_schema_metadata()
    print(f"Success! {len(meta['tables'])} tables defined with {len(meta['relationships'])} relationships.")
    for t in meta["tables"]:
        print(f" - {t['name']} ({t['row_count']} records, {len(t['columns'])} columns)")
