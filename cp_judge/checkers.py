"""Output checkers. Each checker takes (input_text, output_text, answer_text) and returns a CheckResult.

Specs (CLI --checker): exact | lines | tokens | ci (case-insensitive tokens) | float[:EPS] | unordered |
yesno | prog:PATH (testlib-style external checker: PATH input output answer, exit 0 = OK, 1 = WA, 2 = PE) |
py:FILE.py (Python file defining check(input, output, answer) -> bool or (bool, message)).
"""
import importlib.util
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass

_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$|^[-+]?(inf|nan)$", re.I)


@dataclass
class CheckResult:
    ok: bool
    message: str = ""
    presentation: bool = False        # True: answer correct up to whitespace (PE)


def _norm_newlines(s):
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _first_diff(a, b, what):
    for i, (x, y) in enumerate(zip(a, b), 1):
        if x != y:
            return "%s %d differs: expected %s, got %s" % (what, i, _short(y), _short(x))
    if len(a) != len(b):
        return "expected %d %ss, got %d" % (len(b), what, len(a))
    return ""


def _short(s, n=60):
    s = repr(s)
    return s if len(s) <= n else s[:n] + "...'"


def exact(inp, out, ans):
    o, a = _norm_newlines(out).rstrip("\n"), _norm_newlines(ans).rstrip("\n")
    if o == a:
        return CheckResult(True)
    if o.split() == a.split():
        return CheckResult(False, "whitespace differs", presentation=True)
    return CheckResult(False, _first_diff(o.split("\n"), a.split("\n"), "line"))


def lines(inp, out, ans):
    o = [l.rstrip() for l in _norm_newlines(out).rstrip().split("\n")]
    a = [l.rstrip() for l in _norm_newlines(ans).rstrip().split("\n")]
    return CheckResult(True) if o == a else CheckResult(False, _first_diff(o, a, "line"))


def tokens(inp, out, ans):
    o, a = out.split(), ans.split()
    return CheckResult(True) if o == a else CheckResult(False, _first_diff(o, a, "token"))


def case_insensitive(inp, out, ans):
    o, a = out.lower().split(), ans.lower().split()
    return CheckResult(True) if o == a else CheckResult(False, _first_diff(out.split(), ans.split(), "token"))


def yesno(inp, out, ans):
    norm = lambda t: [{"yes": "yes", "y": "yes", "no": "no", "n": "no"}.get(x.lower(), x.lower()) for x in t.split()]
    o, a = norm(out), norm(ans)
    return CheckResult(True) if o == a else CheckResult(False, _first_diff(o, a, "answer"))


def make_float(eps=1e-6):
    """Numeric tokens match when absolute OR relative error <= eps; other tokens must match exactly."""
    def check(inp, out, ans):
        o, a = out.split(), ans.split()
        if len(o) != len(a):
            return CheckResult(False, "expected %d tokens, got %d" % (len(a), len(o)))
        for i, (x, y) in enumerate(zip(o, a), 1):
            if _NUM.match(y):
                if not _NUM.match(x):
                    return CheckResult(False, "token %d: expected a number, got %s" % (i, _short(x)))
                fx, fy = float(x), float(y)
                if math.isnan(fy) and math.isnan(fx):
                    continue
                err = abs(fx - fy)
                if not (err <= eps or err <= eps * abs(fy)):
                    return CheckResult(False, "token %d: expected %s, got %s (error %.3g > %g)" % (i, y, x, err, eps))
            elif x != y:
                return CheckResult(False, "token %d differs: expected %s, got %s" % (i, _short(y), _short(x)))
        return CheckResult(True)
    return check


def unordered(inp, out, ans):
    o = sorted(l.strip() for l in _norm_newlines(out).strip().split("\n") if l.strip())
    a = sorted(l.strip() for l in _norm_newlines(ans).strip().split("\n") if l.strip())
    if o == a:
        return CheckResult(True)
    missing = len([x for x in a if x not in o])
    return CheckResult(False, "line multisets differ (%d expected line(s) missing)" % missing)


def make_program(path_or_cmd):
    """External testlib-compatible checker: <checker> <input> <output> <answer>."""
    cmd = [sys.executable, path_or_cmd] if path_or_cmd.endswith(".py") else [path_or_cmd]

    def check(inp, out, ans):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, text in (("input.txt", inp), ("output.txt", out), ("answer.txt", ans)):
                p = os.path.join(d, name)
                with open(p, "w", encoding="utf-8", newline="") as fh:
                    fh.write(text)
                paths.append(p)
            r = subprocess.run(cmd + paths, capture_output=True, text=True, timeout=60)
        msg = (r.stderr.strip() or r.stdout.strip())[:300]
        if r.returncode == 0:
            return CheckResult(True, msg)
        if r.returncode == 2:
            return CheckResult(False, msg or "presentation error", presentation=True)
        if r.returncode in (1, 4, 5, 7):
            return CheckResult(False, msg or "wrong answer")
        raise RuntimeError("checker failed (exit %d): %s" % (r.returncode, msg))
    return check


def make_python(path):
    spec = importlib.util.spec_from_file_location("cp_judge_user_checker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "check"):
        raise ValueError("%s must define check(input, output, answer)" % path)

    def check(inp, out, ans):
        r = mod.check(inp, out, ans)
        if isinstance(r, tuple):
            return CheckResult(bool(r[0]), str(r[1]) if len(r) > 1 else "")
        return CheckResult(bool(r))
    return check


BUILTIN = {"exact": exact, "lines": lines, "tokens": tokens, "ci": case_insensitive, "yesno": yesno,
           "unordered": unordered}


def get_checker(spec="tokens"):
    if spec in BUILTIN:
        return BUILTIN[spec]
    if spec == "float" or spec.startswith("float:"):
        return make_float(float(spec.split(":", 1)[1]) if ":" in spec else 1e-6)
    if spec.startswith("prog:"):
        return make_program(spec[5:])
    if spec.startswith("py:"):
        return make_python(spec[3:])
    raise ValueError("unknown checker %r" % spec)
