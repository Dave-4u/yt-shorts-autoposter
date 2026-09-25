"""Upload rendered Shorts to YouTube via Data API v3 (OAuth desktop flow)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from shorts_bot.analyze import ClipCandidate
from shorts_bot.config import Config
from shorts_bot.render import RenderedShort

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE = "youtube"
API_VERSION = "v3"


def _token_path(cfg: Config) -> Path:
    return cfg.tokens_dir / "youtube_token.json"


def get_youtube_service(cfg: Config):
    """OAuth desktop flow; caches token under tokens/."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    cfg.ensure_dirs()
    creds = None
    token_file = _token_path(cfg)
    secrets = Path(cfg.google_client_secrets)
    if not secrets.is_absolute():
        secrets = Path.cwd() / secrets

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets.exists():
                raise FileNotFoundError(
                    f"OAuth client secrets not found: {secrets}\n"
                    "Download from Google Cloud Console → APIs & Services → Credentials "
                    "→ Create OAuth client ID (Desktop app) and save as client_secrets.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build(API_SERVICE, API_VERSION, credentials=creds)


def build_metadata(clip: ClipCandidate, cfg: Config, source_title: str = "") -> dict:
    title = clip.title.strip()
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    title = title[:100]

    desc_parts = [
        clip.hook or clip.title,
        "",
        f"Clip from: {source_title}" if source_title else "",
        "",
        "#Shorts #YouTubeShorts",
        "",
        "Created with yt-shorts-autoposter (content you own / have rights to).",
    ]
    description = "\n".join(p for p in desc_parts if p is not None)[:5000]

    tags = ["Shorts", "YouTubeShorts"]
    for w in (clip.title + " " + (cfg.niche or "")).split():
        w = "".join(c for c in w if c.isalnum())
        if len(w) > 2 and w not in tags:
            tags.append(w)
        if len(tags) >= 12:
            break

    privacy = cfg.visibility if cfg.visibility in {"private", "unlisted", "public"} else "private"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": cfg.category_id or "22",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    return body


def upload_short(
    cfg: Config,
    rendered: RenderedShort,
    *,
    source_title: str = "",
    youtube=None,
) -> Optional[str]:
    """Upload one Short; returns video id or None on dry-run."""
    if cfg.dry_run:
        log.info(
            "[dry-run] Would upload %s as %s (%s)",
            rendered.video_path.name,
            rendered.clip.title,
            cfg.visibility,
        )
        return None

    from googleapiclient.http import MediaFileUpload

    youtube = youtube or get_youtube_service(cfg)
    body = build_metadata(rendered.clip, cfg, source_title=source_title)
    media = MediaFileUpload(
        str(rendered.video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    log.info("Uploading %s …", rendered.video_path.name)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("Upload progress: %d%%", int(status.progress() * 100))
    video_id = response.get("id")
    log.info("Uploaded: https://youtube.com/shorts/%s", video_id)
    return video_id


def upload_all(
    cfg: Config,
    rendered: List[RenderedShort],
    *,
    source_title: str = "",
) -> List[Optional[str]]:
    if not rendered:
        return []
    youtube = None if cfg.dry_run else get_youtube_service(cfg)
    ids: List[Optional[str]] = []
    for r in rendered:
        try:
            vid = upload_short(cfg, r, source_title=source_title, youtube=youtube)
            ids.append(vid)
        except Exception as e:
            log.error("Upload failed for %s: %s", r.video_path.name, e)
            ids.append(None)
    return ids
