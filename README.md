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
- `loop/prompts/*.md` — one prompt per stage; every one ends with the same hand-back contract
- `loop/drivers/claude_code.py` — one headless `claude -p` session with a wall-clock budget
- `hooks/guard.py` — the PreToolUse fence (write roots, no sudo/systemctl/push/ssh)
- `loop/pass.sh` — brain health check → lane lock → one iteration; `loop/systemd/` runs it every 15 min

Two lanes (`a` = the V100 brain, `b` = the P100 pair) run independent projects; the idea
prompt sees every project under the goal and the pass refuses a category already live on
the other lane. `make test` runs the machine offline with a fake driver.

Plan and history: the `AUTOGOD v3 — Goal Loop` note in the vault. Predecessor: autogod-v2.
