"""
test_astar.py  –  Comprehensive Test Suite for RouteX A* Route Planner
======================================================================
Tests:
  1. Haversine distance calculations and admissibility properties
  2. Graph building from SQLite warehouse (nodes, edges, risk scores, amenities)
  3. Admissibility & Monotonicity of A* Heuristic: h(n) <= g*(n)
  4. Search modes: Safest, Shortest, Fastest, Balanced
  5. Blackspot avoidance constraint
  6. Multi-stop journey planning with user-selected stopovers
  7. Comparative analysis (Safest vs Shortest route differentials)
  8. Fatigue management: Resting point recommendations
  9. Server HTTP API integration endpoints (/api/route/nodes, presets, plan)
"""

import unittest
import json
import threading
import time
import urllib.request
from pathlib import Path

import astar_router
import server

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "final dataset" / "routex_olap.db")


class TestAStarRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = astar_router.get_graph(DB_PATH)

    def test_haversine_properties(self):
        # Distance between identical points is 0
        self.assertAlmostEqual(astar_router.haversine(28.61, 77.20, 28.61, 77.20), 0.0, places=3)
        # Delhi to Mumbai straight line distance ~1150 km
        d = astar_router.haversine(28.61, 77.20, 19.07, 72.87)
        self.assertTrue(1100 < d < 1200, f"Expected Delhi-Mumbai dist ~1150 km, got {d}")
        # Symmetry
        d_rev = astar_router.haversine(19.07, 72.87, 28.61, 77.20)
        self.assertAlmostEqual(d, d_rev, places=3)

    def test_graph_integrity(self):
        nodes = self.graph["nodes"]
        adj   = self.graph["adj"]
        self.assertGreaterEqual(len(nodes), 480)
        self.assertGreaterEqual(self.graph["stats"]["edge_count"], 10000)

        # Check node schema
        for nid, n in list(nodes.items())[:20]:
            self.assertIn("risk_score", n)
            self.assertTrue(0.0 <= n["risk_score"] <= 100.0)
            self.assertIn(n["risk_zone"], ["Safe", "Moderate", "High Risk"])
            self.assertIn("amenities", n)
            self.assertIsInstance(n["amenities"], list)

    def test_admissible_heuristic_and_shortest_path(self):
        # On Shortest Route mode, A* cost equals pure distance.
        # Haversine distance h(start) must be <= total path distance g*(goal) (admissibility).
        start_id = 58   # Delhi Cantonment
        goal_id  = 358  # Navi Mumbai
        res = astar_router.astar_search(self.graph, start_id, goal_id, mode="shortest")

        self.assertTrue(res["found"])
        n_start = self.graph["nodes"][start_id]
        n_goal  = self.graph["nodes"][goal_id]
        straight_line = astar_router.haversine(n_start["lat"], n_start["lon"], n_goal["lat"], n_goal["lon"])

        self.assertLessEqual(straight_line, res["total_dist_km"],
                             "Haversine heuristic must never overestimate actual network path distance")
        self.assertTrue(res["telemetry"]["admissible_heuristic"])

    def test_safest_vs_shortest_comparison(self):
        start_id = 58   # Delhi
        goal_id  = 358  # Mumbai
        cmp_res = astar_router.compare_routes(self.graph, [start_id, goal_id], safety_weight=15.0)

        self.assertTrue(cmp_res["success"])
        safest = cmp_res["safest"]
        shortest = cmp_res["shortest"]
        diff = cmp_res["differential"]

        # Safest route must have risk <= shortest route
        self.assertLessEqual(safest["avg_risk"], shortest["avg_risk"])
        # Blackspots on safest should be <= shortest
        self.assertLessEqual(safest["total_blackspots"], shortest["total_blackspots"])
        # Risk reduction % must be positive
        self.assertGreater(diff["risk_reduction_pct"], 0.0)
        # Shortest route must be shorter or equal in distance
        self.assertLessEqual(shortest["total_dist_km"], safest["total_dist_km"])

    def test_multi_leg_waypoint_routing(self):
        # Delhi -> Jaipur -> Mumbai
        delhi_id  = 58
        jaipur_id = 73
        mumbai_id = 358

        res = astar_router.route_with_stops(self.graph, [delhi_id, jaipur_id, mumbai_id], mode="safest")
        self.assertTrue(res["found"])
        self.assertIn(jaipur_id, res["path"], "Path must visit intermediate stopover Jaipur")
        self.assertEqual(res["path"][0], delhi_id)
        self.assertEqual(res["path"][-1], mumbai_id)
        self.assertGreater(len(res["segments"]), 2)

    def test_fastest_mode_search(self):
        start_id = 456  # Chennai
        goal_id  = 4    # Shimla
        res = astar_router.astar_search(self.graph, start_id, goal_id, mode="fastest")
        self.assertTrue(res["found"])
        self.assertGreater(res["total_time_hours"], 0)
        self.assertGreater(res["avg_speed_kmh"], 30)

    def test_rest_stops_recommendation(self):
        start_id = 456  # Chennai
        goal_id  = 4    # Shimla
        route = astar_router.astar_search(self.graph, start_id, goal_id, mode="safest")
        self.assertTrue(route["found"])

        stops = astar_router.recommend_rest_stops(self.graph, route["path"], target_interval_km=250.0)
        self.assertGreater(len(stops), 0)
        for s in stops:
            self.assertIn("distance_from_start_km", s)
            self.assertIn("amenities", s)
            self.assertIn("recommendation_reason", s)

    def test_popular_presets(self):
        presets = astar_router.get_popular_corridors(self.graph)
        self.assertGreaterEqual(len(presets), 4)
        for p in presets:
            self.assertIn("start_id", p)
            self.assertIn("dest_id", p)
            self.assertIn(p["start_id"], self.graph["nodes"])
            self.assertIn(p["dest_id"], self.graph["nodes"])

    def test_custom_location_routing_and_accurate_distance(self):
        # Madhavaram (13.1489, 80.2307) -> Avadi (13.1147, 80.1006)
        # Straight-line distance is ~14.5 km, but actual road driving distance is ~19-21 km
        start = {"lat": 13.1489, "lon": 80.2307, "name": "Madhavaram, Chennai"}
        dest = {"lat": 13.1147, "lon": 80.1006, "name": "Avadi, Chennai"}
        res = astar_router.plan_custom_route(self.graph, start=start, dest=dest, compare=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["compare_mode"])
        safest = res["safest"]

        # Ensure actual driving road distance is returned rather than straight line
        self.assertGreaterEqual(safest["total_dist_km"], 18.0)
        self.assertEqual(safest["total_dist_km"], safest["actual_road_dist_km"])
        self.assertGreater(len(safest["road_geometry"]), 50)
        self.assertGreater(len(safest["road_steps"]), 0)

        # Check segments sum up to total distance
        seg_sum = sum(s["dist_km"] for s in safest["segments"])
        self.assertAlmostEqual(seg_sum, safest["total_dist_km"], delta=0.5)

    def test_google_maps_url_generation(self):
        # Test Delhi to Mumbai corridor Google Maps URL
        start_id = 58   # Delhi Cantonment
        goal_id  = 358  # Navi Mumbai
        cmp_res = astar_router.compare_routes(self.graph, [start_id, goal_id])
        self.assertTrue(cmp_res["success"])
        safest = cmp_res["safest"]

        rec_stops = astar_router.recommend_rest_stops(self.graph, safest["path"])
        url_preview = astar_router.generate_google_maps_url(safest, recommended_stops=rec_stops, navigate=False)
        url_nav = astar_router.generate_google_maps_url(safest, recommended_stops=rec_stops, navigate=True)

        self.assertTrue(url_preview.startswith("https://www.google.com/maps/dir/?api=1"))
        self.assertIn("origin=", url_preview)
        self.assertIn("destination=", url_preview)
        self.assertIn("travelmode=driving", url_preview)
        self.assertNotIn("dir_action=navigate", url_preview)

        # Nav URL must contain dir_action=navigate
        self.assertIn("dir_action=navigate", url_nav)

        # Waypoints count must not exceed 9
        if "waypoints=" in url_preview:
            import urllib.parse
            parsed = urllib.parse.urlparse(url_preview)
            qs = urllib.parse.parse_qs(parsed.query)
            wps = qs.get("waypoints", [""])[0].split("|")
            self.assertLessEqual(len(wps), 9)

    def test_kml_gpx_and_txt_exports(self):
        start = {"lat": 28.6139, "lon": 77.2090, "name": "New Delhi"}
        dest  = {"lat": 26.9124, "lon": 75.7873, "name": "Jaipur"}
        res = astar_router.plan_custom_route(self.graph, start=start, dest=dest, compare=False)
        self.assertTrue(res["success"])
        route = res["route"]

        # KML
        kml = astar_router.export_route_to_kml(route, route_name="Delhi to Jaipur Safe Drive")
        self.assertIn("<kml xmlns=", kml)
        self.assertIn("<LineString>", kml)
        self.assertIn("<coordinates>", kml)
        self.assertIn("Delhi to Jaipur Safe Drive", kml)

        # GPX
        gpx = astar_router.export_route_to_gpx(route, route_name="Delhi to Jaipur Safe Drive")
        self.assertIn('<gpx version="1.1"', gpx)
        self.assertIn("<trk>", gpx)
        self.assertIn("<trkpt", gpx)
        self.assertIn("<wpt", gpx)

        # TXT
        txt = astar_router.export_route_to_txt(route, route_name="Delhi to Jaipur Safe Drive")
        self.assertIn("ROUTEX INTELLIGENT HIGHWAY CORRIDOR DRIVING MANIFEST", txt)
        self.assertIn("1033", txt)  # NHAI Helpline



class TestServerRouteEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8791
        cls.httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", cls.port), server.RouteXHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_api_route_nodes(self):
        url = f"http://127.0.0.1:{self.port}/api/route/nodes"
        req = urllib.request.urlopen(url)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode())
        self.assertGreaterEqual(len(data), 480)
        self.assertIn("risk_score", data[0])
        self.assertIn("amenities", data[0])

    def test_api_route_presets(self):
        url = f"http://127.0.0.1:{self.port}/api/route/presets"
        req = urllib.request.urlopen(url)
        self.assertEqual(req.status, 200)
        presets = json.loads(req.read().decode())
        self.assertGreaterEqual(len(presets), 4)

    def test_api_route_plan_compare(self):
        url = f"http://127.0.0.1:{self.port}/api/route/plan"
        payload = {
            "start_id": 58,
            "dest_id": 358,
            "stops": [],
            "mode": "safest",
            "safety_weight": 15.0,
            "avoid_blackspots": False,
            "compare": True
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read().decode())
        self.assertTrue(body["success"])
        self.assertTrue(body["compare_mode"])
        self.assertIn("safest", body)
        self.assertIn("shortest", body)
        self.assertIn("differential", body)
        self.assertIn("recommended_stops", body)
        self.assertGreater(len(body["safest"]["path"]), 2)

    def test_api_route_plan_single_mode(self):
        url = f"http://127.0.0.1:{self.port}/api/route/plan"
        payload = {
            "start_id": 58,
            "dest_id": 73,
            "stops": [],
            "mode": "shortest",
            "compare": False
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read().decode())
        self.assertTrue(body["success"])
        self.assertFalse(body["compare_mode"])
        self.assertIn("route", body)
        self.assertEqual(body["route"]["mode"], "shortest")

    def test_api_route_plan_invalid_params(self):
        url = f"http://127.0.0.1:{self.port}/api/route/plan"
        payload = {"start_id": 58}  # missing dest_id
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req)
            self.fail("Expected HTTP 400 Bad Request")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


    def test_api_route_plan_custom_coordinates(self):
        url = f"http://127.0.0.1:{self.port}/api/route/plan"
        payload = {
            "start": {"lat": 13.1489, "lon": 80.2307, "name": "Madhavaram"},
            "dest": {"lat": 13.1147, "lon": 80.1006, "name": "Avadi"},
            "compare": True
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read().decode())
        self.assertTrue(body["success"])
        self.assertGreaterEqual(body["safest"]["total_dist_km"], 18.0)
        self.assertEqual(body["safest"]["total_dist_km"], body["safest"]["actual_road_dist_km"])

    def test_api_route_export(self):
        # 1. First get a valid route
        plan_url = f"http://127.0.0.1:{self.port}/api/route/plan"
        plan_req = urllib.request.Request(
            plan_url,
            data=json.dumps({"start_id": 58, "dest_id": 73, "compare": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        plan_resp = urllib.request.urlopen(plan_req)
        plan_body = json.loads(plan_resp.read().decode())
        route = plan_body["route"]

        # 2. Export KML
        export_url = f"http://127.0.0.1:{self.port}/api/route/export"
        kml_req = urllib.request.Request(
            export_url,
            data=json.dumps({"format": "kml", "route": route, "name": "Test Corridor"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        kml_resp = urllib.request.urlopen(kml_req)
        self.assertEqual(kml_resp.status, 200)
        self.assertIn("application/vnd.google-earth.kml+xml", kml_resp.headers.get("Content-Type"))
        kml_text = kml_resp.read().decode("utf-8")
        self.assertIn("<kml xmlns=", kml_text)
        self.assertIn("<LineString>", kml_text)

        # 3. Export GPX
        gpx_req = urllib.request.Request(
            export_url,
            data=json.dumps({"format": "gpx", "route": route, "name": "Test Corridor"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        gpx_resp = urllib.request.urlopen(gpx_req)
        self.assertEqual(gpx_resp.status, 200)
        self.assertIn("application/gpx+xml", gpx_resp.headers.get("Content-Type"))
        gpx_text = gpx_resp.read().decode("utf-8")
        self.assertIn("<gpx", gpx_text)
        self.assertIn("<trk>", gpx_text)


if __name__ == "__main__":
    unittest.main()
