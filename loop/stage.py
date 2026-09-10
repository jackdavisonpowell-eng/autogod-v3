#!/usr/bin/env python3
"""loop/stage.py — the stage machine. One call = one iteration on one lane.

    idea -> plan -> prototype -> polish -> showcase -> verdict
                                      -> stuck (after the retries)

The model writes a hand-back; THIS code reads it and moves `stage:`. The model
never edits PROJECT.md's frontmatter (the pass owns it).

Usage:  stage.py --lane a [--driver claude_code|mock] [--dry-run]
"""
import argparse
import importlib
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from goal import State, SLUG_RE, now, today  # noqa: E402

ROOT = os.path.realpath(os.environ.get("AUTOGOD_ROOT", os.path.join(HERE, "..")))
STATE_DIR = os.environ.get("AUTOGOD_STATE_DIR", os.path.join(ROOT, "state"))
PROMPTS = os.path.join(HERE, "prompts")

BUDGET = {"idea": 1800, "plan": 2700, "prototype": 5400, "polish": 2700}
TURNS = {"idea": 15, "plan": 25, "prototype": 60, "polish": 40}
TOOLS = {
    # no WebSearch: it is a server-side tool, nothing executes it against a local brain
    "idea": "Read,Grep,Glob,Write",
    "plan": "Read,Grep,Glob,Write",
    "prototype": "Read,Write,Edit,Bash,Grep,Glob",
    "polish": "Read,Write,Edit,Bash,Grep,Glob",
}
RETRIES = {"idea": 1, "plan": 1, "prototype": 2, "polish": 2}
NEXT = {"plan": "prototype", "prototype": "polish", "polish": "showcase"}


def log(msg):
    print("%s stage: %s" % (now(), msg), flush=True)


def load_driver(name):
    return importlib.import_module("drivers.%s" % name)


def render(stage, ctx):
    with open(os.path.join(PROMPTS, stage + ".md"), encoding="utf-8") as f:
        t = f.read()
    for k, v in ctx.items():
        t = t.replace("{{%s}}" % k, str(v if v is not None else ""))
    return t


def field(text, key):
    """`KEY: value` — the last occurrence wins, stripped of trailing backticks."""
    m = None
    for m in re.finditer(r"^\s*%s:\s*(.+?)\s*$" % re.escape(key), text, re.M | re.I):
        pass
    return m.group(1).strip().strip("`").strip() if m else ""


def block(text, key):
    """Everything after a line `KEY:` up to the next `WORD:` line at column 0 or EOF."""
    m = re.search(r"^%s:\s*$" % re.escape(key), text, re.M | re.I)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^[A-Z]{3,}:\s*", rest, re.M)
    return (rest[:n.start()] if n else rest).strip()


def json_block(text, key):
    """A ```json fence after `KEY:`, or a raw {...} on/after the KEY line."""
    m = re.search(r"^%s:\s*$" % re.escape(key), text, re.M | re.I)
    if not m:
        m = re.search(r"^%s:\s*(\{.*)$" % re.escape(key), text, re.M | re.I | re.S)
        if not m:
            return None
        cand = m.group(1)
    else:
        cand = text[m.end():]
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cand, re.S)
    raw = fence.group(1) if fence else None
    if raw is None:
        start = cand.find("{")
        if start == -1:
            return None
        depth = 0
        for i, ch in enumerate(cand[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    raw = cand[start:i + 1]
                    break
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def scale():
    try:
        return float(os.environ.get("AUTOGOD_BUDGET_SCALE", "1.0"))
    except ValueError:
        return 1.0


def budget(stage):
    b = int(BUDGET[stage] * scale())
    if os.environ.get("AUTOGOD_NIGHT") == "1":
        b = int(b * 1.5)
    return b


def install_claude_md(code_dir):
    src = os.path.join(HERE, "CLAUDE.md")
    dst = os.path.join(code_dir, "CLAUDE.md")
    os.makedirs(code_dir, exist_ok=True)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy(src, dst)


class Pass:
    def __init__(self, lane, driver, st=None, dry_run=False):
        self.lane = lane
        self.driver = driver
        self.st = st or State()
        self.dry = dry_run
        os.makedirs(STATE_DIR, exist_ok=True)

    # -- one iteration -----------------------------------------------------
    def run(self):
        goal_slug, goal = self.st.active_goal()
        if not goal_slug:
            log("no goal under %s — write goals/<slug>.md first" % self.st.goals)
            return "no-goal"
        proj = self.st.live_project(self.lane)
        t0 = time.time()
        if proj is None:
            outcome = self.iter_idea(goal_slug, goal)
            slug = outcome.split(" ", 1)[1] if outcome.startswith("born ") else "-"
            stage = "idea"
        else:
            slug, stage = proj["slug"], proj["stage"]
            outcome = self.iter_stage(proj, goal)
        secs = int(time.time() - t0)
        with open(os.path.join(STATE_DIR, "passes.log"), "a") as f:
            f.write("%s\t%s\t%s\t%s\t%d\t%s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                  self.lane, stage, slug, secs, outcome))
        log("[%s] %s %s -> %s (%ds)" % (self.lane, stage, slug, outcome, secs))
        return outcome

    def _run_model(self, stage, prompt, cwd, roots, handback, project_dir="", slug=""):
        env = {
            "AUTOGOD_LANE": self.lane,
            "AUTOGOD_STAGE": stage,
            "AUTOGOD_HANDBACK_PATH": handback,
            "AUTOGOD_PROJECT_DIR": project_dir or cwd,
            "AUTOGOD_ALLOWED_ROOTS": ":".join(roots),
            "AUTOGOD_ITER_LOG": handback.replace(".md", ".log"),
            "AUTOGOD_SLUG": slug,
        }
        if self.dry:
            log("dry-run %s: cwd=%s roots=%s budget=%ds" % (stage, cwd, roots, budget(stage)))
            print(prompt)
            return {"is_error": False, "seconds": 0}
        os.makedirs(os.path.dirname(handback), exist_ok=True)
        cur = os.path.join(STATE_DIR, "current-%s.json" % self.lane)
        with open(cur, "w") as f:
            json.dump({"lane": self.lane, "stage": stage, "slug": slug or None,
                       "started": time.time(), "budget": budget(stage),
                       "log": env["AUTOGOD_ITER_LOG"], "cwd": cwd}, f)
        try:
            return self.driver.run(prompt, cwd, TOOLS[stage], budget(stage), TURNS[stage], env)
        finally:
            try:
                os.remove(cur)
            except OSError:
                pass

    # -- idea ----------------------------------------------------------------
    def iter_idea(self, goal_slug, goal, retry_note=""):
        scratch = os.path.join(STATE_DIR, "idea", self.lane)
        if os.path.isdir(scratch):
            old = os.path.join(scratch, "idea.log")
            if os.path.exists(old):   # keep the last attempt's log for post-mortems
                shutil.copy(old, os.path.join(STATE_DIR, "idea", "%s-last.log" % self.lane))
            shutil.rmtree(scratch)
        os.makedirs(scratch)
        handback = os.path.join(scratch, "idea.md")
        ctx = dict(goal=goal, projects=self.st.projects_summary(goal_slug),
                   dead=self.st.dead_lines(), handback_path=handback, lane=self.lane,
                   retry_note=retry_note, today=today())
        self._run_model("idea", render("idea", ctx), scratch, [scratch], handback)
        text = self.st.read_text(handback)
        if not text.strip():
            return "no handback"
        slug = field(text, "SLUG").lower()
        title = field(text, "TITLE")
        cat = field(text, "CATEGORY").lower().split()[0] if field(text, "CATEGORY") else ""
        shape = field(text, "SHAPE")
        problem = None
        if not SLUG_RE.match(slug):
            problem = "bad slug %r" % slug
        elif self.st.read_project(slug) or os.path.exists(self.st.code_dir(slug)):
            problem = "slug %s already exists" % slug
        elif not cat or not shape:
            problem = "missing CATEGORY/SHAPE"
        elif cat in self.st.live_categories():
            problem = "category %s is live on another lane" % cat
        if problem:
            if retry_note:
                return "idea rejected twice: " + problem
            log("idea rejected (%s), one re-run" % problem)
            return self.iter_idea(goal_slug, goal,
                                  "Your previous answer was refused: %s. Pick a different "
                                  "slug and a category that is NOT any of: %s."
                                  % (problem, ", ".join(sorted(self.st.live_categories()))))
        meta = {
            "slug": slug, "title": title or slug, "goal": goal_slug, "category": cat,
            "shape": shape, "stage": "plan", "lane": self.lane, "mode": "solo",
            "born": now(), "iterations": 1, "retries": 0, "verdict": None, "runs": None,
            "code": self.st.code_dir(slug),
        }
        body = "# %s\n\n%s\n" % (meta["title"], block(text, "IDEA") or text)
        self.st.write_project(meta, body)
        os.makedirs(os.path.dirname(self.st.handback_path(slug, 1)), exist_ok=True)
        shutil.copy(handback, self.st.handback_path(slug, 1))
        install_claude_md(self.st.code_dir(slug))
        return "born " + slug

    # -- plan / prototype / polish ---------------------------------------------
    def iter_stage(self, proj, goal):
        slug, stage = proj["slug"], proj["stage"]
        n = proj["iterations"] + 1
        pdir = self.st.project_dir(slug)
        cdir = self.st.code_dir(slug)
        install_claude_md(cdir)
        handback = self.st.handback_path(slug, n)
        _, body = self.st.read_fm(os.path.join(pdir, "PROJECT.md"))
        ctx = dict(
            goal=goal, slug=slug, title=proj.get("title", slug), n=n, lane=self.lane,
            project_dir=pdir, code_dir=cdir, handback_path=handback,
            project_md=body.strip(), plan_md=self.st.read_text(os.path.join(pdir, "PLAN.md")),
            last_handback=self.st.last_handback(slug, n) or "(none)",
            retry_note=("This is retry %d of %d for this stage. Read the last hand-back's "
                        "`could not` and NEXT lines first and do THAT." % (proj["retries"], RETRIES[stage])
                        if proj["retries"] else ""),
            today=today(),
        )
        roots = [cdir, pdir]
        self._run_model(stage, render(stage, ctx), cdir, roots, handback, pdir, slug)
        proj["iterations"] = n
        text = self.st.read_text(handback)
        ok, why = self.check(stage, proj, text)
        if ok:
            proj["stage"] = NEXT[stage]
            proj["retries"] = 0
            if stage == "prototype":
                proj["runs"] = "yes"
            if NEXT[stage] == "showcase":
                proj["showcased"] = now()
                self.write_showcase(proj, text)
            self.st.write_project(proj)
            return "%s ok -> %s" % (stage, NEXT[stage])
        proj["retries"] += 1
        if proj["retries"] > RETRIES[stage]:
            proj["stage"] = "stuck"
            proj["stuck"] = "%s: %s | NEXT: %s" % (stage, why, field(text, "NEXT") or "?")
            self.st.write_project(proj)
            self.write_showcase(proj, text, stuck=True)
            return "%s failed (%s) -> stuck" % (stage, why)
        self.st.write_project(proj)
        return "%s failed (%s), retry %d" % (stage, why, proj["retries"])

    def check(self, stage, proj, text):
        if stage == "plan":
            # The plan IS the deliverable. 2026-09-09: five plan passes wrote a good PLAN.md
            # and then died at the budget before the hand-back file — judge the plan itself.
            plan = self.st.read_text(os.path.join(self.st.project_dir(proj["slug"]), "PLAN.md"))
            if len(plan.strip()) < 200:
                return False, "no hand-back" if not text.strip() else "PLAN.md missing or too short"
            if "done-test" not in plan.lower() and "done test" not in plan.lower():
                return False, "PLAN.md has no done-test lines"
            return True, ""
        if not text.strip():
            return False, "no hand-back"
        if stage == "prototype":
            runs = field(text, "RUNS").lower()
            if not runs.startswith("yes"):
                return False, "RUNS: %s" % (runs or "missing")
            if not block(text, "OUTPUT").strip():
                return False, "no pasted OUTPUT block"
            return True, ""
        if stage == "polish":
            card = json_block(text, "CARD")
            if not isinstance(card, dict) or not card.get("title") or not card.get("blurb"):
                return False, "CARD json missing or incomplete"
            return True, ""
        return False, "unknown stage"

    def write_showcase(self, proj, text, stuck=False):
        slug = proj["slug"]
        card = json_block(text, "CARD") or {} if not stuck else (self.st.read_card(slug) or {})
        out = {
            "title": card.get("title") or proj.get("title") or slug,
            "blurb": card.get("blurb", ""),
            "category": card.get("category") or proj.get("category", ""),
            "run": card.get("run", ""),
            "entry": card.get("entry", "index.html"),
            "runs": bool(card.get("runs", proj.get("runs") == "yes")),
            "screenshot": card.get("screenshot"),
            "repo": card.get("repo"),
            "stage": "stuck" if stuck else "showcase",
            "stuck": proj.get("stuck") if stuck else None,
            "verdict": proj.get("verdict"),
            "lane": proj.get("lane"),
            "goal": proj.get("goal"),
            "born": proj.get("born"),
            "showcased": proj.get("showcased") or now(),
            "code": self.st.code_dir(slug),
            "iterations": proj.get("iterations", 0),
        }
        self.st.write_card(slug, out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane", default=os.environ.get("AUTOGOD_LANE", "a"))
    ap.add_argument("--driver", default=os.environ.get("AUTOGOD_DRIVER", "claude_code"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    drv = load_driver(args.driver)
    out = Pass(args.lane, drv, dry_run=args.dry_run).run()
    return 0 if out and not out.startswith("no") else 1


if __name__ == "__main__":
    sys.exit(main())
