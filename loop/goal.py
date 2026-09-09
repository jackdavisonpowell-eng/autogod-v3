"""loop/goal.py — the loop's state on disk: goal, projects, showcase, dead list.

Everything lives under $VAULT/AUTOGOD (see the plan, §4):
  goals/<slug>.md          Jack's goal text; goals/active names the one in use
  projects/<slug>/         PROJECT.md (frontmatter = state), PLAN.md, handback/<n>.md
  showcase/<slug>.json     the card the wall shows
  dead.md                  killed shapes, one line each
Code lives outside the vault at $AUTOGOD_LAB/<slug>.
"""
import json
import os
import re
import time

from simpleyaml import loads as yaml_loads

LIVE_STAGES = ("plan", "prototype", "polish")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def today():
    return time.strftime("%Y-%m-%d")


class State:
    def __init__(self, vault=None, lab=None):
        self.vault = vault or os.environ.get("VAULT", os.path.expanduser("~/vault"))
        self.lab = lab or os.environ.get("AUTOGOD_LAB", os.path.expanduser("~/lab"))
        self.ag = os.path.join(self.vault, "AUTOGOD")
        self.goals = os.path.join(self.ag, "goals")
        self.projects = os.path.join(self.ag, "projects")
        self.showcase = os.path.join(self.ag, "showcase")
        self.dead = os.path.join(self.ag, "dead.md")
        for d in (self.goals, self.projects, self.showcase):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.dead):
            open(self.dead, "a").close()

    # -- frontmatter -----------------------------------------------------
    @staticmethod
    def read_fm(path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return {}, ""
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                meta = yaml_loads(text[4:end])
                body = text[end + 4:].lstrip("\n")
                return meta, body
        return {}, text

    @staticmethod
    def write_fm(path, meta, body):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = ["---"]
        for k, v in meta.items():
            if v is None:
                lines.append("%s: null" % k)
            elif isinstance(v, bool):
                lines.append("%s: %s" % (k, "true" if v else "false"))
            elif isinstance(v, int):
                lines.append("%s: %d" % (k, v))
            else:
                s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
                lines.append('%s: "%s"' % (k, s))
        lines.append("---")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n" + body.rstrip("\n") + "\n")

    @staticmethod
    def _int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    # -- goal -------------------------------------------------------------
    def active_goal(self):
        """(slug, text). goals/active names a file; else the first *.md."""
        names = sorted(n[:-3] for n in os.listdir(self.goals) if n.endswith(".md"))
        pick = None
        ap = os.path.join(self.goals, "active")
        if os.path.exists(ap):
            with open(ap) as f:
                want = f.read().strip()
            if want in names:
                pick = want
        if pick is None and names:
            pick = names[0]
        if pick is None:
            return None, ""
        meta, body = self.read_fm(os.path.join(self.goals, pick + ".md"))
        return pick, body.strip()

    def append_not_this(self, goal_slug, line):
        p = os.path.join(self.goals, goal_slug + ".md")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n- not this: %s\n" % line.strip())

    # -- projects ---------------------------------------------------------
    def project_dir(self, slug):
        return os.path.join(self.projects, slug)

    def code_dir(self, slug):
        return os.path.join(self.lab, slug)

    def read_project(self, slug):
        meta, body = self.read_fm(os.path.join(self.project_dir(slug), "PROJECT.md"))
        if not meta:
            return None
        meta["slug"] = slug
        meta["iterations"] = self._int(meta.get("iterations"))
        meta["retries"] = self._int(meta.get("retries"))
        for k, v in list(meta.items()):
            if v in ("null", "None", ""):
                meta[k] = None
        return meta

    def write_project(self, meta, body=None):
        slug = meta["slug"]
        p = os.path.join(self.project_dir(slug), "PROJECT.md")
        if body is None:
            _, body = self.read_fm(p)
        out = {k: v for k, v in meta.items() if k != "slug"}
        out = dict([("slug", slug)] + list(out.items()))
        self.write_fm(p, out, body)

    def list_projects(self):
        out = []
        if not os.path.isdir(self.projects):
            return out
        for slug in sorted(os.listdir(self.projects)):
            m = self.read_project(slug)
            if m:
                out.append(m)
        return out

    def live_project(self, lane):
        for m in self.list_projects():
            if m.get("lane") == lane and m.get("stage") in LIVE_STAGES:
                return m
        return None

    def live_categories(self):
        return {m.get("category", "") for m in self.list_projects()
                if m.get("stage") in LIVE_STAGES or m.get("stage") == "idea"}

    def projects_summary(self, goal_slug=None):
        lines = []
        for m in self.list_projects():
            if goal_slug and m.get("goal") and m.get("goal") != goal_slug:
                continue
            st = m.get("stage", "?")
            if m.get("verdict") in ("keep", "kill"):
                st = m["verdict"]
            lines.append("- %s [%s] (%s): %s" % (m["slug"], m.get("category", "?"), st,
                                                  m.get("shape", "")))
        return "\n".join(lines) if lines else "(none yet)"

    def dead_lines(self):
        try:
            with open(self.dead, encoding="utf-8") as f:
                ls = [l.rstrip() for l in f if l.strip() and not l.startswith("#")]
        except OSError:
            ls = []
        return "\n".join(ls) if ls else "(none)"

    def append_dead(self, slug, shape, reason):
        with open(self.dead, "a", encoding="utf-8") as f:
            f.write("- %s %s | shape: %s | reason: %s\n" % (today(), slug, shape, reason))

    # -- hand-backs --------------------------------------------------------
    def handback_path(self, slug, n):
        return os.path.join(self.project_dir(slug), "handback", "%d.md" % n)

    def read_text(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def last_handback(self, slug, n_now):
        for n in range(n_now - 1, 0, -1):
            t = self.read_text(self.handback_path(slug, n))
            if t.strip():
                return t
        return ""

    # -- showcase ------------------------------------------------------------
    def showcase_path(self, slug):
        return os.path.join(self.showcase, slug + ".json")

    def write_card(self, slug, card):
        card = dict(card)
        card["slug"] = slug
        with open(self.showcase_path(slug), "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2, sort_keys=True)

    def read_card(self, slug):
        try:
            with open(self.showcase_path(slug), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
