"""Console, JSON and HTML renderings of a JudgeReport."""
import html
import json
import os
import sys
from dataclasses import asdict

from .judge import VERDICTS

COLORS = {"AC": "32", "OK": "36", "WA": "31", "PE": "33", "TLE": "35", "MLE": "35", "OLE": "35", "RE": "31",
          "CE": "31", "IE": "31", "SKIP": "90"}


def _use_color(stream):
    return hasattr(stream, "isatty") and stream.isatty() and os.environ.get("NO_COLOR") is None


def color(v, enabled):
    return "\033[%sm%s\033[0m" % (COLORS.get(v, "0"), v) if enabled else v


def fmt_mem(kb):
    return "-" if not kb else ("%.1f MB" % (kb / 1024))


def line_for(r, enabled=False):
    return "%-14s %-5s %6.3fs %9s  %s" % (r.name[:14], color(r.verdict, enabled), r.time, fmt_mem(r.memory_kb), r.message[:90])


def text(report, stream=None):
    stream = stream or sys.stdout
    c = _use_color(stream)
    lines = []
    if report.verdict == "CE":
        lines += ["%s  %s" % (color("CE", c), VERDICTS["CE"]), report.compile_log[:3000]]
        return "\n".join(lines) + "\n"
    lines += [line_for(r, c) for r in report.results]
    lines.append("-" * 60)
    pts = " | score %.4g/%.4g" % (report.score, report.max_score) if any(r.group for r in report.results) or \
        len({r.max_points for r in report.results}) > 1 else ""
    lines.append("%s  %s | %d/%d passed | max %.3fs, %s%s" % (
        color(report.verdict, c), VERDICTS.get(report.verdict, ""), report.passed, len(report.results),
        report.max_time, fmt_mem(report.max_memory_kb), pts))
    return "\n".join(lines) + "\n"


def to_json(report):
    d = asdict(report)
    d.update({"passed": report.passed, "score": report.score, "max_score": report.max_score,
              "max_time": report.max_time, "max_memory_kb": report.max_memory_kb})
    return json.dumps(d, indent=2)


def to_html(report, cases=None):
    """Standalone HTML report; failing tests show input, expected and actual output side by side."""
    by_name = {c.name: c for c in (cases or [])}
    esc = html.escape
    rows = []
    for r in report.results:
        detail = ""
        if r.verdict not in ("AC", "OK", "SKIP") and r.name in by_name:
            c = by_name[r.name]
            detail = ("<tr class='d'><td colspan='5'><div class='cols'><div><b>Input</b><pre>%s</pre></div>"
                      "<div><b>Expected</b><pre>%s</pre></div><div><b>Output</b><pre>%s</pre></div></div>%s</td></tr>") % (
                esc(c.input[:3000]), esc((c.answer or "")[:3000]), esc(r.output[:3000]),
                "<pre class='err'>%s</pre>" % esc(r.stderr) if r.stderr.strip() else "")
        rows.append("<tr><td>%s</td><td class='v %s'>%s</td><td>%.3f s</td><td>%s</td><td>%s</td></tr>%s" % (
            esc(r.name), r.verdict, r.verdict, r.time, fmt_mem(r.memory_kb), esc(r.message), detail))
    ce = "<pre class='err'>%s</pre>" % esc(report.compile_log) if report.verdict == "CE" else ""
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>%s - %s</title><style>
:root{--bg:#fff;--fg:#1b1b1f;--line:#e3e3e8;--muted:#6b6b72}@media(prefers-color-scheme:dark){:root{--bg:#141417;--fg:#ececf0;--line:#2d2d33;--muted:#9a9aa3}}
body{font:14px system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1100px;margin:auto;padding:16px}
table{border-collapse:collapse;width:100%%}td,th{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
.v{font-weight:700}.AC{color:#2e9d4b}.OK{color:#2a8fb0}.WA,.RE,.CE,.IE{color:#d23b3b}.TLE,.MLE,.OLE{color:#9b4fd0}.PE{color:#c98a12}.SKIP{color:var(--muted)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:8px}pre{background:rgba(127,127,127,.12);padding:6px;overflow:auto;max-height:260px;margin:4px 0}
.err{color:#d23b3b}h1{font-size:20px}</style></head><body>
<h1>%s: <span class="%s">%s</span></h1><p>%s &middot; %d/%d passed &middot; TL %.3g s &middot; ML %d MB &middot; max %.3f s, %s</p>%s
<table><tr><th>Test</th><th>Verdict</th><th>Time</th><th>Memory</th><th>Message</th></tr>%s</table></body></html>
""" % (esc(os.path.basename(report.source)), report.verdict, esc(os.path.basename(report.source)), report.verdict,
       VERDICTS.get(report.verdict, ""), report.language, report.passed, len(report.results), report.time_limit,
       report.memory_limit_mb, report.max_time, fmt_mem(report.max_memory_kb), ce, "".join(rows))
