"""Offline tests for the v3 stage machine: a fake driver plays the model."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import stage  # noqa: E402
from goal import State  # noqa: E402


class FakeDriver:
    """Writes scripted hand-backs. script[stage] = (handback_text, extra_files)."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def run(self, prompt, cwd, tools, budget_secs, max_turns=40, env_extra=None):
        st = env_extra["AUTOGOD_STAGE"]
        self.calls.append((st, prompt, env_extra))
        entry = self.script.get(st)
        if callable(entry):
            entry = entry(self)
        if entry is None:
            return {"is_error": True, "seconds": 0}
        text, files = entry
        hb = env_extra["AUTOGOD_HANDBACK_PATH"]
        os.makedirs(os.path.dirname(hb), exist_ok=True)
        with open(hb, "w") as f:
            f.write(text)
        for rel, content in (files or {}).items():
            base = env_extra["AUTOGOD_PROJECT_DIR"] if rel.startswith("vault:") else cwd
            p = os.path.join(base, rel.replace("vault:", ""))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(content)
        return {"is_error": False, "seconds": 1}


IDEA = "SLUG: pulse-grid\nTITLE: Pulse Grid\nCATEGORY: visualizer\nSHAPE: a grid that pulses\nIDEA:\nsome lines\nNEXT: plan\n"
PLAN = "# plan\n\n## What\nx\n\n## Tasks\n1. build\n   done-test: `grep -c canvas index.html` -> 1\n" + ("filler\n" * 30)
PROTO_OK = "what I did:\n- built\nfiles:\nindex.html\ncould not:\nnothing\nOUTPUT:\n$ grep -c canvas index.html\n1\nRUNS: yes\nNEXT: polish\n"
PROTO_NO = "what I did:\n- tried\nfiles:\nindex.html\ncould not:\nJS error\nOUTPUT:\nnope\nRUNS: no\nNEXT: fix the JS\n"
POLISH = ("what I did:\n- readme\nfiles:\nREADME.md\ncould not:\nnothing\nCARD:\n```json\n"
          + json.dumps({"title": "Pulse Grid", "blurb": "A grid that pulses.", "category": "visualizer",
                        "run": "open index.html", "entry": "index.html", "runs": True, "screenshot": None})
          + "\n```\nNEXT: showcase\n")


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        self.lab = os.path.join(self.tmp, "lab")
        stage.STATE_DIR = os.path.join(self.tmp, "state")
        self.st = State(self.vault, self.lab)
        with open(os.path.join(self.st.goals, "build-cool-apps.md"), "w") as f:
            f.write("---\nname: build cool apps\n---\n\nbuild cool apps\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make(self, script, lane="a"):
        drv = FakeDriver(script)
        return stage.Pass(lane, drv, self.st), drv

    def test_full_path_to_showcase(self):
        p, drv = self.make({
            "idea": (IDEA, {}),
            "plan": ("what I did:\nplanned\nfiles:\nPLAN.md\ncould not:\nnothing\nNEXT: prototype\n",
                     {"vault:PLAN.md": PLAN}),
            "prototype": (PROTO_OK, {"index.html": "<canvas></canvas>"}),
            "polish": (POLISH, {"README.md": "x"}),
        })
        self.assertEqual(p.run(), "born pulse-grid")
        m = self.st.read_project("pulse-grid")
        self.assertEqual(m["stage"], "plan")
        self.assertEqual(m["category"], "visualizer")
        self.assertTrue(os.path.exists(self.st.handback_path("pulse-grid", 1)))
        self.assertTrue(os.path.exists(os.path.join(self.lab, "pulse-grid", "CLAUDE.md")))
        self.assertEqual(p.run(), "plan ok -> prototype")
        self.assertEqual(p.run(), "prototype ok -> polish")
        self.assertEqual(self.st.read_project("pulse-grid")["runs"], "yes")
        self.assertEqual(p.run(), "polish ok -> showcase")
        card = self.st.read_card("pulse-grid")
        self.assertEqual(card["stage"], "showcase")
        self.assertIsNone(card["verdict"])
        self.assertEqual(card["blurb"], "A grid that pulses.")
        self.assertEqual(self.st.read_project("pulse-grid")["iterations"], 4)
        # the prompt for prototype carried the plan and the last hand-back
        proto_prompt = [c[1] for c in drv.calls if c[0] == "prototype"][0]
        self.assertIn("done-test", proto_prompt)
        self.assertIn("planned", proto_prompt)
        # the guard roots were the code dir and the vault project dir
        roots = drv.calls[-1][2]["AUTOGOD_ALLOWED_ROOTS"].split(":")
        self.assertIn(self.st.code_dir("pulse-grid"), roots)
        self.assertIn(self.st.project_dir("pulse-grid"), roots)
        # lane is free again: next run is a new idea, and the old one is listed
        drv.script["idea"] = (IDEA.replace("pulse-grid", "tide-clock").replace("visualizer", "timer"), {})
        self.assertEqual(p.run(), "born tide-clock")
        idea_prompt = [c[1] for c in drv.calls if c[0] == "idea"][-1]
        self.assertIn("pulse-grid [visualizer] (showcase)", idea_prompt)

    def test_prototype_retries_then_stuck(self):
        p, drv = self.make({
            "idea": (IDEA, {}),
            "plan": ("NEXT: prototype\n", {"vault:PLAN.md": PLAN}),
            "prototype": (PROTO_NO, {}),
        })
        p.run(); p.run()
        self.assertEqual(p.run(), "prototype failed (RUNS: no), retry 1")
        self.assertEqual(p.run(), "prototype failed (RUNS: no), retry 2")
        self.assertTrue(p.run().endswith("-> stuck"))
        m = self.st.read_project("pulse-grid")
        self.assertEqual(m["stage"], "stuck")
        self.assertIn("fix the JS", m["stuck"])
        self.assertEqual(self.st.read_card("pulse-grid")["stage"], "stuck")
        # retry prompt told the model it was a retry
        self.assertIn("retry 1 of 2", [c[1] for c in drv.calls if c[0] == "prototype"][1])
        # lane is free (stuck is not live) -> next run is an idea
        self.assertEqual(p.run(), "idea rejected twice: slug pulse-grid already exists")

    def test_no_handback_counts_as_failure(self):
        p, _ = self.make({"idea": (IDEA, {}), "plan": None})
        p.run()
        self.assertEqual(p.run(), "plan failed (no hand-back), retry 1")
        self.assertTrue(p.run().endswith("-> stuck"))

    def test_category_clash_reruns_idea_once(self):
        p, drv = self.make({"idea": (IDEA, {})})
        p.run()  # lane a: visualizer, live at plan
        seen = []

        def lane_b_idea(d):
            seen.append(1)
            if len(seen) == 1:
                return (IDEA.replace("pulse-grid", "other-thing"), {})   # same category -> refused
            return (IDEA.replace("pulse-grid", "other-thing").replace("visualizer", "game"), {})
        pb, drvb = self.make({"idea": lane_b_idea}, lane="b")
        self.assertEqual(pb.run(), "born other-thing")
        self.assertEqual(len(seen), 2)
        self.assertIn("category visualizer is live", drvb.calls[1][1])
        self.assertEqual(self.st.read_project("other-thing")["category"], "game")
        self.assertEqual(self.st.live_project("b")["slug"], "other-thing")
        self.assertEqual(self.st.live_project("a")["slug"], "pulse-grid")

    def test_bad_idea_twice_gives_up(self):
        p, _ = self.make({"idea": ("SLUG: Bad Slug!\nCATEGORY: x\nSHAPE: y\n", {})})
        self.assertTrue(p.run().startswith("idea rejected twice"))
        self.assertEqual(self.st.list_projects(), [])

    def test_polish_without_card_retries(self):
        p, _ = self.make({
            "idea": (IDEA, {}), "plan": ("x\n", {"vault:PLAN.md": PLAN}),
            "prototype": (PROTO_OK, {}), "polish": ("what I did:\nstuff\nNEXT: showcase\n", {}),
        })
        p.run(); p.run(); p.run()
        self.assertEqual(p.run(), "polish failed (CARD json missing or incomplete), retry 1")

    def test_parsers(self):
        self.assertEqual(stage.field("a\nRUNS: `yes`\nb", "RUNS"), "yes")
        self.assertEqual(stage.block("OUTPUT:\nline1\nline2\nRUNS: yes\n", "OUTPUT"), "line1\nline2")
        self.assertEqual(stage.json_block('CARD: {"title": "t", "blurb": "b"}\nNEXT: x', "CARD")["title"], "t")
        self.assertIsNone(stage.json_block("nothing", "CARD"))


if __name__ == "__main__":
    unittest.main()


class TVerdict(T):
    def test_kill_and_keep(self):
        import verdict
        verdict.STATE_DIR = stage.STATE_DIR
        p, drv = self.make({
            "idea": (IDEA, {}), "plan": ("x\n", {"vault:PLAN.md": PLAN}),
            "prototype": (PROTO_OK, {}), "polish": (POLISH, {}),
        })
        self.assertTrue(verdict.apply(self.st, "pulse-grid", "kill").startswith("no such"))
        p.run(); p.run()
        self.assertIn("not showcased", verdict.apply(self.st, "pulse-grid", "kill"))
        p.run(); p.run()
        self.assertEqual(verdict.apply(self.st, "pulse-grid", "kill", "boring"), "ok")
        m = self.st.read_project("pulse-grid")
        self.assertEqual((m["verdict"], m["stage"]), ("kill", "verdict"))
        self.assertIn("a grid that pulses", self.st.dead_lines())
        self.assertIn("not this: a grid that pulses", self.st.active_goal()[1])
        self.assertEqual(self.st.read_card("pulse-grid")["verdict"], "kill")
        # the next idea prompt carries the kill
        drv.script["idea"] = (IDEA.replace("pulse-grid", "tide-clock").replace("visualizer", "timer"), {})
        p.run()
        idea_prompt = [c[1] for c in drv.calls if c[0] == "idea"][-1]
        self.assertIn("boring", idea_prompt)
        self.assertIn("pulse-grid [visualizer] (kill)", idea_prompt)
        # keep leaves a marker for the repo step
        for _ in range(3):
            p.run()
        self.assertEqual(verdict.apply(self.st, "tide-clock", "keep"), "ok")
        self.assertTrue(os.path.exists(os.path.join(stage.STATE_DIR, "keep", "tide-clock")))
