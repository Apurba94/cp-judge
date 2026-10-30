import io
import json
import os
import shutil
import unittest
from contextlib import redirect_stderr, redirect_stdout

from cp_judge import runner
from cp_judge.cli import main
from cp_judge.judge import Judge, generate_answers
from cp_judge.languages import LanguageRegistry
from cp_judge.report import to_html, to_json
from cp_judge.testcases import TestCase, load

from .helpers import Workspace


def verdicts(report):
    return [r.verdict for r in report.results]


class JudgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Workspace()
        cls.cases = load(cls.ws.tests)

    @classmethod
    def tearDownClass(cls):
        cls.ws.close()

    def judge(self, sol, **kw):
        return Judge(self.ws.path(sol), **kw).judge(self.cases)

    def test_accepted_parallel(self):
        rep = self.judge("ac.py", jobs=3)
        self.assertEqual((rep.verdict, rep.passed), ("AC", 3))
        self.assertTrue(all(r.time >= 0 for r in rep.results))

    def test_wrong_answer_message(self):
        rep = self.judge("wa.py")
        self.assertEqual(verdicts(rep), ["AC", "WA", "AC"])
        self.assertEqual(rep.verdict, "WA")
        self.assertIn("expected '30', got '31'", rep.results[1].message)

    def test_stop_on_fail_skips_rest(self):
        rep = self.judge("wa.py", stop_on_fail=True)
        self.assertEqual(verdicts(rep), ["AC", "WA", "SKIP"])

    def test_time_limit_busy_and_sleeping(self):
        self.assertEqual(Judge(self.ws.path("tle.py"), time_limit=0.5).judge(self.cases[:1]).verdict, "TLE")
        self.assertEqual(Judge(self.ws.path("sleep.py"), time_limit=0.3).judge(self.cases[:1]).verdict, "TLE")

    def test_runtime_error(self):
        rep = self.judge("re.py")
        self.assertEqual(rep.verdict, "RE")
        self.assertIn("ZeroDivisionError", rep.results[0].message)

    @unittest.skipUnless(os.name == "nt" or os.path.exists("/proc/self/status"), "memory measurement unavailable")
    def test_memory_limit(self):
        rep = Judge(self.ws.path("mle.py"), memory_limit_mb=64, time_limit=5).judge(self.cases[:1])
        self.assertIn(rep.verdict, ("MLE", "RE"))         # RE when the OS refuses the allocation (Linux rlimit)

    def test_presentation_and_float_checker(self):
        self.assertEqual(self.judge("pe.py", checker="exact").verdict, "PE")
        self.assertEqual(self.judge("pe.py", checker="tokens").verdict, "AC")
        cases = [TestCase("f", "1 1\n", "0.666667\n")]
        self.assertEqual(Judge(self.ws.path("float.py"), checker="float:1e-5").judge(cases).verdict, "AC")
        self.assertEqual(Judge(self.ws.path("float.py"), checker="exact").judge(cases).verdict, "WA")

    def test_compile_error(self):
        bad = self.ws.write("bad.pyc-check", "def f(:\n")
        rep = Judge(bad).judge(self.cases)
        self.assertEqual(rep.verdict, "CE")
        self.assertIn("SyntaxError", rep.compile_log)
        self.assertEqual(set(verdicts(rep)), {"SKIP"})

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_javascript(self):
        self.assertEqual(self.judge("ac.js").verdict, "AC")

    def test_no_expected_output(self):
        rep = Judge(self.ws.path("ac.py")).judge([TestCase("x", "2 2\n")])
        self.assertEqual((rep.verdict, rep.results[0].output.strip()), ("OK", "4"))

    def test_interactive(self):
        inp = self.ws.write("itests/1.in", "1000000000 123456789\n")
        cases = [TestCase("1", "1000000000 123456789\n", None, inp)]
        good = Judge(self.ws.path("guess.py"), interactor=self.ws.path("interactor.py")).judge(cases)
        self.assertEqual(good.verdict, "AC")
        bad = Judge(self.ws.path("badguess.py"), interactor=self.ws.path("interactor.py")).judge(cases)
        self.assertEqual(bad.verdict, "WA")

    def test_group_scoring(self):
        cases = [TestCase("1", "1 2\n", "3\n", points=10, group="g1"), TestCase("2", "10 20\n", "30\n", points=10, group="g1"),
                 TestCase("3", "3 4\n", "7\n", points=5, group="g2")]
        rep = Judge(self.ws.path("wa.py")).judge(cases)
        self.assertEqual((rep.score, rep.max_score), (5, 25))


class AnswersAndReportTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()

    def tearDown(self):
        self.ws.close()

    def test_generate_answers(self):
        folder = os.path.join(self.ws.root, "new")
        self.ws.write("new/1.in", "5 6\n")
        written = generate_answers(self.ws.path("ac.py"), load(folder), folder)
        self.assertEqual(written, ["1"])
        with open(os.path.join(folder, "1.out")) as fh:
            self.assertEqual(fh.read().strip(), "11")

    def test_reports(self):
        cases = load(self.ws.tests)
        rep = Judge(self.ws.path("wa.py")).judge(cases)
        data = json.loads(to_json(rep))
        self.assertEqual((data["verdict"], data["passed"]), ("WA", 2))
        page = to_html(rep, cases)
        self.assertIn("<td class='v WA'>WA</td>", page)
        self.assertIn("<b>Expected</b><pre>30\n</pre>", page)

    def test_cli(self):
        out = os.path.join(self.ws.root, "r.json")
        with redirect_stdout(io.StringIO()) as buf, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", self.ws.path("ac.py"), self.ws.tests, "--json", out]), 0)
            self.assertEqual(main(["run", self.ws.path("wa.py"), self.ws.tests, "-j", "2"]), 1)
            self.assertEqual(main(["langs"]), 0)
        self.assertIn("Accepted", buf.getvalue())
        self.assertTrue(os.path.exists(out))


class RunnerTests(unittest.TestCase):
    def test_run_measures(self):
        import sys
        r = runner.run([sys.executable, "-c", "print(input()[::-1])"], b"abc\n", 5, 256)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, b"cba"))
        self.assertGreater(r.wall, 0)
        if os.name == "nt":
            self.assertIsNotNone(r.memory_kb)
            self.assertIsNotNone(r.cpu)

    def test_registry(self):
        reg = LanguageRegistry()
        self.assertEqual(reg.detect("sol.cpp").name, "cpp")
        self.assertEqual(reg.detect("Main.java").name, "java")
        with self.assertRaises(KeyError):
            reg.detect("x.unknownext")


if __name__ == "__main__":
    unittest.main()
