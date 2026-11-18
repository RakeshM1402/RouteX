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
from urllib.parse import urlparse, parse_qs
from pathlib import Path

PORT = int(os.environ.get("PORT", 8765))
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "users.db"
OLAP_DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"

import dwdm_schema
import dwdm_etl
import dwdm_olap
import dwdm_mining
import astar_router

def get_dwdm_kpis(db_path=OLAP_DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    fact_stats = cur.execute("""
        SELECT 
            COUNT(Trip_ID) as total_trips,
            COALESCE(SUM(Accident_Count), 0) as total_accidents,
            ROUND(COALESCE(AVG(Travel_Time_Minutes), 0), 1) as avg_travel_time,
            ROUND(COALESCE(AVG(Waiting_Time_Minutes), 0), 1) as avg_waiting_time,
            ROUND(COALESCE(AVG(Average_Speed), 0), 1) as avg_speed,
            ROUND(COALESCE(SUM(Distance_KM), 0), 1) as total_distance
        FROM FACT_TRIP_ANALYTICS;
    """).fetchone()

    total_locations = cur.execute("SELECT COUNT(*) FROM DIM_LOCATION;").fetchone()[0]
    total_services = cur.execute("SELECT COUNT(*) FROM DIM_SERVICE;").fetchone()[0]
    conn.close()

    return {
        "total_trips": fact_stats[0],
        "total_accidents": fact_stats[1],
        "total_locations": total_locations,
        "avg_travel_time": fact_stats[2],
        "avg_waiting_time": fact_stats[3],
        "avg_speed": fact_stats[4],
        "total_distance_km": fact_stats[5],
        "total_services": total_services
    }

def get_dwdm_analytics(db_path=OLAP_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    traffic_by_level = [dict(r) for r in cur.execute("""
        SELECT t.Congestion_Level, COUNT(f.Trip_ID) as trip_count, 
               ROUND(AVG(f.Average_Speed), 1) as avg_speed,
               ROUND(AVG(f.Waiting_Time_Minutes), 1) as avg_wait
        FROM FACT_TRIP_ANALYTICS f
        JOIN DIM_TRAFFIC t ON f.Traffic_ID = t.Traffic_ID
        GROUP BY t.Congestion_Level
        ORDER BY trip_count DESC;
    """).fetchall()]

    accident_by_severity = [dict(r) for r in cur.execute("""
        SELECT a.Accident_Severity, SUM(f.Accident_Count) as accident_count
        FROM FACT_TRIP_ANALYTICS f
        JOIN DIM_ACCIDENT a ON f.Accident_ID = a.Accident_ID
        GROUP BY a.Accident_Severity
        ORDER BY accident_count DESC;
    """).fetchall()]

    service_distribution = [dict(r) for r in cur.execute("""
        SELECT Service_Type, COUNT(Service_ID) as count
        FROM DIM_SERVICE
        GROUP BY Service_Type
        ORDER BY count DESC;
    """).fetchall()]

    monthly_trend = [dict(r) for r in cur.execute("""
        SELECT d.Year || '-' || substr('0' || d.Month, -2, 2) as month_label,
               COUNT(f.Trip_ID) as trip_count,
               SUM(f.Accident_Count) as accident_count
        FROM FACT_TRIP_ANALYTICS f
        JOIN DIM_DATE d ON f.Date_ID = d.Date_ID
        GROUP BY d.Year, d.Month
        ORDER BY d.Year, d.Month
        LIMIT 24;
    """).fetchall()]

    top_cities = [dict(r) for r in cur.execute("""
        SELECT l.City, l.State, COUNT(f.Trip_ID) as trip_count, 
               SUM(f.Accident_Count) as accident_count,
               ROUND(AVG(f.Average_Speed), 1) as avg_speed
        FROM FACT_TRIP_ANALYTICS f
        JOIN DIM_LOCATION l ON f.Location_ID = l.Location_ID
        GROUP BY l.City, l.State
        ORDER BY trip_count DESC
        LIMIT 10;
    """).fetchall()]

    conn.close()

    return {
        "traffic_by_level": traffic_by_level,
        "accident_by_severity": accident_by_severity,
        "service_distribution": service_distribution,
        "monthly_trend": monthly_trend,
        "top_cities": top_cities
    }

def get_map_locations(db_path=OLAP_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    locations = [dict(r) for r in cur.execute("""
        SELECT l.Location_ID, l.Location_Name, l.City, l.State, l.Latitude, l.Longitude, l.Location_Type,
               COUNT(f.Trip_ID) as trip_count,
               COALESCE(SUM(f.Accident_Count), 0) as total_accidents,
               ROUND(COALESCE(AVG(f.Average_Speed), 0), 1) as avg_speed
        FROM DIM_LOCATION l
        LEFT JOIN FACT_TRIP_ANALYTICS f ON l.Location_ID = f.Location_ID
        GROUP BY l.Location_ID
    """).fetchall()]
    conn.close()
    return locations

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
    def end_headers(self):
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Cookie")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/user":
            cookie = self.headers.get("Cookie", "") if self.headers else ""
            username = None
            for item in cookie.split(";"):
                if "routex_user=" in item:
                    username = item.split("=")[1].strip()
            
            if username:
                response = {"logged_in": True, "username": username}
            else:
                response = {"logged_in": False}
            self.send_json(200, response)
            return

        elif path == "/api/dwdm/schema":
            meta = dwdm_schema.get_star_schema_metadata(OLAP_DB_PATH)
            self.send_json(200, meta)
            return

        elif path == "/api/dwdm/kpis":
            kpis = get_dwdm_kpis(OLAP_DB_PATH)
            self.send_json(200, kpis)
            return

        elif path == "/api/dwdm/analytics":
            analytics = get_dwdm_analytics(OLAP_DB_PATH)
            self.send_json(200, analytics)
            return

        elif path == "/api/dwdm/mining":
            mining = dwdm_mining.get_data_mining_overview(OLAP_DB_PATH)
            self.send_json(200, mining)
            return

        elif path == "/api/dwdm/etl/status":
            etl_status = dwdm_etl.get_latest_etl_status(OLAP_DB_PATH)
            self.send_json(200, etl_status)
            return

        elif path == "/api/dwdm/map-locations":
            locations = get_map_locations(OLAP_DB_PATH)
            self.send_json(200, locations)
            return

        elif path == "/api/route/nodes":
            g = astar_router.get_graph(str(OLAP_DB_PATH))
            self.send_json(200, list(g["nodes"].values()))
            return

        elif path == "/api/route/presets":
            g = astar_router.get_graph(str(OLAP_DB_PATH))
            presets = astar_router.get_popular_corridors(g)
            self.send_json(200, presets)
            return

        elif path == "/api/route/pitstops":
            params = parse_qs(parsed.query)
            category = params.get("category", [None])[0]
            lat = params.get("lat", [None])[0]
            lon = params.get("lon", [None])[0]
            radius = float(params.get("radius", [10.0])[0])
            
            conn = sqlite3.connect(str(OLAP_DB_PATH))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            if lat and lon:
                c_lat, c_lon = float(lat), float(lon)
                delta = radius / 111.0
                query = "SELECT * FROM DIM_CORRIDOR_PITSTOPS WHERE Latitude BETWEEN ? AND ? AND Longitude BETWEEN ? AND ?"
                args = [c_lat - delta, c_lat + delta, c_lon - delta, c_lon + delta]
                if category and category != "all":
                    query += " AND Category = ?"
                    args.append(category.lower())
                query += " ORDER BY Rating DESC LIMIT 30"
                rows = cur.execute(query, args).fetchall()
            else:
                query = "SELECT * FROM DIM_CORRIDOR_PITSTOPS"
                args = []
                if category and category != "all":
                    query += " WHERE Category = ?"
                    args.append(category.lower())
                query += " ORDER BY Rating DESC LIMIT 40"
                rows = cur.execute(query, args).fetchall()
            conn.close()
            
            pitstops = []
            for r in rows:
                pitstops.append({
                    "id": r["Pitstop_ID"],
                    "name": r["Name"],
                    "category": r["Category"],
                    "category_label": r["Category_Label"],
                    "subcategory": r["Subcategory"],
                    "city": r["City"],
                    "state": r["State"],
                    "lat": r["Latitude"],
                    "lon": r["Longitude"],
                    "rating": float(r["Rating"] or 4.2),
                    "review_count": int(r["Review_Count"] or 100),
                    "price_range": r["Price_Range"] or "₹₹",
                    "opening_hours": r["Opening_Hours"] or "24 Hours",
                    "features": [f.strip() for f in (r["Features"] or "").split(",") if f.strip()],
                    "chill_reason": r["Chill_Reason"] or "",
                    "contact_number": r["Contact_Number"] or ""
                })
            self.send_json(200, pitstops)
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

        if path == "/api/route/plan":
            start = data.get("start")
            if start is None:
                start = data.get("start_id")
            if start is None and "start_coord" in data:
                sc = data["start_coord"]
                start = {"lat": float(sc[0]), "lon": float(sc[1]), "name": data.get("start_name", "Custom Origin")}

            dest = data.get("dest")
            if dest is None:
                dest = data.get("dest_id")
            if dest is None and "dest_coord" in data:
                dc = data["dest_coord"]
                dest = {"lat": float(dc[0]), "lon": float(dc[1]), "name": data.get("dest_name", "Custom Destination")}

            stops = data.get("stops", [])
            custom_stops = data.get("custom_stops", [])
            if custom_stops:
                stops = list(stops) + list(custom_stops)

            mode = data.get("mode", "safest")
            safety_weight = float(data.get("safety_weight", 15.0))
            avoid_blackspots = bool(data.get("avoid_blackspots", False))
            compare = bool(data.get("compare", True))
            traffic_density = data.get("traffic_density", "normal")

            if start is None or dest is None:
                self.send_json(400, {"success": False, "error": "start and dest are required"})
                return

            g = astar_router.get_graph(str(OLAP_DB_PATH))

            try:
                res = astar_router.plan_custom_route(
                    g, start=start, dest=dest, stops=stops,
                    mode=mode, safety_weight=safety_weight, avoid_blackspots=avoid_blackspots,
                    compare=compare, traffic_density=traffic_density
                )
            except Exception as e:
                self.send_json(400, {"success": False, "error": f"Route computation error: {e}"})
                return

            if not res.get("success"):
                self.send_json(400, {"success": False, "error": res.get("error", "Failed to compute corridor")})
                return

            # Attach fatigue management recommended rest stops
            if compare:
                path_for_stops = res["safest"].get("path", [])
                rec_stops = astar_router.recommend_rest_stops(g, path_for_stops)
                res["recommended_stops"] = rec_stops
                res["safest"]["google_maps_url"] = astar_router.generate_google_maps_url(res["safest"], recommended_stops=rec_stops, navigate=False)
                res["safest"]["google_maps_nav_url"] = astar_router.generate_google_maps_url(res["safest"], recommended_stops=rec_stops, navigate=True)
                res["shortest"]["google_maps_url"] = astar_router.generate_google_maps_url(res["shortest"], include_rest_stops=False, navigate=False)
                res["shortest"]["google_maps_nav_url"] = astar_router.generate_google_maps_url(res["shortest"], include_rest_stops=False, navigate=True)
            else:
                path_for_stops = res["route"].get("path", [])
                rec_stops = astar_router.recommend_rest_stops(g, path_for_stops)
                res["recommended_stops"] = rec_stops
                res["route"]["google_maps_url"] = astar_router.generate_google_maps_url(res["route"], recommended_stops=rec_stops, navigate=False)
                res["route"]["google_maps_nav_url"] = astar_router.generate_google_maps_url(res["route"], recommended_stops=rec_stops, navigate=True)

            self.send_json(200, res)
            return

        elif path == "/api/route/export":
            export_fmt = (data.get("format") or "kml").lower().strip()
            route = data.get("route") or {}
            route_name = data.get("name") or "RouteX Driving Corridor"
            rec_stops = data.get("recommended_stops") or []

            if export_fmt == "kml":
                content = astar_router.export_route_to_kml(route, route_name=route_name, recommended_stops=rec_stops)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.google-earth.kml+xml; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="routex_corridor.kml"')
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            elif export_fmt == "gpx":
                content = astar_router.export_route_to_gpx(route, route_name=route_name)
                self.send_response(200)
                self.send_header("Content-Type", "application/gpx+xml; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="routex_corridor.gpx"')
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            elif export_fmt == "txt":
                content = astar_router.export_route_to_txt(route, route_name=route_name, recommended_stops=rec_stops)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="routex_itinerary.txt"')
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            else:
                self.send_json(400, {"success": False, "error": f"Unsupported format: {export_fmt}"})
                return

        elif path == "/api/dwdm/olap":
            res = dwdm_olap.execute_olap_query(data, OLAP_DB_PATH)
            self.send_json(200, res)
            return

        elif path == "/api/dwdm/etl/run":
            res = dwdm_etl.run_etl(OLAP_DB_PATH)
            self.send_json(200, res)
            return

        elif path == "/api/signup":
            username = (data.get("username") or data.get("fullName") or "").strip()
            email = data.get("email", "").strip().lower()
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
            identifier = (data.get("identifier") or data.get("email") or data.get("username") or "").strip()
            password = data.get("password", "")
            
            if not identifier or not password:
                self.send_json(400, {"success": False, "message": "Username/email and password are required."})
                return
                
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, password_hash FROM users WHERE username = ? OR LOWER(email) = LOWER(?)",
                (identifier, identifier)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row and row[1] == hash_password(password):
                username = row[0]
                response_bytes = json.dumps({"success": True, "username": username, "message": "Login successful!"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_bytes)))
                self.send_header("Connection", "close")
                self.send_header("Set-Cookie", f"routex_user={username}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(response_bytes)
            else:
                self.send_json(401, {"success": False, "message": "Invalid credentials."})
            return

        elif path == "/api/logout":
            response_bytes = json.dumps({"success": True, "message": "Logged out successfully."}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.send_header("Connection", "close")
            self.send_header("Set-Cookie", "routex_user=; Path=/; Max-Age=0")
            self.end_headers()
            self.wfile.write(response_bytes)
            return

        self.send_json(404, {"success": False, "message": "Not found"})

    def send_json(self, status, data):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(response_bytes)

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    print(f"Starting RouteX Web Server at http://127.0.0.1:{PORT}")
    with http.server.ThreadingHTTPServer(("0.0.0.0", PORT), RouteXHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
