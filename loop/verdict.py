#!/usr/bin/env python3
"""loop/verdict.py — Jack's keep / kill on a showcased project.

    verdict.py <slug> keep|kill [--reason "..."]

kill: PROJECT.md verdict=kill, stage=verdict; one line in dead.md (the shape);
      "- not this: <shape>" appended to the goal; card verdict=kill.
keep: PROJECT.md verdict=keep, stage=verdict; card verdict=keep; a KEEP marker in
      state/keep/<slug> for the repo step (nitro has gh; this box does not).
Called by the fleet collector's POST /v1/showcase/verdict and by hand.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from goal import State, now  # noqa: E402
import publish  # noqa: E402

STATE_DIR = os.environ.get("AUTOGOD_STATE_DIR", os.path.join(HERE, "..", "state"))


def apply(st, slug, verdict, reason=""):
    proj = st.read_project(slug)
    if not proj:
        return "no such project: %s" % slug
    if proj.get("stage") not in ("showcase", "stuck", "verdict"):
        return "%s is at stage %s, not showcased yet" % (slug, proj.get("stage"))
    proj["verdict"] = verdict
    proj["stage"] = "verdict"
    proj["decided"] = now()
    if reason:
        proj["reason"] = reason
    st.write_project(proj)
    card = st.read_card(slug) or {"title": proj.get("title", slug)}
    card["verdict"] = verdict
    card["stage"] = "verdict"
    card["decided"] = proj["decided"]
    st.write_card(slug, card)
    try:
        publish.set_verdict(st, slug, verdict)
    except OSError:
        pass
    if verdict == "kill":
        shape = proj.get("shape") or card.get("blurb") or slug
        st.append_dead(slug, shape, reason or "Jack killed it on the showcase")
        if proj.get("goal"):
            st.append_not_this(proj["goal"], shape)
    else:
        d = os.path.join(STATE_DIR, "keep")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, slug), "w") as f:
            f.write("%s %s\n" % (now(), st.code_dir(slug)))
    return "ok"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("verdict", choices=("keep", "kill"))
    ap.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    out = apply(State(), a.slug, a.verdict, a.reason)
    print(out)
    return 0 if out == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
