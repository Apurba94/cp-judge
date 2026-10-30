# cp-judge

**A local online judge for competitive programming: compile and run your solution in C++, C, Python,
Java, Kotlin, Rust, Go or JavaScript against a whole test suite, with time and memory limits, the usual
verdicts (AC, WA, PE, TLE, MLE, OLE, RE, CE), special checkers, interactive problems, subtask scoring,
parallel execution and HTML/JSON reports.**

Part of the *Competitive Programming Suite* (10 large automation tools for algorithmic problem solving).

## Why

Online judges tell you only "Wrong answer on test 7". Locally, you want to run *all* samples and your own
tests in one command, see exactly which token differs, catch TLE and MLE before submitting, test
floating-point answers with a tolerance, and work on interactive problems without hand-typing replies.
`cp-judge` does all of this with nothing but Python installed.

## Features

| Area | Details |
|------|---------|
| Languages | C++17, C11, Python, PyPy, Java, Kotlin, Rust, Go, JavaScript (Node), plus your own definitions via JSON; compiled binaries are cached by source hash |
| Limits | CPU time (Windows `GetProcessTimes`, Linux `/proc`), wall-clock deadline for sleeping processes, peak memory (Windows `GetProcessMemoryInfo`, Linux `VmHWM` + `RLIMIT_AS`), output size |
| Verdicts | AC, WA, PE (whitespace only), TLE, MLE, OLE, RE (with the last stderr line), CE (with compiler log), IE (checker crash), OK (no expected output) |
| Checkers | `exact`, `lines`, `tokens` (default), `ci`, `yesno`, `unordered`, `float:EPS` (absolute or relative error), `prog:PATH` (testlib-style: input output answer, exit codes 0/1/2), `py:FILE` (Python `check()` function) |
| Tests | `1.in/1.out`, `1.in/1.ans`, `input1.txt/output1.txt`, Polygon `tests/01` + `01.a`, `name/input` + `name/output`, globs, Competitive Companion JSON; natural ordering; `points.json` for subtasks |
| Interactive | `--interactor` connects solution and interactor through pipes; the interactor's exit code decides |
| Workflow | parallel runs (`-j`), stop at first failure (`-x`), `answers` generates expected outputs from a reference solution, `add` appends tests from stdin |
| Reports | coloured console table, JSON, standalone HTML with input / expected / actual side by side for every failing test |

## Usage

```bash
pip install .
cp-judge run solution.cpp tests/ -t 1 -m 256
cp-judge run sol.py samples.json --checker float:1e-6 -j 4 --html report.html
cp-judge run sol.py tests/ --checker prog:checker.py -x
cp-judge run sol.py tests/ --interactor interactor.py
cp-judge answers brute.py tests/                 # fill in missing .out files
cp-judge add tests/ < new_input.txt
cp-judge langs                                   # which compilers are installed
```

Custom languages (`--languages mylangs.json`):

```json
{"cpp20": {"extensions": [".cpp"], "compile": ["g++", "-std=c++20", "-O2", "{src}", "-o", "{exe}"], "run": ["{exe}"]}}
```

Exit code 0 when every test passes, 1 otherwise, so it can drive scripts and CI.

## Limitations

Memory is sampled every 5 ms (very short allocation spikes can be missed); there is no sandbox, so only run
code you trust. CPU-time measurement falls back to wall time on systems other than Windows and Linux.

## Testing

```bash
python -m unittest discover -s tests -t .
```

## License

MIT (c) JANIN A APURBA
