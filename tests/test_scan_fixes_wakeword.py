"""Regressionstests aus dem Gesamt-Scan — Bereich D (Wakeword)."""
import voice.wakeword_engines as we


class _FakeHandle:
    def __init__(self):
        self.deleted = False

    def delete(self):
        self.deleted = True


def test_porcupine_close_releases_and_is_restart_safe():
    # Scan-Fix D: Porcupine-Handle (native C-Ressourcen) wurde nie freigegeben
    # und die Engine war nach close nicht neustart-faehig.
    eng = we.PorcupineWakeWordEngine()
    handle = _FakeHandle()
    eng._handle = handle
    eng._load_attempted = True

    eng.close()

    assert handle.deleted is True
    assert eng._handle is None
    assert eng._load_attempted is False   # ensure_ready() darf neu laden
    # ohne Handle muss close() ein sicheres No-Op sein
    eng.close()


def test_porcupine_close_swallows_delete_errors():
    eng = we.PorcupineWakeWordEngine()

    class _BadHandle:
        def delete(self):
            raise RuntimeError("native crash")

    eng._handle = _BadHandle()
    eng.close()  # darf nicht werfen
    assert eng._handle is None
