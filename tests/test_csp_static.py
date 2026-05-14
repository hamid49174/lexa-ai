from pathlib import Path
import re


FRONTEND_SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


BLOCKERS = {
    "unsafe-inline": re.compile(r"unsafe-inline"),
    "style tag": re.compile(r"<style\b", re.IGNORECASE),
    "inline style attribute": re.compile(r"\sstyle\s*=", re.IGNORECASE),
    "inline event handler": re.compile(r"\son[a-z]+\s*=", re.IGNORECASE),
    "direct style write": re.compile(r"\.style\b|cssText|setAttribute\([^)]*['\"]style['\"]", re.IGNORECASE),
}


def test_frontend_has_no_inline_style_or_csp_bypass_regressions():
    findings = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix.lower() not in {".html", ".js", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pattern in BLOCKERS.items():
                if pattern.search(line):
                    rel = path.relative_to(FRONTEND_SRC.parents[1])
                    findings.append(f"{rel}:{line_no}: {label}: {line.strip()}")

    assert not findings, "CSP/static inline-style blockers found:\n" + "\n".join(findings)
