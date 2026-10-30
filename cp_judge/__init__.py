"""cp-judge: a local online judge for competitive programming."""
from .checkers import CheckResult, get_checker
from .judge import Judge, JudgeReport, TestResult, VERDICTS, generate_answers
from .languages import Language, LanguageRegistry, Program
from .runner import RunResult, run, run_interactive
from .testcases import TestCase, load

__version__ = "0.1.0"
__all__ = ["CheckResult", "get_checker", "Judge", "JudgeReport", "TestResult", "VERDICTS", "generate_answers",
           "Language", "LanguageRegistry", "Program", "RunResult", "run", "run_interactive", "TestCase", "load"]
