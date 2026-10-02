"""Smoke test for the Clip Studio local server (no network, no ffmpeg)."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from shorts_bot.web import Handler

ROOT = Path(__file__).resolve().parent.parent


def _call(base, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read()


def test_health_index_and_analyze(monkeypatch):
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(k, "")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        status, body = _call(base, "/api/health")
        assert status == 200 and json.loads(body)["engine"] == "offline heuristic"
        status, body = _call(base, "/")
        assert b"Clip Studio" in body
        segs = json.loads((ROOT / "samples" / "sample_transcript.json").read_text())
        status, body = _call(base, "/api/analyze", {"segments": segs, "maxShorts": 3})
        clips = json.loads(body)["clips"]
        assert status == 200 and 1 <= len(clips) <= 3
        assert all(15 <= c["end"] - c["start"] <= 61 for c in clips)
    finally:
        srv.shutdown()
