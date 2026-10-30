import os
import tempfile
import textwrap

SOLUTIONS = {
    "ac.py": "a, b = map(int, input().split())\nprint(a + b)\n",
    "wa.py": "a, b = map(int, input().split())\nprint(a + b + (1 if a > 5 else 0))\n",
    "tle.py": "x = 0\nwhile True:\n    x += 1\n",
    "sleep.py": "import time\ntime.sleep(30)\n",
    "re.py": "a, b = map(int, input().split())\nprint(a // (b - b))\n",
    "mle.py": "data = bytearray(400 * 1024 * 1024)\nprint(len(data))\n",
    "pe.py": "a, b = map(int, input().split())\nprint(' %d ' % (a + b))\n",
    "float.py": "a, b = map(int, input().split())\nprint((a + b) / 3)\n",
    "ac.js": "const [a,b]=require('fs').readFileSync(0,'utf8').trim().split(/\\s+/).map(Number);console.log(a+b);\n",
}
INTERACTOR = textwrap.dedent('''
    import sys
    secret = int(open(sys.argv[1]).read().split()[1])
    for _ in range(40):
        line = sys.stdin.readline().split()
        if not line:
            sys.exit(1)
        if line[0] == "!":
            sys.exit(0 if int(line[1]) == secret else 1)
        x = int(line[1])
        print("<" if secret < x else (">" if secret > x else "="), flush=True)
    sys.exit(1)
''')
GUESSER = textwrap.dedent('''
    lo, hi = 1, 10 ** 9
    while lo < hi:
        mid = (lo + hi) // 2
        print("?", mid, flush=True)
        r = input().strip()
        if r == "=":
            lo = hi = mid
        elif r == "<":
            hi = mid - 1
        else:
            lo = mid + 1
    print("!", lo, flush=True)
''')
BAD_GUESSER = 'print("! 1", flush=True)\n'


class Workspace:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for name, src in SOLUTIONS.items():
            self.write(name, src)
        self.write("interactor.py", INTERACTOR)
        self.write("guess.py", GUESSER)
        self.write("badguess.py", BAD_GUESSER)
        self.tests = os.path.join(self.root, "tests")
        os.makedirs(self.tests)
        for i, (a, b) in enumerate([(1, 2), (10, 20), (3, 4)], 1):
            self.write("tests/%d.in" % i, "%d %d\n" % (a, b))
            self.write("tests/%d.out" % i, "%d\n" % (a + b))

    def write(self, rel, text):
        p = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return p

    def path(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def close(self):
        self.tmp.cleanup()
