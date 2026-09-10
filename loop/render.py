"""loop/render.py — deterministic renderers the pass runs so the 27B never writes HTML
for a report or a diff. Markdown (a useful subset) -> one monotone page; unified diff ->
one monotone page. Stdlib only, no dependencies, inline CSS, no emoji.
"""
import html
import re

CSS = """
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#0b0b0c;color:#e6e6e6;font:15px/1.55 -apple-system,Segoe UI,Inter,system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:1.7rem;letter-spacing:-.01em;margin:0 0 .3em;font-style:italic}
h2{font-size:1.15rem;margin:2em 0 .5em;border-bottom:1px solid #2a2a2c;padding-bottom:.25em}
h3{font-size:1rem;margin:1.5em 0 .4em}
p{margin:.7em 0}a{color:#e6e6e6;text-decoration:underline;text-underline-offset:3px}
a:hover{color:#fff}code{background:#161618;padding:.1em .35em;font-size:.9em}
pre{background:#111113;border:1px solid #232325;padding:12px 14px;overflow-x:auto;font-size:.85rem;line-height:1.45}
pre code{background:none;padding:0}blockquote{border-left:2px solid #444;margin:1em 0;padding:.2em 1em;color:#bdbdbd}
ul,ol{padding-left:1.4em}li{margin:.25em 0}hr{border:0;border-top:1px solid #2a2a2c;margin:2em 0}
.kicker{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:#8a8a8a;margin-bottom:1.4em}
table{border-collapse:collapse;margin:1em 0;font-size:.92rem}td,th{border:1px solid #2a2a2c;padding:.35em .7em;text-align:left}
.d{font:.84rem/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre;overflow-x:auto}
.d .f{color:#fff;background:#1a1a1d;padding:.4em .6em;margin-top:1.2em;font-weight:600}
.d .h{color:#8a8a8a}.d .a{color:#c7f0c7;background:#0f1a0f}.d .r{color:#f0c7c7;background:#1a0f0f}
.d span{display:block;padding:0 .6em}
"""


def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', s)
    s = re.sub(r"(?<![\"'>=])(https?://[^\s<)]+)", r'<a href="\1" rel="noopener">\1</a>', s)
    return s


def md_to_html(md, title=None, kicker="AUTOGOD research", extra_html=""):
    lines = md.replace("\r", "").split("\n")
    out, i, n = [], 0, len(lines)
    para, lst, ltype = [], [], None

    def flush_para():
        if para:
            out.append("<p>%s</p>" % _inline(" ".join(para))); para.clear()

    def flush_list():
        nonlocal ltype
        if lst:
            out.append("<%s>%s</%s>" % (ltype, "".join("<li>%s</li>" % _inline(x) for x in lst), ltype))
            lst.clear(); ltype = None

    first_h1 = None
    while i < n:
        ln = lines[i]
        if ln.startswith("```"):
            flush_para(); flush_list()
            j = i + 1; buf = []
            while j < n and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(buf)))
            i = j + 1; continue
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            flush_para(); flush_list()
            lvl = len(m.group(1)); txt = m.group(2).strip()
            if lvl == 1 and first_h1 is None:
                first_h1 = txt
                if title is None:
                    title = txt
                i += 1; continue   # the page's own h1 is written once, from the title
            out.append("<h%d>%s</h%d>" % (lvl, _inline(txt), lvl)); i += 1; continue
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", ln):
            flush_para()
            typ = "ol" if re.match(r"^\s*\d+[.)]", ln) else "ul"
            if ltype and ltype != typ:
                flush_list()
            ltype = typ
            lst.append(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", ln)); i += 1; continue
        if ln.startswith(">"):
            flush_para(); flush_list()
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ")); i += 1
            out.append("<blockquote>%s</blockquote>" % _inline(" ".join(buf))); continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln):
            flush_para(); flush_list(); out.append("<hr>"); i += 1; continue
        if "|" in ln and i + 1 < n and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            flush_para(); flush_list()
            rows = []
            while i < n and "|" in lines[i]:
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            head, body = rows[0], rows[2:]
            out.append("<table><tr>%s</tr>%s</table>" % (
                "".join("<th>%s</th>" % _inline(c) for c in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline(c) for c in r) for r in body)))
            continue
        if not ln.strip():
            flush_para(); flush_list(); i += 1; continue
        if lst and ln.startswith(("  ", "\t")):
            lst[-1] += " " + ln.strip(); i += 1; continue
        flush_list(); para.append(ln.strip()); i += 1
    flush_para(); flush_list()
    title = title or "Report"
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\">"
            "<title>%s</title><style>%s</style><main><div class=kicker>%s</div><h1>%s</h1>%s</main>\n"
            % (html.escape(title), CSS, html.escape(kicker), html.escape(title), "\n".join(out) + extra_html))


def diff_block(diff):
    """The unified diff as one monotone block (for md_to_html's extra_html)."""
    rows = []
    for ln in diff.replace("\r", "").split("\n"):
        e = html.escape(ln) or " "
        if ln.startswith("diff --git"):
            rows.append('<span class=f>%s</span>' % e)
        elif ln.startswith(("+++", "---", "index ", "new file", "deleted file", "similarity", "rename")):
            rows.append('<span class=h>%s</span>' % e)
        elif ln.startswith("@@"):
            rows.append('<span class=h>%s</span>' % e)
        elif ln.startswith("+"):
            rows.append('<span class=a>%s</span>' % e)
        elif ln.startswith("-"):
            rows.append('<span class=r>%s</span>' % e)
        else:
            rows.append("<span>%s</span>" % e)
    return ('<h2>Diff</h2><p><a href="changes.diff">changes.diff</a></p><div class=d>%s</div>'
            % "".join(rows))
