"""Judge a program against test cases and produce per-test and overall verdicts."""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import runner
from .checkers import get_checker
from .languages import CompileError, LanguageRegistry, Program

VERDICTS = {
    "AC": "Accepted", "WA": "Wrong Answer", "PE": "Presentation Error", "TLE": "Time Limit Exceeded",
    "MLE": "Memory Limit Exceeded", "OLE": "Output Limit Exceeded", "RE": "Runtime Error",
    "CE": "Compilation Error", "OK": "Ran (no expected output)", "IE": "Internal Error (checker failed)",
    "SKIP": "Skipped",
}
SEVERITY = ["CE", "IE", "RE", "MLE", "TLE", "OLE", "WA", "PE", "OK", "AC", "SKIP"]


@dataclass
class TestResult:
    name: str
    verdict: str
    time: float = 0.0
    wall: float = 0.0
    memory_kb: int = None
    message: str = ""
    output: str = ""
    stderr: str = ""
    points: float = 0.0
    max_points: float = 1.0
    group: str = ""


@dataclass
class JudgeReport:
    source: str
    language: str
    verdict: str
    results: list = field(default_factory=list)
    compile_log: str = ""
    time_limit: float = 2.0
    memory_limit_mb: int = 256

    @property
    def passed(self):
        return sum(1 for r in self.results if r.verdict in ("AC", "OK"))

    @property
    def score(self):
        return sum(r.points for r in self.results)

    @property
    def max_score(self):
        return sum(r.max_points for r in self.results)

    @property
    def max_time(self):
        return max((r.time for r in self.results), default=0.0)

    @property
    def max_memory_kb(self):
        vals = [r.memory_kb for r in self.results if r.memory_kb]
        return max(vals) if vals else None


def _decode(b):
    return b.decode("utf-8", errors="replace")


class Judge:
    def __init__(self, source, language=None, time_limit=2.0, memory_limit_mb=256, checker="tokens",
                 interactor=None, jobs=1, stop_on_fail=False, registry=None, output_limit_mb=64, build_root=None):
        self.registry = registry or LanguageRegistry()
        self.language = self.registry.get(language) if language else self.registry.detect(source)
        self.program = Program(source, self.language, build_root)
        self.time_limit, self.memory_limit_mb, self.output_limit_mb = time_limit, memory_limit_mb, output_limit_mb
        self.checker_spec = checker
        self.checker = get_checker(checker) if isinstance(checker, str) else checker
        self.interactor = interactor
        self.jobs = max(1, jobs)
        self.stop_on_fail = stop_on_fail

    def _interactor_cmd(self, input_path, answer_path):
        lang = self.registry.detect(self.interactor)
        prog = Program(self.interactor, lang)
        prog.compile()
        return prog.command([input_path, answer_path or input_path])

    def run_case(self, case):
        cmd = self.program.command()
        if self.interactor:
            with tempfile.TemporaryDirectory() as d:
                ip = case.input_path or os.path.join(d, "input.txt")
                if not case.input_path:
                    with open(ip, "w", encoding="utf-8") as fh:
                        fh.write(case.input)
                res, code, msg = runner.run_interactive(cmd, self._interactor_cmd(ip, case.answer_path), self.time_limit)
            v = "TLE" if res.timed_out else ("RE" if res.returncode not in (0, None) else ("AC" if code == 0 else "WA"))
            if code not in (0, 1, 2) and v == "AC":
                v = "IE"
            return self._result(case, v, res, msg)
        res = runner.run(cmd, case.input.encode("utf-8"), self.time_limit, self.memory_limit_mb, self.output_limit_mb)
        out = _decode(res.stdout)
        if res.memory_exceeded:
            return self._result(case, "MLE", res, "peak memory above %d MB" % self.memory_limit_mb, out)
        if res.timed_out:
            return self._result(case, "TLE", res, "", out)
        if res.output_exceeded:
            return self._result(case, "OLE", res, "output above %d MB" % self.output_limit_mb, out)
        if res.returncode != 0:
            err = _decode(res.stderr).strip().splitlines()
            return self._result(case, "RE", res, "exit code %s%s" % (res.returncode, (": " + err[-1][:200]) if err else ""), out)
        if case.answer is None:
            return self._result(case, "OK", res, "no expected output", out)
        try:
            cr = self.checker(case.input, out, case.answer)
        except Exception as exc:                    # checker crashed
            return self._result(case, "IE", res, str(exc), out)
        verdict = "AC" if cr.ok else ("PE" if cr.presentation else "WA")
        return self._result(case, verdict, res, cr.message, out)

    def _result(self, case, verdict, res, message="", output=""):
        return TestResult(case.name, verdict, round(res.time, 3), round(res.wall, 3), res.memory_kb, message,
                          output[:2000], _decode(res.stderr)[-1000:], case.points if verdict in ("AC", "OK") else 0.0,
                          case.points, case.group)

    def judge(self, cases, progress=None):
        report = JudgeReport(self.program.source, self.language.name, "AC", time_limit=self.time_limit,
                             memory_limit_mb=self.memory_limit_mb)
        try:
            self.program.compile()
            report.compile_log = self.program.compile_log
        except CompileError as exc:
            report.verdict, report.compile_log = "CE", "%s\n%s" % (exc, exc.log)
            report.results = [TestResult(c.name, "SKIP", max_points=c.points) for c in cases]
            return report
        if self.stop_on_fail or self.jobs == 1:
            results = []
            for c in cases:
                r = self.run_case(c)
                results.append(r)
                if progress:
                    progress(r)
                if self.stop_on_fail and r.verdict not in ("AC", "OK"):
                    results += [TestResult(x.name, "SKIP", max_points=x.points) for x in cases[len(results):]]
                    break
        else:
            with ThreadPoolExecutor(self.jobs) as ex:
                results = list(ex.map(self.run_case, cases))
            if progress:
                for r in results:
                    progress(r)
        _apply_groups(results)
        report.results = results
        failing = [r.verdict for r in results if r.verdict not in ("AC", "OK", "SKIP")]
        report.verdict = failing[0] if failing else ("AC" if any(r.verdict == "AC" for r in results) else
                                                    ("OK" if results else "AC"))
        return report


def _apply_groups(results):
    """Subtask scoring: a group earns its points only if every test in it passes."""
    groups = {}
    for r in results:
        if r.group:
            groups.setdefault(r.group, []).append(r)
    for rs in groups.values():
        if any(r.verdict not in ("AC", "OK") for r in rs):
            for r in rs:
                r.points = 0.0


def generate_answers(reference, cases, folder, language=None, time_limit=10.0, overwrite=False):
    """Run a trusted reference solution to create missing .out files. Returns names written."""
    j = Judge(reference, language, time_limit=time_limit, memory_limit_mb=0)
    j.program.compile()
    written = []
    for c in cases:
        if c.answer is not None and not overwrite:
            continue
        res = runner.run(j.program.command(), c.input.encode(), time_limit, 0)
        if res.returncode != 0 or res.timed_out:
            raise RuntimeError("reference failed on %s (exit %s)" % (c.name, res.returncode))
        stem = os.path.splitext(c.input_path)[0] if c.input_path else os.path.join(folder, c.name)
        with open(stem + ".out", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_decode(res.stdout))
        written.append(c.name)
    return written
