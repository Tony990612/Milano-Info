#!/usr/bin/env python3
"""Step 3: build database documents + write batches.
Usage: python3 build.py OUTDIR SELECTION.json PREV_LATEST.json
  OUTDIR       dir with raw.json and articles/
  SELECTION    Chinese selection written by Claude
  PREV_LATEST  the currently published data/latest.json (missing file is fine)
Writes OUTDIR/site/data/<date>.json and OUTDIR/site/data/latest.json and prints the `files` map to publish.
"""
import sys, os, re, json, io, glob, base64, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests
from PIL import Image

OUT, SEL, PREV = sys.argv[1], sys.argv[2], sys.argv[3]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
raw = json.load(open(os.path.join(OUT, "raw.json")))
sel = json.load(open(SEL))
from zoneinfo import ZoneInfo
ROME = ZoneInfo("Europe/Rome")
today = sel.get("date") or dt.datetime.now(ROME).date().isoformat()
POOL = {i["id"]: i for i in raw["news"]}
POOL.update({e["id"]: e for e in raw.get("events", [])})
POOL.update({s["id"]: dict(s, source="意大利交通部罢工公告 (MIT)") for s in raw.get("strikes", [])})
CLUBS = {c["id"]: c for c in raw.get("clubs", [])}


def art(cid):
    p = os.path.join(OUT, "articles", cid + ".json")
    return json.load(open(p)) if os.path.exists(p) else {}


def thumb(url):
    if not url:
        return None
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        w, h = im.size
        if w < 120 or h < 80:
            return None
        tw = 560
        if w > tw:
            im = im.resize((tw, int(h * tw / w)), Image.LANCZOS)
        # crop to max 16:10-ish height
        w, h = im.size
        if h > w * 0.75:
            top = int((h - w * 0.75) / 2)
            im = im.crop((0, top, w, top + int(w * 0.75)))
        b = io.BytesIO()
        im.save(b, "WEBP", quality=52, method=6)
        return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception as ex:
        print("! image", url[:80], ex, file=sys.stderr)
        return None


def safe_id(s):
    return re.sub(r"[^A-Za-z0-9_\-.~:@+]", "-", s)[:180]


docs = {}  # (collection, id) -> body

# ---- news ----
news_jobs = []
for rank, n in enumerate(sel.get("news", [])):
    src = POOL.get(n["cid"], {})
    a = art(n["cid"])
    news_jobs.append((rank, n, src, a))

with ThreadPoolExecutor(8) as ex:
    imgs = list(ex.map(lambda j: thumb(j[3].get("image") or j[2].get("image")), news_jobs))
for (rank, n, src, a), img in zip(news_jobs, imgs):
    did = safe_id(today + "_" + n["cid"])
    docs[("news", did)] = {
        "date": today, "rank": rank, "scope": n["scope"], "cat": n["cat"],
        "title_zh": n["title_zh"], "summary_zh": n["summary_zh"], "body_zh": n.get("body_zh", []),
        "title_orig": src.get("title", ""), "source": n.get("source") or src.get("source", ""),
        "url": a.get("url") or src.get("link", ""), "published": src.get("published"),
        "place_zh": n.get("place_zh", ""), "region": n.get("region", ""), "lat": n.get("lat"), "lon": n.get("lon"),
        "tags": n.get("tags", []), "image": img,
    }

# ---- run id: every document is written once (version 1), so no version lookups are needed ----
now = dt.datetime.now(dt.timezone.utc)
now_iso = now.isoformat()
RUN = now.astimezone(ROME).strftime("%Y%m%dT%H%M")

# ---- events ----
ev_jobs = []
for rank, e in enumerate(sel.get("events", [])):
    src = POOL.get(e["cid"], {})
    a = art(e["cid"])
    ev_jobs.append((rank, e, src, a))
with ThreadPoolExecutor(8) as ex:
    eimgs = list(ex.map(lambda j: thumb(j[3].get("image") or j[2].get("image")), ev_jobs))
for (rank, e, src, a), img in zip(ev_jobs, eimgs):
    did = safe_id(RUN + "_" + e["cid"])
    docs[("events", did)] = {
        "run": RUN, "rank": rank, "cat": e["cat"], "title_zh": e["title_zh"], "summary_zh": e["summary_zh"], "body_zh": e.get("body_zh", []),
        "start": e.get("start") or src.get("start"), "end": (e["end"] if "end" in e else (src.get("end") or e.get("start") or src.get("start"))),
        "time_zh": e.get("time_zh", ""), "venue_zh": e.get("venue_zh") or src.get("venue", ""),
        "title_orig": src.get("title", ""), "source": e.get("source") or src.get("source", ""),
        "url": a.get("url") or src.get("link", ""), "image": img, "updated": today,
    }

# ---- club nights (Resident Advisor candidates, picked and described by Claude) ----
club_jobs = [(rank, c, CLUBS.get(c.get("cid"), {})) for rank, c in enumerate(sel.get("clubs", []))]
with ThreadPoolExecutor(8) as ex:
    cimgs = list(ex.map(lambda j: thumb(j[2].get("image")), club_jobs))
clubs = []
for (rank, c, src), img in zip(club_jobs, cimgs):
    if not src:
        continue
    clubs.append({"id": safe_id(RUN + "_" + src["id"]), "rank": rank, "title": src["title"], "title_zh": c.get("title_zh", ""),
                  "note_zh": c.get("note_zh", ""), "genres": src["genres"], "genres_zh": c.get("genres_zh", []), "funk": bool(c.get("funk", src["funk"])),
                  "date": src["date"], "start": src["start"], "end": src["end"], "venue": src["venue"], "address": src["address"],
                  "artists": src["artists"], "cost": src["cost"], "url": src["link"], "source": src["source"], "image": img})


def og_image(url):
    try:
        h = requests.get(url, headers=UA, timeout=15).text
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', h) or re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', h)
        return m.group(1) if m else None
    except Exception:
        return None


# ---- street dance (battles, workshops, jams) found by Claude via news + web search; earlier finds roll over until they end ----
dance = []
for d in sel.get("dance", []):
    if not d.get("url") or not d.get("title_zh"):
        continue
    dance.append({k: d.get(k) for k in ("scope", "type", "styles", "locking", "title_zh", "summary_zh", "start", "end", "time_zh",
                                        "city_zh", "venue_zh", "url", "source", "title_orig")})
with ThreadPoolExecutor(6) as ex:
    dimgs = list(ex.map(lambda d: thumb(og_image(d["url"])), dance))
for d, img in zip(dance, dimgs):
    d["image"], d["id"] = img, safe_id(RUN + "_" + re.sub(r"\W+", "", d["url"])[-40:])
    d["found"] = today

# ---- weather ----
if raw.get("weather"):
    docs[("weather", RUN)] = dict(raw["weather"], updatedAt=now_iso, run=RUN)

# ---- previous latest.json -> archive dates ----
try:
    prev = json.load(open(PREV))
except Exception:
    prev = {}
cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=6)).isoformat()
prev_dates = set((prev.get("status") or {}).get("dates") or [])
dates = sorted({today} | {d for d in prev_dates if d >= cutoff}, reverse=True)
dropped = sorted(d for d in prev_dates if d < cutoff and d != today)

status = {"run": RUN, "updatedAt": now_iso, "date": today, "dates": dates,
          "schedule_zh": "每天 07:00（米兰时间）自动更新",
          "counts": {"news": len(sel.get("news", [])), "events": len(sel.get("events", [])), "clubs": len(clubs), "dance": len(dance)},
          "brief_zh": sel.get("brief_zh", "")}
news = [dict(v, id=k[1]) for k, v in docs.items() if k[0] == "news"]
events = [dict(v, id=k[1]) for k, v in docs.items() if k[0] == "events"]
weather = docs.get(("weather", RUN)) or prev.get("weather")
seen_urls = {d["url"] for d in dance}
for d in prev.get("dance") or []:
    if d.get("url") not in seen_urls and (d.get("end") or d.get("start") or "") >= today:
        dance.append(d); seen_urls.add(d.get("url"))

ddir = os.path.join(OUT, "site", "data")
os.makedirs(ddir, exist_ok=True)
day_path = os.path.join(ddir, today + ".json")
latest_path = os.path.join(ddir, "latest.json")
json.dump({"date": today, "run": RUN, "news": news}, open(day_path, "w"), ensure_ascii=False, separators=(",", ":"))
json.dump({"status": status, "weather": weather, "events": events, "clubs": clubs, "dance": dance}, open(latest_path, "w"), ensure_ascii=False, separators=(",", ":"))

files = {f"data/{today}.json": os.path.abspath(day_path), "data/latest.json": os.path.abspath(latest_path)}
market_path = os.path.join(ddir, "market.json")  # written by market.py (housing + flights), published when present
if os.path.exists(market_path):
    files["data/market.json"] = os.path.abspath(market_path)
for d in dropped:
    files[f"data/{d}.json"] = None
print(f"run {RUN}  news: {len(news)}  events: {len(events)}  images: {sum(1 for x in imgs + eimgs if x)}/{len(imgs) + len(eimgs)}  "
      f"sizes: day {os.path.getsize(day_path)//1024} KB, latest {os.path.getsize(latest_path)//1024} KB  dates kept: {dates}")
print("Publish with the Artifact tool: url=<artifact>, file_path=<downloaded index.html>, files=")
print(json.dumps(files, ensure_ascii=False))
