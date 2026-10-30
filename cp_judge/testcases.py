"""Discover test cases in the many layouts used by judges, problem packages and browser extensions."""
import glob
import json
import os
import re
from dataclasses import dataclass

PAIR_PATTERNS = [            # (input pattern, output candidates) with {name}
    ("{name}.in", ("{name}.out", "{name}.ans", "{name}.a", "{name}.ok")),
    ("{name}.txt", ("{name}.a",)),
    ("input{name}.txt", ("output{name}.txt", "answer{name}.txt")),
    ("in{name}.txt", ("out{name}.txt",)),
    ("{name}.input", ("{name}.output",)),
    ("{name}", ("{name}.a",)),           # Polygon packages: tests/01 and tests/01.a
]


@dataclass
class TestCase:
    name: str
    input: str
    answer: str = None        # None when no expected output is known
    input_path: str = ""
    answer_path: str = ""
    points: float = 1.0
    group: str = ""


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _read(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def from_directory(folder, require_answers=False):
    """Pair inputs and outputs in a folder (and its 'tests' / 'samples' sub-folders)."""
    files = set(os.listdir(folder))
    cases, used = [], set()
    for f in sorted(files, key=natural_key):
        full = os.path.join(folder, f)
        if os.path.isdir(full) or f in used:
            continue
        for inp_pat, out_pats in PAIR_PATTERNS:
            regex = "^" + re.escape(inp_pat).replace(re.escape("{name}"), "(.+?)") + "$"
            m = re.match(regex, f)
            if not m:
                continue
            name = m.group(1)
            if inp_pat == "{name}" and ("." in f or f.endswith(".a")):
                continue
            ans = next((o.format(name=name) for o in out_pats if o.format(name=name) in files), None)
            if inp_pat in ("{name}.txt", "{name}") and ans is None:
                continue                         # too generic without an answer file
            if ans is None and require_answers:
                continue
            used.add(f)
            if ans:
                used.add(ans)
            cases.append(TestCase(name, _read(full), _read(os.path.join(folder, ans)) if ans else None, full,
                                  os.path.join(folder, ans) if ans else ""))
            break
    # nested layout: folder/<name>/input and folder/<name>/output
    for d in sorted(files, key=natural_key):
        sub = os.path.join(folder, d)
        if os.path.isdir(sub):
            inp = next((os.path.join(sub, n) for n in ("input", "input.txt", "in", "in.txt") if os.path.exists(os.path.join(sub, n))), None)
            out = next((os.path.join(sub, n) for n in ("output", "output.txt", "out", "answer", "ans") if os.path.exists(os.path.join(sub, n))), None)
            if inp:
                cases.append(TestCase(d, _read(inp), _read(out) if out else None, inp, out or ""))
            elif d in ("tests", "samples", "sample"):
                cases += [TestCase("%s/%s" % (d, c.name), c.input, c.answer, c.input_path, c.answer_path)
                          for c in from_directory(sub, require_answers)]
    _apply_points(folder, cases)
    return cases


def _apply_points(folder, cases):
    """Optional points.json: {"test name": points} or {"groups": {"g1": {"points": 30, "tests": ["1", "2"]}}}."""
    p = os.path.join(folder, "points.json")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as fh:
        spec = json.load(fh)
    if "groups" in spec:
        for g, info in spec["groups"].items():
            for c in cases:
                if c.name in info["tests"]:
                    c.group = g
                    c.points = info["points"] / len(info["tests"])
    else:
        for c in cases:
            c.points = float(spec.get(c.name, c.points))


def from_companion_json(path):
    """Competitive Companion / problem-fetcher JSON: {"name": ..., "tests": [{"input": ..., "output": ...}]}."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return [TestCase("sample%d" % i, t["input"], t.get("output"), path) for i, t in enumerate(data.get("tests", []), 1)]


def load(path_or_glob, require_answers=False):
    if os.path.isdir(path_or_glob):
        return from_directory(path_or_glob, require_answers)
    if path_or_glob.lower().endswith(".json") and os.path.isfile(path_or_glob):
        return from_companion_json(path_or_glob)
    cases = []
    for inp in sorted(glob.glob(path_or_glob), key=natural_key):
        stem = os.path.splitext(inp)[0]
        ans = next((stem + e for e in (".out", ".ans", ".a") if os.path.exists(stem + e)), None)
        cases.append(TestCase(os.path.basename(stem), _read(inp), _read(ans) if ans else None, inp, ans or ""))
    if not cases:
        raise FileNotFoundError("no test cases found at %s" % path_or_glob)
    return cases


def write_case(folder, name, input_text, answer_text=None):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ".in"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(input_text if input_text.endswith("\n") else input_text + "\n")
    if answer_text is not None:
        with open(os.path.join(folder, name + ".out"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(answer_text if answer_text.endswith("\n") else answer_text + "\n")


def next_name(folder):
    nums = [int(m.group(1)) for f in (os.listdir(folder) if os.path.isdir(folder) else [])
            for m in [re.match(r"^(\d+)\.in$", f)] if m]
    return str(max(nums, default=0) + 1)
