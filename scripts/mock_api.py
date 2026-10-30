"""A tiny mock API for front-end testing. Standard library only.

Run from the repository root:
    uv run --locked python scripts/mock_api.py

Endpoints:
    GET  /health
    GET  /results                  serves results.mock.json
    GET, POST  /practice/items     practice CRUD, kept in memory
    GET, PUT, DELETE  /practice/items/<id>

This is not the real API. When it exists, stop this script and point API_URL
at the real one.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", 8000
RESULTS_FILE = Path(__file__).resolve().parent.parent / "results.mock.json"

items = {1: {"id": 1, "text": "First practice item"}}
next_id = 2


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

    def do_OPTIONS(self):
        self.send_json(204)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif self.path == "/results":
            with open(RESULTS_FILE, encoding="utf-8") as f:
                self.send_json(200, json.load(f))
        elif self.path == "/practice/items":
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
    HTTPServer((HOST, PORT), Handler).serve_forever()