#!/usr/bin/env python3
"""Step 1: collect raw candidates (news, China news, weather, strikes, Milan events, Milan club nights, street-dance news + Milan dance calendar).
Usage: python3 collect.py OUTDIR
Writes OUTDIR/raw.json and prints a compact candidate list for selection."""
import sys, os, re, json, time, html, hashlib, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests, feedparser

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
os.makedirs(OUT, exist_ok=True)
NOW = dt.datetime.now(dt.timezone.utc)

FEEDS = [
    # (key, source name, scope hint, url)
    ("ansa", "ANSA", "italy", "https://www.ansa.it/sito/ansait_rss.xml"),
    ("corriere", "Corriere della Sera", "italy", "https://www.corriere.it/rss/homepage.xml"),
    ("repubblica", "la Repubblica", "italy", "https://www.repubblica.it/rss/homepage/rss2.0.xml"),
    ("sole24", "Il Sole 24 Ore", "italy", "https://www.ilsole24ore.com/rss/italia.xml"),
    ("ansa_lomb", "ANSA Lombardia", "italy", "https://www.ansa.it/lombardia/notizie/lombardia_rss.xml"),
    ("corriere_mi", "Corriere Milano", "italy", "https://milano.corriere.it/rss/homepage.xml"),
    ("ilgiorno_mi", "Il Giorno Milano", "italy", "https://www.ilgiorno.it/rss/milano"),
    ("ansa_mondo", "ANSA Mondo", "europe", "https://www.ansa.it/sito/notizie/mondo/mondo_rss.xml"),
    ("bbc_eu", "BBC News", "europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
    ("euronews", "Euronews", "europe", "https://www.euronews.com/rss?level=theme&name=news"),
    ("dw_eu", "DW", "europe", "https://rss.dw.com/rdf/rss-en-eu"),
    ("guardian_eu", "The Guardian", "europe", "https://www.theguardian.com/world/europe-news/rss"),
    ("france24_eu", "France 24", "europe", "https://www.france24.com/en/europe/rss"),
    ("guardian_cn", "The Guardian", "china", "https://www.theguardian.com/world/china/rss"),
    ("bbc_cn", "BBC News", "china", "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml"),
    ("scmp", "South China Morning Post", "china", "https://www.scmp.com/rss/5/feed"),
    ("gn_cina_it", "Google News (IT)", "china", "https://news.google.com/rss/search?q=Cina+Italia+when:2d&hl=it&gl=IT&ceid=IT:it"),
    ("gn_china_eu", "Google News (EU)", "china", "https://news.google.com/rss/search?q=China+EU+when:2d&hl=en-GB&gl=GB&ceid=GB:en"),
    ("gn_corteo", "Google News", "milan_protest", "https://news.google.com/rss/search?q=Milano+corteo+OR+manifestazione+OR+presidio+when:7d&hl=it&gl=IT&ceid=IT:it"),
    ("gn_sciopero", "Google News", "milan_protest", "https://news.google.com/rss/search?q=sciopero+Milano+when:7d&hl=it&gl=IT&ceid=IT:it"),
    # street dance (thin in news; the daily task tops this up with web search)
    ("gn_dance_it", "Google News", "dance", "https://news.google.com/rss/search?q=locking+OR+%22funk+styles%22+OR+popping+battle+OR+workshop+danza+when:60d&hl=it&gl=IT&ceid=IT:it"),
    ("gn_dance_mi", "Google News", "dance", "https://news.google.com/rss/search?q=hip+hop+danza+Milano+battle+OR+contest+OR+stage+when:60d&hl=it&gl=IT&ceid=IT:it"),
    ("gn_dance_eu", "Google News", "dance", "https://news.google.com/rss/search?q=locking+dance+battle+OR+workshop+Europe+when:60d&hl=en-GB&gl=GB&ceid=GB:en"),
]
CHINA_RE = re.compile(r"\b(Cina|cines[ei]|China|Chinese|Pechino|Beijing|Xi Jinping|Hong Kong|Taiwan|Shanghai|Huawei|BYD|Shein|Temu|TikTok)\b", re.I)


def get(url, timeout=20, tries=1):
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as ex:
            last = ex
            time.sleep(1 + k)
    raise last


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def entry_image(e):
    for k in ("media_content", "media_thumbnail"):
        for m in e.get(k, []) or []:
            u = m.get("url")
            if u and not u.endswith(".gif"):
                return u
    for l in e.get("links", []):
        if l.get("rel") == "enclosure" and "image" in (l.get("type") or "image"):
            return l.get("href")
    m = re.search(r'<img[^>]+src="([^"]+)"', e.get("summary", "") or "")
    return m.group(1) if m else None


def fetch_feed(f):
    key, src, scope, url = f
    try:
        d = feedparser.parse(get(url).content)
    except Exception as ex:
        print(f"! feed {key}: {ex}", file=sys.stderr)
        return []
    out = []
    for rank, e in enumerate(d.entries[:40]):
        t = e.get("published_parsed") or e.get("updated_parsed")
        pub = dt.datetime(*t[:6], tzinfo=dt.timezone.utc) if t else None
        if pub and (NOW - pub).days > (60 if scope == "dance" else 2) and scope not in ("milan_protest",):
            continue
        title = clean(e.get("title"))
        source = src
        if key.startswith("gn_") and " - " in title:
            title, source = title.rsplit(" - ", 1)
        link = e.get("link", "")
        cid = key + "-" + hashlib.md5(link.encode()).hexdigest()[:8]
        out.append({"id": cid, "feed": key, "source": source, "scope": scope, "rank": rank,
                    "title": title, "desc": clean(e.get("summary"))[:400], "link": link,
                    "published": pub.isoformat() if pub else None, "image": entry_image(e),
                    "china": bool(CHINA_RE.search(title + " " + clean(e.get("summary"))))})
    return out


# ---------------- weather (open-meteo) ----------------
IT_CITIES = [("米兰", "Milano", "Lombardia", 45.464, 9.190), ("都灵", "Torino", "Piemonte", 45.070, 7.687),
             ("热那亚", "Genova", "Liguria", 44.407, 8.934), ("威尼斯", "Venezia", "Veneto", 45.441, 12.316),
             ("的里雅斯特", "Trieste", "Friuli-Venezia Giulia", 45.650, 13.777), ("特伦托", "Trento", "Trentino-Alto Adige/Südtirol", 46.067, 11.121),
             ("博洛尼亚", "Bologna", "Emilia-Romagna", 44.494, 11.343), ("佛罗伦萨", "Firenze", "Toscana", 43.770, 11.256),
             ("佩鲁贾", "Perugia", "Umbria", 43.110, 12.390), ("安科纳", "Ancona", "Marche", 43.616, 13.519),
             ("罗马", "Roma", "Lazio", 41.903, 12.496), ("佩斯卡拉", "Pescara", "Abruzzo", 42.462, 14.216),
             ("那不勒斯", "Napoli", "Campania", 40.852, 14.268), ("巴里", "Bari", "Puglia", 41.117, 16.872),
             ("波坦察", "Potenza", "Basilicata", 40.640, 15.806), ("卡坦扎罗", "Catanzaro", "Calabria", 38.910, 16.588),
             ("巴勒莫", "Palermo", "Sicilia", 38.116, 13.361), ("卡利亚里", "Cagliari", "Sardegna", 39.224, 9.122),
             ("奥斯塔", "Aosta", "Valle d'Aosta/Vallée d'Aoste", 45.737, 7.320), ("坎波巴索", "Campobasso", "Molise", 41.561, 14.668)]
EU_CITIES = [("伦敦", "London", "United Kingdom", 51.507, -0.128), ("巴黎", "Paris", "France", 48.857, 2.352),
             ("柏林", "Berlin", "Germany", 52.520, 13.405), ("马德里", "Madrid", "Spain", 40.417, -3.704),
             ("里斯本", "Lisbon", "Portugal", 38.722, -9.139), ("罗马", "Roma", "Italy", 41.903, 12.496),
             ("阿姆斯特丹", "Amsterdam", "Netherlands", 52.368, 4.904), ("布鲁塞尔", "Brussels", "Belgium", 50.850, 4.352),
             ("维也纳", "Vienna", "Austria", 48.208, 16.373), ("苏黎世", "Zürich", "Switzerland", 47.377, 8.541),
             ("华沙", "Warsaw", "Poland", 52.230, 21.012), ("布拉格", "Prague", "Czechia", 50.076, 14.438),
             ("布达佩斯", "Budapest", "Hungary", 47.498, 19.040), ("雅典", "Athens", "Greece", 37.984, 23.728),
             ("斯德哥尔摩", "Stockholm", "Sweden", 59.329, 18.069), ("哥本哈根", "Copenhagen", "Denmark", 55.676, 12.568),
             ("奥斯陆", "Oslo", "Norway", 59.914, 10.752), ("赫尔辛基", "Helsinki", "Finland", 60.170, 24.938),
             ("都柏林", "Dublin", "Ireland", 53.350, -6.260), ("布加勒斯特", "Bucharest", "Romania", 44.427, 26.103),
             ("基辅", "Kyiv", "Ukraine", 50.450, 30.523), ("伊斯坦布尔", "Istanbul", "Turkey", 41.008, 28.978),
             ("萨格勒布", "Zagreb", "Croatia", 45.815, 15.982), ("贝尔格莱德", "Belgrade", "Serbia", 44.787, 20.457)]


def weather_multi(cities):
    lat = ",".join(str(c[3]) for c in cities); lon = ",".join(str(c[4]) for c in cities)
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&forecast_days=3&timezone=Europe%%2FRome" % (lat, lon))
    data = get(url, 12, 8).json()
    if isinstance(data, dict):
        data = [data]
    out = []
    for c, d in zip(cities, data):
        cur, day = d["current"], d["daily"]
        out.append({"zh": c[0], "name": c[1], "area": c[2], "lat": c[3], "lon": c[4],
                    "t": round(cur["temperature_2m"]), "code": cur["weather_code"], "wind": round(cur["wind_speed_10m"]),
                    "hum": cur["relative_humidity_2m"],
                    "days": [{"d": day["time"][i], "code": day["weather_code"][i], "max": round(day["temperature_2m_max"][i]),
                              "min": round(day["temperature_2m_min"][i]), "pp": day["precipitation_probability_max"][i]} for i in range(len(day["time"]))]})
    return out


def weather_milan():
    url = ("https://api.open-meteo.com/v1/forecast?latitude=45.464&longitude=9.190"
           "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m,pressure_msl"
           "&hourly=temperature_2m,weather_code,precipitation_probability"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,sunrise,sunset,uv_index_max"
           "&forecast_days=7&timezone=Europe%2FRome")
    d = get(url, 12, 8).json()
    h = d["hourly"]
    hours = [{"t": h["time"][i], "temp": round(h["temperature_2m"][i]), "code": h["weather_code"][i], "pp": h["precipitation_probability"][i]}
             for i in range(min(48, len(h["time"])))]
    dd = d["daily"]
    days = [{"d": dd["time"][i], "code": dd["weather_code"][i], "max": round(dd["temperature_2m_max"][i]), "min": round(dd["temperature_2m_min"][i]),
             "pp": dd["precipitation_probability_max"][i], "rain": dd["precipitation_sum"][i], "wind": round(dd["wind_speed_10m_max"][i]),
             "sunrise": dd["sunrise"][i][-5:], "sunset": dd["sunset"][i][-5:], "uv": dd["uv_index_max"][i]} for i in range(len(dd["time"]))]
    c = d["current"]
    return {"t": round(c["temperature_2m"]), "feels": round(c["apparent_temperature"]), "code": c["weather_code"],
            "wind": round(c["wind_speed_10m"]), "hum": c["relative_humidity_2m"], "pres": round(c["pressure_msl"]),
            "hours": hours, "days": days}


# ---------------- strikes (MIT) ----------------
def strikes():
    d = feedparser.parse(get("https://scioperi.mit.gov.it/mit2/public/scioperi/rss").content)
    out = []
    for e in d.entries:
        t, desc = clean(e.title), clean(e.get("summary", "").replace("<br/>", " | "))
        if not re.search(r"Lombardia|Milano|Rilevanza: Nazionale", t + desc):
            continue
        m = re.search(r"Data inizio: (\d\d/\d\d/\d{4})", t)
        start = dt.datetime.strptime(m.group(1), "%d/%m/%Y").date() if m else None
        if start and (start - NOW.date()).days > 21:
            continue
        out.append({"id": "mit-" + hashlib.md5((t + desc).encode()).hexdigest()[:8], "title": t, "desc": desc,
                    "start": start.isoformat() if start else None, "link": "https://scioperi.mit.gov.it"})
    return out


# ---------------- Milan events (MilanoToday) ----------------
def events():
    today = NOW.astimezone(dt.timezone(dt.timedelta(hours=1))).date()
    pages = ["https://www.milanotoday.it/eventi/",
             f"https://www.milanotoday.it/eventi/dal/{today}/al/{today + dt.timedelta(days=13)}/"]
    pages += [f"https://www.milanotoday.it/eventi/tipo/{t}/" for t in ("mostre", "concerti", "teatri", "manifestazioni", "inaugurazioni", "disco-feste", "sport")]
    links = []
    for p in pages:
        try:
            h = get(p).text
        except Exception as ex:
            print(f"! events page {p}: {ex}", file=sys.stderr); continue
        for l in re.findall(r'href="(/eventi/[a-z0-9\-]+\.html)"', h):
            u = "https://www.milanotoday.it" + l
            if u not in links:
                links.append(u)
    links = links[:70]

    def one(u):
        try:
            h = get(u).text
        except Exception:
            return None
        ev = None
        for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                j = json.loads(b)
            except Exception:
                continue
            for x in (j if isinstance(j, list) else [j]):
                if isinstance(x, dict) and x.get("@type") == "Event":
                    ev = x
        if not ev:
            return None
        img = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        tipo = re.search(r'href="/eventi/tipo/([a-z\-]+)/"[^>]*>', h)
        end = ev.get("endDate") or ev.get("startDate")
        if end and end[:10] < today.isoformat():
            return None
        loc = ev.get("location") or {}
        return {"id": "mt-" + hashlib.md5(u.encode()).hexdigest()[:8], "title": clean(ev.get("name")), "desc": clean(ev.get("description"))[:500],
                "start": (ev.get("startDate") or "")[:10], "end": (end or "")[:10], "venue": clean(loc.get("name") if isinstance(loc, dict) else ""),
                "type": tipo.group(1) if tipo else "", "image": img.group(1) if img else None, "link": u, "source": "MilanoToday"}
    with ThreadPoolExecutor(8) as ex:
        res = [r for r in ex.map(one, links) if r]
    res.sort(key=lambda r: r["start"])
    return res


# ---------------- Milan club nights (Resident Advisor public listings API) ----------------
FUNK_RE = re.compile(r"funk|soul|disco|boogie|hip-hop|hip hop|r&b|rnb|old ?school|jazz|groove|motown|breaks", re.I)


def clubs():
    q = ("query Q($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) { eventListings(filters: $filters, pageSize: $pageSize, page: $page) "
         "{ data { listingDate event { id title date startTime endTime cost venue { name address } genres { name } artists { name } contentUrl images { filename } } } totalResults } }")
    H = dict(UA, **{"Content-Type": "application/json", "Referer": "https://ra.co/", "ra-content-language": "en"})
    end = (NOW + dt.timedelta(days=21)).date().isoformat()
    out, seen = [], set()
    for page in range(1, 6):
        body = {"query": q, "variables": {"filters": {"areas": {"eq": 347}, "listingDate": {"gte": NOW.date().isoformat(), "lte": end}},
                                           "pageSize": 50, "page": page}}
        try:
            d = requests.post("https://ra.co/graphql", headers=H, data=json.dumps(body), timeout=25).json()["data"]["eventListings"]
        except Exception as ex:
            print("! clubs:", str(ex)[:120], file=sys.stderr); break
        for x in d["data"]:
            e = x["event"]
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            genres = [g["name"] for g in e.get("genres") or []]
            # Baile Funk is Brazilian funk, not the old-school funk/soul this list wants first
            funk = any(FUNK_RE.search(g) and "baile" not in g.lower() for g in genres) or bool(re.search(r"\bfunk\b|old ?school|soul|disco|boogie", e["title"], re.I))
            day = max(e["date"][:10], (x.get("listingDate") or "")[:10])  # residencies list an old start date
            out.append({"id": "ra-" + e["id"], "title": e["title"], "date": day, "start": (e.get("startTime") or "")[11:16],
                        "end": (e.get("endTime") or "")[11:16], "venue": (e.get("venue") or {}).get("name", ""), "address": (e.get("venue") or {}).get("address", ""),
                        "genres": genres, "artists": [a["name"] for a in e.get("artists") or []][:5], "cost": (e.get("cost") or "").strip(),
                        "image": ((e.get("images") or [{}])[0]).get("filename"), "link": "https://ra.co" + e["contentUrl"], "source": "Resident Advisor", "funk": funk})
        if len(seen) >= d["totalResults"]:
            break
    out.sort(key=lambda c: (not c["funk"], c["date"], c["start"]))
    return out


# ---------------- Milan urban-dance calendar (Milano Movement Hub, public Google Calendar ICS) ----------------
MMH_ICS = "https://calendar.google.com/calendar/ical/milanomovementhub%40gmail.com/public/basic.ics"
FUNKSTYLE_RE = re.compile(r"locking|popping|waacking|whacking|boogaloo|funk", re.I)


def dance_calendar():
    from zoneinfo import ZoneInfo
    rome = ZoneInfo("Europe/Rome")
    text = get(MMH_ICS).text.replace("\r\n ", "").replace("\n ", "")  # unfold ICS lines
    out = []
    for blk in text.split("BEGIN:VEVENT")[1:]:
        f = {}
        for line in blk.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                f.setdefault(k.split(";")[0], v)
        raw = f.get("DTSTART", "")
        if len(raw) == 8:
            day, hm = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}", ""
        else:
            t = dt.datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
            t = t.replace(tzinfo=dt.timezone.utc).astimezone(rome) if raw.endswith("Z") else t
            day, hm = t.date().isoformat(), t.strftime("%H:%M")
        if not (NOW.date().isoformat() <= day <= (NOW + dt.timedelta(days=60)).date().isoformat()):
            continue
        unesc = lambda s: s.replace(r"\n", " ").replace(r"\,", ",").replace(r"\;", ";").strip()
        title, loc, desc = unesc(f.get("SUMMARY", "")), unesc(f.get("LOCATION", "")), unesc(f.get("DESCRIPTION", ""))
        blob = title + " " + desc
        out.append({"id": "mmh-" + hashlib.md5((raw + title).encode()).hexdigest()[:8], "date": day, "time": hm, "title": title,
                    "venue": loc, "desc": desc[:300], "funk": bool(FUNKSTYLE_RE.search(blob)), "locking": bool(re.search(r"locking", blob, re.I)),
                    "kind": "battle" if re.search(r"battle|contest|jam|cypher", blob, re.I) else "workshop" if re.search(r"workshop|intensive|stage", blob, re.I) else "class",
                    "link": "https://www.milanomovementhub.com", "source": "Milano Movement Hub"})
    out.sort(key=lambda e: (not e["funk"], e["date"], e["time"]))
    return out


def main():
    with ThreadPoolExecutor(10) as ex:
        items = [i for lst in ex.map(fetch_feed, FEEDS) for i in lst]
    raw = {"generatedAt": NOW.isoformat(), "news": items}
    try:
        raw["weather"] = {"italy": weather_multi(IT_CITIES), "europe": weather_multi(EU_CITIES), "milan": weather_milan()}
    except Exception as ex:
        print("! weather:", ex, file=sys.stderr)
    try:
        raw["strikes"] = strikes()
    except Exception as ex:
        print("! strikes:", ex, file=sys.stderr); raw["strikes"] = []
    raw["events"] = events()
    raw["clubs"] = clubs()
    try:
        raw["dance_cal"] = dance_calendar()
    except Exception as ex:
        print("! dance calendar:", str(ex)[:120], file=sys.stderr); raw["dance_cal"] = []
    json.dump(raw, open(os.path.join(OUT, "raw.json"), "w"), ensure_ascii=False, indent=1)

    # compact listing for selection
    def line(i):
        return f"{i['id']} | {i['source']} | {(i['published'] or '')[:16]} | {'CN ' if i.get('china') else ''}{'IMG ' if i.get('image') else ''}| {i['title']}"
    for scope in ("italy", "europe", "china", "milan_protest", "dance"):
        print(f"\n=== {scope.upper()} ===")
        per = {}
        for i in [x for x in items if x["scope"] == scope]:
            per[i["feed"]] = per.get(i["feed"], 0) + 1
            if per[i["feed"]] <= (14 if i["feed"].startswith("gn_") else 12):
                print(line(i))
    print("\n=== CHINA-KEYWORD HITS IN GENERAL FEEDS ===")
    for i in [x for x in items if x["china"] and x["scope"] in ("italy", "europe")]:
        print(line(i))
    print("\n=== STRIKES (MIT) ===")
    for s in raw["strikes"]:
        print(s["id"], "|", s["start"], "|", s["title"], "|", s["desc"][:160])
    print("\n=== EVENTS (MilanoToday) ===")
    for e in raw["events"]:
        print(e["id"], "|", e["start"], "→", e["end"], "|", e["type"], "|", e["venue"], "|", e["title"])
    print("\n=== DANCE CALENDAR (Milano Movement Hub, Milan, next 60 days; FUNK = locking/popping/waacking/boogaloo, listed first) ===")
    for e in raw["dance_cal"]:
        print(e["id"], "|", e["date"], e["time"] or "--:--", "|", e["kind"], "|", "FUNK |" if e["funk"] else "|", e["title"], "|", e["venue"][:50], "|", e["desc"][:140])
    print("\n=== CLUBS (Resident Advisor, Milan, next 21 days; FUNK = funk/soul/disco/old school/hip-hop, listed first) ===")
    for c in raw["clubs"]:
        print(c["id"], "|", c["date"], c["start"], "|", c["venue"], "|", "FUNK |" if c["funk"] else "|", ", ".join(c["genres"]) or "-", "|", c["title"], "|", c["cost"] or "-")
    print("\nweather:", "ok" if "weather" in raw else "MISSING")


if __name__ == "__main__":
    main()
