import unittest
import sqlite3
import json
import urllib.request
import urllib.error
import threading
import time
import http.client
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
import server

class RouteXQATest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = server.DB_PATH
        server.init_db()

        # Start server in thread
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 8766), server.RouteXHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

        cls.unique_suffix = str(int(time.time()))
        cls.username = f"qatest_{cls.unique_suffix}"
        cls.email = f"qatest_{cls.unique_suffix}@example.com"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_database_integrity(self):
        """Test database file exists and table schema is correct."""
        self.assertTrue(self.db_path.exists())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        self.assertIn("id", columns)
        self.assertIn("username", columns)
        self.assertIn("email", columns)
        self.assertIn("password_hash", columns)

    def test_02_signup_success(self):
        """Test user signup with valid data."""
        data = json.dumps({
            "username": self.username,
            "email": self.email,
            "password": "SecurePassword123"
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://127.0.0.1:8766/api/signup",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                res_data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(res_data["success"])
        except urllib.error.HTTPError as e:
            self.fail(f"Signup failed: {e.read().decode('utf-8')}")

    def test_03_signup_duplicate(self):
        """Test signup failure on duplicate username/email."""
        data = json.dumps({
            "username": self.username,
            "email": self.email,
            "password": "AnotherPassword123"
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://127.0.0.1:8766/api/signup",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                # Should fail with 400
                self.assertEqual(resp.status, 400)
                res_data = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(res_data["success"])
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            res_data = json.loads(e.read().decode("utf-8"))
            self.assertFalse(res_data["success"])

    def test_04_login_and_session(self):
        """Test login flow and /api/user session check."""
        data = json.dumps({
            "identifier": self.username,
            "password": "SecurePassword123"
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://127.0.0.1:8766/api/login",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                cookie = resp.headers.get("Set-Cookie", "")
                self.assertIn(f"routex_user={self.username}", cookie)

                # Test session check with cookie
                req_user = urllib.request.Request(
                    "http://127.0.0.1:8766/api/user",
                    headers={"Cookie": cookie}
                )
                with urllib.request.urlopen(req_user) as resp_user:
                    user_data = json.loads(resp_user.read().decode("utf-8"))
                    self.assertTrue(user_data["logged_in"])
                    self.assertEqual(user_data["username"], self.username)
        except urllib.error.HTTPError as e:
            self.fail(f"Login failed: {e.read().decode('utf-8')}")

    def test_05_olap_database_check(self):
        """Test routex_olap.db existence and core tables."""
        olap_db = BASE_DIR / "final dataset" / "routex_olap.db"
        self.assertTrue(olap_db.exists())
        conn = sqlite3.connect(olap_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        self.assertIn("dim_geography", tables)
        self.assertIn("fact_annual_safety", tables)

if __name__ == "__main__":
    unittest.main()
