"""Language definitions: how to compile and run a source file, detected from its extension.

Commands are lists with placeholders: {src} source path, {exe} compiled binary path, {dir} build directory,
{stem} file name without extension, {python} the running Python interpreter. Users can add or override
languages with a JSON file (see README).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

EXE = ".exe" if os.name == "nt" else ""


@dataclass
class Language:
    name: str
    extensions: tuple
    run: list
    compile: list = field(default_factory=list)
    output: str = ""                # file produced by compile ({exe} by default when compile is set)
    note: str = ""

    def needs_compile(self):
        return bool(self.compile)

    def available(self):
        tool = (self.compile or self.run)[0]
        if tool in ("{python}", "{exe}"):
            return True
        return shutil.which(tool) is not None


DEFAULT_LANGUAGES = [
    Language("cpp", (".cpp", ".cc", ".cxx"), ["{exe}"],
             ["g++", "-std=c++17", "-O2", "-pipe", "-DLOCAL", "{src}", "-o", "{exe}"], note="GNU C++17"),
    Language("c", (".c",), ["{exe}"], ["gcc", "-std=c11", "-O2", "{src}", "-o", "{exe}", "-lm"], note="GNU C11"),
    Language("python", (".py",), ["{python}", "-X", "utf8", "{src}"], note="current Python interpreter"),
    Language("pypy", (".pypy",), ["pypy3", "{src}"], note="PyPy 3"),
    Language("java", (".java",), ["java", "-Xss256m", "-cp", "{dir}", "{stem}"], ["javac", "-d", "{dir}", "{src}"],
             output="{dir}", note="class name must match the file name"),
    Language("kotlin", (".kt",), ["java", "-jar", "{dir}/{stem}.jar"],
             ["kotlinc", "{src}", "-include-runtime", "-d", "{dir}/{stem}.jar"], output="{dir}/{stem}.jar"),
    Language("rust", (".rs",), ["{exe}"], ["rustc", "-O", "--edition", "2021", "{src}", "-o", "{exe}"]),
    Language("go", (".go",), ["{exe}"], ["go", "build", "-o", "{exe}", "{src}"]),
    Language("javascript", (".js", ".mjs"), ["node", "{src}"], note="Node.js"),
    Language("csharp", (".cs",), ["dotnet", "{dir}/{stem}.dll"], [], note="build with dotnet beforehand"),
    # Compile-checked Python: useful for catching syntax errors as CE before running.
    Language("python-checked", (".pyc-check",), ["{python}", "{src}"], ["{python}", "-m", "py_compile", "{src}"],
             output="{src}", note="py_compile first, then run"),
]


class LanguageRegistry:
    def __init__(self, languages=None):
        self.languages = {l.name: l for l in (languages or DEFAULT_LANGUAGES)}

    @classmethod
    def with_overrides(cls, path=None):
        reg = cls()
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for name, spec in json.load(fh).items():
                    reg.languages[name] = Language(name, tuple(spec.get("extensions", [])), spec["run"],
                                                   spec.get("compile", []), spec.get("output", ""), spec.get("note", ""))
        return reg

    def get(self, name):
        if name not in self.languages:
            raise KeyError("unknown language %r (known: %s)" % (name, ", ".join(sorted(self.languages))))
        return self.languages[name]

    def detect(self, path):
        ext = os.path.splitext(path)[1].lower()
        for lang in self.languages.values():
            if ext in lang.extensions:
                return lang
        raise KeyError("cannot detect the language of %s; pass --lang" % path)


class CompileError(Exception):
    def __init__(self, message, log=""):
        super().__init__(message)
        self.log = log


def _fill(parts, values):
    return [p.format(**values) for p in parts]


class Program:
    """A source file prepared for execution (compiled once and cached by content hash)."""

    def __init__(self, source, language, build_root=None):
        self.source = os.path.abspath(source)
        self.language = language
        with open(self.source, "rb") as fh:
            digest = hashlib.sha256(fh.read() + language.name.encode() + json.dumps(language.compile).encode()).hexdigest()[:16]
        root = build_root or os.path.join(tempfile.gettempdir(), "cp-judge-build")
        self.build_dir = os.path.join(root, digest)
        stem = os.path.splitext(os.path.basename(self.source))[0]
        self.values = {"src": self.source, "dir": self.build_dir, "stem": stem, "python": sys.executable,
                       "exe": os.path.join(self.build_dir, stem + EXE)}
        self.compile_log = ""
        self.compile_seconds = 0.0

    def compile(self, timeout=60):
        if not self.language.needs_compile():
            return False
        os.makedirs(self.build_dir, exist_ok=True)
        marker = os.path.join(self.build_dir, ".ok")
        if os.path.exists(marker):
            return False                    # cached
        import time
        t0 = time.perf_counter()
        cmd = _fill(self.language.compile, self.values)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=self.build_dir)
        except FileNotFoundError:
            raise CompileError("compiler not found: %s" % cmd[0])
        except subprocess.TimeoutExpired:
            raise CompileError("compilation timed out after %ds" % timeout)
        self.compile_seconds = time.perf_counter() - t0
        self.compile_log = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            raise CompileError("compilation failed (exit %d)" % r.returncode, self.compile_log)
        with open(marker, "w") as fh:
            fh.write("ok")
        return True

    def command(self, extra_args=()):
        return _fill(self.language.run, self.values) + list(extra_args)
