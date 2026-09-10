"""Offline tests for research and patch modes: a fake driver plays the model."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import stage  # noqa: E402
import verdict  # noqa: E402
from goal import State  # noqa: E402
from test_stage import FakeDriver, PLAN  # noqa: E402

URLS = ["https://a.example/%d" % i for i in range(6)]
NOTES = "".join("## src %d\nURL: %s\nfor: 1\n> quote\n- takeaway: x\n- trust: high\n\n" % (i, u) for i, u in enumerate(URLS))
REPORT = "# Q\n\n**TL;DR** answer [1].\n\n## Sub 1\n\n" + ("A cited fact [2]. " * 120) + "\n\n## Sources\n\n" + "\n".join("%d. t — %s — high" % (i + 1, u) for i, u in enumerate(URLS)) + "\n"
HB = "what I did:\n- x\nfiles:\n%s\ncould not:\nnothing\n"
R_IDEA = "SLUG: kv-quant\nTITLE: KV quant\nCATEGORY: inference\nSHAPE: does q8 kv cost quality\nIDEA:\nlines\nNEXT: plan\n"
R_PROTO = HB % "NOTES.md" + "OUTPUT:\n$ grep -c '^URL:' NOTES.md\n6\nRUNS: yes\nNEXT: write\n"
R_POLISH = HB % "REPORT.md" + "CARD:\n```json\n" + json.dumps({"title": "KV quant", "blurb": "Q8 is free.", "category": "inference", "sources": 6}) + "\n```\nNEXT: showcase\n"
P_IDEA = "SLUG: demo-fix-greet\nTITLE: Fix greet\nTARGET: demo\nCATEGORY: demo\nSHAPE: demo: greet() drops the name\nIDEA:\nlines\nNEXT: plan\n"
P_PROTO = HB % "hello.py" + "OUTPUT:\n$ python3 hello.py\nhi jack\nRUNS: yes\nNEXT: polish\n"
P_POLISH = HB % "hello.py" + "CARD:\n```json\n" + json.dumps({"title": "Fix greet", "blurb": "greet keeps the name.", "category": "demo", "target": "demo", "files_changed": 1}) + "\n```\nNEXT: showcase\n"
PLAN_HB = HB % "PLAN.md" + "NEXT: prototype\n"


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        self.lab = os.path.join(self.tmp, "lab")
        stage.STATE_DIR = os.path.join(self.tmp, "state")
        os.environ["AUTOGOD_APPS_DIR"] = os.path.join(self.tmp, "landing", "apps")
        os.environ["AUTOGOD_SITE_BLOG"] = os.path.join(self.vault, "Site", "Blog")
        self.st = State(self.vault, self.lab)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def goal(self, mode):
        with open(os.path.join(self.st.goals, "g.md"), "w") as f:
            f.write("---\nname: g\nmode: %s\n---\n\nthe goal\n" % mode)

    def make(self, script):
        drv = FakeDriver(script)
        return stage.Pass("a", drv, self.st), drv

    def test_mode_parse_and_set(self):
        self.goal("research")
        self.assertEqual(self.st.active_goal_full()[2], "research")
        self.st.set_goal_mode("g", "patch")
        self.assertEqual(self.st.active_goal_full()[2], "patch")
        self.assertEqual(self.st.active_goal()[1], "the goal")
        self.st.set_goal_mode("g", "tinker")
        with open(os.path.join(self.st.goals, "g.md"), "w") as f:
            f.write("---\nname: g\nmode: bogus\n---\n\nx\n")
        self.assertEqual(self.st.active_goal_full()[2], "tinker")

    def test_research_path(self):
        self.goal("research")
        p, drv = self.make({
            "idea": (R_IDEA, {}),
            "plan": (PLAN_HB, {"vault:PLAN.md": PLAN}),
            "prototype": (R_PROTO, {"NOTES.md": NOTES}),
            "polish": (R_POLISH, {"REPORT.md": REPORT}),
        })
        self.assertEqual(p.run(), "born kv-quant")
        self.assertEqual(self.st.read_project("kv-quant")["kind"], "research")
        self.assertIn("DRILLED", drv.calls[0][1])        # the research idea prompt, not tinker's
        self.assertNotIn("web.py", drv.calls[0][1])
        self.assertEqual(p.run(), "plan ok -> prototype")
        self.assertEqual(p.run(), "prototype ok -> polish")
        self.assertIn("python3 " + stage.WEB, drv.calls[-1][1])
        self.assertEqual(p.run(), "polish ok -> showcase")
        card = self.st.read_card("kv-quant")
        self.assertEqual(card["kind"], "research")
        self.assertEqual(card["sources"], 6)
        cdir = self.st.code_dir("kv-quant")
        self.assertIn("<h1>KV quant</h1>", self.st.read_text(os.path.join(cdir, "index.html")))
        self.assertTrue(os.path.exists(os.path.join(self.st.research, "kv-quant.md")))
        apps = os.path.join(self.tmp, "landing", "apps", "kv-quant")
        self.assertTrue(os.path.exists(os.path.join(apps, "index.html")))
        self.assertFalse(os.path.exists(os.path.join(apps, "CLAUDE.md")))
        note = self.st.read_text(os.path.join(self.vault, "Site", "Projects", "kv-quant.md"))
        self.assertIn("researched by AUTOGOD", note)
        # keep -> blog post
        self.assertEqual(verdict.apply(self.st, "kv-quant", "keep"), "ok")
        blog = self.st.read_text(os.path.join(self.vault, "Site", "Blog", "kv-quant.md"))
        self.assertTrue(blog.startswith("---\ntitle: KV quant\n"))
        self.assertIn("A cited fact [2].", blog)

    def test_research_too_few_sources_fails(self):
        self.goal("research")
        p, drv = self.make({
            "idea": (R_IDEA, {}), "plan": (PLAN_HB, {"vault:PLAN.md": PLAN}),
            "prototype": (R_PROTO, {"NOTES.md": NOTES.split("## src 4")[0]}),
        })
        p.run(); p.run()
        self.assertIn("NOTES.md cites 4 sources", p.run())

    def _demo_repo(self):
        src = os.path.join(self.tmp, "demo")
        os.makedirs(src)
        with open(os.path.join(src, "hello.py"), "w") as f:
            f.write("def greet(n):\n    return 'hi'\nprint(greet('jack'))\n")
        with open(os.path.join(src, "README.md"), "w") as f:
            f.write("# demo\n\nA greeter.\n")
        env = {**os.environ, **stage.GIT_ENV}
        for a in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git"] + a, cwd=src, check=True, env=env)
        with open(self.st.repos, "w") as f:
            f.write("# targets\n- demo: file://%s\n" % src)
        return src

    def test_patch_path_and_keep(self):
        self.goal("patch")
        src = self._demo_repo()
        p, drv = self.make({
            "idea": (P_IDEA, {}),
            "plan": (PLAN_HB, {"vault:PLAN.md": PLAN}),
            "prototype": (P_PROTO, {"repo/hello.py": "def greet(n):\n    return 'hi ' + n\nprint(greet('jack'))\n"}),
            "polish": (P_POLISH, {"NOTES.md": "## What\n\ngreet keeps the name.\n"}),
        })
        self.assertEqual(p.run(), "born demo-fix-greet")
        # the idea stage saw the mirror and its README line
        self.assertIn("- demo (repo) at %s: A greeter." % self.st.mirror_dir("demo"), drv.calls[0][1])
        self.assertIn(self.st.mirror_dir("demo"), drv.calls[0][2]["AUTOGOD_ALLOWED_ROOTS"])
        m = self.st.read_project("demo-fix-greet")
        self.assertEqual((m["kind"], m["target"], m["category"]), ("patch", "demo", "demo"))
        self.assertEqual(p.run(), "plan ok -> prototype")
        repo = os.path.join(self.st.code_dir("demo-fix-greet"), "repo")
        self.assertTrue(os.path.isdir(os.path.join(repo, ".git")))
        self.assertIn(repo, drv.calls[-1][1])
        self.assertEqual(p.run(), "prototype ok -> polish")
        self.assertEqual(p.run(), "polish ok -> showcase")
        cdir = self.st.code_dir("demo-fix-greet")
        diff = self.st.read_text(os.path.join(cdir, "changes.diff"))
        self.assertIn("+    return 'hi ' + n", diff)
        page = self.st.read_text(os.path.join(cdir, "index.html"))
        self.assertIn("class=a", page); self.assertIn("greet keeps the name", page)
        card = self.st.read_card("demo-fix-greet")
        self.assertEqual((card["kind"], card["target"], card["files_changed"]), ("patch", "demo", 1))
        apps = os.path.join(self.tmp, "landing", "apps", "demo-fix-greet")
        self.assertEqual(sorted(os.listdir(apps)), ["NOTES.md", "changes.diff", "index.html"])
        self.assertEqual(verdict.apply(self.st, "demo-fix-greet", "keep"), "ok")
        out = os.path.join(self.st.patches, "demo-fix-greet")
        self.assertTrue(any(n.endswith(".patch") for n in os.listdir(out)), os.listdir(out))
        # the source repo itself was never touched
        self.assertIn("return 'hi'\n", self.st.read_text(os.path.join(src, "hello.py")))

    def test_patch_idea_bad_target_retries(self):
        self.goal("patch")
        self._demo_repo()
        calls = {"n": 0}
        def idea(drv):
            calls["n"] += 1
            return (P_IDEA.replace("TARGET: demo", "TARGET: nope") if calls["n"] == 1 else P_IDEA, {})
        p, drv = self.make({"idea": idea})
        self.assertEqual(p.run(), "born demo-fix-greet")
        self.assertEqual(calls["n"], 2)
        self.assertIn("TARGET 'nope' is not one of: demo", drv.calls[1][1])

    def test_patch_no_changes_fails(self):
        self.goal("patch")
        self._demo_repo()
        p, drv = self.make({"idea": (P_IDEA, {}), "plan": (PLAN_HB, {"vault:PLAN.md": PLAN}),
                            "prototype": (P_PROTO, {})})
        p.run(); p.run()
        self.assertIn("no changes in the repo", p.run())

    def test_patch_on_kept_app(self):
        self.goal("patch")
        app = self.st.code_dir("clock")
        os.makedirs(app)
        with open(os.path.join(app, "index.html"), "w") as f:
            f.write("<h1>clock</h1>")
        self.st.write_project({"slug": "clock", "title": "Clock", "stage": "verdict", "verdict": "keep",
                               "category": "tool", "shape": "a clock", "lane": "b"}, "# Clock\n")
        self.st.write_card("clock", {"title": "Clock", "blurb": "tick", "category": "tool"})
        idea = P_IDEA.replace("demo", "clock")
        p, drv = self.make({
            "idea": (idea, {}), "plan": (PLAN_HB, {"vault:PLAN.md": PLAN}),
            "prototype": (P_PROTO, {"repo/index.html": "<h1>clock</h1><p>seconds</p>"}),
            "polish": (P_POLISH.replace("demo", "clock"), {"NOTES.md": "## What\n\nseconds.\n"}),
        })
        self.assertEqual(p.run(), "born clock-fix-greet")
        self.assertIn("- clock (app) at %s: a clock" % app, drv.calls[0][1])
        for _ in range(3):
            p.run()
        self.assertEqual(self.st.read_card("clock-fix-greet")["stage"], "showcase")
        self.assertEqual(verdict.apply(self.st, "clock-fix-greet", "keep"), "ok")
        self.assertIn("<p>seconds</p>", self.st.read_text(os.path.join(app, "index.html")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "landing", "apps", "clock", "index.html")))


if __name__ == "__main__":
    unittest.main()
