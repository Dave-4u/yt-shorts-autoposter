"""CLI entrypoint: discover → fetch → analyze → render → upload."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from shorts_bot.analyze import analyze_clips, load_clips_json, save_clips_json
from shorts_bot.config import CAPTION_STYLES, Config
from shorts_bot.discover import discover_search, discover_trending, pick_best
from shorts_bot.fetch import (
    FetchedVideo,
    TranscriptSegment,
    extract_video_id,
    fetch_video,
    load_transcript_json,
)
from shorts_bot.render import make_synthetic_source, render_all
from shorts_bot.upload import upload_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("shorts_bot")


LEGAL_BANNER = """
⚠  LEGAL: Only process videos you own or have explicit rights to reuse.
   Re-uploading others' content can violate copyright and YouTube Terms of Service.
   This tool does NOT scrape third-party Shorts SaaS APIs.
"""


def _apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    if getattr(args, "max_shorts", None):
        cfg.max_shorts = args.max_shorts
    if getattr(args, "caption_style", None):
        cfg.caption_style = args.caption_style
    if getattr(args, "visibility", None):
        cfg.visibility = args.visibility
    if getattr(args, "niche", None):
        cfg.niche = args.niche
    if getattr(args, "dry_run", False):
        cfg.dry_run = True
    if getattr(args, "heuristic", False):
        # force no LLM by clearing keys temporarily via flag handled in analyze
        pass
    return cfg


def cmd_discover(args: argparse.Namespace) -> int:
    cfg = _apply_overrides(Config.from_env(), args)
    if args.search:
        cands = discover_search(cfg, query=args.search, max_results=args.limit)
    else:
        cands = discover_trending(cfg, region=args.region, max_results=args.limit)
    for c in cands:
        print(f"{c.view_count:>12,}  {c.video_id}  {c.title[:70]}")
        print(f"              {c.url}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps([c.__dict__ for c in cands], indent=2),
            encoding="utf-8",
        )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    cfg = _apply_overrides(Config.from_env(), args)
    fv = fetch_video(cfg, args.url, use_whisper=args.whisper)
    print(f"Downloaded: {fv.video_path}")
    print(f"Title:      {fv.title}")
    print(f"Duration:   {fv.duration:.1f}s")
    print(f"Segments:   {len(fv.transcript)}")
    if fv.meta_path:
        print(f"Transcript: {fv.meta_path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    cfg = _apply_overrides(Config.from_env(), args)
    segments: list[TranscriptSegment] = []
    duration = 0.0
    if args.transcript:
        segments = load_transcript_json(Path(args.transcript))
        if segments:
            duration = segments[-1].end
    elif args.url:
        fv = fetch_video(cfg, args.url, skip_download=args.skip_download, use_whisper=args.whisper)
        segments = fv.transcript
        duration = fv.duration
    else:
        sample = Path(__file__).resolve().parent.parent / "samples" / "sample_transcript.json"
        segments = load_transcript_json(sample)
        duration = segments[-1].end if segments else 120.0
        log.info("Using sample transcript: %s", sample)

    clips = analyze_clips(
        segments,
        cfg,
        source_duration=duration,
        force_heuristic=args.heuristic or not cfg.has_llm,
    )
    out = Path(args.out or "output/clips.json")
    save_clips_json(clips, out)
    for i, c in enumerate(clips):
        print(f"[{i:02d}] {c.start:7.1f}-{c.end:7.1f}s  score={c.score:5.1f}  {c.title}")
    print(f"Wrote {out}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    cfg = _apply_overrides(Config.from_env(), args)
    clips = load_clips_json(args.clips)
    segments: list[TranscriptSegment] = []
    if args.transcript:
        segments = load_transcript_json(Path(args.transcript))

    if args.source:
        source = Path(args.source)
        video_id = source.stem
    elif args.url:
        fv = fetch_video(cfg, args.url, skip_download=True)
        source = fv.video_path
        video_id = fv.video_id
        if not segments:
            segments = fv.transcript
    else:
        raise SystemExit("Provide --source or --url")

    rendered = render_all(cfg, source, clips, segments, video_id=video_id)
    for r in rendered:
        print(r.video_path)
    return 0 if rendered else 1


def cmd_upload_only(args: argparse.Namespace) -> int:
    cfg = _apply_overrides(Config.from_env(), args)
    from shorts_bot.analyze import ClipCandidate
    from shorts_bot.render import RenderedShort

    paths = [Path(p) for p in args.videos]
    clips_meta = load_clips_json(args.clips) if args.clips else []
    rendered = []
    for i, p in enumerate(paths):
        clip = clips_meta[i] if i < len(clips_meta) else ClipCandidate(
            start=0, end=30, title=p.stem, hook=p.stem, score=5.0
        )
        rendered.append(RenderedShort(clip=clip, video_path=p))
    ids = upload_all(cfg, rendered, source_title=args.source_title or "")
    for vid in ids:
        if vid:
            print(f"https://youtube.com/shorts/{vid}")
    return 0


def cmd_clip(args: argparse.Namespace) -> int:
    """Fetch + analyze + render for a specific URL (no upload)."""
    cfg = _apply_overrides(Config.from_env(), args)
    print(LEGAL_BANNER)
    fv = fetch_video(cfg, args.url, use_whisper=args.whisper)
    clips = analyze_clips(
        fv.transcript,
        cfg,
        source_duration=fv.duration,
        force_heuristic=args.heuristic,
    )
    clips_path = cfg.output_dir / fv.video_id / "clips.json"
    save_clips_json(clips, clips_path)
    print(f"Clips JSON: {clips_path}")
    if args.analyze_only:
        for i, c in enumerate(clips):
            print(f"[{i:02d}] {c.start:.1f}-{c.end:.1f}s  {c.title}")
        return 0
    rendered = render_all(cfg, fv.video_path, clips, fv.transcript, video_id=fv.video_id)
    for r in rendered:
        print(r.video_path)
    return 0 if rendered else 1


def cmd_demo(args: argparse.Namespace) -> int:
    """Offline demo: synthetic video + sample transcript → rendered Shorts."""
    cfg = _apply_overrides(Config.from_env(), args)
    cfg.dry_run = True
    print(LEGAL_BANNER)
    print("Demo mode — no YouTube download or upload.\n")

    sample_tx = Path(__file__).resolve().parent.parent / "samples" / "sample_transcript.json"
    segments = load_transcript_json(sample_tx)
    source = make_synthetic_source(cfg, duration=120.0)
    clips = analyze_clips(segments, cfg, source_duration=120.0, force_heuristic=True)
    # clamp clips into synthetic duration
    safe = []
    for c in clips:
        if c.start >= 115:
            continue
        c.end = min(c.end, 118.0)
        if c.end - c.start >= cfg.min_clip_seconds:
            safe.append(c)
    clips = safe[: cfg.max_shorts]
    clips_path = cfg.output_dir / "demo" / "clips.json"
    save_clips_json(clips, clips_path)
    rendered = render_all(cfg, source, clips, segments, video_id="demo")
    print(f"\nClips: {clips_path}")
    for r in rendered:
        print(f"  → {r.video_path}")
    print(f"\nDone. {len(rendered)} Shorts rendered (dry-run, nothing uploaded).")
    return 0 if rendered else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline end-to-end."""
    cfg = _apply_overrides(Config.from_env(), args)
    print(LEGAL_BANNER)

    if args.demo:
        return cmd_demo(args)

    # Resolve source URL
    url = args.url
    if not url:
        if not cfg.youtube_api_key:
            log.error("No --url and no YOUTUBE_API_KEY. Use --demo or pass --url.")
            return 2
        print(
            "⚠  Discover finds public trending/search results for research only.\n"
            "   Only continue if YOU own the chosen video or have rights to clip it.\n"
        )
        cands = (
            discover_search(cfg, max_results=10)
            if args.search
            else discover_trending(cfg, max_results=10)
        )
        best = pick_best(cands)
        if not best:
            log.error("No candidates found.")
            return 1
        print(f"Selected: {best.title} ({best.url})")
        if not args.yes:
            log.error("Refusing to auto-process discovered videos without --yes "
                      "(and you must own/have rights). Prefer: run --url <your-video>")
            return 2
        url = best.url

    fv = fetch_video(cfg, url, use_whisper=args.whisper)
    clips = analyze_clips(
        fv.transcript,
        cfg,
        source_duration=fv.duration,
        force_heuristic=args.heuristic,
    )
    clips_path = cfg.output_dir / fv.video_id / "clips.json"
    save_clips_json(clips, clips_path)
    print(f"Analyzed {len(clips)} clips → {clips_path}")

    if args.analyze_only:
        return 0

    rendered = render_all(cfg, fv.video_path, clips, fv.transcript, video_id=fv.video_id)
    if not rendered:
        return 1

    if args.skip_upload:
        for r in rendered:
            print(r.video_path)
        return 0

    ids = upload_all(cfg, rendered, source_title=fv.title)
    ok = sum(1 for i in ids if i)
    print(f"Uploaded {ok}/{len(ids)} Shorts (visibility={cfg.visibility})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shorts_bot",
        description="Turn long-form videos YOU OWN into captioned YouTube Shorts.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--max-shorts", type=int, default=None)
        sp.add_argument("--caption-style", choices=list(CAPTION_STYLES), default=None)
        sp.add_argument("--visibility", choices=["private", "unlisted", "public"], default=None)
        sp.add_argument("--niche", default=None)
        sp.add_argument("--dry-run", action="store_true")
        sp.add_argument("--heuristic", action="store_true", help="Force offline heuristic analyze")
        sp.add_argument("--whisper", action="store_true", help="Fallback to local Whisper")

    # discover
    d = sub.add_parser("discover", help="List trending / search videos")
    d.add_argument("--search", default=None)
    d.add_argument("--region", default="US")
    d.add_argument("--limit", type=int, default=10)
    d.add_argument("--json-out", default=None)
    add_common(d)
    d.set_defaults(func=cmd_discover)

    # fetch
    f = sub.add_parser("fetch", help="Download video + transcript")
    f.add_argument("--url", required=True)
    add_common(f)
    f.set_defaults(func=cmd_fetch)

    # analyze
    a = sub.add_parser("analyze", help="Score transcript → clip JSON")
    a.add_argument("--url", default=None)
    a.add_argument("--transcript", default=None)
    a.add_argument("--out", default=None)
    a.add_argument("--skip-download", action="store_true")
    add_common(a)
    a.set_defaults(func=cmd_analyze)

    # render
    r = sub.add_parser("render", help="Render Shorts from clip JSON")
    r.add_argument("--clips", required=True)
    r.add_argument("--source", default=None)
    r.add_argument("--url", default=None)
    r.add_argument("--transcript", default=None)
    add_common(r)
    r.set_defaults(func=cmd_render)

    # upload-only
    u = sub.add_parser("upload-only", help="Upload already-rendered mp4 Shorts")
    u.add_argument("videos", nargs="+")
    u.add_argument("--clips", default=None)
    u.add_argument("--source-title", default="")
    add_common(u)
    u.set_defaults(func=cmd_upload_only)

    # clip
    c = sub.add_parser("clip", help="Fetch+analyze+render one URL (no upload)")
    c.add_argument("--url", required=True)
    c.add_argument("--analyze-only", action="store_true")
    add_common(c)
    c.set_defaults(func=cmd_clip)

    # demo
    demo = sub.add_parser("demo", help="Offline demo with synthetic video")
    add_common(demo)
    demo.set_defaults(func=cmd_demo)

    # run
    run = sub.add_parser("run", help="Full pipeline discover→…→upload")
    run.add_argument("--url", default=None, help="Your video URL (preferred)")
    run.add_argument("--search", action="store_true", help="Use search discover instead of trending")
    run.add_argument("--yes", action="store_true", help="Confirm you have rights to discovered video")
    run.add_argument("--demo", action="store_true")
    run.add_argument("--analyze-only", action="store_true")
    run.add_argument("--skip-upload", action="store_true")
    add_common(run)
    run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
