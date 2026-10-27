#!/usr/bin/env python3
"""Milan housing (Trovacasa.it listings) + cheapest flights from Milan (Ryanair + Wizz Air fares in EUR, Google Flights in CNY for China).
Usage: python3 market.py OUTDIR MILAN_GEOJSON
  MILAN_GEOJSON  the published geo/milan.json (88 NIL zones, used to place listings in zones)
Writes OUTDIR/site/data/market.json. No Claude step needed: everything here is deterministic."""
import sys, os, re, json, time, html, statistics, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import requests

OUT, GEO = sys.argv[1], sys.argv[2]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
ROME = ZoneInfo("Europe/Rome")
TODAY = dt.datetime.now(ROME).date()


def get(url, timeout=25, tries=2, **kw):
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except Exception as ex:
            last = ex
            time.sleep(2 + 2 * k)
    raise last


# ---------------- zones ----------------
ZONES = json.load(open(GEO))["features"]


def in_ring(x, y, ring):
    inside = False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i], ring[i + 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def zone_of_point(lat, lon):
    for f in ZONES:
        for poly in f["geometry"]["coordinates"]:
            if in_ring(lon, lat, poly[0]):
                return f["properties"]["name"]
    return None


# every NIL name part ("LODI - CORVETTO" -> lodi, corvetto) plus a few everyday aliases
ALIAS = {"navigli": "PORTA TICINESE - CONCA DEL NAVIGLIO", "nolo": "LORETO - CASORETTO - NOLO", "porta venezia": "BUENOS AIRES - PORTA VENEZIA - PORTA MONFORTE",
         "citylife": "TRE TORRI", "city life": "TRE TORRI", "bocconi": "PORTA VIGENTINA - PORTA LODOVICA", "centrale": "STAZIONE CENTRALE - PONTE SEVESO",
         "porta romana": "PTA ROMANA", "san siro": "SAN SIRO", "chinatown": "SARPI", "paolo sarpi": "SARPI", "garibaldi": "PORTA GARIBALDI - PORTA NUOVA",
         "porta nuova": "PORTA GARIBALDI - PORTA NUOVA", "politecnico": "CITTA' STUDI", "citta studi": "CITTA' STUDI", "città studi": "CITTA' STUDI",
         "niguarda": "NIGUARDA - CA' GRANDA - PRATO CENTENARO - Q.RE FULVIO TESTI", "gallaratese": "Q.RE GALLARATESE - Q.RE SAN LEONARDO - LAMPUGNANO",
         "lampugnano": "Q.RE GALLARATESE - Q.RE SAN LEONARDO - LAMPUGNANO", "santa giulia": "ROGOREDO - SANTA GIULIA", "turro": "PADOVA - TURRO - CRESCENZAGO",
         "via padova": "PADOVA - TURRO - CRESCENZAGO", "crescenzago": "PADOVA - TURRO - CRESCENZAGO", "precotto": "GORLA - PRECOTTO", "gorla": "GORLA - PRECOTTO"}
NAME_KEYS = []
for f in ZONES:
    n = f["properties"]["name"]
    for part in n.split(" - "):
        p = part.replace("Q.RE ", "").replace("P.TA", "PORTA").replace("PTA ", "PORTA ").strip().lower()
        if len(p) >= 5 and not p.startswith("parco"):
            NAME_KEYS.append((p, n))
NAME_KEYS += list(ALIAS.items())
NAME_KEYS.sort(key=lambda kv: -len(kv[0]))


def zone_of_text(text):
    t = " " + re.sub(r"[^a-zà-ù' ]", " ", text.lower()) + " "
    for key, n in NAME_KEYS:
        if f" {key} " in t:
            return n
    return None


# ---------------- housing (Trovacasa.it) ----------------
# Trovacasa labels each ad with its own micro-zone ("Bocconi, Ravizza", "Martini - Insubria"); these map them onto NIL zones
ALIAS2 = {"ravizza": "PORTA VIGENTINA - PORTA LODOVICA", "crocetta": "PORTA VIGENTINA - PORTA LODOVICA", "quadronno": "PORTA VIGENTINA - PORTA LODOVICA",
          "pezzotti": "TIBALDI", "meda": "TIBALDI", "romolo": "TIBALDI", "vercelli": "PAGANO", "wagner": "PAGANO", "sempione": "PAGANO",
          "amendola": "PAGANO", "buonarroti": "PAGANO", "arena": "PAGANO", "arco della pace": "PAGANO", "fiera": "TRE TORRI", "milanocity": "TRE TORRI",
          "corso genova": "MAGENTA - S. VITTORE", "genova": "PORTA GENOVA", "solari": "PORTA GENOVA", "tortona": "PORTA GENOVA", "washington": "PORTA MAGENTA",
          "frua": "DE ANGELI - MONTE ROSA", "martini": "UMBRIA - MOLISE - CALVAIRATE", "insubria": "UMBRIA - MOLISE - CALVAIRATE", "cuoco": "UMBRIA - MOLISE - CALVAIRATE",
          "villa san giovanni": "PADOVA - TURRO - CRESCENZAGO", "plebisciti": "CITTA' STUDI", "susa": "CITTA' STUDI", "piazza napoli": "GIAMBELLINO",
          "napoli": "GIAMBELLINO", "soderini": "GIAMBELLINO", "san paolo": "CANTALUPA", "repubblica": "PORTA GARIBALDI - PORTA NUOVA",
          "moscova": "BRERA", "rovereto": "LORETO - CASORETTO - NOLO", "pasteur": "LORETO - CASORETTO - NOLO", "tre castelli": "BARONA", "faenza": "BARONA",
          "famagosta": "BARONA", "darsena": "PORTA TICINESE - CONCA DEL NAVIGLIO", "ticinese": "PORTA TICINESE - CONCA DEL NAVIGLIO",
          "udine": "CIMIANO - ROTTOLE - Q.RE FELTRE", "istria": "MACIACHINI - MAGGIOLINA", "porta vittoria": "XXII MARZO", "montenero": "XXII MARZO",
          "indipendenza": "XXII MARZO", "cadore": "PTA ROMANA", "medaglie d'oro": "PTA ROMANA", "centro": "DUOMO", "palestro": "GIARDINI P.TA VENEZIA",
          "inganni": "LORENTEGGIO", "bisceglie": "BAGGIO - Q.RE DEGLI OLMI - Q.RE VALSESIA", "olmi": "BAGGIO - Q.RE DEGLI OLMI - Q.RE VALSESIA",
          "ripamonti": "VIGENTINO - Q.RE FATIMA", "abbiategrasso": "STADERA - CHIESA ROSSA - Q.RE TORRETTA - CONCA FALLATA",
          "cenisio": "GHISOLFA", "monumentale": "SARPI", "qt8": "QT 8", "lotto": "SAN SIRO", "rubattino": "LAMBRATE - ORTICA", "piazzale siena": "BANDE NERE", "san vittore": "MAGENTA - S. VITTORE",
          "parco trotter": "LORETO - CASORETTO - NOLO", "bignami": "NIGUARDA - CA' GRANDA - PRATO CENTENARO - Q.RE FULVIO TESTI", "gambara": "DE ANGELI - MONTE ROSA",
          "monte stella": "QT 8", "dezza": "PORTA MAGENTA", "ascanio sforza": "PORTA TICINESE - CONCHETTA", "sulmona": "UMBRIA - MOLISE - CALVAIRATE",
          "san gottardo": "PORTA TICINESE - CONCHETTA", "ponte nuovo": "GORLA - PRECOTTO", "ripa di porta ticinese": "PORTA TICINESE - CONCA DEL NAVIGLIO"}
NAME_KEYS += list(ALIAS2.items())
NAME_KEYS.sort(key=lambda kv: -len(kv[0]))

TROVA = "https://www.trovacasa.it/{what}-in-{deal}/milano?page={page}"
PAGES = {("appartamenti", "affitto"): 20, ("appartamenti", "vendita"): 20, ("negozi", "affitto"): 4, ("negozi", "vendita"): 4}
ROOM_RE = re.compile(r"\b(stanza|camera singola|camera doppia|posto letto|affitto breve|transitorio turistico)\b", re.I)
SKIP_RE = re.compile(r"\b(asta|aste|nuda propriet|rent to buy|affitto con riscatto)", re.I)  # auctions etc. distort prices
TAG = lambda cls, h: (lambda m: html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else "")(re.search(r'class="%s[^"]*"[^>]*>(.*?)</' % cls, h, re.S))


def num(s):
    s = re.sub(r"[^0-9]", "", s or "")
    return float(s) if s else None


def trova_page(args):
    (what, deal), page = args
    time.sleep(0.6 * page)  # stay polite: spread requests out
    try:
        h = get(TROVA.format(what=what, deal=deal, page=page), timeout=45).text
    except Exception as ex:
        print(f"! trovacasa {what}/{deal} p{page}: {str(ex)[:120]}", file=sys.stderr)
        return []
    out = []
    for card in h.split('class="immobileListing__card')[1:]:
        m = re.search(r'href="(/annunci/[^"]+)" class="card__title[^"]*">(.*?)</a>', card, re.S)
        if not m:
            continue
        title = html.unescape(m.group(2)).strip()
        infos = [html.unescape(x).strip() for x in re.findall(r'class="card__info">(.*?)</span>', card)]
        mq = next((num(x) for x in infos if "m" in x and "\xb2" in x), None)
        rooms = next((int(num(x)) for x in infos if "local" in x and num(x)), None)
        price, quart, desc = num(TAG("card__price", card)), TAG("card__quartiere", card), TAG("card__description", card)
        img = re.search(r'data-src="(https://[^"]+\.jpg)"', card)
        if not price or not mq:
            continue
        rent, kind = deal == "affitto", "home" if what == "appartamenti" else "shop"
        if rent and kind == "home" and ROOM_RE.search(title + " " + desc[:120]):
            continue
        if SKIP_RE.search(title + " " + desc):
            continue
        ppm = price / mq
        if not (12 <= mq <= 600) or (rent and not (250 <= price <= 30000 and 8 <= ppm <= 80)) or (not rent and not (30000 <= price <= 6e6 and 1500 <= ppm <= 25000)):
            continue
        out.append({"id": m.group(1).rsplit("-", 1)[-1], "deal": "rent" if rent else "buy", "kind": kind, "price": round(price), "mq": round(mq),
                    "rooms": rooms if kind == "home" else None, "ppm": round(price / mq, 2 if rent else 0),
                    "zone": zone_of_text(quart) or zone_of_text(title), "area": quart, "title": title[:120], "desc": desc[:160],
                    "url": "https://www.trovacasa.it" + m.group(1), "img": img.group(1) if img else None, "source": "Trovacasa"})
    return out


def thumb(url):
    try:
        from PIL import Image
        import io, base64
        im = Image.open(io.BytesIO(get(url, timeout=20, tries=1).content)).convert("RGB")
        w, h = im.size
        im = im.resize((136, max(1, int(h * 136 / w))))
        b = io.BytesIO(); im.save(b, "WEBP", quality=35)
        return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


def merge_duplicates(items):
    """Same flat listed on several sites (same deal, zone, size within 3 m², same rooms, price within 12%):
    keep the cheapest as the card and list the others under "alts" for a price comparison."""
    items.sort(key=lambda i: i["price"])
    out = []
    for i in items:
        hit = next((o for o in out if o["deal"] == i["deal"] and o["kind"] == i["kind"] and o.get("zone") and o["zone"] == i.get("zone")
                    and o["source"] != i["source"] and abs(o["mq"] - i["mq"]) <= 3 and o.get("rooms") == i.get("rooms")
                    and abs(o["price"] - i["price"]) <= 0.12 * o["price"]), None)
        if hit:
            hit.setdefault("alts", []).append({"source": i["source"], "price": i["price"], "url": i["url"]})
        else:
            out.append(i)
    items[:] = out


def housing():
    jobs = [(k, p) for k, n in PAGES.items() for p in range(1, n + 1)]
    with ThreadPoolExecutor(3) as ex:
        items = [i for lst in ex.map(trova_page, jobs) for i in lst]
    seen, uniq = set(), []
    for i in items:
        if i["id"] not in seen:
            seen.add(i["id"]); uniq.append(i)
    homes = [i for i in uniq if i["kind"] == "home"]
    typical = [i for i in homes if 30 <= i["mq"] <= 150]  # tiny studios / student rooms inflate €/m², keep zone stats like-for-like
    med = lambda xs: round(statistics.median(xs), 1) if xs else None
    city = {"rent": med([i["ppm"] for i in typical if i["deal"] == "rent"]), "buy": med([i["ppm"] for i in typical if i["deal"] == "buy"])}
    zones = {}
    for f in ZONES:
        n = f["properties"]["name"]
        r = [i["ppm"] for i in typical if i["zone"] == n and i["deal"] == "rent"]
        b = [i["ppm"] for i in typical if i["zone"] == n and i["deal"] == "buy"]
        if not r and not b:
            continue
        z = {"rent": med(r), "buy": med(b), "n_rent": len(r), "n_buy": len(b)}
        if len(r) >= 4 and len(b) >= 4:
            z["ratio"] = round(z["buy"] / z["rent"])          # 租售比 1:N (months of rent to pay the price)
            z["yield"] = round(z["rent"] * 12 / z["buy"] * 100, 2)  # gross annual yield %
        zones[n] = z
    # value score: rent -> cheaper per m2 than its zone; buy -> higher estimated rent yield
    for i in uniq:
        ref = zones.get(i["zone"], {})
        if i["kind"] != "home":
            i["score"] = -i["ppm"] if i["deal"] == "rent" else -i["ppm"] / 200
            continue
        if i["deal"] == "rent":
            base = ref.get("rent") if ref.get("n_rent", 0) >= 3 else city["rent"]
            i["vs_zone"] = round((i["ppm"] / base - 1) * 100) if base else None
            i["score"] = -(i["vs_zone"] or 0)
        else:
            zr = ref.get("rent") if ref.get("n_rent", 0) >= 5 else city["rent"]
            zr = min(max(zr, city["rent"] * 0.7), city["rent"] * 1.4) if zr and city["rent"] else zr  # small samples swing wildly
            i["est_yield"] = round(zr * 12 / i["ppm"] * 100, 2) if zr else None
            i["score"] = i["est_yield"] or 0
    merge_duplicates(uniq)
    keep = []
    for deal in ("rent", "buy"):
        for kind in ("home", "shop"):
            grp = sorted((i for i in uniq if i["deal"] == deal and i["kind"] == kind), key=lambda i: -i["score"])
            if kind == "home":  # every flat type gets a share, one-bedrooms (bilocali) first
                by = {}
                for i in grp:
                    by.setdefault(min(i["rooms"] or 2, 4), []).append(i)
                for r, cap in ((2, 24), (1, 12), (3, 12), (4, 8)):
                    keep += by.get(r, [])[:cap]
            else:
                keep += grp[:16]
    with ThreadPoolExecutor(6) as ex:
        imgs = list(ex.map(lambda i: thumb(i["img"]) if i.get("img") else None, keep))
    for i, im in zip(keep, imgs):
        i["img"] = im
        i.pop("score", None)
    print(f"housing: {len(uniq)} listings ({len(homes)} homes, {sum(1 for i in uniq if i['zone'])} placed), {len(zones)} zones, kept {len(keep)}", file=sys.stderr)
    return {"city": city, "zones": zones, "listings": keep, "sample": len(uniq), "placed": sum(1 for i in uniq if i["zone"]), "source": "Trovacasa.it"}


# ---------------- flights ----------------
CHINA = [("PEK", "北京", 40.08, 116.58), ("PVG", "上海", 31.14, 121.81), ("CAN", "广州", 23.39, 113.30), ("SZX", "深圳", 22.64, 113.81),
         ("CTU", "成都", 30.58, 103.95), ("HGH", "杭州", 30.23, 120.43), ("WNZ", "温州", 27.91, 120.85), ("CKG", "重庆", 29.72, 106.64),
         ("WUH", "武汉", 30.78, 114.21), ("XIY", "西安", 34.45, 108.75), ("NKG", "南京", 31.74, 118.86), ("XMN", "厦门", 24.54, 118.13),
         ("FOC", "福州", 25.93, 119.66), ("TAO", "青岛", 36.36, 120.09), ("HKG", "香港", 22.31, 113.91)]
GF_COOKIES = {"CONSENT": "YES+cb", "SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg"}
GF_RE = re.compile(r'aria-label="From ([0-9,]+) Chinese yuan\. ([^"]*?)"')  # China fares are asked for in CNY


def gf_one(args):
    code, day = args
    url = f"https://www.google.com/travel/flights?q=Flights%20to%20{code}%20from%20MIL%20on%20{day}%20oneway&curr=CNY&hl=en&gl=IT"
    try:
        h = requests.get(url, headers=UA, cookies=GF_COOKIES, timeout=30).text
    except Exception as ex:
        print(f"! gflights {code} {day}: {str(ex)[:80]}", file=sys.stderr)
        return None
    best = None
    for p, desc in GF_RE.findall(h):
        p = int(p.replace(",", ""))
        if best is None or p < best[0]:
            best = (p, html.unescape(desc))
    if not best:
        return None
    desc = best[1]
    stops = 0 if desc.startswith("Nonstop") else int((re.match(r"(\d+) stop", desc) or [0, 0])[1])
    air = re.search(r"flight with (.+?)\.", desc)
    dep = re.search(r"Leaves (.+?) at", desc)
    dur = re.search(r"Total duration ([^.]+)", desc)
    return {"code": code, "date": day, "price": best[0], "stops": stops, "airline": air.group(1) if air else "",
            "from": dep.group(1) if dep else "", "duration": dur.group(1) if dur else "", "url": url, "cur": "CNY"}


def china_flights():
    days = [(TODAY + dt.timedelta(days=d)).isoformat() for d in (3, 8, 13, 18, 23, 28)]
    jobs = [(c[0], d) for c in CHINA for d in days]
    with ThreadPoolExecutor(4) as ex:
        res = [r for r in ex.map(gf_one, jobs) if r]
    out = []
    for code, zh, lat, lon in CHINA:
        rs = sorted((r for r in res if r["code"] == code), key=lambda r: r["price"])
        if rs:
            out.append(dict(rs[0], zh=zh, lat=lat, lon=lon, region="china", checked=len(rs), source="Google Flights"))
    print(f"china flights: {len(out)}/{len(CHINA)} cities from {len(res)}/{len(jobs)} searches", file=sys.stderr)
    return out


CITY_ZH = {"London": "伦敦", "Paris": "巴黎", "Barcelona": "巴塞罗那", "Madrid": "马德里", "Lisbon": "里斯本", "Porto": "波尔图", "Seville": "塞维利亚",
           "Valencia": "瓦伦西亚", "Malaga": "马拉加", "Alicante": "阿利坎特", "Palma": "帕尔马", "Ibiza": "伊维萨", "Berlin": "柏林", "Hamburg": "汉堡",
           "Frankfurt": "法兰克福", "Cologne": "科隆", "Dusseldorf": "杜塞尔多夫", "Memmingen": "梅明根", "Brussels": "布鲁塞尔", "Charleroi": "沙勒罗瓦",
           "Amsterdam": "阿姆斯特丹", "Eindhoven": "埃因霍温", "Dublin": "都柏林", "Edinburgh": "爱丁堡", "Manchester": "曼彻斯特", "Vienna": "维也纳",
           "Prague": "布拉格", "Budapest": "布达佩斯", "Warsaw": "华沙", "Krakow": "克拉科夫", "Athens": "雅典", "Thessaloniki": "塞萨洛尼基",
           "Copenhagen": "哥本哈根", "Stockholm": "斯德哥尔摩", "Oslo": "奥斯陆", "Helsinki": "赫尔辛基", "Riga": "里加", "Vilnius": "维尔纽斯",
           "Tallinn": "塔林", "Bucharest": "布加勒斯特", "Sofia": "索非亚", "Zagreb": "萨格勒布", "Split": "斯普利特", "Dubrovnik": "杜布罗夫尼克",
           "Malta": "马耳他", "Valletta": "马耳他", "Bratislava": "布拉迪斯拉发", "Belgrade": "贝尔格莱德", "Tirana": "地拉那", "Podgorica": "波德戈里察",
           "Sarajevo": "萨拉热窝", "Skopje": "斯科普里", "Marseille": "马赛", "Nice": "尼斯", "Bordeaux": "波尔多", "Toulouse": "图卢兹",
           "Rome": "罗马", "Naples": "那不勒斯", "Palermo": "巴勒莫", "Catania": "卡塔尼亚", "Bari": "巴里", "Brindisi": "布林迪西", "Cagliari": "卡利亚里",
           "Lamezia": "拉梅齐亚", "Reggio Calabria": "雷焦卡拉布里亚", "Trapani": "特拉帕尼", "Alghero": "阿尔盖罗", "Olbia": "奥尔比亚", "Pescara": "佩斯卡拉",
           "Comiso": "科米索", "Crotone": "克罗托内", "Venice": "威尼斯", "Trieste": "的里雅斯特", "Istanbul": "伊斯坦布尔", "Kaunas": "考纳斯",
           "Gdansk": "格但斯克", "Wroclaw": "弗罗茨瓦夫", "Poznan": "波兹南", "Katowice": "卡托维兹", "Bologna": "博洛尼亚", "Pisa": "比萨",
           "Tenerife": "特内里费", "Gran Canaria": "大加那利", "Lanzarote": "兰萨罗特", "Fuerteventura": "富埃特文图拉", "Santiago": "圣地亚哥-德孔波斯特拉",
           "Corfu": "科孚", "Chania": "哈尼亚", "Heraklion": "伊拉克利翁", "Rhodes": "罗得岛", "Kos": "科斯", "Santorini": "圣托里尼", "Mykonos": "米科诺斯",
           "Faro": "法鲁", "Luxembourg": "卢森堡", "Bristol": "布里斯托尔", "Liverpool": "利物浦", "Leeds": "利兹", "Glasgow": "格拉斯哥", "Shannon": "香农",
           "Marrakesh": "马拉喀什", "Fez": "非斯", "Tangier": "丹吉尔", "Agadir": "阿加迪尔", "Rabat": "拉巴特", "Amman": "安曼", "Tel Aviv": "特拉维夫",
           "Paphos": "帕福斯", "Larnaca": "拉纳卡", "Lyon": "里昂", "Nantes": "南特", "Billund": "比隆", "Aarhus": "奥胡斯", "Gothenburg": "哥德堡",
           "Bergen": "卑尔根", "Tampere": "坦佩雷", "Lodz": "罗兹", "Rzeszow": "热舒夫", "Lublin": "卢布林", "Bydgoszcz": "比得哥什", "Szczecin": "什切青",
           "Iasi": "雅西", "Cluj": "克卢日", "Timisoara": "蒂米什瓦拉", "Plovdiv": "普罗夫迪夫", "Varna": "瓦尔纳", "Burgas": "布尔加斯",
           "Zadar": "扎达尔", "Pula": "普拉", "Rijeka": "里耶卡", "Bremen": "不来梅", "Karlsruhe": "卡尔斯鲁厄", "Nuremberg": "纽伦堡", "Weeze": "韦泽",
           "Hahn": "法兰克福哈恩", "Beauvais": "巴黎博韦", "Kiev": "基辅", "Lviv": "利沃夫", "Chisinau": "基希讷乌", "Yerevan": "埃里温", "Tbilisi": "第比利斯",
           "Kutaisi": "库塔伊西", "Granada": "格拉纳达", "Bilbao": "毕尔巴鄂", "Zaragoza": "萨拉戈萨", "Girona": "赫罗纳", "Reus": "雷乌斯",
           "Murcia": "穆尔西亚", "Almeria": "阿尔梅里亚", "Jerez": "赫雷斯", "Menorca": "梅诺卡", "Santander": "桑坦德", "Vigo": "维戈", "Asturias": "阿斯图里亚斯",
           "Valladolid": "巴利亚多利德", "Madeira": "马德拉", "Ponta Delgada": "蓬塔德尔加达", "Brno": "布尔诺", "Ostrava": "俄斯特拉发", "Kosice": "科希策",
           "Debrecen": "德布勒森", "Maastricht": "马斯特里赫特", "Bournemouth": "伯恩茅斯", "Newcastle": "纽卡斯尔", "East Midlands": "东米德兰兹",
           "Birmingham": "伯明翰", "Cork": "科克", "Knock": "诺克", "Kerry": "凯里", "Belfast": "贝尔法斯特", "Aberdeen": "阿伯丁", "Exeter": "埃克塞特",
           "Cardiff": "加的夫", "Kaunas ": "考纳斯", "Palanga": "帕兰加", "Perugia": "佩鲁贾", "Ancona": "安科纳", "Genoa": "热那亚", "Turin": "都灵",
           "Treviso": "特雷维索", "Verona": "维罗纳", "Lamezia Terme": "拉梅齐亚", "Salerno": "萨莱诺", "Eilat": "埃拉特", "Essaouira": "索维拉",
           "Nador": "纳祖尔", "Oujda": "乌季达", "Ouarzazate": "瓦尔扎扎特", "Tetouan": "得土安", "Aqaba": "亚喀巴", "Ljubljana": "卢布尔雅那", "Biarritz": "比亚里茨", "Kefalonia": "凯法利尼亚", "Kalamata": "卡拉马塔", "Lourdes": "卢尔德", "Rovaniemi": "罗瓦涅米",
           "Sandefjord": "桑讷菲尤尔", "Vitoria": "维多利亚", "Funchal": "丰沙尔", "Wroclaw": "弗罗茨瓦夫", "Bucharest": "布加勒斯特", "Thessaloniki": "塞萨洛尼基",
           "Paphos": "帕福斯", "Rhodes": "罗得岛", "Zaragoza": "萨拉戈萨", "Toulouse": "图卢兹", "Menorca": "梅诺卡", "Naples": "那不勒斯", "Oslo": "奥斯陆",
           "Torp": "奥斯陆托尔普", "Rygge": "奥斯陆里格", "Skavsta": "斯德哥尔摩", "Vasteras": "韦斯特罗斯", "Lappeenranta": "拉彭兰塔", "Gothenburg": "哥德堡",
           "Bergamo": "贝加莫", "Milan": "米兰", "Trapani": "特拉帕尼", "Brindisi": "布林迪西", "Tours": "图尔", "Poitiers": "普瓦捷", "Carcassonne": "卡尔卡松",
           "Perpignan": "佩皮尼昂", "Nimes": "尼姆", "Montpellier": "蒙彼利埃", "La Rochelle": "拉罗谢尔", "Bergerac": "贝尔热拉克", "Brive": "布里夫", "Dole": "多勒",
           "Grenoble": "格勒诺布尔", "Limoges": "利摩日", "Pau": "波城", "Rodez": "罗德兹", "Tarbes": "塔布", "Santiago de Compostela": "圣地亚哥-德孔波斯特拉",
           "Chania (Crete)": "哈尼亚", "Heraklion (Crete)": "伊拉克利翁", "Billund": "比隆", "Vaxjo": "韦克舍", "Ostend": "奥斯坦德", "Groningen": "格罗宁根",
           "Leipzig": "莱比锡", "Dortmund": "多特蒙德", "Baden-Baden": "巴登-巴登", "Friedrichshafen": "腓特烈港", "Munich": "慕尼黑", "Stuttgart": "斯图加特",
           "Salzburg": "萨尔茨堡", "Linz": "林茨", "Graz": "格拉茨", "Klagenfurt": "克拉根福", "Innsbruck": "因斯布鲁克", "Zadar": "扎达尔", "Osijek": "奥西耶克",
           "Maribor": "马里博尔", "Nis": "尼什", "Podgorica": "波德戈里察", "Preveza": "普雷韦扎", "Kos": "科斯", "Skiathos": "斯基亚索斯", "Volos": "沃洛斯", "Zakynthos": "扎金索斯",
           "Malmo": "马尔默", "Aalborg": "奥尔堡", "Haugesund": "海于格松", "Kaunas": "考纳斯", "Riga": "里加", "Tallinn": "塔林", "Palanga": "帕兰加",
           "Suceava": "苏恰瓦", "Oradea": "奥拉迪亚", "Sibiu": "锡比乌", "Targu Mures": "特尔古穆列什", "Craiova": "克拉约瓦", "Bacau": "巴克乌", "Satu Mare": "萨图马雷",
           "Iasi": "雅西", "IASI": "雅西", "Arad": "阿拉德", "Brasov": "布拉索夫", "Lampedusa": "兰佩杜萨", "Prishtina": "普里什蒂纳", "Reykjavik": "雷克雅未克", "Vitoria-Gasteiz": "维多利亚", "Cluj-Napoca": "克卢日", "Timisoara": "蒂米什瓦拉"}
NON_EUROPE = {"ma", "jo", "il", "eg", "tn", "dz", "lb", "sa", "ae", "kw", "om", "qa", "bh", "kz", "uz", "mv", "ly"}


def km(a, b):
    import math
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def ryanair_fares():
    try:
        airports = {a["code"]: a for a in get("https://www.ryanair.com/api/views/locate/5/airports/en/active").json()}
    except Exception as ex:
        print("! ryanair airports:", ex, file=sys.stderr)
        return []
    frm, to = (TODAY + dt.timedelta(days=1)).isoformat(), (TODAY + dt.timedelta(days=30)).isoformat()
    out = []
    for dep in ("BGY", "MXP", "LIN"):
        url = (f"https://services-api.ryanair.com/farfnd/v4/oneWayFares?departureAirportIataCode={dep}"
               f"&outboundDepartureDateFrom={frm}&outboundDepartureDateTo={to}&currency=EUR&market=it-it")
        try:
            fares = get(url).json().get("fares", [])
        except Exception as ex:
            print(f"! ryanair {dep}: {ex}", file=sys.stderr)
            continue
        for f in fares:
            o = f["outbound"]
            code = o["arrivalAirport"]["iataCode"]
            a = airports.get(code)
            if not a or a["country"]["code"] in NON_EUROPE:
                continue
            day = o["departureDate"][:10]
            out.append({"code": code, "city": a["city"]["name"], "country": a["country"]["name"], "cc": a["country"]["code"],
                        "lat": a["coordinates"]["latitude"], "lon": a["coordinates"]["longitude"], "price": o["price"]["value"],
                        "date": day, "time": o["departureDate"][11:16], "from": o["departureAirport"]["name"], "fromCode": dep,
                        "airline": "Ryanair",
                        "url": (f"https://www.ryanair.com/it/it/trip/flights/select?adults=1&teens=0&children=0&infants=0&dateOut={day}"
                                f"&isReturn=false&originIata={dep}&destinationIata={code}")})
    print(f"ryanair: {len(out)} fares", file=sys.stderr)
    return out


def wizz_fares():
    try:  # the API path carries the site build number, read it from the home page
        ver = re.search(r"be\.wizzair\.com/([0-9]+\.[0-9]+\.[0-9]+)", get("https://wizzair.com/it-it", timeout=40).text).group(1)
        H = dict(UA, **{"Content-Type": "application/json", "Origin": "https://wizzair.com", "Referer": "https://wizzair.com/"})
        cities = {c["iata"]: c for c in requests.get(f"https://be.wizzair.com/{ver}/Api/asset/map?languageCode=en-gb", headers=H, timeout=30).json()["cities"]}
    except Exception as ex:
        print("! wizz setup:", str(ex)[:120], file=sys.stderr)
        return []
    frm, to = (TODAY + dt.timedelta(days=1)).isoformat(), (TODAY + dt.timedelta(days=30)).isoformat()
    jobs = []
    for dep in ("MXP", "BGY"):
        for c in (cities.get(dep) or {}).get("connections", []):
            a = cities.get(c["iata"])
            if a and c.get("isDirectFlight", True) and not c.get("isConnected") and a["countryCode"].lower() not in NON_EUROPE:
                jobs.append((dep, a))

    def one(job):
        dep, a = job
        body = {"flightList": [{"departureStation": dep, "arrivalStation": a["iata"], "from": frm, "to": to}],
                "priceType": "regular", "adultCount": 1, "childCount": 0, "infantCount": 0}
        try:
            r = requests.post(f"https://be.wizzair.com/{ver}/Api/search/timetable", headers=H, data=json.dumps(body), timeout=30)
            fl = [f for f in r.json().get("outboundFlights", []) if f.get("priceType") == "price" and (f.get("price") or {}).get("amount")]
        except Exception as ex:
            print(f"! wizz {dep}-{a['iata']}: {str(ex)[:80]}", file=sys.stderr)
            return None
        if not fl:
            return None
        f = min(fl, key=lambda f: f["price"]["amount"])
        day = f["departureDate"][:10]
        t = (f.get("departureDates") or [""])[0][11:16]
        return {"code": a["iata"], "city": a["shortName"], "country": a["countryName"], "cc": a["countryCode"].lower(),
                "lat": a["latitude"], "lon": a["longitude"], "price": f["price"]["amount"], "date": day, "time": t,
                "from": cities[dep]["shortName"], "fromCode": dep, "airline": "Wizz Air",
                "url": f"https://wizzair.com/it-it/booking/select-flight/{dep}/{a['iata']}/{day}/null/1/0/0/null"}
    with ThreadPoolExecutor(3) as ex:
        out = [r for r in ex.map(one, jobs) if r]
    print(f"wizz: {len(out)} fares from {len(jobs)} routes", file=sys.stderr)
    return out


def europe_flights():
    fares = ryanair_fares() + wizz_fares()
    # one entry per destination city: airports within 70 km count as the same city (Luton/Stansted, Charleroi/Brussels...)
    best = []
    for f in sorted(fares, key=lambda f: f["price"]):
        hit = next((b for b in best if km((b["lat"], b["lon"]), (f["lat"], f["lon"])) < 70), None)
        if hit is None:
            name = f["city"].strip()
            best.append(dict(f, zh=CITY_ZH.get(name) or CITY_ZH.get(name.split(" ")[0], name), stops=0, region="europe",
                             source=f["airline"], cur="EUR", others=[]))
        elif f["airline"] not in {hit["airline"]} | {o["airline"] for o in hit["others"]}:
            hit["others"].append({k: f[k] for k in ("airline", "price", "date", "from", "code", "url")})
    print(f"europe flights: {len(best)} cities from {len(fares)} fares", file=sys.stderr)
    return best


def main():
    with ThreadPoolExecutor(3) as ex:
        fh, fe, fc = ex.submit(housing), ex.submit(europe_flights), ex.submit(china_flights)
        house, eu, cn = fh.result(), fe.result(), fc.result()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    data = {"updatedAt": now, "date": TODAY.isoformat(), "housing": house,
            "flights": {"window": [(TODAY + dt.timedelta(days=1)).isoformat(), (TODAY + dt.timedelta(days=30)).isoformat()],
                        "europe": eu, "china": cn}}
    ddir = os.path.join(OUT, "site", "data")
    os.makedirs(ddir, exist_ok=True)
    p = os.path.join(ddir, "market.json")
    json.dump(data, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"market: listings {len(house['listings'])}, zones {len(house['zones'])}, europe {len(eu)}, china {len(cn)}, {os.path.getsize(p)//1024} KB")
    print("market:", "ok" if house["listings"] and eu and cn else "PARTIAL")


if __name__ == "__main__":
    main()
