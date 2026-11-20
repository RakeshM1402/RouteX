"""
Automated Unit & Integration Test Suite for RouteX BI Analytics
Verifies Power BI configuration, secret isolation, schema integrity,
dynamic filtering, verified KPI denominators, and CSV formula sanitization.
"""

import unittest
import sqlite3
import json
import os
import io
import csv
import threading
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import bi_analytics
import server

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"


class TestBIAnalytics(unittest.TestCase):

    def setUp(self):
        self.db_path = DB_PATH
        self.assertTrue(self.db_path.exists(), f"Database not found at {self.db_path}")

    # 1. Power BI Config & Secret Isolation
    def test_powerbi_config_unconfigured(self):
        # Clear env vars
        old_secret = os.environ.pop("POWERBI_CLIENT_SECRET", None)
        old_url = os.environ.pop("POWERBI_REPORT_URL", None)
        try:
            cfg = bi_analytics.get_powerbi_config()
            self.assertFalse(cfg["configured"])
            self.assertEqual(cfg["embed_type"], "unconfigured")
            self.assertIn("setup_guide", cfg)
            # Guarantee secret is never present
            self.assertNotIn("POWERBI_CLIENT_SECRET", cfg)
            self.assertNotIn("client_secret", cfg)
        finally:
            if old_secret: os.environ["POWERBI_CLIENT_SECRET"] = old_secret
            if old_url: os.environ["POWERBI_REPORT_URL"] = old_url

    def test_powerbi_config_direct_url(self):
        os.environ["POWERBI_REPORT_URL"] = "https://app.powerbi.com/reportEmbed?reportId=test-uuid-123"
        try:
            cfg = bi_analytics.get_powerbi_config()
            self.assertTrue(cfg["configured"])
            self.assertEqual(cfg["embed_type"], "secure_embed_url")
            self.assertEqual(cfg["embed_url"], "https://app.powerbi.com/reportEmbed?reportId=test-uuid-123")
            self.assertNotIn("client_secret", cfg)
        finally:
            os.environ.pop("POWERBI_REPORT_URL", None)

    # 2. Database Schema & Data Integrity
    def test_database_schema_integrity(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Check required tables exist
        required_tables = [
            "FACT_TRIP_ANALYTICS", "DIM_DATE", "DIM_LOCATION", "DIM_TRAFFIC",
            "DIM_ACCIDENT", "DIM_SERVICE", "dim_geography", "dim_highway",
            "fact_annual_safety", "ETL_AUDIT_LOG"
        ]
        for tbl in required_tables:
            res = cur.execute(f"SELECT COUNT(*) FROM '{tbl}';").fetchone()[0]
            self.assertGreater(res, 0, f"Table {tbl} must not be empty")

        # Zero null foreign keys in FACT_TRIP_ANALYTICS
        null_fk_check = cur.execute("""
            SELECT COUNT(*) FROM FACT_TRIP_ANALYTICS
            WHERE Date_ID IS NULL OR Location_ID IS NULL OR Traffic_ID IS NULL
               OR Accident_ID IS NULL OR Service_ID IS NULL;
        """).fetchone()[0]
        self.assertEqual(null_fk_check, 0, "FACT_TRIP_ANALYTICS contains null foreign keys")

        conn.close()

    # 3. Dynamic Filter Options
    def test_filter_options(self):
        opts = bi_analytics.get_filter_options(self.db_path)
        self.assertIn("years", opts)
        self.assertIn(2024, opts["years"])
        self.assertIn(2023, opts["years"])
        self.assertIn(2022, opts["years"])
        self.assertIn("states", opts)
        self.assertGreater(len(opts["states"]), 10)
        self.assertIn("cities_by_state", opts)
        self.assertIn("severities", opts)
        self.assertIn("Fatal", opts["severities"])
        self.assertIn("road_types", opts)
        self.assertIn("Highway Corridor", opts["road_types"])

        # Dynamic Coverage
        cov = opts["coverage"]
        self.assertEqual(cov["earliest_date"], "2022-01-01")
        self.assertEqual(cov["latest_date"], "2024-12-31")
        self.assertIsNotNone(cov["last_etl_refresh"])

    # 4. Multi-dimensional BI Analytics & Verified Denominators
    def test_bi_analytics_unfiltered(self):
        res = bi_analytics.get_bi_analytics({}, self.db_path)
        kpis = res["kpis"]
        self.assertEqual(kpis["total_trips"], 4800)
        self.assertGreater(kpis["total_accidents"], 0)
        self.assertGreater(kpis["avg_speed_kmh"], 0)
        self.assertGreater(kpis["avg_waiting_time_min"], 0)
        self.assertGreater(kpis["monitored_corridors"], 400)
        self.assertGreater(kpis["critical_blackspots"], 100)
        self.assertGreater(kpis["verified_population"], 1000000000)
        self.assertGreater(kpis["fatality_rate_per_100k"], 0)
        self.assertGreater(kpis["severity_index"], 0)

        # Accident Analytics
        acc = res["accident_analytics"]
        self.assertEqual(len(acc["year_trends"]), 3)
        self.assertEqual(len(acc["severity_distribution"]), 4)
        self.assertEqual(len(acc["top_locations"]), 10)
        self.assertGreater(len(acc["accidents_by_road_type"]), 0)
        self.assertEqual(len(acc["monthly_frequency"]), 12)

        # Traffic Analytics
        traf = res["traffic_analytics"]
        self.assertEqual(len(traf["congestion_levels"]), 4)
        self.assertEqual(len(traf["traffic_density"]), 10)
        self.assertEqual(len(traf["peak_traffic_hours"]), 8)

        # Location Analytics & Geo Points
        loc = res["safety_and_locations"]
        self.assertGreater(len(loc["hotspots"]), 0)
        self.assertGreater(len(loc["geo_points"]), 0)
        for pt in loc["geo_points"]:
            self.assertIsNotNone(pt["lat"])
            self.assertIsNotNone(pt["lon"])

    def test_bi_analytics_year_and_state_filter(self):
        res_2023 = bi_analytics.get_bi_analytics({"year": 2023}, self.db_path)
        res_2024 = bi_analytics.get_bi_analytics({"year": 2024}, self.db_path)
        self.assertEqual(len(res_2023["accident_analytics"]["year_trends"]), 1)
        self.assertEqual(res_2023["accident_analytics"]["year_trends"][0]["year"], 2023)
        self.assertEqual(len(res_2024["accident_analytics"]["year_trends"]), 1)
        self.assertEqual(res_2024["accident_analytics"]["year_trends"][0]["year"], 2024)

        # State filter
        res_mh = bi_analytics.get_bi_analytics({"state": "Maharashtra"}, self.db_path)
        self.assertGreater(res_mh["kpis"]["total_accidents"], 0)
        self.assertLess(res_mh["kpis"]["total_accidents"], 4800 * 5)

    def test_bi_analytics_empty_result_graceful(self):
        res_empty = bi_analytics.get_bi_analytics({"city": "NonExistentCityXYZ"}, self.db_path)
        self.assertEqual(res_empty["kpis"]["total_trips"], 0)
        self.assertEqual(res_empty["kpis"]["total_accidents"], 0)
        self.assertEqual(len(res_empty["accident_analytics"]["top_locations"]), 0)

    # 5. Data Export & Formula Sanitization
    def test_csv_export_formula_sanitization(self):
        # Test helper directly
        self.assertEqual(bi_analytics.sanitize_csv_cell("=SUM(A1:A10)"), "'=SUM(A1:A10)")
        self.assertEqual(bi_analytics.sanitize_csv_cell("+1234"), "'+1234")
        self.assertEqual(bi_analytics.sanitize_csv_cell("@attack"), "'@attack")
        self.assertEqual(bi_analytics.sanitize_csv_cell("Normal Text"), "Normal Text")
        self.assertEqual(bi_analytics.sanitize_csv_cell(123.45), "123.45")

        # Full CSV export
        csv_data, mime, filename = bi_analytics.export_bi_dataset({"year": 2024}, "csv", self.db_path)
        self.assertEqual(mime, "text/csv; charset=utf-8")
        self.assertTrue(filename.endswith(".csv"))
        self.assertIn("Trip_ID", csv_data)
        self.assertIn("Full_Date", csv_data)

    def test_json_export(self):
        json_data, mime, filename = bi_analytics.export_bi_dataset({"year": 2024}, "json", self.db_path)
        self.assertEqual(mime, "application/json")
        self.assertTrue(filename.endswith(".json"))
        parsed = json.loads(json_data)
        self.assertIn("records_count", parsed)
        self.assertGreater(parsed["records_count"], 0)
        self.assertIn("data", parsed)


class TestBIServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8789
        cls.server = server.http.server.ThreadingHTTPServer(("127.0.0.1", cls.port), server.RouteXHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_http_bi_config(self):
        url = f"http://127.0.0.1:{self.port}/api/bi/config"
        with urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("configured", data)
            self.assertIn("embed_type", data)

    def test_http_bi_filter_options(self):
        url = f"http://127.0.0.1:{self.port}/api/bi/filter-options"
        with urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("years", data)
            self.assertIn("states", data)

    def test_http_bi_analytics(self):
        url = f"http://127.0.0.1:{self.port}/api/bi/analytics?year=2024"
        with urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("kpis", data)
            self.assertIn("accident_analytics", data)
            self.assertIn("traffic_analytics", data)
            self.assertIn("safety_and_locations", data)

    def test_http_bi_export(self):
        url = f"http://127.0.0.1:{self.port}/api/bi/export?format=csv&year=2024"
        with urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/csv", resp.headers.get("Content-Type", ""))
            content = resp.read().decode("utf-8")
            self.assertIn("Trip_ID", content)


if __name__ == "__main__":
    unittest.main()
