# AUTOGOD v3 — the goal loop

A local 27B model, driven headless through Claude Code, that invents and builds small
apps under a one-paragraph GOAL a human wrote. Each iteration is one fresh session that
does exactly one stage and hands back a file; the pass — plain Python, not the model —
reads the hand-back and moves the project forward.

```
GOAL ──▶ idea ──▶ plan ──▶ prototype ──▶ polish ──▶ showcase ──▶ verdict (keep / kill)
                                   └── stuck after the retries
```

- `loop/stage.py` — the stage machine (`--lane a|b`, `--driver claude_code|mock`, `--dry-run`)
- `loop/goal.py` — state on disk: `$VAULT/AUTOGOD/{goals,projects,showcase,dead.md}`; code in `~/lab/<slug>`
- `loop/prompts/<mode>/*.md` — one prompt per stage per mode; every one ends with the same hand-back contract
- `loop/tools/web.py` — research mode's stdlib search + fetch (the one deliberate way out of the box)
- `loop/render.py` — the pass renders reports and diffs to a page; the model never writes HTML for them
- `loop/drivers/claude_code.py` — one headless `claude -p` session with a wall-clock budget
- `hooks/guard.py` — the PreToolUse fence (write roots, no sudo/systemctl/push/ssh)
- `loop/pass.sh` — the lane loop: brain + proxy health → one iteration → next, as a persistent system service (`loop/systemd/`); the rack daemon starts it in auto mode, stops it in chat

## Three modes (2026-09-10)

The goal note's `mode:` picks what an iteration makes — the wall's mode keys set it:

| mode | idea picks | prototype | polish | showcase page | keep |
|---|---|---|---|---|---|
| `tinker` | one new app | build until it runs | add a feature, card | the app | repo step |
| `research` | one question under the goal | search + read the web into NOTES.md (≥5 sources) | REPORT.md, every claim cited | the report | a Blog post |
| `patch` | one target + one change (reads a mirror) | edit a fresh clone on `autogod/<slug>` until the proof passes | mergeable diff + NOTES.md | the diff + notes | git patches into `AUTOGOD/patches/` (an app: applied + republished) |

Patch targets = `$VAULT/AUTOGOD/repos.md` (`- name: url` lines) plus every kept tinker
app. The pass owns git: clone, branch, commit, diff, format-patch; the model only edits.

Two lanes (`a` = the V100 brain, `b` = the P100 pair) run independent projects; the idea
prompt sees every project under the goal and the pass refuses a category already live on
the other lane. `make test` runs the machine offline with a fake driver.

Plan and history: the `AUTOGOD v3 — Goal Loop` note in the vault. Predecessor: autogod-v2.
