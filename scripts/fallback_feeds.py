#!/usr/bin/env python3
"""Rolling two-month free fixtures with multi-provider fallback and cached-data safety.

No invented dates, teams or events. A failed provider never deletes good cached
fixtures. SportsEvents24 has a 30-day maximum horizon; use it once daily.
"""
import calendar
import json
import os
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Asia/Colombo")
TODAY = datetime.now(TZ).date()
FIRST = date(TODAY.year, TODAY.month, 1)
NEXT = date(TODAY.year + (TODAY.month == 12), TODAY.month % 12 + 1, 1)
LAST = date(NEXT.year, NEXT.month, calendar.monthrange(NEXT.year, NEXT.month)[1])
OUT = Path("data/matches.json")
MONTHS = [FIRST.strftime("%Y-%m"), NEXT.strftime("%Y-%m")]
HEADERS = {"User-Agent": "BETSS-SportsCalendar/2.1 (public schedule aggregator)", "Accept": "application/json"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
records = []
health = {}
errors = []
SOURCES = ("Sporting Events", "SportsEvents24", "OpenLigaDB", "Jolpica F1", "ESPN", "TheSportsDB", "previous snapshot")

COUNTRIES = {
    "sri lanka": "LK", "india": "IN", "pakistan": "PK", "australia": "AU",
    "england": "GB", "scotland": "GB", "wales": "GB", "south africa": "ZA",
    "new zealand": "NZ", "bangladesh": "BD", "afghanistan": "AF",
    "west indies": "WI", "ireland": "IE", "zimbabwe": "ZW", "nepal": "NP",
    "namibia": "NA", "oman": "OM", "united arab emirates": "AE",
    "france": "FR", "germany": "DE", "spain": "ES", "italy": "IT",
    "portugal": "PT", "brazil": "BR", "argentina": "AR", "netherlands": "NL",
    "belgium": "BE", "croatia": "HR", "japan": "JP", "south korea": "KR",
    "united states": "US", "usa": "US", "canada": "CA", "switzerland": "CH",
    "fiji": "FJ", "samoa": "WS", "tonga": "TO", "uruguay": "UY",
    "denmark": "DK", "sweden": "SE", "norway": "NO", "poland": "PL",
    "morocco": "MA", "mexico": "MX",
}
SPORTS = {
    "cricket": "Cricket", "football": "Soccer", "soccer": "Soccer",
    "rugby": "Rugby", "rugby union": "Rugby",
    "f1": "Formula 1", "formula 1": "Formula 1", "motorsport": "Formula 1",
    "tennis": "Tennis", "basketball": "Basketball", "badminton": "Badminton",
    "boxing": "Boxing", "volleyball": "Volleyball", "golf": "Golf",
}
SCORE = {"SportsEvents24": 95, "OpenLigaDB": 94, "Jolpica F1": 96,
         "ESPN": 90, "TheSportsDB": 66, "Sporting Events": 65, "previous snapshot": 20}
def warning(source, exc):
    msg = str(exc).replace("\n", " ")[:220]
    errors.append(source + ": " + msg)
    health.setdefault(source, {"status": "warning", "count": 0, "errors": 0})
    health[source]["errors"] += 1
    print("WARN", source, msg, flush=True)

def request_json(source, url, params=None):
    r = SESSION.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def value(row, *keys):
    for key in keys:
        item = row.get(key)
        if isinstance(item, dict):
            item = item.get("name") or item.get("displayName") or item.get("title")
        if item is not None and str(item).strip():
            return str(item).strip()
    return ""

def normalize_time(raw, day=None):
    raw = str(raw or "").strip()
    if not raw and not day:
        return None, "date_only"
    if not raw and day:
        raw = str(day)
    raw = raw.replace("Z", "+00:00")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return raw + "T12:00:00Z", "date_only"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "exact"
    except (ValueError, TypeError):
        return None, "date_only"

def country_code(team):
    name = re.sub(r"\s+(women|men|u\d+|under[- ]\d+|a team)$", "", str(team).lower().strip())
    return COUNTRIES.get(name, "")

def add(source, sport, title, first_team="", second_team="", when=None, precision="exact",
        competition="", status="scheduled", url="", event_id="", international=False):
    sport = SPORTS.get(str(sport).lower().strip(), sport)
    if sport not in SPORTS.values() or not when:
        return
    try:
        local_day = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(TZ).date()
    except (ValueError, AttributeError):
        return
    if not FIRST <= local_day <= LAST:
        return
    first_team = str(first_team or "").strip()
    second_team = str(second_team or "").strip()
    title = str(title or " vs ".join(filter(None, (first_team, second_team)))).strip()
    if not title:
        return
    ca, cb = country_code(first_team), country_code(second_team)
    international = bool(international or (ca and cb and sport in ("Cricket", "Soccer", "Rugby")))
    event_id = str(event_id or (source + ":" + str(local_day) + ":" + title))
    if status not in ("scheduled", "finished", "cancelled"):
        status = "scheduled"
    records.append({
        "event_id": source + ":" + event_id, "sport": sport,
        "event_name": title, "tournament_name": competition or "Other",
        "participant_1": first_team, "participant_2": second_team,
        "start_time": when, "time_precision": precision, "status": status,
        "is_country_match": international,
        "participant_1_country_code": ca if international else "",
        "participant_2_country_code": cb if international else "",
        "promotion_signal": "Monitor", "promotion_score": 20,
        "promotion_reasons": ["Fixture listed by " + source],
        "source": source, "source_url": url or "", "source_verified": True,
    })
    h = health.setdefault(source, {"status": "ok", "count": 0, "errors": 0})
    h["count"] += 1

def fetch_sporting_events():
    # Whole-category JSON downloads (attribution required).
    for slug, sport in (
        ("football", "Soccer"), ("cricket", "Cricket"),
        ("rugby-union", "Rugby"), ("formula-1", "Formula 1"),
        ("tennis", "Tennis"), ("basketball", "Basketball"),
    ):
        try:
            url = "https://sporting-events.org/data/" + slug + ".json"
            data = request_json("Sporting Events", url)
            rows = data if isinstance(data, list) else (
                data.get("events") or data.get("fixtures") or data.get("data") or [])
            if isinstance(rows, dict):
                rows = rows.get("events") or rows.get("items") or []
            if not isinstance(rows, list):
                raise ValueError("unsupported dataset payload")
            for e in rows:
                if not isinstance(e, dict):
                    continue
                start, precision = normalize_time(
                    value(e, "start_time", "startTime", "datetime", "start", "date_time", "kickoff_utc",
                          "date_utc", "dateUTC", "time_utc", "utc"),
                    value(e, "date", "event_date", "start_date"))
                home = value(e, "home_team", "homeTeam", "team1", "team_1", "participant_1")
                away = value(e, "away_team", "awayTeam", "team2", "team_2", "participant_2")
                name = value(e, "event", "name", "title", "event_name", "match")
                status = value(e, "status").lower()
                add("Sporting Events", sport, name, home, away, start, precision,
                    value(e, "competition", "league", "tournament"),
                    "finished" if status in ("finished", "final", "ft") else "scheduled",
                    value(e, "url", "link", "event_url") or "https://sporting-events.org/data/",
                    value(e, "id", "event_id"))
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            warning("Sporting Events " + slug, exc)

def fetch_sportsevents24():
    # 30-day forward limit, 100 req/day and 10 req/min; at most 12 queries per daily refresh.
    selections = (
        ("GB", 1, "Soccer"), ("DE", 1, "Soccer"), ("ES", 1, "Soccer"),
        ("IT", 1, "Soccer"), ("FR", 1, "Soccer"),
        ("LK", 11, "Cricket"), ("IN", 11, "Cricket"), ("AU", 11, "Cricket"),
        ("GB", 5, "Rugby"), ("NZ", 5, "Rugby"), ("ZA", 5, "Rugby"),
        ("US", 2, "Basketball"),
    )
    to = min(TODAY + timedelta(days=30), LAST + timedelta(days=1))
    for country, sport_id, sport in selections:
        source = "SportsEvents24"
        try:
            payload = request_json(source, "https://sportsevents24.com/api/v1/events",
                {"country": country, "sport_id": sport_id, "from": TODAY.isoformat(),
                 "to": to.isoformat(), "limit": 100})
            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise ValueError("unexpected events payload")
            for e in rows:
                if not isinstance(e, dict):
                    continue
                start, precision = normalize_time(
                    value(e, "startTime", "start_time", "start", "scheduled_at",
                          "scheduledAt", "dateTime", "date_time", "kickoff", "utc_time"),
                    value(e, "date", "event_date"))
                home = value(e, "homeTeam", "home_team", "team1", "team_1", "participant_1")
                away = value(e, "awayTeam", "away_team", "team2", "team_2", "participant_2")
                tournament = value(e, "tournament", "tournament_name", "league", "competition")
                title = value(e, "name", "title", "event_name") or " vs ".join(filter(None,(home,away)))
                status = value(e, "status").lower()
                add(source, sport, title, home, away, start, precision, tournament,
                    "finished" if status in ("finished", "final", "ft") else
                    "cancelled" if status in ("cancelled", "canceled") else "scheduled",
                    "https://sportsevents24.com/events", value(e, "id", "event_id"))
            if payload.get("nextCursor"):
                warning(source + " " + country + ":" + str(sport_id),
                        "extra pages available; daily request budget prioritizes sport coverage")
        except (requests.RequestException, ValueError, AttributeError, TypeError) as exc:
            warning(source + " " + country + ":" + str(sport_id), exc)
        time.sleep(0.2)

def fetch_openligadb():
    # Football: Bundesliga first/second division, and selected competition seasons.
    seasons = {FIRST.year if FIRST.month >= 7 else FIRST.year - 1,
               NEXT.year if NEXT.month >= 7 else NEXT.year - 1}
    for season in sorted(seasons):
        for league in ("bl1", "bl2"):
            try:
                url = f"https://api.openligadb.de/getmatchdata/{league}/{season}"
                rows = request_json("OpenLigaDB", url)
                if not isinstance(rows, list):
                    raise ValueError("unexpected league payload")
                for e in rows:
                    start, precision = normalize_time(e.get("matchDateTimeUTC") or e.get("matchDateTime"))
                    a, b = e.get("team1") or {}, e.get("team2") or {}
                    home, away = a.get("teamName", ""), b.get("teamName", "")
                    add("OpenLigaDB", "Soccer", home + " vs " + away, home, away, start, precision,
                        e.get("leagueName") or league,
                        "finished" if e.get("matchIsFinished") else "scheduled",
                        "https://www.openligadb.de/", e.get("matchID"))
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                warning("OpenLigaDB " + league + " " + str(season), exc)

def fetch_jolpica():
    for year in {FIRST.year, NEXT.year}:
        try:
            payload = request_json("Jolpica F1", f"https://api.jolpi.ca/ergast/f1/{year}.json", {"limit": 100})
            for e in payload["MRData"]["RaceTable"]["Races"]:
                start, precision = normalize_time(
                    str(e.get("date") or "") + ("T" + e["time"] if e.get("time") else ""))
                add("Jolpica F1", "Formula 1", e.get("raceName", "Grand Prix"),
                    when=start, precision=precision, competition="Formula 1 World Championship",
                    url=e.get("url") or "https://www.formula1.com/",
                    event_id=str(year) + "-" + str(e.get("round", "")))
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            warning("Jolpica F1 " + str(year), exc)

def fetch_espn():
    # ESPN is unofficial; failures are expected and never block other providers.
    leagues = (
        ("soccer", "eng.1", "Soccer"), ("soccer", "esp.1", "Soccer"),
        ("soccer", "ger.1", "Soccer"), ("soccer", "ita.1", "Soccer"),
        ("soccer", "fra.1", "Soccer"), ("soccer", "uefa.champions", "Soccer"),
        ("basketball", "nba", "Basketball"), ("tennis", "atp", "Tennis"),
        ("tennis", "wta", "Tennis"), ("racing", "f1", "Formula 1"),
        ("cricket", "8048", "Cricket"),
    )
    for sport_path, league, sport in leagues:
        start = FIRST
        while start <= LAST:
            end = min(start + timedelta(days=13), LAST)
            try:
                payload = request_json("ESPN",
                    f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league}/scoreboard",
                    {"dates": start.strftime("%Y%m%d") + "-" + end.strftime("%Y%m%d"), "limit": 1000})
                for e in payload.get("events", []):
                    comp = (e.get("competitions") or [{}])[0]
                    stamp, precision = normalize_time(comp.get("date") or e.get("date"))
                    competitors = comp.get("competitors") or []
                    teams = [x.get("team", x.get("athlete", {})).get("displayName", "") for x in competitors]
                    home, away = (teams + ["", ""])[:2]
                    links = e.get("links") or []
                    status = (comp.get("status") or e.get("status") or {}).get("type") or {}
                    add("ESPN", sport, e.get("name") or e.get("shortName") or " vs ".join(teams),
                        home, away, stamp, precision,
                        (payload.get("leagues") or [{}])[0].get("name") or league,
                        "finished" if status.get("completed") else "scheduled",
                        links[0].get("href", "") if links else "",
                        str(comp.get("id") or e.get("id")))
            except (requests.RequestException, KeyError, ValueError, AttributeError, TypeError) as exc:
                warning("ESPN " + league, exc)
                break  # Don't spam an unavailable feed.
            start = end + timedelta(days=1)
            time.sleep(0.1)

def fetch_sportsdb():
    # Last-resort (small) public feed; avoid 60+ day queries known to be blocked.
    for offset in range(0, 8):
        day = TODAY + timedelta(days=offset)
        try:
            payload = request_json("TheSportsDB",
                "https://www.thesportsdb.com/api/v1/json/123/eventsday.php",
                {"d": day.isoformat()})
            for e in payload.get("events") or []:
                sport = SPORTS.get(str(e.get("strSport", "")).lower())
                if not sport:
                    continue
                stamp, precision = normalize_time(e.get("strTimestamp"),
                    e.get("dateEvent"))
                a, b = e.get("strHomeTeam", ""), e.get("strAwayTeam", "")
                add("TheSportsDB", sport, e.get("strEvent", ""), a, b,
                    stamp, precision, e.get("strLeague", ""),
                    "finished" if "finish" in str(e.get("strStatus", "")).lower() else "scheduled",
                    "https://www.thesportsdb.com/event/" + str(e.get("idEvent", "")),
                    e.get("idEvent"))
        except (requests.RequestException, TypeError, AttributeError, ValueError) as exc:
            warning("TheSportsDB", exc)
            break

def import_previous():
    # GitHub Pages is refreshed by the deployment; last successful feed is accessible
    # even though data/matches.json isn't committed to main.
    old = None
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if not old:
        try:
            old = request_json("previous snapshot",
                "https://rusiru-sss.github.io/sports-match-calendar/data/matches.json")
        except (requests.RequestException, ValueError, TypeError) as exc:
            warning("previous snapshot", exc)
            return
    imported = 0
    for e in old.get("matches", []):
        # Keep only the rolling window. Mark cached rows as such; don't claim fresh data.
        stamp = e.get("start_time")
        if not stamp:
            continue
        before = len(records)
        add("previous snapshot", e.get("sport", ""), e.get("event_name", ""),
            e.get("participant_1", ""), e.get("participant_2", ""),
            stamp, e.get("time_precision", "exact"),
            e.get("tournament_name", ""), e.get("status", "scheduled"),
            e.get("source_url", ""), e.get("event_id", ""), e.get("is_country_match", False))
        imported += len(records) - before
    print("Previous snapshot retained candidates:", imported)

def deduplicate():
    # Canonical identity: sport, Sri Lanka date and normalized teams or event.
    # Preference is accurate timestamp and structured feeds over a date-only listing.
    chosen = {}
    def norm(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    for e in records:
        day = datetime.fromisoformat(e["start_time"].replace("Z", "+00:00")).astimezone(TZ).date()
        teams = sorted([norm(e.get("participant_1")), norm(e.get("participant_2"))])
        if all(teams):
            key = (e["sport"], str(day), *teams)
        else:
            title = norm(e.get("event_name"))
            key = (e["sport"], str(day), title)
        score = SCORE.get(e["source"], 10) + (12 if e["time_precision"] == "exact" else 0)
        if key not in chosen or score > chosen[key][0]:
            chosen[key] = (score, e)
    rows = [item[1] for item in chosen.values()]
    return sorted(rows, key=lambda x: x["start_time"])

def main():
    fetch_sporting_events()
    fetch_openligadb()
    fetch_jolpica()
    fetch_sportsevents24()
    fetch_espn()
    fetch_sportsdb()
    import_previous()
    matches = deduplicate()
    # Preserve last-known-good data rather than publishing an empty / broken calendar.
    if not matches:
        raise SystemExit("No valid fixtures from any provider or previous snapshot; deployment aborted")
    sport_counts = Counter(e["sport"] for e in matches)
    today_count = sum(datetime.fromisoformat(e["start_time"].replace("Z", "+00:00")).astimezone(TZ).date() == TODAY for e in matches)
    provider_health = {}
    for sport in sorted(set(SPORTS.values())):
        count = sport_counts.get(sport, 0)
        providers = sorted(set(e["source"] for e in matches if e["sport"] == sport))
        provider_health[sport] = {
            "status": "ok" if count and any(p != "previous snapshot" for p in providers) else
                      "warning" if count else "empty",
            "count": count, "provider": ", ".join(providers) if providers else "No fixtures returned",
        }
    output = {
        "generated_at_local": datetime.now(TZ).isoformat(),
        "target_month": MONTHS[0], "months_available": MONTHS,
        "matches": matches, "provider_health": provider_health,
        "source_health": health, "feed_warnings": errors[:40],
        "analytics": {"today_match_count": today_count},
        "credits": [{"source": "Sporting Events", "url": "https://sporting-events.org/data/"}],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print("SOURCE COUNTS", dict(Counter(m["source"] for m in matches)))
    print("SPORT COUNTS", dict(sport_counts))
    print("WROTE", len(matches), "events; errors", len(errors), "months", MONTHS, flush=True)

if __name__ == "__main__":
    main()
