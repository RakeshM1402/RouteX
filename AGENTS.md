# AGENTS.md

Instructions and context for AI agents working in this repository.

## Project Overview & Core Pillars
- **Project Name**: RouteX: An Intelligent Road Safety, Traffic Analytics, and Smart Location Recommendation System
- **Pillars**:
  1. **Road Safety Analysis**: Hotspots, temporal trends (monthly/time-of-day), fatality metrics, and severity patterns (MoRTH 2024 & historical datasets).
  2. **Traffic Analytics**: National highway infrastructure networks (`india_national_highways.geojson`) integrated with accident density.
  3. **Smart Location Recommendation**: Geospatial boundaries, population metrics (100k+ cities, census data), and risk scores for optimal logistics/infrastructure deployment.
  4. **A* Intelligent Route Planner**: Heuristic A* graph search for national highway corridors with multi-objective optimization (Safest, Shortest, Fastest, Balanced), admissible Haversine heuristics, blackspot avoidance, and fatigue rest stop recommendations.

## Workspace & Environment Quirks
- **Platform**: Windows (`win32`), PowerShell. Always wrap file paths in double quotes (paths contain spaces, e.g., `"Slot A\Capstone\Raw datasets"`).
- **Git Status**: Git repository present.
- **Python**: Python 3.14 (`python`). Data packages (`pandas`, `numpy`, `geopandas`) should be installed in a virtual environment (`python -m venv .venv`) if needed. For quick inspection, use built-in `csv` and `json` modules.

## Large File & Data Parsing Gotchas (`Raw datasets/`)
- **Do not read large files directly into prompt context**:
  - `Raw datasets/road-accidents-in-india-2024.pdf` (~21.3 MB)
  - `Raw datasets/highways/india_national_highways.geojson` (~17.1 MB)
  - `Raw datasets/boundaries/india_districts.geojson` (~5.3 MB)
  - `Raw datasets/boundaries/india_states.geojson` (~2.1 MB)
- **CSV & Entity Quirks**:
  - `road-accidents-2024-states-fatalities.csv`: Values contain commas (e.g., `"7,039"`). Strip commas before numeric casting.
  - `RS_Session_267_AU_1540_A_to_C.1.csv`: Missing values represented as literal `"NA"` strings.
  - `reference/` headers (`state_codes.csv`, `district_codes.csv`): Include trailing spaces after commas in header row; strip field names.
  - **Entity Name Divergence**: Boundary GeoJSONs use uppercase (`"ANDAMAN AND NICOBAR ISLANDS"`), while historical CSVs vary (`"A & N Islands"`, `"Delhi"` vs `"NCT Of Delhi"`). Normalize case and symbols (`&` / `and`) when merging.

## Key Execution Commands
```powershell
# Run the ETL Pipeline (extracts raw data, transforms, outputs to 'final dataset/')
python "etl_pipeline.py"

# Build Multidimensional OLAP Cube & Star Schema SQLite DB (`final dataset/routex_olap.db`)
python "build_olap_cube.py"

# Query OLAP Engine (slice, dice, roll-up, drill-down, pivot demo)
python "olap_engine.py" --demo

# Test RouteX A* Search Engine standalone
python "astar_router.py"

# Run A* Router and Server Test Suite
python "test_astar.py"

# Start the Integrated Web & Auth Server (http://127.0.0.1:8765)
python "server.py"

# Render 3D OLAP cube views into 'visuals/' (matplotlib + numpy required)
python "olap_cube_3d.py" --mode all

# Build the self-contained interactive OLAP demo page (no server required)
python "build_olap_web.py"

# Build and open the demo in the default browser
python "build_olap_web.py" --open
```

## A* Intelligent Route Planner Architecture
- **Router Engine**: `astar_router.py`
  - In-memory graph built from `routex_olap.db` (`DIM_LOCATION`, `FACT_TRIP_ANALYTICS`, `DIM_ACCIDENT`, `DIM_SERVICE`).
  - 486 nodes, 11,379 edges within 300 km radius across India.
  - Multi-objective cost functions: `safest`, `shortest`, `fastest`, `balanced`.
  - Strictly admissible heuristics: $h(n) \le g^*(n)$ via Haversine great-circle distance.
  - **Custom Location Selection**: Supports arbitrary custom coordinates anywhere in India via `plan_custom_route()`, with dual routing behavior:
    - Intra-city / local trips ($\le 80$ km): direct door-to-door real road driving route with localized OLAP safety scores and blackspot proximity.
    - Intercity corridors ($> 80$ km): snaps custom endpoints to nearest national highway corridor nodes, executes multi-objective A*, and stitches door-to-door real road geometry.
  - **Accurate Real Road Driving Distances**: Overwrites straight-line proxy distances everywhere with exact driving road kilometers and durations from `ROAD_GEOMETRY_CACHE` / OSRM, scaling all itinerary segments proportionally.
  - Features: Multi-leg stopover planning, comparative safest vs shortest analysis, fatigue resting points recommendations (~250 km intervals with certified amenities), along-route pitstops (food, fuel, chill), and Google Maps extraction with universal URL calibration, KML for Google My Maps, and GPX tracks.
- **Backend API Endpoints (`server.py`)**:
  - `GET /api/route/nodes`: All graph nodes with hazard scores, coordinates, and road amenities.
  - `GET /api/route/presets`: Popular intercity highway corridors (Delhi-Mumbai, Chennai-Shimla, Kolkata-Delhi, etc.).
  - `POST /api/route/plan`: Executes A* search, accepting custom coordinates (`start: {lat, lon, name}`, `dest: {lat, lon, name}`) or node IDs, returning full road coordinates, turn-by-turn maneuvers, comparison metrics, rest stop recommendations, and calibrated Google Maps universal navigation links.
  - `POST /api/route/export`: Exports corridors in KML (`application/vnd.google-earth.kml+xml`), GPX (`application/gpx+xml`), or TXT driving manifest formats.
- **Frontend Dashboard**: `route_planner.html`
  - Address search input with real-time OpenStreetMap Nominatim autocomplete (debounced 250ms).
  - True custom map click dropper (drops draggable pins anywhere on the map, reverse-geocodes addresses via Nominatim).
  - Draggable markers (`dragend` updates location and recalculates route automatically).
  - Interactive Leaflet GIS map with dual polyline rendering (Safest glow line & Shortest dashed line).
  - Side-by-side comparison cards and analytical trade-off verdict with real road driving kilometers and realistic travel durations.
  - **Google Maps Driving Sync & Route Extraction**:
    - One-click **Start Driving in Google Maps** (`dir_action=navigate`) with sampled intermediate waypoints adhering strictly to the RouteX corridor.
    - **Driver Mobile QR Code** rendered with local `qrcode.min.js`: drivers scan with iPhone Camera or Android Google Lens to launch turn-by-turn driving in their vehicle.
    - **Save to Google My Maps (KML)**: exports full route geometry, rest stops, and hazard markers for permanent sync to the Google Maps phone app under *Saved > Maps*.
    - **Universal GPS Track (GPX)** for car infotainment, Garmin, and OsmAnd.
    - **Printable Offline Driving Sheet (TXT)** with maneuvers and Indian 24/7 highway emergency helplines (NHAI 1033 & 112).
    - Quick Copy Directions link and direct WhatsApp route sharing.
  - Fatigue management resting points cards with amenities badges.
  - Step-by-step segment itinerary table with exact driving distances.

## OLAP Data Warehouse & Datasets
- **Database**: `final dataset/routex_olap.db` (Star schema with dimensions `dim_geography`, `dim_time`, `dim_diurnal`, `dim_highway` and indexed fact tables).
- **3D visuals**: `visuals/olap_cube_3d_{bars,regional,voxel}.png`, generated from the database by `olap_cube_3d.py`.
- **Interactive demo**: `olap_cube.html` is generated by `build_olap_web.py` from `olap_cube.template.html`. Edit `olap_cube.template.html` and rebuild rather than editing the generated HTML directly.
- **Key Output Tables (`final dataset/`)**:
  - `dim_state.csv`, `dim_district.csv`, `dim_national_highways.csv`, `dim_city_recommendation.csv`
  - `fact_state_safety_recent.csv`, `fact_accidents_monthly_trend_long.csv`, `fact_accidents_time_of_day_long.csv`
  - `routex_integrated_state_risk_profile.csv` (master analytical table)
  - `DATA_DICTIONARY.md` (full column definitions)
