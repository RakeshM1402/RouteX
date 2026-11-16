"""
RouteX DWDM Test Suite (Module 9: Testing and Final Verification)
Tests:
1. Star Schema table and constraint integrity
2. ETL Pipeline execution, deduplication & idempotency
3. All 5 OLAP operations (Roll-up, Drill-down, Slice, Dice, Pivot)
4. Data Mining capabilities (K-Means, Blackspot CRI, Decision rules)
5. DWDM REST APIs over HTTP
"""

import unittest
import sqlite3
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"

import dwdm_schema
import dwdm_etl
import dwdm_olap
import dwdm_mining
import server
import threading
import http.server
import time


class RouteXDWDMTestSuite(unittest.TestCase):
    server_instance = None

    @classmethod
    def setUpClass(cls):
        # Initialize schema and run ETL to ensure full test environment
        dwdm_schema.init_star_schema(DB_PATH)
        dwdm_etl.run_etl(DB_PATH)

        # Check if server is already running on port 8765
        server_running = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/api/dwdm/kpis", timeout=0.5):
                server_running = True
        except Exception:
            server_running = False

        if not server_running:
            try:
                cls.server_instance = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), server.RouteXHandler)
                cls.server_thread = threading.Thread(target=cls.server_instance.serve_forever, daemon=True)
                cls.server_thread.start()
                time.sleep(0.5)
            except Exception as e:
                print(f"Warning: could not bind test server to port 8765: {e}")

    @classmethod
    def tearDownClass(cls):
        if cls.server_instance:
            try:
                cls.server_instance.shutdown()
                cls.server_instance.server_close()
            except Exception:
                pass

    def test_01_star_schema_tables_and_columns(self):
        """Verify all 6 Star Schema tables exist with correct Primary Keys and Columns."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        expected_tables = {
            "FACT_TRIP_ANALYTICS": ["Trip_ID", "Date_ID", "Location_ID", "Traffic_ID", "Accident_ID", "Service_ID", "Distance_KM", "Travel_Time_Minutes", "Waiting_Time_Minutes", "Accident_Count", "Average_Speed"],
            "DIM_DATE": ["Date_ID", "Full_Date", "Day", "Month", "Quarter", "Year", "Weekday", "Weekend_Status"],
            "DIM_LOCATION": ["Location_ID", "Location_Name", "City", "State", "Country", "Latitude", "Longitude", "Location_Type"],
            "DIM_TRAFFIC": ["Traffic_ID", "Congestion_Level", "Vehicle_Count", "Average_Speed", "Waiting_Time", "Traffic_Status"],
            "DIM_ACCIDENT": ["Accident_ID", "Accident_Type", "Accident_Severity", "Accident_Zone", "Accident_Count", "Accident_Date"],
            "DIM_SERVICE": ["Service_ID", "Service_Name", "Service_Type", "Contact_Number", "Latitude", "Longitude", "Availability_Status"],
            "ETL_AUDIT_LOG": ["run_id", "start_time", "status", "extracted_records", "transformed_records", "loaded_records", "rejected_records", "duration_seconds"]
        }

        for tbl, expected_cols in expected_tables.items():
            cols = [col[1] for col in cur.execute(f"PRAGMA table_info([{tbl}])").fetchall()]
            for ec in expected_cols:
                self.assertIn(ec, cols, f"Column '{ec}' missing in table '{tbl}'")

        # Verify foreign keys on FACT_TRIP_ANALYTICS
        fks = cur.execute("PRAGMA foreign_key_list(FACT_TRIP_ANALYTICS)").fetchall()
        fk_targets = {fk[2] for fk in fks}
        self.assertIn("DIM_DATE", fk_targets)
        self.assertIn("DIM_LOCATION", fk_targets)
        self.assertIn("DIM_TRAFFIC", fk_targets)
        self.assertIn("DIM_ACCIDENT", fk_targets)
        self.assertIn("DIM_SERVICE", fk_targets)
        conn.close()

    def test_02_etl_idempotency_and_audit(self):
        """Verify that repeated ETL runs execute idempotently without duplicating records."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        count_before = cur.execute("SELECT COUNT(*) FROM FACT_TRIP_ANALYTICS").fetchone()[0]
        self.assertGreater(count_before, 0)
        conn.close()

        # Run ETL second time
        res = dwdm_etl.run_etl(DB_PATH)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreater(res["run_id"], 0)

        # Count after should remain identical (no duplicate rows)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        count_after = cur.execute("SELECT COUNT(*) FROM FACT_TRIP_ANALYTICS").fetchone()[0]
        self.assertEqual(count_before, count_after, "ETL is not idempotent: row count increased on repeat run!")

        # Verify audit log recorded run
        latest_audit = cur.execute("SELECT status, loaded_records FROM ETL_AUDIT_LOG ORDER BY run_id DESC LIMIT 1").fetchone()
        self.assertEqual(latest_audit[0], "SUCCESS")
        conn.close()

    def test_03_olap_rollup(self):
        """Verify OLAP Roll-up hierarchy (Location -> City -> State -> Country)."""
        olap = dwdm_olap.RouteXStarOLAP(DB_PATH)
        try:
            res_city = olap.rollup("city")
            self.assertEqual(res_city["operation"], "Roll-up")
            self.assertGreater(len(res_city["data"]), 0)
            self.assertIn("total_trips", res_city["data"][0])
            self.assertIn("total_accidents", res_city["data"][0])

            res_state = olap.rollup("state")
            self.assertGreater(len(res_state["data"]), 0)

            res_country = olap.rollup("country")
            self.assertGreater(len(res_country["data"]), 0)
        finally:
            olap.close()

    def test_04_olap_drilldown(self):
        """Verify OLAP Drill-down navigation."""
        olap = dwdm_olap.RouteXStarOLAP(DB_PATH)
        try:
            # National drill-down to states
            dd_nat = olap.drilldown()
            self.assertGreater(len(dd_nat["data"]), 0)

            # State drill-down to cities
            dd_state = olap.drilldown(state="Karnataka")
            self.assertGreater(len(dd_state["data"]), 0)
        finally:
            olap.close()

    def test_05_olap_slice_and_dice(self):
        """Verify OLAP Slice (1D) and Dice (multi-D sub-cube) operations."""
        olap = dwdm_olap.RouteXStarOLAP(DB_PATH)
        try:
            # Slice by congestion
            sl = olap.slice("congestion", "Severe")
            self.assertGreater(len(sl["data"]), 0)

            # Dice by City + Year
            dc = olap.dice({"city": "Delhi", "year": 2024})
            self.assertGreater(len(dc["data"]), 0)
        finally:
            olap.close()

    def test_06_olap_pivot(self):
        """Verify OLAP 2D Cross-tabulation Pivot."""
        olap = dwdm_olap.RouteXStarOLAP(DB_PATH)
        try:
            pv = olap.pivot("city", "year", "accidents")
            self.assertEqual(pv["operation"], "Pivot")
            self.assertIn("Row", pv["columns"])
            self.assertIn("Total", pv["columns"])
            self.assertGreater(len(pv["data"]), 0)
        finally:
            olap.close()

    def test_07_data_mining_models(self):
        """Verify K-Means clustering, Hotspot CRI scoring, and Severity Classification."""
        dm = dwdm_mining.RouteXDataMining(DB_PATH)
        try:
            km = dm.run_kmeans(k=4)
            self.assertEqual(len(km["clusters"]), 4)
            total_clustered = sum(c["size"] for c in km["clusters"])
            self.assertEqual(total_clustered, km["total_samples"])

            hs = dm.get_accident_hotspots(limit=10)
            self.assertGreater(len(hs["hotspots"]), 0)
            top_hs = hs["hotspots"][0]
            self.assertIn("composite_risk_index", top_hs)
            self.assertGreaterEqual(top_hs["composite_risk_index"], 0)
            self.assertLessEqual(top_hs["composite_risk_index"], 100)

            rules = dm.get_severity_classification_rules()
            self.assertGreater(len(rules["decision_rules"]), 0)
        finally:
            dm.close()

    def test_08_dwdm_http_apis(self):
        """Verify live REST API endpoints over HTTP on port 8765."""
        endpoints = ["schema", "kpis", "analytics", "mining", "etl/status"]
        for ep in endpoints:
            url = f"http://127.0.0.1:8765/api/dwdm/{ep}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertIsInstance(body, dict)

        # Test POST /api/dwdm/olap
        olap_payload = json.dumps({"operation": "rollup", "level": "city"}).encode("utf-8")
        req_olap = urllib.request.Request(
            "http://127.0.0.1:8765/api/dwdm/olap",
            data=olap_payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_olap) as resp:
            self.assertEqual(resp.status, 200)
            res_json = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res_json["operation"], "Roll-up")


if __name__ == "__main__":
    unittest.main()
