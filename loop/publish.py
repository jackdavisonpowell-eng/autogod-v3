#!/usr/bin/env python3
"""loop/publish.py — put a finished app on autogod.org before the iteration ends.

Two things, both on thebeast where the loop runs:
  1. copy ~/lab/<slug>/ (minus harness + scratch files) to ~/landing/apps/<slug>/ —
     landing.service serves it at https://autogod.org/apps/<slug>/ at once
  2. write vault Site/Projects/<slug>.md — the note the site's publish.py turns into a
     showcase card within two minutes (see vault Site/HOW TO UPDATE THE SITE.md)

Jack's verdict is after the fact: kill = the note goes `draft: true` (card gone, files
stay); keep = the card's readout says kept. Called from stage.py (polish -> showcase)
and verdict.py; `python3 loop/publish.py <slug>` publishes one by hand.
"""
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from goal import State  # noqa: E402

SKIP_NAMES = {".claude", "CLAUDE.md", "__pycache__", "node_modules", ".git"}
SITE_URL = os.environ.get("AUTOGOD_SITE_URL", "https://autogod.org")


def apps_dir():
    return os.environ.get("AUTOGOD_APPS_DIR", os.path.expanduser("~/landing/apps"))


def site_projects(st):
    return os.environ.get("AUTOGOD_SITE_PROJECTS", os.path.join(st.vault, "Site", "Projects"))


def _ignore(_dir, names):
    # harness files never ship; scratch (`_t.js`, `.proof.js`) never ships
    return [n for n in names if n in SKIP_NAMES or n.startswith((".", "_"))]


def _minutes_since(born):
    try:
        t = time.mktime(time.strptime(born, "%Y-%m-%d %H:%M"))
        return max(1, int((time.time() - t) / 60))
    except (ValueError, TypeError):
        return None


def _body(st, slug, card):
    _, body = st.read_fm(os.path.join(st.project_dir(slug), "PROJECT.md"))
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()
             and not p.strip().startswith("#")]
    return "\n\n".join(paras[:2])


def publish(st, proj, card):
    """Copy the app + write the note. Returns the public URL."""
    slug = proj["slug"]
    src = st.code_dir(slug)
    dst = os.path.join(apps_dir(), slug)
    os.makedirs(apps_dir(), exist_ok=True)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)
    url = "%s/apps/%s/" % (SITE_URL, slug)

    # PROJECT.md's title is the one the idea chose ("Delta"); the CARD json tends to
    # come back lowercased by the 27B ("delta") — prefer the project's.
    title = proj.get("title") or card.get("title") or slug
    cat = card.get("category") or proj.get("category") or "app"
    mins = _minutes_since(proj.get("born"))
    stats = ["built by = AUTOGOD", "lane = %s" % proj.get("lane", "?")]
    if mins:
        stats.append("idea to live = %d min" % mins)
    stats.append("verdict = pending")
    run = card.get("run") or "open index.html"
    lines = [
        "---",
        "title: %s" % title,
        "kicker: built by AUTOGOD, no human in the loop",
        "date: %s" % time.strftime("%Y-%m-%d"),
        "status: live",
        "tags: [autogod, %s]" % cat,
        "href: %s" % url,
        "stats: %s" % " | ".join(stats),
        "slug: %s" % slug,
        "---",
        "",
        card.get("blurb") or proj.get("shape") or "",
        "",
        _body(st, slug, card),
        "",
        "## How it got here",
        "",
        "AUTOGOD invented it, planned it, built it until its own proof passed, polished it and "
        "put it here — one pass per stage, nobody watching. Jack judges it afterwards on the "
        "wall; a kill takes it down. Run it: `%s`. No dependencies." % run,
        "",
    ]
    os.makedirs(site_projects(st), exist_ok=True)
    note = os.path.join(site_projects(st), "%s.md" % slug)
    with open(note, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return url


def set_verdict(st, slug, verdict):
    """kill -> unpublish the card (draft: true); keep -> readout says kept."""
    note = os.path.join(site_projects(st), "%s.md" % slug)
    try:
        with open(note, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    if verdict == "kill":
        if "\ndraft: true\n" not in text:
            text = text.replace("\nstatus: live\n", "\nstatus: shelved\ndraft: true\n", 1)
    else:
        text = text.replace("verdict = pending", "verdict = kept", 1)
    with open(note, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def main(argv=None):
    slug = (argv or sys.argv[1:] or [None])[0]
    if not slug:
        print("usage: publish.py <slug>"); return 2
    st = State()
    proj = st.read_project(slug)
    if not proj:
        print("no such project: %s" % slug); return 1
    card = st.read_card(slug) or {}
    url = publish(st, proj, card)
    card["site"] = url
    st.write_card(slug, card)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
