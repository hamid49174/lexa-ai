"""Regressionstests aus dem Gesamt-Scan — Bereich C (KI-Kern-Entrümpelung)."""
import backend.ai_engine as ai_engine


def test_quality_marker_tuples_have_no_exact_duplicates():
    """Scan-Fix C: Quality-Mode-Marker-Tupel enthielten 48 exakte Duplikate (no-op Ballast).
    Dieser Guard verhindert, dass exakte Wort-Doppelungen wieder eingeschleppt werden."""
    offenders = []
    for name in dir(ai_engine):
        if "MARKER" not in name or not name.isupper():
            continue
        val = getattr(ai_engine, name)
        if isinstance(val, tuple) and val and all(isinstance(x, str) for x in val):
            if len(val) != len(set(val)):
                dups = sorted({x for x in val if val.count(x) > 1})
                offenders.append((name, dups))
    assert not offenders, f"Marker-Tupel mit exakten Duplikaten: {offenders}"
