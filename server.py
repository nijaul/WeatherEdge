"""WeatherEdge AI 0.2 — read-only local research server.
Standard library only. No Kalshi account or trading routes.
"""
import http.server
import json
import math
import re
import time
import datetime as dt
import urllib.parse
import urllib.request
import urllib.error
import threading
import webbrowser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
KALSHI="https://api.elections.kalshi.com/trade-api/v2"
NWS="https://api.weather.gov"
USER_AGENT="WeatherEdgeResearch/0.2 (read-only research; contact: weatheredge-support@example.com)"
CITIES={
 "New York":(40.7128,-74.0060,"America/New_York",["new york","nyc","central park","knyc"]),
 "Chicago":(41.8781,-87.6298,"America/Chicago",["chicago","ohare","o'hare","ord","kord"]),
 "Miami":(25.7617,-80.1918,"America/New_York",["miami","kmia"]),
 "Los Angeles":(34.0522,-118.2437,"America/Los_Angeles",["los angeles","downtown la","kcqt"]),
 "Denver":(39.7392,-104.9903,"America/Denver",["denver","kden"]),
 "Austin":(30.2672,-97.7431,"America/Chicago",["austin","kaus"]),
 "Philadelphia":(39.9526,-75.1636,"America/New_York",["philadelphia","kphl"]),
 "Seattle":(47.6062,-122.3321,"America/Los_Angeles",["seattle","ksea"]),
 "Atlanta":(33.7490,-84.3880,"America/New_York",["atlanta","katl"]),
 "Boston":(42.3601,-71.0589,"America/New_York",["boston","kbos"]),
 "Washington DC":(38.9072,-77.0369,"America/New_York",["washington dc","washington d.c.","dca","kdca"]),
 "Dallas":(32.7767,-96.7970,"America/Chicago",["dallas","dfw","kdfw"]),
 "Houston":(29.7604,-95.3698,"America/Chicago",["houston","kiah"]),
 "Phoenix":(33.4484,-112.0740,"America/Phoenix",["phoenix","kphx"]),
 "San Francisco":(37.7749,-122.4194,"America/Los_Angeles",["san francisco","ksfo"]),
 "Cincinnati":(39.1031,-84.5120,"America/New_York",["cincinnati","kcvg"]),
}
CACHE={}
def upstream(base,path="",params=None,ttl=90):
    query=("?"+urllib.parse.urlencode(params)) if params else ""
    url=base+path+query
    entry=CACHE.get(url)
    if entry and time.monotonic()-entry[0]<ttl:
        return entry[1]
    req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/geo+json, application/json"})
    with urllib.request.urlopen(req,timeout=18) as response:
        data=json.loads(response.read(12_000_000))
    CACHE[url]=(time.monotonic(),data)
    return data

def market_price(m,side):
    value=m.get(side+"_dollars")
    if value is not None and str(value)!="":
        try:return float(value)*100
        except (ValueError,TypeError):pass
    value=m.get(side)
    if value is not None and str(value)!="":
        try:return float(value)
        except (ValueError,TypeError):pass
    return None

def is_weather(m,event=None):
    text=" ".join(str(x or "") for x in (
        m.get("title"),m.get("subtitle"),m.get("ticker"),
        m.get("event_ticker"),(event or {}).get("title"),
        (event or {}).get("category"),(event or {}).get("sub_title"))).lower()
    return bool(re.search(r"weather|temperature|highest temp|high temp|lowest temp|low temp|snowfall|rainfall|precipitation|hurricane|wind speed|climate|heat index|daily high|daily low|k[x]?(?:high|low|temp)",text))

def collect_weather(max_pages=8):
    """Paginate event catalog; only filter locally after retrieving market metadata."""
    events=[]
    markets=[]
    cursor=""
    pages=0
    error=None
    seen=set()
    for _ in range(min(max_pages,30)):
        args={"limit":"200","status":"open","with_nested_markets":"true"}
        if cursor:args["cursor"]=cursor
        try:
            payload=upstream(KALSHI,"/events",args,ttl=45)
        except Exception as ex:
            error=str(ex)
            break
        pages+=1
        for event in payload.get("events",[]):
            nested=event.get("markets") or []
            for m in nested:
                if not is_weather(m,event):continue
                ticker=m.get("ticker")
                if ticker and ticker not in seen:
                    seen.add(ticker)
                    m=dict(m)
                    m["event_title"]=event.get("title","")
                    m["category"]=event.get("category","")
                    m["interpretation"]=interpret(m)
                    markets.append(m)
            if any(is_weather(m,event) for m in nested):
                events.append({"ticker":event.get("event_ticker"),"title":event.get("title")})
        new_cursor=payload.get("cursor") or ""
        if not new_cursor or new_cursor==cursor:break
        cursor=new_cursor
    return {"markets":markets,"events":events,"pages":pages,
            "has_more":bool(cursor),"next_cursor":cursor,
            "error":error,"scanned_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "coverage_note":"Scanned open event pages. Further API pages may exist; weather coverage is not guaranteed complete."}

def detect_city(text):
    lower=text.lower()
    matches=[]
    for name,(_,_,_,aliases) in CITIES.items():
        for alias in aliases:
            if re.search(r"(?<![a-z])"+re.escape(alias)+r"(?![a-z])",lower):
                matches.append(name)
                break
    return matches[0] if len(matches)==1 else None

def detect_date(text):
    # Only explicit ISO or full named-month dates; ticker-encoded dates intentionally excluded.
    iso=re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b",text)
    dates=[]
    for s in iso:
        try:dates.append(dt.date.fromisoformat(s))
        except ValueError:pass
    month_re=r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b"
    for mo,day,year in re.findall(month_re,text,re.I):
        month=dt.datetime.strptime(mo[:3],"%b").month
        today=dt.date.today()
        yr=int(year) if year else today.year
        try:
            d=dt.date(yr,month,int(day))
            if not year and d<today-dt.timedelta(days=3):
                d=dt.date(yr+1,month,int(day))
            dates.append(d)
        except ValueError:pass
    dates=list(set(dates))
    return dates[0] if len(dates)==1 else None

def detect_range(text):
    # Conservative extraction: explicit textual comparisons and bounded ranges.
    t=text.lower()
    # Must be a high-temperature market. We do not auto-interpret lows or precipitation.
    if not re.search(r"\b(high(?:est)?|maximum|max)\b",t) or not re.search(r"\b(temp(?:erature)?|degrees?|°f|fahrenheit)\b",t):
        return None
    n=r"(-?\d{1,3})"
    patterns=[
        (rf"(?:between|from)\s+{n}\s*(?:°f|degrees?)?\s+(?:and|to|-)\s+{n}", "range"),
        (rf"{n}\s*(?:°f|degrees?)?\s*(?:to|-)\s*{n}\s*(?:°f|degrees?)?", "range"),
        (rf"(?:above|over|greater than|higher than)\s+{n}", "above"),
        (rf"(?:at least|or higher|or more)\s+{n}", "atleast"),
        (rf"(?:below|under|less than|lower than)\s+{n}", "below"),
        (rf"(?:at most|or lower|or less)\s+{n}", "atmost"),
    ]
    for pattern,kind in patterns:
        m=re.search(pattern,t)
        if not m:continue
        nums=[int(x) for x in m.groups()]
        if any(x < -60 or x > 140 for x in nums):continue
        if kind=="range" and nums[0]<=nums[1]:
            return {"low":nums[0],"high":nums[1],"kind":kind}
        if kind=="above":return {"low":nums[0]+1,"high":None,"kind":kind}
        if kind=="atleast":return {"low":nums[0],"high":None,"kind":kind}
        if kind=="below":return {"low":None,"high":nums[0]-1,"kind":kind}
        if kind=="atmost":return {"low":None,"high":nums[0],"kind":kind}
    return None

def interpret(m):
    title=" ".join(str(m.get(k) or "") for k in ("event_title","title","subtitle","yes_sub_title"))
    city=detect_city(title)
    day=detect_date(title)
    bounds=detect_range(title)
    issues=[]
    if not city:issues.append("City not unambiguously recognized")
    if not day:issues.append("Full target date not explicit")
    if not bounds:issues.append("Supported high-temperature threshold not unambiguously recognized")
    # Station verification is NOT possible from name matching alone.
    if city and day and bounds:
        issues.append("Official settlement station and measurement rules require manual verification")
    return {"city":city,"date":day.isoformat() if day else None,"bounds":bounds,
            "match_status":"REVIEW_REQUIRED" if city and day and bounds else "UNMATCHED",
            "issues":issues}

def forecast_for(city):
    lat,lon,tz,_=CITIES[city]
    points=upstream(NWS,f"/points/{lat},{lon}",ttl=86400)["properties"]
    hourly=upstream(points["forecastHourly"],ttl=600)["properties"]["periods"]
    daily=upstream(points["forecast"],ttl=600)["properties"]["periods"]
    grouped={}
    for p in hourly:
        stamp=p.get("startTime")
        temp=p.get("temperature")
        if not stamp or not isinstance(temp,(int,float)):continue
        local=dt.datetime.fromisoformat(stamp).astimezone(ZoneInfo(tz))
        # Temperature conversion if NWS changes temperature unit.
        fahrenheit=float(temp) if p.get("temperatureUnit","F")=="F" else float(temp)*9/5+32
        key=local.date().isoformat()
        grouped.setdefault(key,[]).append(fahrenheit)
    return {"city":city,"timezone":tz,"daily":daily[:14],
            "highs":{day:{"high_f":max(vals),"hourly_points":len(vals)} for day,vals in grouped.items()},
            "fetched_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "warning":"Point forecast hourly highs are not official settlement-station maxima."}

def cdf(x):return .5*(1+math.erf(x/math.sqrt(2)))
def estimate(mu,bounds,sigma=5.0):
    low=bounds.get("low")
    high=bounds.get("high")
    # continuity correction for integer-reported daily max
    p=(cdf((high+.5-mu)/sigma) if high is not None else 1.0)-(cdf((low-.5-mu)/sigma) if low is not None else 0.0)
    return max(0,min(1,p))

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed=urllib.parse.urlsplit(self.path)
        try:
            if parsed.path=="/":
                data=(ROOT/"index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length",str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if parsed.path=="/api/weather-markets":
                return self.reply(collect_weather())
            if parsed.path=="/api/forecast":
                q=dict(urllib.parse.parse_qsl(parsed.query))
                city=q.get("city","")
                if city not in CITIES:raise ValueError("Unsupported city")
                return self.reply(forecast_for(city))
            if parsed.path=="/api/cities":
                return self.reply({"cities":list(CITIES)})
            return self.reply({"error":"Not found"},404)
        except urllib.error.HTTPError as e:
            return self.reply({"error":f"Upstream HTTP {e.code}","details":e.read(300).decode("utf-8","replace")},502)
        except Exception as e:
            return self.reply({"error":str(e)},400 if isinstance(e,ValueError) else 502)
    def reply(self,obj,status=200):
        data=json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self,*args):pass

class Server(http.server.ThreadingHTTPServer):
    daemon_threads=True

if __name__=="__main__":
    server=Server(("127.0.0.1",0),Handler)
    address=f"http://127.0.0.1:{server.server_port}"
    print("WeatherEdge AI 0.2:",address,flush=True)
    threading.Timer(.8,lambda:webbrowser.open(address)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
