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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import time
import html
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

# In-memory store for pending signup OTP verifications
# Map: email -> { "otp": str, "username": str, "expires_at": float, "created_at": float, "attempts": int }
SIGNUP_OTP_STORE = {}

def send_otp_email(to_email: str, otp_code: str, username: str) -> tuple:
    """
    Dispatch 6-digit verification code via SMTP if configured, or log to console.
    Supported environment variables: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    """
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    smtp_from = os.environ.get("SMTP_FROM", "").strip() or smtp_user or "no-reply@routex.ai"

    print(f"\n[RouteX OTP Service] >>> Generated 6-digit verification code for {to_email} ({username}): {otp_code} (Valid for 5 mins) <<<\n")

    if not smtp_host or not smtp_user or not smtp_pass:
        return True, "Dev mode: code logged to console"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your RouteX Sign-Up Verification Code: {otp_code}"
        msg["From"] = f"RouteX Road Safety <{smtp_from}>"
        msg["To"] = to_email

        plain_body = (
            f"Hello {username},\n\n"
            f"Your RouteX verification code is: {otp_code}\n\n"
            f"This code will expire in 5 minutes. If you did not request this, please ignore this email.\n\n"
            f"Best regards,\nRouteX Road Safety Intelligence Team"
        )

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif; background:#0a0e16; color:#f1f5f9; padding:24px; margin:0;">
  <div style="max-width:480px; margin:0 auto; background:#131a27; border:1px solid rgba(148,163,184,0.2); border-radius:14px; padding:32px; box-shadow:0 8px 30px rgba(0,0,0,0.5);">
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:20px;">
      <div style="width:36px; height:36px; border-radius:10px; background:linear-gradient(135deg,#5b8ff9,#5ad8a6); color:#07101f; font-weight:800; font-size:18px; text-align:center; line-height:36px;">R</div>
      <span style="font-size:18px; font-weight:700; color:#ffffff;">RouteX <small style="font-size:12px; color:#94a3b8; font-weight:normal;">Road Safety Intelligence</small></span>
    </div>
    <h2 style="font-size:20px; color:#ffffff; margin-top:0;">Verify Your Email Address</h2>
    <p style="font-size:14px; color:#94a3b8; line-height:1.5;">Hello <strong>{html.escape(username)}</strong>,</p>
    <p style="font-size:14px; color:#94a3b8; line-height:1.5;">Thank you for registering with RouteX. Use the 6-digit verification code below to verify your email and complete your account creation:</p>
    <div style="text-align:center; margin:24px 0;">
      <span style="display:inline-block; font-size:32px; font-weight:800; letter-spacing:8px; color:#5ad8a6; background:rgba(90,216,166,0.12); border:1px solid rgba(90,216,166,0.3); padding:12px 28px; border-radius:12px; font-family:monospace;">{otp_code}</span>
    </div>
    <p style="font-size:12.5px; color:#94a3b8; line-height:1.5;">This code will expire in <strong>5 minutes</strong>. If you did not request this verification, no action is needed.</p>
    <hr style="border:none; border-top:1px solid rgba(148,163,184,0.15); margin:24px 0 16px;">
    <p style="font-size:11px; color:#64748b; margin:0; text-align:center;">RouteX Road Safety Analytics &middot; Automated Security Dispatch</p>
  </div>
</body>
</html>"""

        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if smtp_port == 465:
            mailer = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
        else:
            mailer = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
            mailer.starttls()

        mailer.login(smtp_user, smtp_pass)
        mailer.sendmail(smtp_from, [to_email], msg.as_string())
        mailer.quit()
        return True, "Email dispatched via SMTP"
    except Exception as e:
        print(f"[RouteX OTP Service Warning] SMTP delivery failed ({e}). Verification code remains active in logs.")
        return True, f"SMTP error: {e}" 

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

        elif path == "/api/signup/send-otp":
            username = (data.get("username") or data.get("fullName") or "").strip()
            email = (data.get("email") or "").strip().lower()

            if not username or not email:
                self.send_json(400, {"success": False, "message": "Username and email address are required."})
                return

            if "@" not in email or "." not in email:
                self.send_json(400, {"success": False, "message": "Please enter a valid email address."})
                return

            # Check if username or email already registered
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT username, email FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)", (username, email))
            existing = cur.fetchone()
            conn.close()

            if existing:
                if existing[0].lower() == username.lower():
                    self.send_json(400, {"success": False, "message": "This username is already taken. Please choose another."})
                else:
                    self.send_json(400, {"success": False, "message": "An account with this email already exists. Please sign in."})
                return

            # Rate limit check: prevent rapid re-sending within 30 seconds
            now = time.time()
            if email in SIGNUP_OTP_STORE:
                prev = SIGNUP_OTP_STORE[email]
                if now - prev.get("created_at", 0) < 30:
                    wait_sec = int(30 - (now - prev.get("created_at", 0)))
                    self.send_json(429, {"success": False, "message": f"Please wait {wait_sec}s before requesting a new code."})
                    return

            # Generate 6-digit cryptographic OTP
            otp_code = f"{secrets.randbelow(900000) + 100000}"
            SIGNUP_OTP_STORE[email] = {
                "otp": otp_code,
                "username": username,
                "expires_at": now + 300,  # 5 minutes validity
                "created_at": now,
                "attempts": 0
            }

            # Send email
            ok, status_msg = send_otp_email(email, otp_code, username)
            smtp_configured = bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER"))

            resp_data = {
                "success": True,
                "message": f"Verification code sent to {email}!",
                "expires_in": 300,
                "smtp_active": smtp_configured
            }
            if not smtp_configured:
                resp_data["dev_otp"] = otp_code
                resp_data["dev_note"] = "SMTP not configured yet. Code logged to console & provided for testing."

            self.send_json(200, resp_data)
            return

        elif path == "/api/signup":
            username = (data.get("username") or data.get("fullName") or "").strip()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password", "")
            otp = str(data.get("otp") or "").strip()
            
            if not username or not email or not password:
                self.send_json(400, {"success": False, "message": "All fields are required."})
                return

            if len(password) < 6:
                self.send_json(400, {"success": False, "message": "Password must be at least 6 characters long."})
                return

            if not otp:
                self.send_json(400, {"success": False, "message": "Verification code (OTP) is required."})
                return

            # Verify OTP
            now = time.time()
            if email not in SIGNUP_OTP_STORE:
                self.send_json(400, {"success": False, "message": "No verification code requested or session expired. Please request a new code."})
                return

            record = SIGNUP_OTP_STORE[email]
            if now > record["expires_at"]:
                del SIGNUP_OTP_STORE[email]
                self.send_json(400, {"success": False, "message": "Verification code has expired. Please request a new one."})
                return

            if record["attempts"] >= 5:
                del SIGNUP_OTP_STORE[email]
                self.send_json(400, {"success": False, "message": "Too many invalid attempts. Please request a new code."})
                return

            if str(record["otp"]).strip() != otp:
                record["attempts"] += 1
                rem = max(0, 5 - record["attempts"])
                self.send_json(400, {"success": False, "message": f"Invalid verification code. {rem} attempt(s) remaining."})
                return

            # Verification successful: insert into database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, hash_password(password))
                )
                conn.commit()
                conn.close()
                if email in SIGNUP_OTP_STORE:
                    del SIGNUP_OTP_STORE[email]
                self.send_json(200, {"success": True, "message": "Account verified and created successfully!"})
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
