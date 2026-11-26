#!/usr/bin/env python3
"""Build a rolling current + next-month match feed from TheSportsDB's public API."""
import calendar
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import requests

BASE = "https://www.thesportsdb.com/api/v1/json"
KEY = os.getenv("SPORTSDB_API_KEY", "123")
SPORTS = {"Soccer": "Soccer", "Cricket": "Cricket", "Tennis": "Tennis",
          "Basketball": "Basketball", "Rugby": "Rugby", "Motorsport": "Formula 1",
          "Boxing": "Boxing", "Badminton": "Badminton", "Volleyball": "Volleyball"}
TODAY = date.today()
MONTHS = [(TODAY.year, TODAY.month)]
MONTHS.append((TODAY.year + (TODAY.month == 12), TODAY.month % 12 + 1))
session = requests.Session()
session.headers["User-Agent"] = "SportsMatchCalendar/1.0 (public sports schedule)"
matches, seen, errors = [], set(), []

def event_time(event):
    day = event.get("dateEvent")
    if not day:
        return None, None
    raw = (event.get("strTimestamp") or "").strip()
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo:
                return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "exact"
        except ValueError:
            pass
    rawtime = (event.get("strTime") or "").strip()
    if rawtime:
        try:
            dt = datetime.fromisoformat(day + "T" + rawtime[:8] + "+00:00")
            return dt.isoformat().replace("+00:00", "Z"), "exact"
        except ValueError:
            pass
    return day + "T12:00:00Z", "date_only"

def convert(e):
    stamp, precision = event_time(e)
    if not stamp:
        return None
    sport = SPORTS.get(e.get("strSport"))
    if not sport:
        return None
    name = e.get("strEvent") or "Event"
    home, away = e.get("strHomeTeam") or "", e.get("strAwayTeam") or ""
    league = e.get("strLeague") or "Other"
    status = (e.get("strStatus") or "").lower()
    score = 20 + (15 if sport == "Cricket" else 10 if sport == "Soccer" else 0)
    key = str(e.get("idEvent") or (stamp + name + league))
    if key in seen:
        return None
    seen.add(key)
    return {"event_id": key, "sport": sport, "tournament_name": league,
        "event_name": name, "participant_1": home, "participant_2": away,
        "start_time": stamp, "time_precision": precision,
        "status": "finished" if "finish" in status or "match finished" in status else
                  "cancelled" if "cancel" in status else "scheduled",
        "promotion_signal": "Monitor", "promotion_score": score,
        "promotion_reasons": ["Public schedule listing"],
        "is_country_match": False, "source": "TheSportsDB",
        "source_url": "https://www.thesportsdb.com/event/" + key}
        
for year, month in MONTHS:
    for d in range(1, calendar.monthrange(year, month)[1] + 1):
        day = date(year, month, d).isoformat()
        url = BASE + "/" + KEY + "/eventsday.php?" + urlencode({"d": day})
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
            events = response.json().get("events") or []
            for event in events:
                obj = convert(event)
                if obj:
                    matches.append(obj)
        except (requests.RequestException, ValueError, AttributeError) as exc:
            errors.append(day + ": " + str(exc))
        time.sleep(0.18)

matches.sort(key=lambda m: m["start_time"])
if errors and not matches:
    raise SystemExit("All sports feed requests failed; refusing empty deployment: " + "; ".join(errors[:3]))
out = {"generated_at_local": datetime.now(timezone.utc).isoformat(),
       "target_month": f"{MONTHS[0][0]:04d}-{MONTHS[0][1]:02d}",
       "months_available": [f"{y:04d}-{m:02d}" for y,m in MONTHS],
       "matches": matches,
       "provider_health": {sport: {"status": "warning" if errors else "ok",
           "count": sum(m["sport"] == sport for m in matches),
           "provider": "TheSportsDB (limited free API coverage)"}
           for sport in SPORTS.values()},
       "feed_warnings": errors[:20]}
Path("data").mkdir(exist_ok=True)
Path("data/matches.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {len(matches)} events, {len(errors)} day-fetch errors, for {out['months_available']}")
