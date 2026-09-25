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
