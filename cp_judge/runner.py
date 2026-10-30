"""Run a command on an input with time, memory and output limits, measuring CPU time and peak memory.

Measurement backends: Windows (GetProcessTimes / GetProcessMemoryInfo through ctypes) and Linux (/proc).
On other systems only wall time is measured. A monitor thread samples memory and kills the process when the
memory limit is exceeded; a wall-clock deadline kills processes that sleep or block.
"""
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

IS_WINDOWS = os.name == "nt"


@dataclass
class RunResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    wall: float
    cpu: float = None          # seconds, None when unavailable
    memory_kb: int = None      # peak resident memory, None when unavailable
    timed_out: bool = False
    memory_exceeded: bool = False
    output_exceeded: bool = False

    @property
    def time(self):
        return self.cpu if self.cpu is not None else self.wall


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4

    def _handle(proc):
        return wintypes.HANDLE(int(proc._handle))

    def _peak_kb(proc):
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if _k32.K32GetProcessMemoryInfo(_handle(proc), ctypes.byref(pmc), pmc.cb):
            return max(pmc.PeakWorkingSetSize, pmc.PeakPagefileUsage) // 1024
        return None

    def _cpu_seconds(proc):
        t = [wintypes.FILETIME() for _ in range(4)]
        if _k32.GetProcessTimes(_handle(proc), *[ctypes.byref(x) for x in t]):
            to_s = lambda ft: ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7
            return to_s(t[2]) + to_s(t[3])
        return None
else:
    def _read_proc(pid, key):
        try:
            with open("/proc/%d/status" % pid) as fh:
                for line in fh:
                    if line.startswith(key):
                        return int(line.split()[1])
        except (OSError, ValueError, IndexError):
            return None
        return None

    def _peak_kb(proc):
        return _read_proc(proc.pid, "VmHWM:")

    def _cpu_seconds(proc):
        try:
            with open("/proc/%d/stat" % proc.pid) as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
            return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError, IndexError):
            return None


def run(cmd, stdin_data=b"", time_limit=2.0, memory_limit_mb=256, output_limit_mb=64, cwd=None, env=None,
        wall_factor=2.5, poll=0.005):
    """Execute cmd and return a RunResult. time_limit applies to CPU time when measurable."""
    kwargs = {}
    if not IS_WINDOWS and memory_limit_mb:
        def _limits():
            import resource
            soft = int(memory_limit_mb * 1024 * 1024 * 1.25)    # address space is larger than RSS
            try:
                resource.setrlimit(resource.RLIMIT_AS, (soft, soft))
            except (ValueError, OSError):
                pass
        kwargs["preexec_fn"] = _limits
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                            env=env, **kwargs)
    state = {"peak": None, "mle": False, "done": False, "cpu": None}
    limit_kb = memory_limit_mb * 1024 if memory_limit_mb else None

    def monitor():
        while not state["done"]:
            kb = _peak_kb(proc)
            if kb is not None:
                state["peak"] = max(state["peak"] or 0, kb)
                if limit_kb and kb > limit_kb:
                    state["mle"] = True
                    proc.kill()
                    return
            c = _cpu_seconds(proc)
            if c is not None:
                state["cpu"] = c
                if c > time_limit * 1.05 + 0.05:
                    proc.kill()
                    return
            time.sleep(poll)

    mon = threading.Thread(target=monitor, daemon=True)
    mon.start()
    timed_out = False
    try:
        out, err = proc.communicate(stdin_data, timeout=time_limit * wall_factor + 0.5)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        out, err = proc.communicate()
    wall = time.perf_counter() - t0
    if IS_WINDOWS:                       # the handle stays valid until the Popen object is collected
        state["peak"] = max(state["peak"] or 0, _peak_kb(proc) or 0) or None
        state["cpu"] = _cpu_seconds(proc) or state["cpu"]
    state["done"] = True
    mon.join(0.2)
    cpu = state["cpu"]
    if cpu is not None and cpu > time_limit:
        timed_out = True
    elif cpu is None and wall > time_limit:
        timed_out = True
    out_limit = output_limit_mb * 1024 * 1024 if output_limit_mb else None
    return RunResult(proc.returncode, out[:out_limit] if out_limit else out, err[-20000:], wall, cpu, state["peak"],
                     timed_out, state["mle"], bool(out_limit and len(out) > out_limit))


def run_interactive(sol_cmd, interactor_cmd, time_limit=2.0, cwd=None, wall_factor=2.5):
    """Connect solution stdout -> interactor stdin and interactor stdout -> solution stdin.

    Returns (solution RunResult, interactor returncode, interactor stderr)."""
    t0 = time.perf_counter()
    inter = subprocess.Popen(interactor_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    sol = subprocess.Popen(sol_cmd, stdin=inter.stdout, stdout=inter.stdin, stderr=subprocess.PIPE, cwd=cwd)
    inter.stdout.close()           # the two processes now own the pipe ends
    inter.stdin.close()
    inter.stdout = inter.stdin = None   # so communicate() only collects stderr
    deadline = time_limit * wall_factor + 0.5
    timed_out = False
    try:
        sol_err = sol.communicate(timeout=deadline)[1]
    except subprocess.TimeoutExpired:
        timed_out = True
        sol.kill()
        sol_err = sol.communicate()[1]
    try:
        inter_err = inter.communicate(timeout=max(0.5, deadline - (time.perf_counter() - t0)))[1]
    except subprocess.TimeoutExpired:
        inter.kill()
        inter_err = inter.communicate()[1] + b"\ninteractor timed out"
    wall = time.perf_counter() - t0
    cpu = _cpu_seconds(sol) if IS_WINDOWS else None
    if (cpu if cpu is not None else wall) > time_limit:
        timed_out = True
    res = RunResult(sol.returncode, b"", sol_err[-20000:], wall, cpu, _peak_kb(sol) if IS_WINDOWS else None, timed_out)
    return res, inter.returncode, (inter_err or b"").decode("utf-8", "replace").strip()
