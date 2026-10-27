#!/usr/bin/env python3
"""Step 2: fetch article text + image for selected candidate ids.
Usage: python3 article.py OUTDIR id1 id2 ...
Reads OUTDIR/raw.json, writes OUTDIR/articles/<id>.json, prints compact text for translation."""
import sys, os, re, json, html
from concurrent.futures import ThreadPoolExecutor
import requests

OUT = sys.argv[1]
IDS = sys.argv[2:]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
raw = json.load(open(os.path.join(OUT, "raw.json")))
POOL = {i["id"]: i for i in raw["news"]}
POOL.update({e["id"]: dict(e, scope="event") for e in raw.get("events", [])})
POOL.update({s["id"]: dict(s, scope="strike", source="MIT", image=None) for s in raw.get("strikes", [])})
os.makedirs(os.path.join(OUT, "articles"), exist_ok=True)


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def resolve_gn(s, link):
    h = s.get(link, timeout=20).text
    aid = re.search(r'data-n-a-id="([^"]+)"', h).group(1)
    sg = re.search(r'data-n-a-sg="([^"]+)"', h).group(1)
    ts = re.search(r'data-n-a-ts="([^"]+)"', h).group(1)
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"%s",%s,"%s"]' % (aid, ts, sg))
    r = s.post("https://news.google.com/_/DotsSplashUi/data/batchexecute", data={"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])},
               headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}, timeout=20)
    return json.loads(json.loads(r.text.split("\n\n", 1)[1])[0][2])[1]


def meta(h, prop):
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]+)"' % re.escape(prop), h) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="%s"' % re.escape(prop), h)
    return html.unescape(m.group(1)) if m else None


def one(cid):
    it = POOL.get(cid)
    if not it:
        return cid, {"error": "unknown id"}
    res = {"id": cid, "url": it.get("link"), "image": it.get("image"), "text": "", "desc": it.get("desc", "")}
    if it.get("scope") == "strike":
        res["text"] = it["desc"]
        return cid, res
    s = requests.Session(); s.headers.update(UA)
    try:
        url = it["link"]
        if "news.google.com" in url:
            url = resolve_gn(s, url)
            res["url"] = url
        r = s.get(url, timeout=20)
        r.raise_for_status()
        h = r.text
        res["image"] = res["image"] or meta(h, "og:image") or meta(h, "twitter:image")
        res["desc"] = meta(h, "og:description") or res["desc"]
        body = re.sub(r"<(script|style|nav|footer|header|aside|figure)[\s\S]*?</\1>", " ", h, flags=re.I)
        ps = [clean(p) for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>", body, re.I)]
        ps = [p for p in ps if len(p) > 70 and not re.search(r"cookie|abbonati|subscribe|newsletter|©|riproduzione riservata|sign up", p, re.I)]
        res["text"] = "\n".join(ps)[:3000]
    except Exception as ex:
        res["error"] = str(ex)[:120]
    return cid, res


with ThreadPoolExecutor(8) as ex:
    results = dict(ex.map(one, IDS))
for cid in IDS:
    r = results[cid]
    json.dump(r, open(os.path.join(OUT, "articles", cid + ".json"), "w"), ensure_ascii=False)
    it = POOL.get(cid, {})
    print(f"\n##### {cid} | {it.get('source')} | {it.get('title')}")
    print("URL:", r.get("url"), "| IMG:", "yes" if r.get("image") else "no", "|", ("ERR " + r["error"]) if r.get("error") else "")
    print("DESC:", (r.get("desc") or "")[:300])
    print((r.get("text") or "")[:1800])
