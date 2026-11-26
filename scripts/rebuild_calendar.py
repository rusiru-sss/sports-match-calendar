import json, re, subprocess, sys, os
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import requests
p=Path("data/matches.json")
today=datetime.now(ZoneInfo("Asia/Colombo")).date()
months=[today.strftime("%Y-%m"),date(today.year+(today.month==12),today.month%12+1,1).strftime("%Y-%m")]
old={}
try:
    r=requests.get("https://rusiru-sss.github.io/sports-match-calendar/data/matches.json",timeout=20)
    r.raise_for_status()
    old=r.json()
except Exception as e: print("Cache unavailable",e)
payloads=[]
for month in months:
    try:
        subprocess.run([sys.executable,"scraper/scraper.py"],env={**os.environ,"TARGET_MONTH":month},check=True,timeout=600)
        payloads.append(json.loads(p.read_text()))
    except Exception as e: print("Original collector failed",month,e)
try:
    subprocess.run([sys.executable,"scripts/fallback_feeds.py"],check=True,timeout=600)
    payloads.append(json.loads(p.read_text()))
except Exception as e: print("Fallback failed",e)
def norm(s): return re.sub(r"[^a-z0-9]","",str(s or "").lower())
rows={}
for payload in payloads+[old]:
    for m in payload.get("matches",[]):
        name=str(m.get("event_name") or "").strip()
        if not re.search(r"[A-Za-z]",name) or len(name)<3: continue
        try: day=datetime.fromisoformat(m["start_time"].replace("Z","+00:00")).astimezone(ZoneInfo("Asia/Colombo")).date()
        except Exception: continue
        if day.strftime("%Y-%m") not in months: continue
        teams=sorted([norm(m.get("participant_1")),norm(m.get("participant_2"))])
        if m.get("sport") in ("Cricket","Soccer","Rugby") and not all(teams): continue
        key=(m.get("sport"),str(day),*(teams if all(teams) else [norm(name)]))
        rows.setdefault(key,m)
if not rows: raise SystemExit("No valid fixtures; retain deployed site")
out=dict(payloads[0] if payloads else old)
out.update(matches=sorted(rows.values(),key=lambda m:m["start_time"]),target_month=months[0],months_available=months,event_count=len(rows),generated_at_local=datetime.now(ZoneInfo("Asia/Colombo")).isoformat())
out["feed_warnings"]=["Coverage is partial; original feeds have a rolling availability window."]
p.parent.mkdir(exist_ok=True)
p.write_text(json.dumps(out,ensure_ascii=False,indent=2))
from collections import Counter
print("VALID FIXTURES",len(rows),dict(Counter(m["sport"] for m in rows.values())))
