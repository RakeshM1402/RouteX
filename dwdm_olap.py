"""
RouteX DWDM OLAP Analytical Engine
Implements the 5 core OLAP operations on the Star Schema:
1. Roll-up (Location -> City -> State -> Country)
2. Drill-down (Country -> State -> City -> Location)
3. Slice (Single-dimension filter: Year, City, Congestion)
4. Dice (Multi-dimensional subcube: City + Year + Congestion)
5. Pivot (2D Cross-tabulation: Rows x Columns)
"""

import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"


class RouteXStarOLAP:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}. Run dwdm_etl.py first.")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    # 1. ROLL-UP
    def rollup(self, level: str = "city", year: Optional[int] = None) -> Dict[str, Any]:
        """
        Roll-up hierarchy: Location -> City -> State -> Country
        Aggregates trip volume, accident totals, average speed, and travel time.
        """
        level = level.lower().strip()
        group_by_map = {
            "country": "l.Country",
            "state": "l.State, l.Country",
            "city": "l.City, l.State",
            "location": "l.Location_Name, l.City, l.State"
        }

        select_cols = {
            "country": "l.Country as hierarchy_name, 'Country' as level",
            "state": "l.State as hierarchy_name, l.Country as parent_name, 'State' as level",
            "city": "l.City as hierarchy_name, l.State as parent_name, 'City' as level",
            "location": "l.Location_Name as hierarchy_name, l.City as parent_name, 'Location' as level"
        }

        if level not in group_by_map:
            level = "city"

        where_clauses = []
        params = []
        if year:
            where_clauses.append("d.Year = ?")
            params.append(year)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT 
                {select_cols[level]},
                COUNT(f.Trip_ID) as total_trips,
                SUM(f.Accident_Count) as total_accidents,
                ROUND(AVG(f.Average_Speed), 1) as avg_speed_kmh,
                ROUND(AVG(f.Travel_Time_Minutes), 1) as avg_travel_time_min,
                ROUND(AVG(f.Waiting_Time_Minutes), 1) as avg_waiting_time_min,
                ROUND(SUM(f.Distance_KM), 1) as total_distance_km
            FROM FACT_TRIP_ANALYTICS f
            JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
            JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
            JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
            JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
            {where_sql}
            GROUP BY {group_by_map[level]}
            ORDER BY total_trips DESC
            LIMIT 50;
        """

        rows = self._query(sql, tuple(params))
        return {
            "operation": "Roll-up",
            "hierarchy_level": level,
            "record_count": len(rows),
            "data": rows
        }

    # 2. DRILL-DOWN
    def drilldown(self, state: Optional[str] = None, city: Optional[str] = None) -> Dict[str, Any]:
        """
        Drill-down: Country -> State -> City -> Location
        Expands into granular corridors, waiting times, and accident severities.
        """
        if city:
            # Drill-down to individual locations in this city
            sql = """
                SELECT 
                    l.Location_Name,
                    l.City,
                    l.Location_Type,
                    t.Congestion_Level,
                    t.Traffic_Status,
                    a.Accident_Severity,
                    a.Accident_Zone,
                    COUNT(f.Trip_ID) as trip_count,
                    SUM(f.Accident_Count) as accident_count,
                    ROUND(AVG(f.Average_Speed), 1) as avg_speed,
                    ROUND(AVG(f.Waiting_Time_Minutes), 1) as avg_wait_time
                FROM FACT_TRIP_ANALYTICS f
                JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
                JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
                JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
                WHERE LOWER(l.City) LIKE '%' || LOWER(?) || '%'
                GROUP BY l.Location_Name, t.Congestion_Level, a.Accident_Severity
                ORDER BY trip_count DESC
                LIMIT 50;
            """
            rows = self._query(sql, (city,))
            level = "Individual Locations"
            context = f"City matching: {city}"
        elif state:
            # Drill-down to cities in this state
            sql = """
                SELECT 
                    l.City,
                    l.State,
                    COUNT(DISTINCT l.Location_ID) as location_count,
                    COUNT(f.Trip_ID) as total_trips,
                    SUM(f.Accident_Count) as total_accidents,
                    ROUND(AVG(f.Average_Speed), 1) as avg_speed,
                    ROUND(AVG(f.Waiting_Time_Minutes), 1) as avg_wait_time
                FROM FACT_TRIP_ANALYTICS f
                JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
                WHERE LOWER(l.State) LIKE '%' || LOWER(?) || '%'
                GROUP BY l.City, l.State
                ORDER BY total_trips DESC
                LIMIT 50;
            """
            rows = self._query(sql, (state,))
            level = "Cities in State"
            context = f"State matching: {state}"
        else:
            # Top-level: All states
            sql = """
                SELECT 
                    l.State,
                    l.Country,
                    COUNT(DISTINCT l.City) as city_count,
                    COUNT(f.Trip_ID) as total_trips,
                    SUM(f.Accident_Count) as total_accidents,
                    ROUND(AVG(f.Average_Speed), 1) as avg_speed,
                    ROUND(AVG(f.Waiting_Time_Minutes), 1) as avg_wait_time
                FROM FACT_TRIP_ANALYTICS f
                JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
                GROUP BY l.State, l.Country
                ORDER BY total_trips DESC
                LIMIT 50;
            """
            rows = self._query(sql)
            level = "States in Country"
            context = "National Overview (India)"

        return {
            "operation": "Drill-down",
            "drill_level": level,
            "context": context,
            "record_count": len(rows),
            "data": rows
        }

    # 3. SLICE
    def slice(self, dimension: str, value: Any) -> Dict[str, Any]:
        """
        Slice: Filters the multidimensional cube across a single dimension:
        e.g., Year = 2024, City = 'Bengaluru', Congestion_Level = 'Severe'
        """
        dim = dimension.lower().strip()
        where_col = ""
        dim_label = ""

        if dim in ["year", "d.year"]:
            where_col = "d.Year"
            dim_label = f"Year = {value}"
        elif dim in ["city", "l.city"]:
            where_col = "LOWER(l.City)"
            value = str(value).lower()
            dim_label = f"City = {value.title()}"
        elif dim in ["congestion", "congestion_level", "t.congestion_level"]:
            where_col = "LOWER(t.Congestion_Level)"
            value = str(value).lower()
            dim_label = f"Congestion Level = {value.title()}"
        elif dim in ["severity", "accident_severity", "a.accident_severity"]:
            where_col = "LOWER(a.Accident_Severity)"
            value = str(value).lower()
            dim_label = f"Accident Severity = {value.title()}"
        elif dim in ["service", "service_type", "s.service_type"]:
            where_col = "LOWER(s.Service_Type)"
            value = str(value).lower()
            dim_label = f"Service Type = {value.title()}"
        else:
            where_col = "d.Year"
            dim_label = f"Year = {value}"

        sql = f"""
            SELECT 
                l.City,
                l.State,
                d.Quarter,
                t.Congestion_Level,
                t.Traffic_Status,
                a.Accident_Severity,
                a.Accident_Zone,
                COUNT(f.Trip_ID) as trip_count,
                SUM(f.Accident_Count) as accident_count,
                ROUND(AVG(f.Average_Speed), 1) as avg_speed,
                ROUND(AVG(f.Travel_Time_Minutes), 1) as avg_travel_time
            FROM FACT_TRIP_ANALYTICS f
            JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
            JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
            JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
            JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
            JOIN DIM_SERVICE s ON f.Service_ID = s.Service_ID
            WHERE {where_col} = ?
            GROUP BY l.City, d.Quarter, t.Congestion_Level
            ORDER BY trip_count DESC
            LIMIT 50;
        """

        rows = self._query(sql, (value,))
        return {
            "operation": "Slice",
            "filter_applied": dim_label,
            "record_count": len(rows),
            "data": rows
        }

    # 4. DICE
    def dice(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dice: Sub-cube filter across multiple dimensions:
        e.g., City + Year, City + Congestion Level, Accident Severity + Location
        """
        where_clauses = []
        params = []
        applied_labels = []

        if "city" in filters and filters["city"]:
            where_clauses.append("LOWER(l.City) LIKE '%' || LOWER(?) || '%'")
            params.append(filters["city"])
            applied_labels.append(f"City: {filters['city']}")

        if "year" in filters and filters["year"]:
            where_clauses.append("d.Year = ?")
            params.append(int(filters["year"]))
            applied_labels.append(f"Year: {filters['year']}")

        if "congestion" in filters and filters["congestion"]:
            where_clauses.append("LOWER(t.Congestion_Level) = LOWER(?)")
            params.append(filters["congestion"])
            applied_labels.append(f"Congestion: {filters['congestion']}")

        if "severity" in filters and filters["severity"]:
            where_clauses.append("LOWER(a.Accident_Severity) = LOWER(?)")
            params.append(filters["severity"])
            applied_labels.append(f"Severity: {filters['severity']}")

        if "weekend_status" in filters and filters["weekend_status"]:
            where_clauses.append("LOWER(d.Weekend_Status) = LOWER(?)")
            params.append(filters["weekend_status"])
            applied_labels.append(f"Period: {filters['weekend_status']}")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT 
                l.City,
                l.State,
                d.Year,
                d.Quarter,
                d.Weekend_Status,
                t.Congestion_Level,
                a.Accident_Severity,
                a.Accident_Zone,
                COUNT(f.Trip_ID) as trip_count,
                SUM(f.Accident_Count) as accident_count,
                ROUND(AVG(f.Average_Speed), 1) as avg_speed,
                ROUND(AVG(f.Travel_Time_Minutes), 1) as avg_travel_time
            FROM FACT_TRIP_ANALYTICS f
            JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
            JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
            JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
            JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
            {where_sql}
            GROUP BY l.City, d.Year, t.Congestion_Level, a.Accident_Severity
            ORDER BY trip_count DESC
            LIMIT 50;
        """

        rows = self._query(sql, tuple(params))
        return {
            "operation": "Dice",
            "filters_applied": applied_labels,
            "record_count": len(rows),
            "data": rows
        }

    # 5. PIVOT (Cross-Tabulation)
    def pivot(self, row_dim: str = "city", col_dim: str = "year", measure: str = "accidents") -> Dict[str, Any]:
        """
        Pivot: Dynamically transforms row records into a 2D cross-tabulation:
        - Traffic by City and Year
        - Accidents by City and Severity
        - Travel Time by Location and Month
        """
        row_dim = row_dim.lower().strip()
        col_dim = col_dim.lower().strip()
        measure = measure.lower().strip()

        # Dimension mapping
        dim_col_map = {
            "city": ("l.City", "City"),
            "state": ("l.State", "State"),
            "year": ("d.Year", "Year"),
            "quarter": ("d.Quarter", "Quarter"),
            "month": ("d.Month", "Month"),
            "congestion": ("t.Congestion_Level", "Congestion_Level"),
            "severity": ("a.Accident_Severity", "Accident_Severity"),
            "service_type": ("s.Service_Type", "Service_Type"),
            "location_type": ("l.Location_Type", "Location_Type")
        }

        measure_map = {
            "accidents": "SUM(f.Accident_Count)",
            "trips": "COUNT(f.Trip_ID)",
            "speed": "ROUND(AVG(f.Average_Speed), 1)",
            "travel_time": "ROUND(AVG(f.Travel_Time_Minutes), 1)",
            "waiting_time": "ROUND(AVG(f.Waiting_Time_Minutes), 1)"
        }

        r_expr, r_label = dim_col_map.get(row_dim, ("l.City", "City"))
        c_expr, c_label = dim_col_map.get(col_dim, ("d.Year", "Year"))
        m_expr = measure_map.get(measure, "SUM(f.Accident_Count)")

        # First, find top columns
        cur = self.conn.cursor()
        col_sql = f"""
            SELECT DISTINCT {c_expr} as col_val 
            FROM FACT_TRIP_ANALYTICS f
            JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
            JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
            JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
            JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
            JOIN DIM_SERVICE s ON f.Service_ID = s.Service_ID
            WHERE {c_expr} IS NOT NULL
            ORDER BY col_val ASC
            LIMIT 12;
        """
        cols_raw = [str(r[0]) for r in cur.execute(col_sql).fetchall()]

        # Find top rows
        row_sql = f"""
            SELECT {r_expr} as row_val, COUNT(f.Trip_ID) as cnt
            FROM FACT_TRIP_ANALYTICS f
            JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
            JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
            JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
            JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
            JOIN DIM_SERVICE s ON f.Service_ID = s.Service_ID
            WHERE {r_expr} IS NOT NULL
            GROUP BY {r_expr}
            ORDER BY cnt DESC
            LIMIT 15;
        """
        rows_raw = [str(r[0]) for r in cur.execute(row_sql).fetchall()]

        # Query all intersecting cells
        cell_sql = f"""
            SELECT 
                {r_expr} as row_val,
                {c_expr} as col_val,
                {m_expr} as val
            FROM FACT_TRIP_ANALYTICS f
            JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
            JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
            JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
            JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
            JOIN DIM_SERVICE s ON f.Service_ID = s.Service_ID
            GROUP BY {r_expr}, {c_expr};
        """
        cells = cur.execute(cell_sql).fetchall()

        matrix = {}
        for r_val in rows_raw:
            matrix[r_val] = {c_val: 0 for c_val in cols_raw}

        for r_val, c_val, val in cells:
            r_str = str(r_val)
            c_str = str(c_val)
            if r_str in matrix and c_str in matrix[r_str]:
                matrix[r_str][c_str] = round(val, 1) if val is not None else 0

        # Construct final output list with row total
        table_data = []
        for r_str in rows_raw:
            row_dict = {"Row": r_str}
            row_sum = 0
            for c_str in cols_raw:
                val = matrix[r_str][c_str]
                row_dict[c_str] = val
                if isinstance(val, (int, float)):
                    row_sum += val
            row_dict["Total"] = round(row_sum, 1)
            table_data.append(row_dict)

        return {
            "operation": "Pivot",
            "row_dimension": r_label,
            "column_dimension": c_label,
            "measure": measure,
            "columns": ["Row"] + cols_raw + ["Total"],
            "data": table_data
        }


def execute_olap_query(payload: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Helper entry point for API requests executing OLAP operations."""
    olap = RouteXStarOLAP(db_path)
    op = payload.get("operation", "rollup").lower()
    try:
        if op == "rollup":
            level = payload.get("level", "city")
            year = payload.get("year")
            return olap.rollup(level=level, year=int(year) if year else None)
        elif op == "drilldown":
            state = payload.get("state")
            city = payload.get("city")
            return olap.drilldown(state=state, city=city)
        elif op == "slice":
            dim = payload.get("dimension", "year")
            val = payload.get("value", 2024)
            return olap.slice(dimension=dim, value=val)
        elif op == "dice":
            filters = payload.get("filters", {})
            return olap.dice(filters=filters)
        elif op == "pivot":
            row_dim = payload.get("row_dim", "city")
            col_dim = payload.get("col_dim", "year")
            measure = payload.get("measure", "accidents")
            return olap.pivot(row_dim=row_dim, col_dim=col_dim, measure=measure)
        else:
            return {"status": "error", "message": f"Unsupported OLAP operation '{op}'."}
    finally:
        olap.close()


if __name__ == "__main__":
    olap = RouteXStarOLAP()
    print("Testing OLAP Roll-up (Level: City):")
    ru = olap.rollup("city")
    print(f" -> Found {len(ru['data'])} cities rolled up.")

    print("\nTesting OLAP Drill-down (State: Karnataka):")
    dd = olap.drilldown(state="Karnataka")
    print(f" -> Found {len(dd['data'])} cities in Karnataka.")

    print("\nTesting OLAP Slice (Congestion: Severe):")
    sl = olap.slice("congestion", "Severe")
    print(f" -> Found {len(sl['data'])} records for Severe congestion.")

    print("\nTesting OLAP Dice (City: Delhi, Year: 2024):")
    dc = olap.dice({"city": "Delhi", "year": 2024})
    print(f" -> Found {len(dc['data'])} records matching multi-filter.")

    print("\nTesting OLAP Pivot (City x Year, Measure: accidents):")
    pv = olap.pivot("city", "year", "accidents")
    print(f" -> Pivot table generated with columns: {pv['columns']}")
    print(f" -> Top row: {pv['data'][0] if pv['data'] else 'empty'}")

    olap.close()
