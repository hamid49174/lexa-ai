from pathlib import Path
import re


FRONTEND_SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


BLOCKERS = {
    "unsafe-inline": re.compile(r"unsafe-inline"),
    "style tag": re.compile(r"<style\b", re.IGNORECASE),
    "inline style attribute": re.compile(r"\sstyle\s*=", re.IGNORECASE),
    "inline event handler": re.compile(r"<[^>\n]*\s+on[a-z]{2,}\s*=", re.IGNORECASE),
    "direct style write": re.compile(r"\.style\b|cssText|setAttribute\([^)]*['\"]style['\"]", re.IGNORECASE),
    "eval": re.compile(r"\beval\s*\(", re.IGNORECASE),
    "new Function": re.compile(r"\bnew\s+Function\s*\(", re.IGNORECASE),
    "script injection": re.compile(r"createElement\(\s*['\"]script['\"]\s*\)|appendChild\([^)]*\bscript\b", re.IGNORECASE),
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


def test_index_csp_has_electron_defense_in_depth_directives():
    index_html = FRONTEND_SRC / "index.html"
    text = index_html.read_text(encoding="utf-8")
    match = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', text)
    assert match, "index.html must define a Content-Security-Policy meta tag"
    csp = match.group(1)
    for directive in [
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "img-src 'self' data: blob: http: https:",
    ]:
        assert directive in csp, f"CSP missing directive: {directive}"
