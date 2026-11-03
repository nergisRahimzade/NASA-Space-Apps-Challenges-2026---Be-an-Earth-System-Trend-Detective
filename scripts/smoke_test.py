"""Smoke test: check that a running API answers its main endpoints.

ESD-D07-BE. Run it against your local API or the deployed one:

    uv run --locked python scripts/smoke_test.py
    uv run --locked python scripts/smoke_test.py https://<service-name>.onrender.com

With no address it uses API_URL from the environment (or .env), else
http://localhost:8000. It exits with code 0 if every check passes, else 1.
"""

import os
import sys

import requests
from dotenv import load_dotenv

CHECKS = [
    # (path, what the JSON answer must contain)
    ("/health", ["status"]),
    ("/results", ["region", "series", "trend"]),
]


def run(base_url: str) -> bool:
    base_url = base_url.rstrip("/")
    print(f"Smoke testing {base_url}")
    all_ok = True
    for path, keys in CHECKS:
        try:
            response = requests.get(base_url + path, timeout=30)
            body = response.json()
            missing = [key for key in keys if key not in body]
            ok = response.status_code == 200 and not missing
            detail = f"HTTP {response.status_code}" + (f", missing {missing}" if missing else "")
        except (requests.RequestException, ValueError) as exc:
            ok, detail = False, str(exc)
        print(f"  {'PASS' if ok else 'FAIL'}  {path}  ({detail})")
        all_ok = all_ok and ok
    return all_ok


if __name__ == "__main__":
    load_dotenv()
    url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("API_URL", "http://localhost:8000")
    sys.exit(0 if run(url) else 1)
