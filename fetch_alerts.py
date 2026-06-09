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
from datetime import datetime, timezone
from pathlib import Path

GEOMET_URL = "https://api.weather.gc.ca/collections/weather-alerts/items?f=json&limit=1000&lang=en"
DATA_FILE   = Path(__file__).parent / "data.json"
HEAT_PATTERN = re.compile(r"heat|humidex|canicule|chaleur", re.IGNORECASE)

# Boilerplate phrases to truncate alert text before
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
    """Strip boilerplate health advice from the end of alert text."""
    out = text.strip()
    for phrase in STOP_PHRASES:
        idx = out.find(phrase)
        if idx > 80:
            out = out[:idx].strip()
            break
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def fetch_alerts() -> list[dict]:
    try:
        import urllib.request
        with urllib.request.urlopen(GEOMET_URL, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"ERROR fetching GeoMet API: {e}", file=sys.stderr)
        sys.exit(1)

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
            "colour":             p.get("risk_colour_en", ""),
            "alert_type":         name,
            "status":             p.get("status_en", ""),
            "validity_datetime":  p.get("validity_datetime", ""),
            "community":          p.get("feature_name_en", ""),
            "province":           p.get("province", ""),
            "issued":             p.get("publication_datetime", ""),
            "expires":            p.get("expiration_datetime", ""),
            "impact":             p.get("impact_en", ""),
            "confidence":         p.get("confidence_en", ""),
            "detail":             extract_detail(raw_text),
            "alert_text":         raw_text,
            "feature_id":         p.get("feature_id", ""),
        })

    print(f"Fetched {len(alerts)} heat alert(s) for {today}")
    return alerts, today


def load_existing() -> list[dict]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8")).get("alerts", [])
        except Exception as e:
            print(f"Warning: could not read existing data.json: {e}", file=sys.stderr)
    return []


def main():
    new_alerts, today = fetch_alerts()

    existing = load_existing()

    # Remove any existing entries for today (idempotent — safe to re-run)
    existing = [a for a in existing if a.get("date") != today]

    combined = existing + new_alerts

    # Keep only the last 90 days to avoid the file growing indefinitely
    combined.sort(key=lambda a: a.get("date", ""), reverse=True)
    combined = combined[:90 * 500]  # generous upper bound

    DATA_FILE.write_text(
        json.dumps({"alerts": combined}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"data.json updated — {len(combined)} total records ({len(new_alerts)} today, {len(existing)} historical)")


if __name__ == "__main__":
    main()
