"""Cut vertical Shorts and burn-in TikTok-style captions with ffmpeg."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from shorts_bot.analyze import ClipCandidate
from shorts_bot.config import Config
from shorts_bot.fetch import TranscriptSegment

log = logging.getLogger(__name__)


@dataclass
class RenderedShort:
    clip: ClipCandidate
    video_path: Path
    ass_path: Optional[Path] = None


def _ass_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _chunk_words(text: str, max_words: int = 4) -> List[str]:
    words = text.split()
    if not words:
        return []
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def build_ass_for_clip(
    segments: Sequence[TranscriptSegment],
    clip: ClipCandidate,
    style: dict,
    out_path: Path,
) -> Path:
    """Write an ASS subtitle file with karaoke-ish word groups for the clip window."""
    header = f"""[Script Info]
Title: Shorts captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['fontname']},{style['fontsize']},{style['primary']},&H000000FF,{style['outline']},&H80000000,{style['bold']},0,0,0,100,100,0,0,1,{style['outline_width']},{style['shadow']},{style['alignment']},40,40,{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    relevant = [
        s
        for s in segments
        if s.end > clip.start and s.start < clip.end and s.text.strip()
    ]
    if not relevant and clip.text:
        # synthesize from clip.text evenly across duration
        chunks = _chunk_words(clip.text, 5)
        dur = clip.duration / max(len(chunks), 1)
        t = 0.0
        for ch in chunks:
            start_rel = t
            end_rel = min(t + dur, clip.duration)
            lines.append(
                f"Dialogue: 0,{_ass_timestamp(start_rel)},{_ass_timestamp(end_rel)},"
                f"Default,,0,0,0,,{ _escape_ass(ch) }\n"
            )
            t = end_rel
    else:
        for s in relevant:
            start_rel = max(0.0, s.start - clip.start)
            end_rel = min(clip.duration, s.end - clip.start)
            if end_rel <= start_rel:
                continue
            # split long segments into short punchy captions
            chunks = _chunk_words(s.text, 4)
            if len(chunks) <= 1:
                lines.append(
                    f"Dialogue: 0,{_ass_timestamp(start_rel)},{_ass_timestamp(end_rel)},"
                    f"Default,,0,0,0,,{_escape_ass(s.text.upper() if style.get('bold') else s.text)}\n"
                )
            else:
                piece = (end_rel - start_rel) / len(chunks)
                for i, ch in enumerate(chunks):
                    a = start_rel + i * piece
                    b = start_rel + (i + 1) * piece
                    text = ch.upper() if style.get("bold") else ch
                    lines.append(
                        f"Dialogue: 0,{_ass_timestamp(a)},{_ass_timestamp(b)},"
                        f"Default,,0,0,0,,{_escape_ass(text)}\n"
                    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def _escape_ass(text: str) -> str:
    text = text.replace("\n", " ")
    text = text.replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", text).strip()


def vertical_filter(width: int = 1080, height: int = 1920) -> str:
    """Smart center crop to 9:16 then scale."""
    # scale so short side covers, then center crop
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def render_clip(
    cfg: Config,
    source: Path,
    clip: ClipCandidate,
    segments: Sequence[TranscriptSegment],
    *,
    index: int = 0,
    video_id: str = "local",
) -> RenderedShort:
    cfg.ensure_dirs()
    style = cfg.caption_preset()
    stem = f"{video_id}_short_{index:02d}_{int(clip.start)}"
    out_dir = cfg.output_dir / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ass_path = out_dir / f"{stem}.ass"
    mp4_path = out_dir / f"{stem}.mp4"

    build_ass_for_clip(segments, clip, style, ass_path)

    # Escape ASS path for ffmpeg filter (Windows-safe-ish + colons)
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vf = f"{vertical_filter()},ass='{ass_escaped}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(clip.start),
        "-to",
        str(clip.end),
        "-i",
        str(source),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-pix_fmt",
        "yuv420p",
        str(mp4_path),
    ]
    log.info("Rendering %s (%.1f–%.1fs) …", mp4_path.name, clip.start, clip.end)
    subprocess.run(cmd, check=True, capture_output=True)
    return RenderedShort(clip=clip, video_path=mp4_path, ass_path=ass_path)


def render_all(
    cfg: Config,
    source: Path,
    clips: List[ClipCandidate],
    segments: Sequence[TranscriptSegment],
    *,
    video_id: str = "local",
) -> List[RenderedShort]:
    rendered: List[RenderedShort] = []
    for i, clip in enumerate(clips):
        try:
            r = render_clip(cfg, source, clip, segments, index=i, video_id=video_id)
            rendered.append(r)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", errors="replace")[-500:]
            log.error("ffmpeg failed for clip %d: %s", i, err)
    log.info("Rendered %d / %d shorts", len(rendered), len(clips))
    return rendered


def make_synthetic_source(cfg: Config, duration: float = 90.0) -> Path:
    """Generate a colorful test mp4 for demo mode (no YouTube needed)."""
    cfg.ensure_dirs()
    path = cfg.downloads_dir / "sample_source.mp4"
    if path.exists():
        return path
    # 1080x1920 vertical color bars with sine tone — already vertical for simplicity
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=1080x1920:rate=30:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    log.info("Generating synthetic sample source …")
    subprocess.run(cmd, check=True, capture_output=True)
    return path
