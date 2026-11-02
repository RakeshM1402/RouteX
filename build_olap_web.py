"""
RouteX OLAP Cube - local demo builder
Reads the star-schema warehouse and injects the aggregated cube data into a
self-contained HTML page. No server or internet connection is required.

Usage
-----
python "build_olap_web.py"              # generate olap_cube.html
python "build_olap_web.py" --open       # generate and open in the browser
python "build_olap_web.py" --serve      # generate, serve, and open locally
"""

import argparse
import json
import sqlite3
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"
TEMPLATE_PATH = BASE_DIR / "olap_cube.template.html"
OUT_PATH = BASE_DIR / "olap_cube.html"

REGION_ORDER = ["North", "Central", "East", "West", "South", "North-East"]
SEASON_ORDER = ["Winter", "Pre-Monsoon/Summer", "Monsoon", "Post-Monsoon"]
SEASON_COLORS = {
    "Winter": "#5B8FF9",
    "Pre-Monsoon/Summer": "#F6BD16",
    "Monsoon": "#5AD8A6",
    "Post-Monsoon": "#E8684A",
}
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_ABBR = [m[:3] for m in MONTH_NAMES]
YEAR_BANDS = [
    {"label": "2001–2004", "start": 2001, "end": 2004},
    {"label": "2005–2008", "start": 2005, "end": 2008},
    {"label": "2009–2011", "start": 2009, "end": 2011},
    {"label": "2012–2014", "start": 2012, "end": 2014},
]


def build_data():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"OLAP database not found at {DB_PATH}. Run 'build_olap_cube.py' first."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT MIN(year) AS y0, MAX(year) AS y1 FROM dim_time")
    row = cur.fetchone()
    years = list(range(int(row["y0"]), int(row["y1"]) + 1))
    y_index = {y: i for i, y in enumerate(years)}

    # ---- monthly national cube cell -------------------------------------
    cur.execute("""
        SELECT t.year, t.month_number, t.season, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        GROUP BY t.year, t.month_number
    """)
    monthly_national = [[0] * 12 for _ in years]
    monthly_seasons = [[""] * 12 for _ in years]
    for r in cur.fetchall():
        yi = y_index[r["year"]]
        monthly_national[yi][r["month_number"] - 1] = r["accidents"]
        monthly_seasons[yi][r["month_number"] - 1] = r["season"]

    # ---- monthly by region ----------------------------------------------
    cur.execute("""
        SELECT g.region, t.year, t.month_number, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        JOIN dim_geography g ON f.geography_key = g.geography_key
        GROUP BY g.region, t.year, t.month_number
    """)
    monthly_by_region = {
        r: [[0] * 12 for _ in years] for r in REGION_ORDER
    }
    for r in cur.fetchall():
        region = r["region"]
        if region not in monthly_by_region:
            continue
        monthly_by_region[region][y_index[r["year"]]][r["month_number"] - 1] = r["accidents"]

    # ---- region x season -------------------------------------------------
    cur.execute("""
        SELECT g.region, t.season, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        JOIN dim_geography g ON f.geography_key = g.geography_key
        GROUP BY g.region, t.season
    """)
    regional_season = {r: {s: 0 for s in SEASON_ORDER} for r in REGION_ORDER}
    for r in cur.fetchall():
        if r["region"] in regional_season and r["season"] in SEASON_ORDER:
            regional_season[r["region"]][r["season"]] = r["accidents"]

    # ---- diurnal ---------------------------------------------------------
    cur.execute("""
        SELECT time_slot, period, start_hour, end_hour
        FROM dim_diurnal
        ORDER BY start_hour
    """)
    slots = [dict(r) for r in cur.fetchall()]
    cur.execute("""
        SELECT g.region, d.time_slot, SUM(f.accidents_count) AS accidents
        FROM fact_diurnal_accidents f
        JOIN dim_geography g ON f.geography_key = g.geography_key
        JOIN dim_diurnal d ON f.diurnal_key = d.diurnal_key
        GROUP BY g.region, d.time_slot
    """)
    diurnal = {
        r: {s["time_slot"]: 0 for s in slots} for r in REGION_ORDER
    }
    for r in cur.fetchall():
        if r["region"] in diurnal and r["time_slot"] in diurnal[r["region"]]:
            diurnal[r["region"]][r["time_slot"]] = r["accidents"]

    # ---- region x season x year-band voxel -------------------------------
    cur.execute("""
        SELECT g.region, t.year, t.season, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        JOIN dim_geography g ON f.geography_key = g.geography_key
        GROUP BY g.region, t.year, t.season
    """)
    voxel = {
        r: {s: [0] * len(YEAR_BANDS) for s in SEASON_ORDER} for r in REGION_ORDER
    }
    for r in cur.fetchall():
        region = r["region"]
        season = r["season"]
        year = r["year"]
        if region not in voxel or season not in voxel[region]:
            continue
        band_i = next(
            (i for i, b in enumerate(YEAR_BANDS) if b["start"] <= year <= b["end"]),
            None,
        )
        if band_i is not None:
            voxel[region][season][band_i] += r["accidents"]

    # ---- state x year (for drill-down) -----------------------------------
    cur.execute("""
        SELECT g.state_name, g.region, t.year, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        JOIN dim_geography g ON f.geography_key = g.geography_key
        GROUP BY g.state_name, g.region, t.year
    """)
    state_year = {}
    state_region = {}
    for r in cur.fetchall():
        state = r["state_name"]
        state_region[state] = r["region"]
        state_year.setdefault(state, {})[r["year"]] = r["accidents"]

    # ---- safety cube -----------------------------------------------------
    cur.execute("""
        SELECT state_name, region, year, fatalities, total_accidents,
               fatalities_per_lakh, severity_index, safety_risk_tier
        FROM cube_state_safety_measures
        ORDER BY state_name, year
    """)
    safety = [dict(r) for r in cur.fetchall()]

    # ---- pivot: top 12 states by 2024 fatalities -------------------------
    safety_by_state = {}
    for r in safety:
        safety_by_state.setdefault(r["state_name"], {})[r["year"]] = r
    ranked = sorted(
        safety_by_state.items(),
        key=lambda kv: (kv[1].get(2024, {}).get("fatalities") or 0),
        reverse=True,
    )[:12]
    pivot_years = [2020, 2021, 2022, 2023, 2024]
    pivot_rows = []
    for state, by_year in ranked:
        row = {
            "state": state,
            "region": state_region.get(state, by_year.get(2024, {}).get("region", "")),
            "fatalities": [],
            "accidents": [],
            "rate": [],
        }
        for year in pivot_years:
            rec = by_year.get(year, {})
            row["fatalities"].append(rec.get("fatalities"))
            row["accidents"].append(rec.get("total_accidents"))
            row["rate"].append(rec.get("fatalities_per_lakh"))
        pivot_rows.append(row)

    # ---- summary ---------------------------------------------------------
    total_accidents = sum(sum(row) for row in monthly_national)
    total_fatalities_2024 = sum(
        (r["fatalities"] or 0) for r in safety if r["year"] == 2024
    )
    high_risk_states = len({
        r["state_name"] for r in safety
        if r["year"] == 2024 and r["safety_risk_tier"] == "High Risk"
    })
    yearly_totals = [sum(row) for row in monthly_national]
    peak_year = years[yearly_totals.index(max(yearly_totals))]
    monthly_totals = [
        sum(monthly_national[i][j] for i in range(len(years))) for j in range(12)
    ]
    peak_month = MONTH_NAMES[monthly_totals.index(max(monthly_totals))]

    data = {
        "meta": {
            "years": years,
            "months": MONTH_ABBR,
            "monthNames": MONTH_NAMES,
            "seasons": SEASON_ORDER,
            "seasonColors": SEASON_COLORS,
            "regions": REGION_ORDER,
            "yearBands": YEAR_BANDS,
            "periodColors": {"Day": "#F6BD16", "Night": "#5B8FF9"},
            "source": "MoRTH 2024 + historical datasets (2001–2014)",
        },
        "monthlyNational": monthly_national,
        "monthlySeasons": monthly_seasons,
        "monthlyByRegion": monthly_by_region,
        "regionalSeason": regional_season,
        "diurnal": diurnal,
        "slots": slots,
        "voxel": voxel,
        "stateYear": state_year,
        "stateRegion": state_region,
        "safety": safety,
        "pivot": {"years": pivot_years, "rows": pivot_rows},
        "summary": {
            "totalAccidents": total_accidents,
            "totalFatalities2024": total_fatalities_2024,
            "highRiskStates": high_risk_states,
            "peakYear": peak_year,
            "peakMonth": peak_month,
            "statesCount": len(state_region),
            "regionsCount": len(REGION_ORDER),
        },
    }
    conn.close()
    return data


def render(data):
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "__ROUTEX_DATA__" not in html:
        raise ValueError("Template is missing the __ROUTEX_DATA__ placeholder.")
    html = html.replace("__ROUTEX_DATA__", payload)
    OUT_PATH.write_text(html, encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f" -> Generated {OUT_PATH.name} ({size_kb:.0f} KB, self-contained)")


class RouteXRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/api/signup":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode('utf-8'))
                email = data.get('email', '').strip().lower()
                password = data.get('password', '')
                full_name = data.get('fullName', '').strip()

                if not email or not password:
                    self.send_json(400, {"success": False, "error": "Email and password are required."})
                    return

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        full_name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                cursor.execute("SELECT user_id FROM users WHERE email = ?", (email,))
                if cursor.fetchone():
                    conn.close()
                    self.send_json(400, {"success": False, "error": "Email is already registered. Please log in."})
                    return

                cursor.execute("INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)", 
                               (full_name or "User", email, password))
                conn.commit()
                user_id = cursor.lastrowid
                conn.close()

                self.send_json(200, {"success": True, "user": {"id": user_id, "email": email, "fullName": full_name}})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
        elif self.path == "/api/login":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode('utf-8'))
                email = data.get('email', '').strip().lower()
                password = data.get('password', '')

                if not email or not password:
                    self.send_json(400, {"success": False, "error": "Email and password are required."})
                    return

                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        full_name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cursor.execute("SELECT user_id, full_name, email, password FROM users WHERE email = ?", (email,))
                row = cursor.fetchone()
                conn.close()

                if not row or row["password"] != password:
                    self.send_json(401, {"success": False, "error": "Invalid email or password."})
                    return

                self.send_json(200, {
                    "success": True, 
                    "user": {"id": row["user_id"], "email": row["email"], "fullName": row["full_name"]}
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
        else:
            self.send_error(404, "Endpoint not found")

    def send_json(self, status_code, data):
        response = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response))
        self.end_headers()
        self.wfile.write(response)


def serve(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), RouteXRequestHandler)
    url = f"http://127.0.0.1:{port}/{OUT_PATH.name}"
    print(f" -> Serving demo at {url}")
    print(" -> Press Ctrl+C to stop the server.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n -> Server stopped.")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Build the RouteX OLAP cube demo page")
    parser.add_argument("--open", action="store_true", help="open the page in the browser")
    parser.add_argument("--serve", action="store_true", help="serve locally and open the browser")
    parser.add_argument("--port", type=int, default=8765, help="local server port")
    args = parser.parse_args()

    print("Building RouteX OLAP cube demo...")
    data = build_data()
    render(data)

    if args.serve:
        serve(args.port)
    elif args.open:
        webbrowser.open(OUT_PATH.as_uri())
        print(" -> Opened in your default browser.")


if __name__ == "__main__":
    main()
