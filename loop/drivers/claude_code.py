"""loop/drivers/claude_code.py — the real driver: one headless `claude -p` session.

Interface (shared with loop/drivers/mock.py):
    run(prompt, cwd, tools, budget_secs, max_turns, env_extra) -> dict(
        exit_code, num_turns, is_error, seconds, session_id, result)

Every iteration is a fresh session: the model's memory across iterations is
the project's files and the last hand-back, nothing else. The guard hook is
registered in <cwd>/.claude/settings.json before each run.
"""
import json
import os
import subprocess
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENV_SH = os.path.join(_HERE, "..", "env.sh")

CLAUDE_BIN = os.environ.get("AUTOGOD_CLAUDE_BIN", "claude")
_MAX_TURNS_SUPPORTED = None


def load_env(extra=None):
    """The process environment merged with loop/env.sh (which branches on
    AUTOGOD_LANE) and then with `extra`."""
    base = dict(os.environ)
    if extra:
        base.update(extra)
    try:
        proc = subprocess.run(
            ["bash", "-c", 'set -a; source "%s"; env -0' % _ENV_SH],
            capture_output=True, env=base, timeout=10,
        )
        if proc.returncode == 0:
            for chunk in proc.stdout.split(b"\x00"):
                if chunk and b"=" in chunk:
                    k, _, v = chunk.partition(b"=")
                    base[k.decode()] = v.decode()
    except Exception:
        pass
    if extra:
        base.update(extra)
    return base


def ensure_hook(cwd, root):
    """Register hooks/guard.py as the PreToolUse hook for sessions run in cwd."""
    guard = os.path.realpath(os.path.join(root, "hooks", "guard.py"))
    d = os.path.join(cwd, ".claude")
    os.makedirs(d, exist_ok=True)
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "", "hooks": [{"type": "command", "command": guard}]}
    ]}}
    with open(os.path.join(d, "settings.json"), "w") as f:
        json.dump(settings, f, indent=2)


def _parse_result_json(text):
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.rfind("{")
    while start != -1:
        try:
            return json.loads(text[start:])
        except Exception:
            start = text.rfind("{", 0, start)
    return {}


def _supports_max_turns(env):
    global _MAX_TURNS_SUPPORTED
    if _MAX_TURNS_SUPPORTED is None:
        try:
            proc = subprocess.run([CLAUDE_BIN, "-p", "--help"], capture_output=True,
                                  text=True, env=env, timeout=15)
            _MAX_TURNS_SUPPORTED = "--max-turns" in (proc.stdout or "") + (proc.stderr or "")
        except Exception:
            _MAX_TURNS_SUPPORTED = False
    return _MAX_TURNS_SUPPORTED


def _stream_line(obj, out):
    """One stream-json event -> readable lines for the live log (the wall's MINDS pane)."""
    t = obj.get("type")
    if t == "assistant":
        for c in (obj.get("message") or {}).get("content") or []:
            if c.get("type") == "text" and c.get("text", "").strip():
                out.write(c["text"].rstrip() + "\n")
            elif c.get("type") == "thinking" and c.get("thinking"):
                out.write("(thinking, %d chars)\n" % len(c["thinking"]))
            elif c.get("type") == "tool_use":
                inp = c.get("input") or {}
                arg = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("query") or ""
                out.write("> %s %s\n" % (c.get("name", "tool"), str(arg)[:200]))
    elif t == "user":
        for c in (obj.get("message") or {}).get("content") or []:
            if c.get("type") == "tool_result":
                body = c.get("content")
                if isinstance(body, list):
                    body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                body = str(body or "").strip()
                if body:
                    out.write("  " + body[:300].replace("\n", "\n  ") + "\n")
    elif t == "result":
        out.write("[result] %s turns=%s error=%s\n" % (obj.get("subtype"), obj.get("num_turns"), obj.get("is_error")))
    out.flush()


def run(prompt, cwd, tools, budget_secs, max_turns=40, env_extra=None):
    env = load_env(env_extra)
    root = env.get("AUTOGOD_ROOT", os.path.realpath(os.path.join(_HERE, "..", "..")))
    os.makedirs(cwd, exist_ok=True)
    ensure_hook(cwd, root)

    cmd = [CLAUDE_BIN, "-p", "--output-format", "stream-json", "--verbose", "--allowedTools", tools]
    if _supports_max_turns(env):
        cmd += ["--max-turns", str(max_turns)]

    log_path = env.get("AUTOGOD_ITER_LOG")
    log = open(log_path, "w", encoding="utf-8") if log_path else open(os.devnull, "w")
    log.write("$ %s\n[cwd %s] [budget %ds]\n\n" % (" ".join(cmd), cwd, budget_secs))
    log.flush()

    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, cwd=cwd)
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    result = {}
    killed = False
    # stdout is read line by line as the session runs; the budget is enforced
    # by wall clock on the reading loop, not by communicate().
    import selectors
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    buf = ""
    while True:
        left = budget_secs - (time.time() - t0)
        if left <= 0:
            killed = True
            proc.kill()
            break
        if not sel.select(timeout=min(left, 5)):
            if proc.poll() is not None:
                break
            continue
        chunk = proc.stdout.readline()
        if not chunk:
            break
        buf += chunk
        if not chunk.endswith("\n"):
            continue
        line, buf = buf, ""
        try:
            obj = json.loads(line)
        except ValueError:
            log.write(line)
            continue
        if obj.get("type") == "result":
            result = obj
        try:
            _stream_line(obj, log)
        except Exception:
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    stderr = ""
    try:
        stderr = proc.stderr.read() or ""
    except Exception:
        pass
    seconds = time.time() - t0
    if killed:
        log.write("\n[KILLED: budget %ds]\n" % budget_secs)
    if stderr.strip():
        log.write("\n--- stderr ---\n" + stderr[-4000:])
    log.write("\n[%.0fs]\n" % seconds)
    log.close()
    return {
        "session_id": result.get("session_id"),
        "exit_code": -9 if killed else (proc.returncode if proc.returncode is not None else -1),
        "num_turns": result.get("num_turns", 0),
        "is_error": True if killed else bool(result.get("is_error", proc.returncode != 0)),
        "seconds": seconds,
        "result": result.get("result", ""),
    }
