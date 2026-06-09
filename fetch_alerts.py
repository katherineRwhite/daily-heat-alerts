#!/usr/bin/env python3
"""
fetch_alerts.py
Fetches active heat alerts from Environment Canada's GeoMet API
and appends today's records to data.json.
Run daily via GitHub Actions.
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

GEOMET_URL  = "https://api.weather.gc.ca/collections/weather-alerts/items?f=json&limit=1000&lang=en"
DATA_FILE   = Path(__file__).parent / "data.json"
HEAT_PATTERN = re.compile(r"heat|humidex|canicule|chaleur", re.IGNORECASE)

TIMEOUT     = 60       # seconds per attempt
MAX_RETRIES = 3        # number of attempts
RETRY_DELAY = 10       # seconds between retries

STOP_PHRASES = [
    "Take action to protect",
    "Watch for the early signs",
    "Heat stroke is a medical",
    "Drink water often",
    "Close blinds",
    "Plan and schedule",
    "Extreme heat affects",
    "Never leave people",
    "For more information",
    "Please continue to monitor",
]


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def extract_detail(text: str) -> str:
    out = text.strip()
    for phrase in STOP_PHRASES:
        idx = out.find(phrase)
        if idx > 80:
            out = out[:idx].strip()
            break
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def fetch_with_retry(url: str) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  Attempt {attempt}/{MAX_RETRIES} — fetching {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "heat-alerts-bot/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            print(f"  HTTP error: {last_error}", file=sys.stderr)
        except urllib.error.URLError as e:
            last_error = str(e.reason)
            print(f"  URL error: {last_error}", file=sys.stderr)
        except Exception as e:
            last_error = str(e)
            print(f"  Unexpected error: {last_error}", file=sys.stderr)

        if attempt < MAX_RETRIES:
            print(f"  Retrying in {RETRY_DELAY}s…")
            time.sleep(RETRY_DELAY)

    print(f"ERROR: all {MAX_RETRIES} attempts failed. Last error: {last_error}", file=sys.stderr)
    sys.exit(1)


def fetch_alerts():
    data  = fetch_with_retry(GEOMET_URL)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    alerts = []

    for feature in data.get("features", []):
        p = feature.get("properties", {})
        name = p.get("alert_name_en", "")
        if not HEAT_PATTERN.search(name):
            continue

        raw_text = strip_html(p.get("alert_text_en", ""))

        alerts.append({
            "date":               today,
            "colour":             p.get("risk_colour_en",       ""),
            "alert_type":         name,
            "status":             p.get("status_en",            ""),
            "validity_datetime":  p.get("validity_datetime",    ""),
            "community":          p.get("feature_name_en",      ""),
            "province":           p.get("province",             ""),
            "issued":             p.get("publication_datetime", ""),
            "expires":            p.get("expiration_datetime",  ""),
            "impact":             p.get("impact_en",            ""),
            "confidence":         p.get("confidence_en",        ""),
            "detail":             extract_detail(raw_text),
            "alert_text":         raw_text,
        })

    print(f"Fetched {len(alerts)} heat alert(s) for {today}")
    return alerts, today


def load_existing() -> list:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8")).get("alerts", [])
        except Exception as e:
            print(f"Warning: could not read existing data.json: {e}", file=sys.stderr)
    return []


def main():
    new_alerts, today = fetch_alerts()

    existing = load_existing()
    existing = [a for a in existing if a.get("date") != today]

    combined = existing + new_alerts
    combined.sort(key=lambda a: a.get("date", ""), reverse=True)
    combined = combined[:90 * 500]

    DATA_FILE.write_text(
        json.dumps({"alerts": combined}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"data.json updated — {len(combined)} total records ({len(new_alerts)} today, {len(existing)} historical)")


if __name__ == "__main__":
    main()
