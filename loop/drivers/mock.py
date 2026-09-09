"""loop/drivers/mock.py — offline driver. Instead of running a model it copies
a fixture into the hand-back path the pass asked for, so the whole stage
machine can be exercised with no brain.

  AUTOGOD_MOCK_DIR   directory of fixtures: <stage>.md (the hand-back),
                     optional <stage>.PLAN.md (written to the project dir as PLAN.md),
                     optional <stage>.file (written into cwd as index.html).
The stage and paths arrive in env_extra (AUTOGOD_STAGE, AUTOGOD_HANDBACK_PATH,
AUTOGOD_PROJECT_DIR).
"""
import os
import shutil


def run(prompt, cwd, tools, budget_secs, max_turns=40, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    fx = env.get("AUTOGOD_MOCK_DIR", "")
    stage = env.get("AUTOGOD_STAGE", "")
    hb = env.get("AUTOGOD_HANDBACK_PATH", "")
    pd = env.get("AUTOGOD_PROJECT_DIR", "")
    os.makedirs(cwd, exist_ok=True)
    src = os.path.join(fx, stage + ".md")
    if hb and os.path.exists(src):
        os.makedirs(os.path.dirname(hb), exist_ok=True)
        shutil.copy(src, hb)
    plan = os.path.join(fx, stage + ".PLAN.md")
    if pd and os.path.exists(plan):
        shutil.copy(plan, os.path.join(pd, "PLAN.md"))
    fl = os.path.join(fx, stage + ".file")
    if os.path.exists(fl):
        shutil.copy(fl, os.path.join(cwd, "index.html"))
    return {"session_id": "mock", "exit_code": 0, "num_turns": 1,
            "is_error": False, "seconds": 0.0, "result": "mock"}
