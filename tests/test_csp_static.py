from pathlib import Path
import re
import subprocess


FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_SRC = FRONTEND_ROOT / "src"
IGNORED_EXTERNAL_DIRS = {"vendor"}


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
        if any(part in IGNORED_EXTERNAL_DIRS for part in path.relative_to(FRONTEND_SRC).parts):
            continue
        if path.suffix.lower() not in {".html", ".js", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pattern in BLOCKERS.items():
                if pattern.search(line):
                    rel = path.relative_to(FRONTEND_SRC.parents[1])
                    findings.append(f"{rel}:{line_no}: {label}: {line.strip()}")

    assert not findings, "CSP/static inline-style blockers found:\n" + "\n".join(findings)


def test_index_vendor_assets_are_bundled_and_unignored():
    index_html = FRONTEND_SRC / "index.html"
    text = index_html.read_text(encoding="utf-8")
    expected_assets = [
        FRONTEND_SRC / "vendor" / "three.min.js",
        FRONTEND_SRC / "vendor" / "simplex-noise.js",
    ]
    for asset in expected_assets:
        rel = asset.relative_to(FRONTEND_ROOT.parents[0])
        assert f"./vendor/{asset.name}" in text
        assert asset.exists(), f"Bundled vendor asset missing: {asset}"
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(rel)],
            cwd=FRONTEND_ROOT.parents[0],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert result.returncode != 0, f"Bundled vendor asset is still ignored: {rel}"


def test_bundled_vendor_assets_are_dependency_tracked():
    package = (FRONTEND_ROOT / "package.json").read_text(encoding="utf-8")
    sync_script = FRONTEND_ROOT / "scripts" / "sync-vendor.cjs"
    text = sync_script.read_text(encoding="utf-8")

    assert '"three": "0.128.0"' in package
    assert '"simplex-noise": "2.4.0"' in package
    assert '"check-vendor": "node scripts/sync-vendor.cjs --check"' in package
    assert '"sync-vendor": "node scripts/sync-vendor.cjs"' in package
    assert "node_modules" in text
    assert "three.min.js" in text
    assert "simplex-noise.js" in text


def test_index_csp_has_electron_defense_in_depth_directives():
    index_html = FRONTEND_SRC / "index.html"
    text = index_html.read_text(encoding="utf-8")
    match = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', text)
    assert match, "index.html must define a Content-Security-Policy meta tag"
    csp = match.group(1)
    for directive in [
        "object-src 'none'",
        "base-uri 'self'",
        "img-src 'self' data: blob: http: https:",
    ]:
        assert directive in csp, f"CSP missing directive: {directive}"
    assert "frame-ancestors" not in csp, "frame-ancestors must be sent as a header; Chromium ignores it in meta CSP"


def test_electron_main_sets_frame_ancestors_as_header():
    main_js = (FRONTEND_ROOT / "main.js").read_text(encoding="utf-8")
    assert "RENDERER_CSP_HEADER" in main_js
    assert "frame-ancestors 'none'" in main_js
    assert "ses.webRequest.onHeadersReceived" in main_js
    assert 'responseHeaders["Content-Security-Policy"] = [RENDERER_CSP_HEADER]' in main_js
