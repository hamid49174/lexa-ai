"""Tests fuer die zitierte, fakten-gepruefte Synthese (Phase 49 #3).

Deckt ab: SourceRegistry (Dedup + globale [n]-IDs), Quellen-Extraktion aus Tool-Ergebnissen,
Citation-Validierung (kein Halluzinieren von [n]), Synthese-Prompt mit Quellenblock,
claim-level Judge und den End-to-End sources-Event-Fluss. Alles mit injizierten Fakes.
"""
import asyncio

from backend.orchestrator.core import (
    _PLANNER_PERSONA,
    _SYNTH_PERSONA,
    _extract_sources,
    _synth_user_prompt,
    _validate_citations,
    run_orchestration,
    synthesize_results,
)
from backend.orchestrator.sources import SourceRegistry
from backend.orchestrator.verify import judge_result


# ── SourceRegistry ─────────────────────────────────────────────────────────
def test_source_registry_dedups_and_numbers():
    reg = SourceRegistry()
    reg.register([
        {"title": "A", "url": "https://example.com/a"},
        {"title": "B", "url": "https://example.com/b/"},      # trailing slash
    ])
    reg.register([
        {"title": "A wieder", "url": "https://example.com/a#frag"},  # Fragment -> Dup von A
        {"title": "C", "url": "https://example.com/c"},
    ])
    items = reg.as_list()
    assert reg.count() == 3
    assert [it["id"] for it in items] == [1, 2, 3]
    assert [it["title"] for it in items] == ["A", "B", "C"]
    block = reg.numbered_block()
    assert "[1] A — https://example.com/a" in block
    assert "[3] C" in block


def test_source_registry_falls_back_to_title_when_no_url():
    reg = SourceRegistry()
    reg.register([{"title": "Nur Titel", "url": ""}, {"title": "Nur Titel", "url": ""}])
    assert reg.count() == 1  # gleicher Titel -> dedup


# ── _extract_sources ───────────────────────────────────────────────────────
def test_extract_sources_from_web_search_result():
    res = {"success": True, "data": {"query": "x", "sources": [
        {"title": "T1", "url": "https://a.test", "snippet": "s1"},
        {"link": "https://b.test", "content": "s2"},  # link/content-Variante
        {"foo": "bar"},  # weder url noch title -> ignoriert
    ]}}
    out = _extract_sources("web_search", res)
    assert len(out) == 2
    assert out[0]["url"] == "https://a.test"
    assert out[1]["url"] == "https://b.test"


def test_extract_sources_ignores_failures_and_non_sources():
    assert _extract_sources("web_search", {"success": False, "error": "x"}) == []
    assert _extract_sources("memory_search", {"success": True, "data": "nur text"}) == []
    assert _extract_sources("web_search", {"success": True, "data": {"sources": []}}) == []


# ── _validate_citations ────────────────────────────────────────────────────
def test_validate_citations_strips_invalid_ids():
    text = "Fakt A [1]. Fakt B [3]. Erfunden [9]."
    out = _validate_citations(text, max_id=3)
    assert "[1]" in out and "[3]" in out
    assert "[9]" not in out


def test_validate_citations_removes_all_when_no_sources():
    out = _validate_citations("Aussage ohne Beleg [1][2].", max_id=0)
    assert "[1]" not in out and "[2]" not in out
    assert "Aussage ohne Beleg" in out


def test_synth_prompt_includes_sources_block_and_rules():
    prompt = _synth_user_prompt(
        "Frage",
        [{"agent_id": "a1", "role": "research", "objective": "X", "summary": "Befund", "status": "done"}],
        sources_block="[1] Titel — https://a.test",
    )
    assert "QUELLEN" in prompt
    assert "[1] Titel" in prompt
    assert "[n]" in prompt  # Zitier-Regel vorhanden


# ── synthesize_results: Citation-Validierung greift ─────────────────────────
def test_synthesize_results_validates_citations():
    def fake_chat(messages, system_extra, tools_override):
        # Modell zitiert eine nicht existente Quelle [5]
        return {"type": "text", "content": "Antwort mit [1] und erfundenem [5]."}

    out = asyncio.run(synthesize_results(
        "Frage",
        [{"agent_id": "a1", "role": "research", "objective": "X", "summary": "B", "status": "done"}],
        chat_fn=fake_chat,
        sources_block="[1] Titel — https://a.test",
        max_source_id=1,
    ))
    assert "[1]" in out
    assert "[5]" not in out


# ── claim-level Judge ──────────────────────────────────────────────────────
def test_judge_result_returns_claims_and_unsupported_count():
    def fake_chat(messages, system_extra, tools_override):
        return {"type": "text", "content": (
            '{"score":0.4,"passed":false,"reasons":["x"],'
            '"claims":[{"claim":"belegt","source_ids":[1],"supported":true},'
            '{"claim":"erfunden","source_ids":[9],"supported":true}],'
            '"unsupported_count":1}'
        )}

    verdict = asyncio.run(judge_result(
        "Frage",
        {"agent_id": "a1", "role": "research", "objective": "X", "summary": "S", "status": "done"},
        chat_fn=fake_chat,
        sources_block="[1] Titel — https://a.test",
        max_source_id=1,
    ))
    assert verdict["unsupported_count"] == 1
    assert len(verdict["claims"]) == 2
    # erfundene source_id 9 (> max 1) wird gefiltert -> claim gilt als nicht belegt
    bad = [c for c in verdict["claims"] if c["claim"] == "erfunden"][0]
    assert bad["source_ids"] == []
    assert bad["supported"] is False
    # belegter claim referenziert gueltige Quelle
    good = [c for c in verdict["claims"] if c["claim"] == "belegt"][0]
    assert good["source_ids"] == [1] and good["supported"] is True


def test_judge_result_without_sources_has_empty_claims():
    def fake_chat(messages, system_extra, tools_override):
        return {"type": "text", "content": '{"score":0.9,"passed":true,"reasons":[]}'}

    verdict = asyncio.run(judge_result(
        "Frage",
        {"agent_id": "a1", "role": "research", "objective": "X", "summary": "S", "status": "done"},
        chat_fn=fake_chat,
    ))
    assert verdict["claims"] == []
    assert verdict["unsupported_count"] == 0


# ── End-to-End: sources-Event + done.run.sources ───────────────────────────
def _collect(agen):
    async def _run():
        out = []
        async for ev in agen:
            out.append(ev)
        return out

    return asyncio.run(_run())


def test_run_orchestration_emits_sources_event():
    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"research","objective":"Finde X"}]'}
        if system_extra == _SYNTH_PERSONA:
            # Quellenblock muss im Synthese-Prompt ankommen
            joined = " ".join(str(m.get("content", "")) for m in messages)
            assert "QUELLEN" in joined and "Beispiel A" in joined
            return {"type": "text", "content": "Finale Antwort [1]."}
        has_result = any("[TOOL-ERGEBNIS" in str(m.get("content", "")) for m in messages)
        if has_result:
            return {"type": "text", "content": "Sub-Agent fertig."}
        return {"type": "tool_call", "tool_calls": [{"function": {"name": "web_search", "arguments": '{"query":"x"}'}}], "content": ""}

    def fake_exec(name, params):
        return {"success": True, "data": {"query": "x", "sources": [
            {"title": "Beispiel A", "url": "https://a.test", "snippet": "s"},
            {"title": "Beispiel B", "url": "https://b.test", "snippet": "s"},
        ]}}

    # mode=fast: keine Verifikation, fokussiert auf sources-Fluss
    events = _collect(run_orchestration("Recherche X", mode="fast", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    types = [e["type"] for e in events]
    assert "sources" in types
    src_event = [e for e in events if e["type"] == "sources"][0]
    assert len(src_event["sources"]) == 2
    assert src_event["sources"][0]["id"] == 1

    done = events[-1]["run"]
    assert len(done["sources"]) == 2
    assert "[1]" in done["answer"]  # gueltiges Zitat bleibt erhalten


def test_run_orchestration_no_sources_no_event():
    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"knowledge","objective":"lokal"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "Antwort ohne Quellen."}
        return {"type": "text", "content": "Direkt fertig ohne Tool."}

    def fake_exec(name, params):
        return {"success": True, "data": "x"}

    events = _collect(run_orchestration("lokale Frage", mode="fast", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    assert "sources" not in [e["type"] for e in events]
    assert events[-1]["run"]["sources"] == []
