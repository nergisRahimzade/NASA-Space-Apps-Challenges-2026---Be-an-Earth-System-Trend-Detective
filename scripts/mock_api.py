"""A tiny mock API for front-end testing. Standard library only.

Run from the repository root:
    uv run --locked python scripts/mock_api.py

Endpoints, shaped like the real API the backend team described:
    GET  /health
    GET  /results
    GET  /regions
    GET  /series?region=...&variable=...
         region is required (422 if missing), variable is optional, matching
         ignores case, and an unknown region or variable gives
         404 {"detail": "No series for ..."}
    GET, POST  /practice/items     practice CRUD, kept in memory
    GET, PUT, DELETE  /practice/items/<id>

This is not the real API. When it runs for real, stop this script and point
API_URL at the real one.
"""

import json
import math
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST, PORT = "127.0.0.1", 8000
RESULTS_FILE = Path(__file__).resolve().parent.parent / "results.mock.json"
MOCK_REGIONS = ["Example Region B", "Example Region C"]
NO_DATA_REGION = "Example Region D (no data)"  # listed by /regions, always 404

items = {1: {"id": 1, "text": "First practice item"}}
next_id = 2


def read_results():
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def find_name(wanted, names):
    """Case-insensitive match. Returns the canonical spelling, or None."""
    for name in names:
        if name.casefold() == wanted.casefold():
            return name
    return None


def make_series(region, variable):
    """Made-up monthly values. The same choice always gives the same series.

    Regions ending in "C" get two missing months (null), like the contract allows.
    """
    seed = sum(ord(c) for c in region + variable)
    start_value = 10 + seed % 10
    slope = (seed % 7 - 3) / 20  # between -0.15 and +0.15 per month
    series = []
    for i in range(24):
        year, month = 2003 + i // 12, i % 12 + 1
        value = start_value + slope * i + 2 * math.sin(i / 12 * 2 * math.pi)
        if region.endswith("C") and i in (5, 6):
            value = None
        else:
            value = round(value, 1)
        series.append({"date": f"{year}-{month:02d}", "value": value})
    return series


def series_payload(region, variable):
    series = make_series(region, variable)
    return {
        "region": region,
        "variable": variable,
        "units": "°C",
        "period": {"start": series[0]["date"], "end": series[-1]["date"]},
        "series": series,
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # CORS: lets a web page on another port call this API from the browser.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def item_id(self):
        # /practice/items/3 -> 3; anything else -> None
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[2].isdigit():
            return int(parts[2])
        return None

    def handle_series(self, query):
        region = query.get("region", [""])[0]
        if not region:
            self.send_json(
                422,
                {
                    "detail": [
                        {
                            "type": "missing",
                            "loc": ["query", "region"],
                            "msg": "Field required",
                        }
                    ]
                },
            )
            return
        results = read_results()
        default_region = results.get("region", "Example Region")
        default_variable = results.get("variable", "Surface air temperature")
        variable = query.get("variable", [""])[0] or default_variable
        region_name = find_name(region, [default_region, *MOCK_REGIONS])
        variable_name = find_name(variable, [default_variable])
        if region_name is None or variable_name is None:
            self.send_json(404, {"detail": f"No series for {region} / {variable}"})
        elif region_name == default_region:
            keys = ("region", "variable", "units", "period", "series")
            self.send_json(200, {k: results[k] for k in keys if k in results})
        else:
            self.send_json(200, series_payload(region_name, variable_name))

    def do_OPTIONS(self):
        self.send_json(204)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif url.path == "/results":
            self.send_json(200, read_results())
        elif url.path == "/regions":
            default_region = read_results().get("region", "Example Region")
            self.send_json(200, [default_region, *MOCK_REGIONS, NO_DATA_REGION])
        elif url.path == "/series":
            self.handle_series(parse_qs(url.query))
        elif url.path == "/practice/items":
            self.send_json(200, list(items.values()))
        elif self.item_id() in items:
            self.send_json(200, items[self.item_id()])
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        global next_id
        data = self.read_body()
        if self.path != "/practice/items" or not data or "text" not in data:
            self.send_json(400, {"error": 'POST JSON like {"text": "..."}'})
            return
        item = {"id": next_id, "text": data["text"]}
        items[next_id] = item
        next_id += 1
        self.send_json(201, item)

    def do_PUT(self):
        item_id = self.item_id()
        data = self.read_body()
        if item_id not in items:
            self.send_json(404, {"error": "not found"})
        elif not data or "text" not in data:
            self.send_json(400, {"error": 'PUT JSON like {"text": "..."}'})
        else:
            items[item_id]["text"] = data["text"]
            self.send_json(200, items[item_id])

    def do_DELETE(self):
        item_id = self.item_id()
        if item_id in items:
            del items[item_id]
            self.send_json(200, {})
        else:
            self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"Mock API on http://{HOST}:{PORT} (Ctrl+C to stop)")
    try:
        HTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nMock API stopped.")