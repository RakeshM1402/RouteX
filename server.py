"""
RouteX Integrated Web & Auth Server
Serves static pages (index.html, olap_cube.html, login.html, signup.html) and provides
SQLite-backed authentication endpoints (/api/signup, /api/login, /api/logout, /api/user).
"""

import http.server
import socketserver
import json
import sqlite3
import hashlib
import os
from urllib.parse import urlparse
from pathlib import Path

PORT = 8765
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "users.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

class RouteXHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/user":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            cookie = self.headers.get("Cookie", "")
            username = None
            for item in cookie.split(";"):
                if "routex_user=" in item:
                    username = item.split("=")[1].strip()
            
            if username:
                response = {"logged_in": True, "username": username}
            else:
                response = {"logged_in": False}
            self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        if path == "/" or path == "" or path == "/index.html" or path == "/olap_cube.html":
            cookie = self.headers.get("Cookie", "")
            username = None
            for item in cookie.split(";"):
                if "routex_user=" in item:
                    username = item.split("=")[1].strip()
            if not username:
                self.send_response(303)
                self.send_header("Location", "/login.html")
                self.end_headers()
                return
            if path == "/" or path == "":
                self.path = "/index.html"
            
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except Exception:
            data = {}

        if path == "/api/signup":
            username = data.get("username", "").strip()
            email = data.get("email", "").strip()
            password = data.get("password", "")
            
            if not username or not email or not password:
                self.send_json(400, {"success": False, "message": "All fields are required."})
                return
                
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, hash_password(password))
                )
                conn.commit()
                conn.close()
                self.send_json(200, {"success": True, "message": "Account created successfully!"})
            except sqlite3.IntegrityError:
                conn.close()
                self.send_json(400, {"success": False, "message": "Username or email already exists."})
            return

        elif path == "/api/login":
            identifier = data.get("identifier", "").strip()
            password = data.get("password", "")
            
            if not identifier or not password:
                self.send_json(400, {"success": False, "message": "Username/email and password are required."})
                return
                
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, password_hash FROM users WHERE username = ? OR email = ?",
                (identifier, identifier)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row and row[1] == hash_password(password):
                username = row[0]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"routex_user={username}; Path=/; HttpOnly")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "username": username, "message": "Login successful!"}).encode("utf-8"))
            else:
                self.send_json(401, {"success": False, "message": "Invalid credentials."})
            return

        elif path == "/api/logout":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "routex_user=; Path=/; Max-Age=0")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "Logged out successfully."}).encode("utf-8"))
            return

        self.send_json(404, {"success": False, "message": "Not found"})

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    print(f"Starting RouteX Web Server at http://127.0.0.1:{PORT}")
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), RouteXHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
