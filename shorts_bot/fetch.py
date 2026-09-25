"""Download source video and extract transcript."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from shorts_bot.config import Config

log = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    start: float
    duration: float
    text: str

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class FetchedVideo:
    video_id: str
    url: str
    title: str
    video_path: Path
    transcript: List[TranscriptSegment] = field(default_factory=list)
    duration: float = 0.0
    meta_path: Optional[Path] = None


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video id from URL or bare id."""
    s = url_or_id.strip()
    if re.fullmatch(r"[\w-]{11}", s):
        return s
    patterns = [
        r"(?:v=|/shorts/|youtu\.be/|/embed/|/v/)([\w-]{11})",
        r"youtube\.com/watch\?.*?v=([\w-]{11})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            return m.group(1)
    raise ValueError(f"Could not parse YouTube video id from: {url_or_id}")


def download_video(cfg: Config, url: str, *, force: bool = False) -> Path:
    """Download best mp4 via yt-dlp into downloads_dir."""
    cfg.ensure_dirs()
    vid = extract_video_id(url)
    out_tmpl = str(cfg.downloads_dir / f"{vid}.%(ext)s")
    final = cfg.downloads_dir / f"{vid}.mp4"
    if final.exists() and not force:
        log.info("Using cached download: %s", final)
        return final

    cmd = [
        "yt-dlp",
        "-f",
        "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_tmpl,
        "--no-playlist",
        "--write-info-json",
        "--newline",
        url if url.startswith("http") else f"https://www.youtube.com/watch?v={vid}",
    ]
    log.info("Downloading %s …", vid)
    subprocess.run(cmd, check=True)
    if not final.exists():
        # yt-dlp may have used another extension; find it
        matches = list(cfg.downloads_dir.glob(f"{vid}.*"))
        matches = [m for m in matches if m.suffix in {".mp4", ".mkv", ".webm"}]
        if not matches:
            raise FileNotFoundError(f"Download finished but no media found for {vid}")
        final = matches[0]
    return final


def fetch_transcript_youtube(video_id: str, languages: Optional[List[str]] = None) -> List[TranscriptSegment]:
    """Pull captions via youtube-transcript-api."""
    languages = languages or ["en", "en-US", "en-GB"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as e:
        raise RuntimeError("youtube-transcript-api not installed") from e

    try:
        # New API (1.x) uses instance methods
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=languages)
        segs = []
        for item in transcript:
            # FetchedTranscriptSnippet has .start, .duration, .text
            start = getattr(item, "start", None)
            duration = getattr(item, "duration", None)
            text = getattr(item, "text", None)
            if start is None and isinstance(item, dict):
                start = item.get("start", 0)
                duration = item.get("duration", 0)
                text = item.get("text", "")
            segs.append(
                TranscriptSegment(
                    start=float(start or 0),
                    duration=float(duration or 0),
                    text=str(text or "").replace("\n", " ").strip(),
                )
            )
        return [s for s in segs if s.text]
    except Exception as e:
        # Fallback to older list_transcripts style
        log.debug("New transcript API failed (%s); trying legacy", e)
        try:
            from youtube_transcript_api import YouTubeTranscriptApi as YTA

            listing = YTA.list_transcripts(video_id)
            t = listing.find_transcript(languages)
            raw = t.fetch()
            return [
                TranscriptSegment(
                    start=float(r["start"]),
                    duration=float(r["duration"]),
                    text=r["text"].replace("\n", " ").strip(),
                )
                for r in raw
                if r.get("text")
            ]
        except Exception as e2:
            log.warning("YouTube transcript unavailable for %s: %s", video_id, e2)
            return []


def whisper_transcribe(video_path: Path, model_size: str = "base") -> List[TranscriptSegment]:
    """Local whisper fallback (requires openai-whisper)."""
    try:
        import whisper
    except ImportError as e:
        raise RuntimeError(
            "No captions available and openai-whisper is not installed. "
            "Install with: pip install openai-whisper"
        ) from e

    log.info("Running Whisper (%s) on %s …", model_size, video_path.name)
    model = whisper.load_model(model_size)
    result = model.transcribe(str(video_path), verbose=False)
    segs: List[TranscriptSegment] = []
    for s in result.get("segments", []):
        segs.append(
            TranscriptSegment(
                start=float(s["start"]),
                duration=float(s["end"]) - float(s["start"]),
                text=s["text"].strip(),
            )
        )
    return segs


def probe_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    out = subprocess.check_output(cmd, text=True)
    return float(json.loads(out)["format"]["duration"])


def load_title(cfg: Config, video_id: str, fallback: str = "") -> str:
    info = cfg.downloads_dir / f"{video_id}.info.json"
    if info.exists():
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
            return data.get("title") or fallback or video_id
        except Exception:
            pass
    return fallback or video_id


def fetch_video(
    cfg: Config,
    url: str,
    *,
    skip_download: bool = False,
    use_whisper: bool = False,
) -> FetchedVideo:
    """Download (optional) + transcript pipeline."""
    cfg.ensure_dirs()
    video_id = extract_video_id(url)
    full_url = url if url.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"

    if skip_download:
        video_path = cfg.downloads_dir / f"{video_id}.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"skip_download set but {video_path} missing")
    else:
        video_path = download_video(cfg, full_url)

    transcript = fetch_transcript_youtube(video_id)
    if not transcript and use_whisper:
        transcript = whisper_transcribe(video_path)
    if not transcript:
        log.warning(
            "No transcript for %s — analyze will use heuristic windows on duration only.",
            video_id,
        )

    duration = probe_duration(video_path)
    title = load_title(cfg, video_id)

    # Persist transcript for reuse / dry-run
    tx_path = cfg.downloads_dir / f"{video_id}.transcript.json"
    tx_path.write_text(
        json.dumps(
            [{"start": s.start, "duration": s.duration, "text": s.text} for s in transcript],
            indent=2,
        ),
        encoding="utf-8",
    )

    return FetchedVideo(
        video_id=video_id,
        url=full_url,
        title=title,
        video_path=video_path,
        transcript=transcript,
        duration=duration,
        meta_path=tx_path,
    )


def load_transcript_json(path: Path) -> List[TranscriptSegment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        TranscriptSegment(start=float(d["start"]), duration=float(d["duration"]), text=d["text"])
        for d in data
    ]
