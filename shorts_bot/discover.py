"""Discover trending or niche YouTube videos via Data API v3."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

from shorts_bot.config import Config

log = logging.getLogger(__name__)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


@dataclass
class VideoCandidate:
    video_id: str
    title: str
    channel_title: str
    description: str
    view_count: int = 0
    duration: str = ""
    url: str = ""

    def __post_init__(self) -> None:
        if not self.url and self.video_id:
            self.url = f"https://www.youtube.com/watch?v={self.video_id}"


def _require_api_key(cfg: Config) -> str:
    if not cfg.youtube_api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY is required for discover/search "
            "(YouTube Data API v3 free quota ≈ 10k units/day). "
            "Set it in .env, or pass --url to skip discovery."
        )
    return cfg.youtube_api_key


def discover_trending(
    cfg: Config,
    *,
    region: str = "US",
    max_results: int = 10,
) -> List[VideoCandidate]:
    """Fetch mostPopular chart videos for a region / category."""
    key = _require_api_key(cfg)
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": min(max_results, 50),
        "key": key,
    }
    if cfg.category_id:
        params["videoCategoryId"] = cfg.category_id

    resp = requests.get(f"{YOUTUBE_API}/videos", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results: List[VideoCandidate] = []
    for item in data.get("items", []):
        sn = item.get("snippet", {})
        st = item.get("statistics", {})
        cd = item.get("contentDetails", {})
        results.append(
            VideoCandidate(
                video_id=item["id"],
                title=sn.get("title", ""),
                channel_title=sn.get("channelTitle", ""),
                description=sn.get("description", "")[:500],
                view_count=int(st.get("viewCount", 0)),
                duration=cd.get("duration", ""),
            )
        )
    log.info("Discovered %d trending videos (category=%s)", len(results), cfg.category_id)
    return results


def discover_search(
    cfg: Config,
    query: Optional[str] = None,
    *,
    max_results: int = 10,
    order: str = "viewCount",
) -> List[VideoCandidate]:
    """Search YouTube for videos in a niche."""
    key = _require_api_key(cfg)
    q = query or cfg.niche
    params = {
        "part": "snippet",
        "q": q,
        "type": "video",
        "videoDuration": "medium",  # 4–20 min; good source length
        "order": order,
        "maxResults": min(max_results, 50),
        "key": key,
    }
    resp = requests.get(f"{YOUTUBE_API}/search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    ids = [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        return []

    # Enrich with stats
    detail = requests.get(
        f"{YOUTUBE_API}/videos",
        params={
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(ids),
            "key": key,
        },
        timeout=30,
    )
    detail.raise_for_status()
    results: List[VideoCandidate] = []
    for item in detail.json().get("items", []):
        sn = item.get("snippet", {})
        st = item.get("statistics", {})
        cd = item.get("contentDetails", {})
        results.append(
            VideoCandidate(
                video_id=item["id"],
                title=sn.get("title", ""),
                channel_title=sn.get("channelTitle", ""),
                description=sn.get("description", "")[:500],
                view_count=int(st.get("viewCount", 0)),
                duration=cd.get("duration", ""),
            )
        )
    log.info("Search '%s' returned %d videos", q, len(results))
    return results


def pick_best(candidates: List[VideoCandidate]) -> Optional[VideoCandidate]:
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.view_count)
