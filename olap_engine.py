"""
RouteX OLAP Analytical Engine
Provides multidimensional OLAP operations:
- Slice
- Dice
- Roll-up
- Drill-down
- Pivot (Cross-tabulation)
Supports direct programmatic use and an interactive Command-Line Interface.
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent / "final dataset" / "routex_olap.db"

class RouteXOLAP:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        if not self.db_path.exists():
            raise FileNotFoundError(f"OLAP database not found at {self.db_path}. Run build_olap_cube.py first.")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    def _execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def _print_table(self, data: List[Dict[str, Any]], title: str = "Query Results", limit: int = 25):
        if not data:
            print(f"\n--- {title} ---")
            print("No matching records found.")
            return

        headers = list(data[0].keys())
        col_widths = {h: len(h) for h in headers}

        sample = data[:limit]
        for row in sample:
            for h in headers:
                val_str = str(row[h]) if row[h] is not None else "NULL"
                if len(val_str) > col_widths[h]:
                    col_widths[h] = min(len(val_str), 30)

        # Print header
        header_line = " | ".join(h.ljust(col_widths[h]) for h in headers)
        separator = "-+-".join("-" * col_widths[h] for h in headers)

        print(f"\n--- {title} (Showing {len(sample)} of {len(data)} records) ---")
        print(header_line)
        print(separator)

        for row in sample:
            row_line = " | ".join(str(row[h] if row[h] is not None else "NULL")[:30].ljust(col_widths[h]) for h in headers)
            print(row_line)

    # -----------------------------------------------------------------
    # OLAP OPERATION 1: SLICE
    # Fixes one dimension to a single value, viewing the remaining cube.
    # -----------------------------------------------------------------
    def slice(self, cube: str, dimension: str, value: Any, display: bool = True) -> List[Dict[str, Any]]:
        """
        Slices the cube along a single dimension fixed to a specific value.
        Example: slice('cube_temporal_seasonality', 'season', 'Monsoon')
        """
        query = f"SELECT * FROM {cube} WHERE {dimension} = ?"
        results = self._execute_query(query, (value,))
        if display:
            self._print_table(results, title=f"OLAP SLICE [{cube} WHERE {dimension} = '{value}']")
        return results

    # -----------------------------------------------------------------
    # OLAP OPERATION 2: DICE
    # Selects a sub-cube by specifying conditions on multiple dimensions.
    # -----------------------------------------------------------------
    def dice(self, cube: str, conditions: Dict[str, Any], display: bool = True) -> List[Dict[str, Any]]:
        """
        Dices a sub-cube using multiple dimension filters.
        Example: dice('cube_temporal_seasonality', {'region': 'South', 'season': 'Monsoon', 'year': 2014})
        """
        where_clauses = []
        params = []
        for col, val in conditions.items():
            if isinstance(val, (list, tuple)):
                placeholders = ", ".join("?" for _ in val)
                where_clauses.append(f"{col} IN ({placeholders})")
                params.extend(val)
            else:
                where_clauses.append(f"{col} = ?")
                params.append(val)

        where_stmt = " AND ".join(where_clauses) if where_clauses else "1=1"
        query = f"SELECT * FROM {cube} WHERE {where_stmt}"
        results = self._execute_query(query, tuple(params))
        cond_str = ", ".join(f"{k}={v}" for k, v in conditions.items())
        if display:
            self._print_table(results, title=f"OLAP DICE [{cube} FILTER: {cond_str}]")
        return results

    # -----------------------------------------------------------------
    # OLAP OPERATION 3: ROLL-UP
    # Aggregates measures to a coarser granularity (e.g. State -> Region, Month -> Year).
    # -----------------------------------------------------------------
    def rollup_regional(self, year: Optional[int] = None, display: bool = True) -> List[Dict[str, Any]]:
        """
        Roll-up from State level to Regional level for temporal accident metrics.
        """
        where = f"WHERE year = {year}" if year else ""
        query = f"""
        SELECT 
            region,
            COUNT(DISTINCT state_name) AS states_count,
            SUM(total_accidents) AS regional_total_accidents,
            ROUND(AVG(total_accidents), 2) AS avg_accidents_per_state,
            MIN(total_accidents) AS min_state_accidents,
            MAX(total_accidents) AS max_state_accidents
        FROM cube_temporal_seasonality
        {where}
        GROUP BY region
        ORDER BY regional_total_accidents DESC;
        """
        results = self._execute_query(query)
        lbl = f" (Year {year})" if year else " (All Historical Years)"
        if display:
            self._print_table(results, title=f"OLAP ROLL-UP: State -> Region{lbl}")
        return results

    def rollup_annual_fatalities(self, display: bool = True) -> List[Dict[str, Any]]:
        """
        Roll-up annual national safety metrics across all states.
        """
        query = """
        SELECT 
            year,
            SUM(fatalities) AS national_fatalities,
            SUM(total_accidents) AS national_accidents,
            ROUND((SUM(fatalities) * 100.0) / NULLIF(SUM(total_accidents), 0), 2) AS national_severity_index,
            ROUND((SUM(fatalities) * 100000.0) / SUM(population), 2) AS national_fatality_rate_per_lakh
        FROM cube_state_safety_measures
        GROUP BY year
        ORDER BY year ASC;
        """
        results = self._execute_query(query)
        if display:
            self._print_table(results, title="OLAP ROLL-UP: National Annual Safety Totals (2020-2024)")
        return results

    # -----------------------------------------------------------------
    # OLAP OPERATION 4: DRILL-DOWN
    # Navigates from coarse granularity to finer detail.
    # -----------------------------------------------------------------
    def drilldown_region(self, region: str, year: int = 2024, display: bool = True) -> List[Dict[str, Any]]:
        """
        Drills down from a Region to its constituent individual States.
        """
        query = """
        SELECT 
            state_name,
            population,
            density_tier,
            safety_risk_tier,
            fatalities,
            fatalities_per_lakh,
            severity_index,
            fatality_rank
        FROM cube_state_safety_measures
        WHERE region = ? AND year = ?
        ORDER BY fatalities DESC;
        """
        results = self._execute_query(query, (region, year))
        if display:
            self._print_table(results, title=f"OLAP DRILL-DOWN: Region '{region}' -> States (Year {year})")
        return results

    def drilldown_diurnal_slots(self, state_name: str, year: int = 2014, display: bool = True) -> List[Dict[str, Any]]:
        """
        Drills down diurnal risk into specific 3-hour time slots.
        """
        query = """
        SELECT 
            time_slot,
            day_or_night,
            total_accidents,
            avg_time_slot_share_pct
        FROM cube_diurnal_risk
        WHERE state_name = ? AND year = ?
        ORDER BY total_accidents DESC;
        """
        results = self._execute_query(query, (state_name, year))
        if display:
            self._print_table(results, title=f"OLAP DRILL-DOWN: Diurnal Slots for {state_name} ({year})")
        return results

    # -----------------------------------------------------------------
    # OLAP OPERATION 5: PIVOT (Cross-Tabulation)
    # Rotates dimensions to display an aggregated cross-matrix.
    # -----------------------------------------------------------------
    def pivot_state_year_fatalities(self, top_n: int = 10, display: bool = True) -> List[Dict[str, Any]]:
        """
        Cross-tabulation pivot of Top N States (rows) vs Years 2020-2024 (columns) for fatalities.
        """
        query = f"""
        SELECT 
            state_name,
            SUM(CASE WHEN year = 2020 THEN fatalities ELSE 0 END) AS [2020],
            SUM(CASE WHEN year = 2021 THEN fatalities ELSE 0 END) AS [2021],
            SUM(CASE WHEN year = 2022 THEN fatalities ELSE 0 END) AS [2022],
            SUM(CASE WHEN year = 2023 THEN fatalities ELSE 0 END) AS [2023],
            SUM(CASE WHEN year = 2024 THEN fatalities ELSE 0 END) AS [2024],
            ROUND(AVG(fatalities), 1) AS [5yr_avg]
        FROM cube_state_safety_measures
        GROUP BY state_name
        ORDER BY [2024] DESC
        LIMIT {top_n};
        """
        results = self._execute_query(query)
        if display:
            self._print_table(results, title=f"OLAP PIVOT: Top {top_n} States x Fatalities (2020-2024)")
        return results

    def pivot_season_region_accidents(self, year: int = 2014, display: bool = True) -> List[Dict[str, Any]]:
        """
        Cross-tabulation pivot of Regions (rows) vs Seasons (columns) for a given year.
        """
        query = f"""
        SELECT 
            region,
            SUM(CASE WHEN season = 'Winter' THEN total_accidents ELSE 0 END) AS Winter,
            SUM(CASE WHEN season = 'Pre-Monsoon/Summer' THEN total_accidents ELSE 0 END) AS Summer,
            SUM(CASE WHEN season = 'Monsoon' THEN total_accidents ELSE 0 END) AS Monsoon,
            SUM(CASE WHEN season = 'Post-Monsoon' THEN total_accidents ELSE 0 END) AS Post_Monsoon,
            SUM(total_accidents) AS Total_Accidents
        FROM cube_temporal_seasonality
        WHERE year = ?
        GROUP BY region
        ORDER BY Total_Accidents DESC;
        """
        results = self._execute_query(query, (year,))
        if display:
            self._print_table(results, title=f"OLAP PIVOT: Region x Season Accidents ({year})")
        return results

def run_demo():
    print("=" * 70)
    print("RouteX OLAP Analytical Engine - Multidimensional Demonstration")
    print("=" * 70)

    olap = RouteXOLAP()

    print("\n>>> 1. OLAP OPERATION: SLICE (Fixing Season = 'Monsoon' in 2014 for South Region)")
    olap.dice("cube_temporal_seasonality", {"region": "South", "year": 2014, "season": "Monsoon"})

    print("\n>>> 2. OLAP OPERATION: DICE (Sub-cube: Night-time accidents in High Risk States, 2014)")
    olap.dice("cube_diurnal_risk", {"day_or_night": "Night", "year": 2014, "region": "Central"})

    print("\n>>> 3. OLAP OPERATION: ROLL-UP (Aggregating State safety to National Level, 2020-2024)")
    olap.rollup_annual_fatalities()

    print("\n>>> 4. OLAP OPERATION: DRILL-DOWN (Expanding 'South' Region into States in 2024)")
    olap.drilldown_region("South", 2024)

    print("\n>>> 5. OLAP OPERATION: PIVOT (Cross-Tab: Region x Meteorological Season Accidents)")
    olap.pivot_season_region_accidents(2014)

    print("\n>>> 6. OLAP OPERATION: PIVOT (Cross-Tab: Top 10 States x Fatalities over 5 Years)")
    olap.pivot_state_year_fatalities(10)

    olap.close()
    print("\n" + "=" * 70)
    print("OLAP Demonstration Completed Successfully!")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RouteX OLAP Engine CLI")
    parser.add_argument("--demo", action="store_true", help="Run a demonstration of all 5 OLAP operations")
    parser.add_argument("--slice-season", type=str, help="Slice by season (e.g. Monsoon, Winter)")
    parser.add_argument("--drilldown-region", type=str, help="Drill-down into a region (e.g. South, North, Central)")
    parser.add_argument("--pivot-fatalities", action="store_true", help="Pivot top states by fatalities (2020-2024)")

    args = parser.parse_args()

    if len(sys.argv) == 1 or args.demo:
        run_demo()
    else:
        olap = RouteXOLAP()
        if args.slice_season:
            olap.slice("cube_temporal_seasonality", "season", args.slice_season)
        if args.drilldown_region:
            olap.drilldown_region(args.drilldown_region)
        if args.pivot_fatalities:
            olap.pivot_state_year_fatalities(15)
        olap.close()
