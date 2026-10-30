import os
import sys
import tempfile
import unittest

from cp_judge.checkers import get_checker


class CheckerTests(unittest.TestCase):
    def test_exact_and_presentation(self):
        c = get_checker("exact")
        self.assertTrue(c("", "1 2\r\n3\n", "1 2\n3").ok)
        r = c("", "1  2\n3", "1 2\n3")
        self.assertFalse(r.ok)
        self.assertTrue(r.presentation)
        self.assertIn("line 2", c("", "1\n4", "1\n3").message)

    def test_lines_tokens_ci(self):
        self.assertTrue(get_checker("lines")("", "a b  \nc\n\n", "a b\nc").ok)
        self.assertFalse(get_checker("lines")("", "a  b\nc", "a b\nc").ok)
        self.assertTrue(get_checker("tokens")("", "1\n2   3", "1 2 3").ok)
        msg = get_checker("tokens")("", "1 2", "1 2 3").message
        self.assertIn("expected 3 tokens", msg)
        self.assertTrue(get_checker("ci")("", "YES", "yes").ok)
        self.assertTrue(get_checker("yesno")("", "Y n", "YES no").ok)

    def test_float(self):
        c = get_checker("float:1e-6")
        self.assertTrue(c("", "3.3333334", "3.333333333").ok)
        self.assertFalse(c("", "1.1", "1.0").ok)
        self.assertTrue(c("", "1000000.5", "1000000.0").ok)         # relative error 5e-7 is accepted
        self.assertTrue(c("", "1e9", "1000000000.5").ok)
        self.assertFalse(c("", "abc", "1.0").ok)
        self.assertTrue(c("", "x 1.0000001", "x 1").ok)
        self.assertFalse(c("", "y 1", "x 1").ok)

    def test_unordered(self):
        c = get_checker("unordered")
        self.assertTrue(c("", "b\na\n", "a\nb").ok)
        self.assertFalse(c("", "a\na", "a\nb").ok)

    def test_external_and_python_checkers(self):
        with tempfile.TemporaryDirectory() as d:
            prog = os.path.join(d, "chk.py")
            with open(prog, "w") as fh:
                fh.write("import sys\nout=open(sys.argv[2]).read().split()\nans=open(sys.argv[3]).read().split()\n"
                         "sys.exit(0 if sorted(out)==sorted(ans) else 1)\n")
            c = get_checker("prog:" + prog)
            self.assertTrue(c("", "3 1 2", "1 2 3").ok)
            self.assertFalse(c("", "3 1", "1 2 3").ok)
            py = os.path.join(d, "mychk.py")
            with open(py, "w") as fh:
                fh.write("def check(inp, out, ans):\n    return int(out) % 2 == 0, 'need even'\n")
            r = get_checker("py:" + py)("", "3", "")
            self.assertEqual((r.ok, r.message), (False, "need even"))

    def test_unknown(self):
        with self.assertRaises(ValueError):
            get_checker("magic")


if __name__ == "__main__":
    unittest.main()
