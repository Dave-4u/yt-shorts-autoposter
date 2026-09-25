"""Score transcript segments and pick viral clip windows.

LLM preference (free-first): Groq → Gemini → OpenAI → Anthropic → heuristic.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import List, Optional

from shorts_bot.config import (
    GEMINI_OPENAI_BASE_URL,
    GROQ_BASE_URL,
    Config,
)
from shorts_bot.fetch import TranscriptSegment

log = logging.getLogger(__name__)

HOOK_WORDS = {
    "secret", "mistake", "never", "always", "why", "how", "stop", "urgent",
    "shocking", "truth", "hack", "tip", "warning", "crazy", "insane",
    "nobody", "everyone", "proven", "free", "easy", "simple", "actually",
    "wait", "watch", "listen", "remember", "important", "key", "biggest",
    "worst", "best", "first", "last", "finally", "surprising", "revealed",
}


@dataclass
class ClipCandidate:
    start: float
    end: float
    title: str
    hook: str
    score: float
    text: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self)


def _merge_windows(
    segments: List[TranscriptSegment],
    target_len: float,
    max_len: float,
) -> List[tuple]:
    """Build overlapping windows of roughly target_len seconds from segments."""
    if not segments:
        return []
    windows = []
    i = 0
    while i < len(segments):
        start = segments[i].start
        text_parts = []
        j = i
        end = start
        while j < len(segments) and (segments[j].end - start) < target_len:
            text_parts.append(segments[j].text)
            end = segments[j].end
            j += 1
        # stretch a bit if still short
        while j < len(segments) and (segments[j].end - start) <= max_len:
            text_parts.append(segments[j].text)
            end = segments[j].end
            j += 1
            if (end - start) >= target_len:
                break
        if end - start >= 8:  # minimum usable
            windows.append((start, end, " ".join(text_parts).strip()))
        # advance by ~half window worth of segments
        step = max(1, (j - i) // 2) if j > i else 1
        i += step
    return windows


def heuristic_score(text: str, duration: float) -> float:
    """Offline viral-potential score when no LLM key is set."""
    if not text:
        return 0.0
    words = re.findall(r"[A-Za-z']+", text.lower())
    if not words:
        return 0.0
    score = 0.0
    # questions / hooks
    score += text.count("?") * 2.5
    score += text.count("!") * 1.5
    # hook vocabulary
    score += sum(1.5 for w in words if w in HOOK_WORDS)
    # density: prefer punchy sentences
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_len = (sum(len(s.split()) for s in sentences) / len(sentences)) if sentences else 20
    if 5 <= avg_len <= 18:
        score += 3.0
    elif avg_len < 5:
        score += 1.0
    # length sweet spot for Shorts
    if 20 <= duration <= 45:
        score += 4.0
    elif 15 <= duration <= 59:
        score += 2.0
    else:
        score -= 1.0
    # word count density
    wpm = len(words) / max(duration / 60.0, 0.1)
    if 100 <= wpm <= 200:
        score += 2.0
    return round(score, 2)


def _title_from_text(text: str, max_words: int = 8) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text)
    if not words:
        return "Clip"
    # Prefer starting at a capital / question
    chunk = " ".join(words[:max_words])
    if text.strip().startswith(("Why", "How", "What", "When", "Stop", "Never")):
        m = re.match(r"^([^.!?]{10,60})", text.strip())
        if m:
            return m.group(1).strip()[:80]
    return chunk[:80]


def analyze_heuristic(
    segments: List[TranscriptSegment],
    cfg: Config,
    *,
    source_duration: float = 0.0,
) -> List[ClipCandidate]:
    """Pick top clips using keyword / structure heuristics."""
    target = (cfg.min_clip_seconds + cfg.max_clip_seconds) / 2
    windows = _merge_windows(segments, target, float(cfg.max_clip_seconds))

    if not windows and source_duration > 0:
        # No transcript: slice evenly
        step = float(cfg.max_clip_seconds)
        t = 0.0
        while t + cfg.min_clip_seconds <= source_duration and len(windows) < cfg.max_shorts * 2:
            end = min(t + step, source_duration)
            windows.append((t, end, f"Segment at {int(t)}s"))
            t += step * 0.75

    scored: List[ClipCandidate] = []
    for start, end, text in windows:
        dur = end - start
        if dur < cfg.min_clip_seconds or dur > cfg.max_clip_seconds + 2:
            # clamp end
            end = min(start + cfg.max_clip_seconds, end)
            dur = end - start
            if dur < cfg.min_clip_seconds:
                continue
        sc = heuristic_score(text, dur)
        scored.append(
            ClipCandidate(
                start=round(start, 2),
                end=round(end, 2),
                title=_title_from_text(text),
                hook=_title_from_text(text, 6),
                score=sc,
                text=text[:500],
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    # de-duplicate overlapping windows (keep highest score)
    selected: List[ClipCandidate] = []
    for c in scored:
        if any(abs(c.start - s.start) < 8 for s in selected):
            continue
        selected.append(c)
        if len(selected) >= cfg.max_shorts:
            break
    log.info("Heuristic analyze picked %d clips", len(selected))
    return selected


def _llm_prompt(segments: List[TranscriptSegment], cfg: Config) -> str:
    lines = []
    for s in segments[:400]:  # cap context
        lines.append(f"[{s.start:.1f}-{s.end:.1f}] {s.text}")
    transcript_block = "\n".join(lines)
    return f"""You are a viral Shorts editor. From this transcript, pick the best {cfg.max_shorts} clip windows.

Rules:
- Each clip MUST be between {cfg.min_clip_seconds} and {cfg.max_clip_seconds} seconds.
- Prefer hooks, questions, surprising claims, emotional peaks, quotable lines.
- start/end must align to existing timestamps (use the bracket times).
- title: punchy Shorts title (<= 70 chars), no #Shorts tag.
- hook: one-line hook for the first 3 seconds.

Return ONLY valid JSON array:
[{{"start": 12.5, "end": 42.0, "title": "...", "hook": "...", "score": 8.5}}]

TRANSCRIPT:
{transcript_block}
"""


def _chat_completions(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
) -> str:
    """OpenAI-compatible chat completions (Groq / Gemini / OpenAI)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You output only JSON arrays. No markdown."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content or "[]"


def analyze_openai_compatible(
    segments: List[TranscriptSegment],
    cfg: Config,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> List[ClipCandidate]:
    prompt = _llm_prompt(segments, cfg)
    raw = _chat_completions(
        api_key=api_key, base_url=base_url, model=model, prompt=prompt
    )
    return _parse_llm_clips(raw, cfg)


def analyze_openai(segments: List[TranscriptSegment], cfg: Config) -> List[ClipCandidate]:
    return analyze_openai_compatible(
        segments,
        cfg,
        api_key=cfg.openai_api_key,
        base_url=cfg.openai_base_url,
        model=cfg.openai_model,
    )


def analyze_groq(segments: List[TranscriptSegment], cfg: Config) -> List[ClipCandidate]:
    """Groq free tier via OpenAI-compatible API."""
    return analyze_openai_compatible(
        segments,
        cfg,
        api_key=cfg.groq_api_key,
        base_url=GROQ_BASE_URL,
        model=cfg.groq_model,
    )


def analyze_gemini(segments: List[TranscriptSegment], cfg: Config) -> List[ClipCandidate]:
    """Gemini free tier: OpenAI-compatible endpoint, else google-generativeai."""
    prompt = _llm_prompt(segments, cfg)
    # Prefer OpenAI-compatible (uses already-installed openai package)
    try:
        raw = _chat_completions(
            api_key=cfg.gemini_api_key,
            base_url=GEMINI_OPENAI_BASE_URL,
            model=cfg.gemini_model,
            prompt=prompt,
        )
        return _parse_llm_clips(raw, cfg)
    except Exception as e:
        log.debug("Gemini OpenAI-compatible path failed (%s); trying google-generativeai", e)

    try:
        import google.generativeai as genai
    except ImportError as e:
        raise RuntimeError(
            "Gemini call failed and google-generativeai is not installed. "
            "pip install google-generativeai  OR use GROQ_API_KEY instead."
        ) from e

    genai.configure(api_key=cfg.gemini_api_key)
    model = genai.GenerativeModel(
        cfg.gemini_model,
        system_instruction="You output only JSON arrays. No markdown.",
    )
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": 0.4},
    )
    raw = getattr(resp, "text", None) or "[]"
    return _parse_llm_clips(raw, cfg)


def analyze_anthropic(segments: List[TranscriptSegment], cfg: Config) -> List[ClipCandidate]:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    prompt = _llm_prompt(segments, cfg)
    msg = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text if msg.content else "[]"
    return _parse_llm_clips(raw, cfg)


def _parse_llm_clips(raw: str, cfg: Config) -> List[ClipCandidate]:
    raw = raw.strip()
    # strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            log.error("LLM returned non-JSON; falling back to heuristic")
            return []
        data = json.loads(m.group(0))

    clips: List[ClipCandidate] = []
    for item in data:
        start = float(item["start"])
        end = float(item["end"])
        if end - start < cfg.min_clip_seconds:
            end = start + cfg.min_clip_seconds
        if end - start > cfg.max_clip_seconds:
            end = start + cfg.max_clip_seconds
        clips.append(
            ClipCandidate(
                start=round(start, 2),
                end=round(end, 2),
                title=str(item.get("title", "Clip"))[:80],
                hook=str(item.get("hook", item.get("title", "")))[:120],
                score=float(item.get("score", 5.0)),
                text=str(item.get("text", "")),
            )
        )
    clips.sort(key=lambda c: c.score, reverse=True)
    return clips[: cfg.max_shorts]


def analyze_clips(
    segments: List[TranscriptSegment],
    cfg: Config,
    *,
    source_duration: float = 0.0,
    force_heuristic: bool = False,
) -> List[ClipCandidate]:
    """Main entry: free LLM if keys present (Groq→Gemini→…), else heuristic."""
    if force_heuristic or not cfg.has_llm or not segments:
        return analyze_heuristic(segments, cfg, source_duration=source_duration)

    resolved = cfg.resolve_llm()
    if not resolved:
        return analyze_heuristic(segments, cfg, source_duration=source_duration)

    provider, _key, model = resolved
    try:
        if provider == "groq":
            log.info("Analyzing with Groq (free) model %s", model)
            clips = analyze_groq(segments, cfg)
        elif provider == "gemini":
            log.info("Analyzing with Gemini (free) model %s", model)
            clips = analyze_gemini(segments, cfg)
        elif provider == "openai":
            log.info("Analyzing with OpenAI-compatible model %s", model)
            clips = analyze_openai(segments, cfg)
        else:
            log.info("Analyzing with Anthropic model %s", model)
            clips = analyze_anthropic(segments, cfg)
        if clips:
            return clips
        log.warning("LLM returned no clips; using heuristic fallback")
    except Exception as e:
        log.warning("LLM analyze failed (%s); using heuristic fallback", e)

    return analyze_heuristic(segments, cfg, source_duration=source_duration)


def save_clips_json(clips: List[ClipCandidate], path) -> None:
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([c.to_dict() for c in clips], indent=2),
        encoding="utf-8",
    )


def load_clips_json(path) -> List[ClipCandidate]:
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ClipCandidate(**d) for d in data]
