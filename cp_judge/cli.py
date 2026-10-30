"""Command-line interface for cp-judge."""
import argparse
import sys

from . import report as rep
from . import testcases
from .judge import Judge, generate_answers
from .languages import LanguageRegistry


def _common(p):
    p.add_argument("--lang", help="language name (default: detected from the extension)")
    p.add_argument("--languages", help="JSON file adding or overriding language definitions")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cp-judge", description="Local online judge for competitive programming.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="judge a solution against tests")
    r.add_argument("solution")
    r.add_argument("tests", help="folder, glob of .in files, or Competitive Companion JSON")
    r.add_argument("-t", "--time-limit", type=float, default=2.0, help="seconds (CPU time when measurable)")
    r.add_argument("-m", "--memory-limit", type=int, default=256, help="MB (0 = unlimited)")
    r.add_argument("-c", "--checker", default="tokens",
                   help="exact | lines | tokens | ci | yesno | unordered | float[:EPS] | prog:PATH | py:FILE")
    r.add_argument("-i", "--interactor", help="interactor program for interactive problems")
    r.add_argument("-j", "--jobs", type=int, default=1, help="run tests in parallel")
    r.add_argument("-x", "--stop", action="store_true", help="stop at the first failing test")
    r.add_argument("--json", help="write a JSON report")
    r.add_argument("--html", help="write an HTML report")
    _common(r)
    g = sub.add_parser("answers", help="create missing expected outputs with a reference solution")
    g.add_argument("reference")
    g.add_argument("tests")
    g.add_argument("--overwrite", action="store_true")
    g.add_argument("-t", "--time-limit", type=float, default=10.0)
    _common(g)
    a = sub.add_parser("add", help="add a test case from files or stdin")
    a.add_argument("folder")
    a.add_argument("--input", help="input file (default: read stdin)")
    a.add_argument("--answer", help="expected output file")
    lg = sub.add_parser("langs", help="list languages and whether their tools are installed")
    lg.add_argument("--languages")
    args = ap.parse_args(argv)

    registry = LanguageRegistry.with_overrides(getattr(args, "languages", None))
    if args.cmd == "langs":
        for l in sorted(registry.languages.values(), key=lambda l: l.name):
            print("%-15s %-22s %-10s %s" % (l.name, " ".join(l.extensions), "ok" if l.available() else "missing", l.note))
        return 0
    if args.cmd == "add":
        inp = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
        ans = open(args.answer, encoding="utf-8").read() if args.answer else None
        name = testcases.next_name(args.folder)
        testcases.write_case(args.folder, name, inp, ans)
        print("added test %s" % name)
        return 0
    try:
        cases = testcases.load(args.tests)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.cmd == "answers":
        written = generate_answers(args.reference, cases, args.tests, args.lang, args.time_limit, args.overwrite)
        print("wrote %d answer file(s)" % len(written))
        return 0
    judge = Judge(args.solution, args.lang, args.time_limit, args.memory_limit, args.checker, args.interactor, args.jobs,
                  args.stop, registry)
    color = rep._use_color(sys.stdout)
    report = judge.judge(cases, progress=(lambda res: print(rep.line_for(res, color), flush=True)) if args.jobs == 1 else None)
    if report.verdict == "CE" or args.jobs > 1:
        sys.stdout.write(rep.text(report))
    else:
        summary = rep.text(report).splitlines()[-2:]
        print("\n".join(summary))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(rep.to_json(report))
    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(rep.to_html(report, cases))
    return 0 if report.verdict in ("AC", "OK") else 1
