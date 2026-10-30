import json
import os
import tempfile
import unittest

from cp_judge.testcases import from_directory, load, natural_key, next_name, write_case


def make(root, files):
    for rel, text in files.items():
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)


class DiscoveryTests(unittest.TestCase):
    def test_layouts(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {"1.in": "a", "1.out": "A", "2.in": "b", "2.ans": "B", "input3.txt": "c", "output3.txt": "C",
                     "10.in": "j", "notes.txt": "ignore", "sub/input": "x", "sub/output": "X",
                     "tests/01": "p", "tests/01.a": "P"})
            cases = from_directory(d)
            got = {c.name: (c.input, c.answer) for c in cases}
            self.assertEqual(got["1"], ("a", "A"))
            self.assertEqual(got["2"], ("b", "B"))
            self.assertEqual(got["3"], ("c", "C"))
            self.assertEqual(got["10"], ("j", None))
            self.assertEqual(got["sub"], ("x", "X"))
            self.assertEqual(got["tests/01"], ("p", "P"))
            self.assertNotIn("notes", got)
            names = [c.name for c in cases]
            self.assertLess(names.index("2"), names.index("10"))          # natural order

    def test_require_answers_and_points(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {"1.in": "a", "1.out": "A", "2.in": "b",
                     "points.json": json.dumps({"groups": {"g": {"points": 40, "tests": ["1", "2"]}}})})
            self.assertEqual([c.name for c in from_directory(d, require_answers=True)], ["1"])
            cases = from_directory(d)
            self.assertEqual([(c.group, c.points) for c in cases], [("g", 20.0), ("g", 20.0)])

    def test_companion_json_and_glob(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "problem.json")
            with open(p, "w") as fh:
                json.dump({"name": "A", "tests": [{"input": "1 2\n", "output": "3\n"}]}, fh)
            self.assertEqual(load(p)[0].answer, "3\n")
            make(d, {"x1.in": "q", "x1.out": "Q"})
            self.assertEqual(load(os.path.join(d, "x*.in"))[0].answer, "Q")
            with self.assertRaises(FileNotFoundError):
                load(os.path.join(d, "nothing*.in"))

    def test_write_and_next_name(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(next_name(d), "1")
            write_case(d, "1", "5", "6")
            write_case(d, "7", "1")
            self.assertEqual(next_name(d), "8")
            with open(os.path.join(d, "1.in")) as fh:
                self.assertEqual(fh.read(), "5\n")
            self.assertEqual(natural_key("test12"), ["test", 12, ""])


if __name__ == "__main__":
    unittest.main()
