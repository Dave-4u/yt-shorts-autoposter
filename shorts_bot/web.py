"""Clip Studio: a small local web UI for the pipeline (stdlib only).

    python -m shorts_bot web            # http://127.0.0.1:8765
    python -m shorts_bot web --port 9000

It serves docs/index.html (the same page as the GitHub Pages demo) plus a tiny
JSON API, so analysis uses your real config (Groq/Gemini key if set, else the
heuristic) and "Render selected as MP4" runs the real ffmpeg renderer on a
synthetic test source. Nothing is ever uploaded from the web UI.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from shorts_bot.analyze import ClipCandidate, analyze_clips
from shorts_bot.config import CAPTION_STYLES, Config
from shorts_bot.fetch import TranscriptSegment

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
_render_lock = threading.Lock()


def _engine_name(cfg: Config) -> str:
    resolved = cfg.resolve_llm() if cfg.has_llm else None
    return f"{resolved[0]} ({resolved[2]})" if resolved else "offline heuristic"


def _segments(data) -> list[TranscriptSegment]:
    out = []
    for d in data or []:
        text = str(d.get("text", "")).strip()
        if text:
            out.append(TranscriptSegment(start=float(d["start"]), duration=float(d["duration"]), text=text))
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "ClipStudio/1.0"

    def log_message(self, fmt, *args):  # quieter console
        log.debug(fmt, *args)

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._json(404, {"error": "not found"})
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("content-length") or 0)
        if n > 5_000_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):  # noqa: N802
        path = unquote(urlparse(self.path).path)
        cfg = Config.from_env()
        if path == "/api/health":
            return self._json(200, {"ok": True, "engine": _engine_name(cfg), "styles": list(CAPTION_STYLES)})
        if path.startswith("/out/"):
            target = (cfg.output_dir / path[5:]).resolve()
            if cfg.output_dir.resolve() not in target.parents:
                return self._json(403, {"error": "forbidden"})
            return self._file(target)
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (DOCS / rel).resolve()
        if DOCS.resolve() not in target.parents and target != DOCS.resolve():
            return self._json(403, {"error": "forbidden"})
        return self._file(target)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            data = self._body()
        except Exception as e:  # bad JSON
            return self._json(400, {"error": str(e)})
        cfg = Config.from_env()
        cfg.dry_run = True  # the web UI never uploads
        if path == "/api/analyze":
            segs = _segments(data.get("segments"))
            if not segs:
                return self._json(400, {"error": "no transcript lines"})
            cfg.min_clip_seconds = int(data.get("minClip", cfg.min_clip_seconds))
            cfg.max_clip_seconds = int(data.get("maxClip", cfg.max_clip_seconds))
            cfg.max_shorts = max(1, min(10, int(data.get("maxShorts", 5))))
            clips = analyze_clips(segs, cfg, source_duration=segs[-1].end)
            return self._json(200, {"engine": _engine_name(cfg), "clips": [c.to_dict() for c in clips]})
        if path == "/api/render":
            from shorts_bot.render import make_synthetic_source, render_clip

            c = data.get("clip") or {}
            try:
                clip = ClipCandidate(**{k: c[k] for k in ("start", "end", "title", "hook", "score")}, text=c.get("text", ""))
            except (KeyError, TypeError):
                return self._json(400, {"error": "clip needs start, end, title, hook, score"})
            if data.get("caption_style") in CAPTION_STYLES:
                cfg.caption_style = data["caption_style"]
            segs = _segments(data.get("segments"))
            span = max(clip.end, 30.0) + 2
            if not _render_lock.acquire(blocking=False):
                return self._json(429, {"error": "already rendering one, give it a minute"})
            try:
                # shift the clip onto a short synthetic source so renders stay quick
                offset = clip.start
                local = ClipCandidate(start=0.0, end=round(clip.end - offset, 2), title=clip.title, hook=clip.hook, score=clip.score, text=clip.text)
                shifted = [TranscriptSegment(start=s.start - offset, duration=s.duration, text=s.text) for s in segs if s.end > offset and s.start < clip.end]
                src = make_synthetic_source(cfg, duration=60.0)
                r = render_clip(cfg, src, local, shifted, index=int(offset), video_id="studio")
            except Exception as e:
                return self._json(500, {"error": f"render failed: {e}"})
            finally:
                _render_lock.release()
            rel = Path(r.video_path).resolve().relative_to(cfg.output_dir.resolve())
            return self._json(200, {"url": f"/out/{rel.as_posix()}", "span": span})
        return self._json(404, {"error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Clip Studio running on http://{host}:{port}  (Ctrl+C to stop; nothing is uploaded from here)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
