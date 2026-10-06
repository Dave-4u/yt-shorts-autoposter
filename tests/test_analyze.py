"""Offline unit tests — no API keys required."""

from pathlib import Path

from shorts_bot.analyze import analyze_heuristic, heuristic_score
from shorts_bot.config import Config
from shorts_bot.fetch import load_transcript_json


SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "sample_transcript.json"


def test_heuristic_score_prefers_hooks():
    low = heuristic_score("the cat sat on the mat quietly today", 30)
    high = heuristic_score("Why does nobody talk about this secret tip? Crazy!", 30)
    assert high > low


def test_analyze_sample_transcript():
    cfg = Config(max_shorts=5, min_clip_seconds=15, max_clip_seconds=59)
    segs = load_transcript_json(SAMPLE)
    clips = analyze_heuristic(segs, cfg, source_duration=segs[-1].end)
    assert 1 <= len(clips) <= 5
    for c in clips:
        assert cfg.min_clip_seconds - 0.5 <= c.duration <= cfg.max_clip_seconds + 2
        assert c.title
        assert c.end > c.start


def test_resolve_llm_prefers_groq():
    cfg = Config(
        groq_api_key="gsk_test",
        gemini_api_key="gem_test",
        openai_api_key="sk_test",
        anthropic_api_key="ant_test",
    )
    assert cfg.resolve_llm()[0] == "groq"
    assert cfg.has_llm is True


def test_resolve_llm_falls_through_to_gemini():
    cfg = Config(gemini_api_key="gem_test", openai_api_key="sk_test")
    assert cfg.resolve_llm()[0] == "gemini"


def test_resolve_llm_none_without_keys():
    cfg = Config()
    assert cfg.resolve_llm() is None
    assert cfg.has_llm is False


def test_default_llm_ids_not_retired():
    cfg = Config()
    assert cfg.groq_model not in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant")  # Groq retired 2026-08-16
    assert not cfg.gemini_model.startswith("gemini-2.0")                              # shut down 2026-06-01


def test_gpt_oss_gets_low_reasoning(monkeypatch):
    import sys, types
    from shorts_bot import analyze
    seen = {}

    class Fake:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, **kw):
            seen.update(kw)
            msg = types.SimpleNamespace(content="[]")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Fake))
    analyze._chat_completions(api_key="k", base_url="u", model="openai/gpt-oss-120b", prompt="p")
    assert seen["extra_body"] == {"reasoning_effort": "low"}
    seen.clear()
    analyze._chat_completions(api_key="k", base_url="u", model="gemini-2.5-flash", prompt="p")
    assert "extra_body" not in seen
