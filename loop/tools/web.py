#!/usr/bin/env python3
"""loop/tools/web.py — the research stages' only window onto the web. Stdlib, no keys.

    web.py search "<query>" [-n 8]     DuckDuckGo HTML results: title, url, snippet
    web.py fetch <url> [--max 12000]   the page as readable text (scripts/nav stripped)

Only the research mode's prompts name this tool. The guard refuses curl/wget to the
outside; this is the deliberate, logged exception (state/web.log) so a report can cite
what it actually read instead of what a 27B half-remembers.
"""
import argparse
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
LOG = os.environ.get("AUTOGOD_WEB_LOG", os.path.join(os.path.dirname(__file__), "..", "..", "state", "web.log"))


def _log(line):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        raw = r.read(2_000_000)
    m = re.search(r"charset=([\w-]+)", ctype)
    enc = m.group(1) if m else "utf-8"
    try:
        return raw.decode(enc, "replace"), ctype
    except LookupError:
        return raw.decode("utf-8", "replace"), ctype


def _text(doc):
    doc = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|aside|form)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?is)<!--.*?-->", " ", doc)
    doc = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article|blockquote|pre)>", "\n", doc)
    doc = re.sub(r"(?s)<[^>]+>", " ", doc)
    doc = html.unescape(doc)
    doc = re.sub(r"[ \t\r\f\v]+", " ", doc)
    doc = re.sub(r"\n\s*\n+", "\n\n", doc)
    return doc.strip()


def search(q, n=8):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    doc, _ = _get(url)
    out = []
    for m in re.finditer(r'(?s)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<div class="result results|$)', doc):
        href, title, rest = m.group(1), m.group(2), m.group(3)
        # DDG wraps links: //duckduckgo.com/l/?uddg=<url>&rut=...
        u = urllib.parse.urlparse(href if "://" in href else "https:" + href)
        real = urllib.parse.parse_qs(u.query).get("uddg", [href])[0]
        if "duckduckgo.com/y.js" in real or real.startswith("https://duckduckgo.com/y.js"):
            continue  # an ad
        sm = re.search(r'(?s)class="result__snippet"[^>]*>(.*?)</a>', rest)
        out.append({"title": _text(title), "url": real, "snippet": _text(sm.group(1)) if sm else ""})
        if len(out) >= n:
            break
    _log("search %r -> %d" % (q, len(out)))
    return out


def fetch(url, cap=12000):
    doc, ctype = _get(url)
    if "html" in ctype or doc.lstrip().startswith("<"):
        text = _text(doc)
    else:
        text = doc
    _log("fetch %s -> %d chars" % (url, len(text)))
    if len(text) > cap:
        text = text[:cap] + "\n\n[... cut at %d chars]" % cap
    return text


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("-n", type=int, default=8)
    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("--max", type=int, default=12000)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "search":
            res = search(a.query, a.n)
            if not res:
                print("no results"); return 1
            for i, r in enumerate(res, 1):
                print("%d. %s\n   %s\n   %s\n" % (i, r["title"], r["url"], r["snippet"]))
        else:
            print(fetch(a.url, a.max))
    except Exception as e:  # noqa: BLE001
        print("error: %s" % e); _log("error %s" % e); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
