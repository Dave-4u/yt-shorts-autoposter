"""Configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from cwd or project root if present
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOWNLOADS = PROJECT_ROOT / "downloads"
DEFAULT_OUTPUT = PROJECT_ROOT / "output"
DEFAULT_TOKENS = PROJECT_ROOT / "tokens"

CAPTION_STYLES = {
    "bold_yellow": {
        "fontname": "Arial Black",
        "fontsize": 72,
        "primary": "&H0000FFFF",  # yellow (ASS BGR)
        "outline": "&H00000000",
        "outline_width": 4,
        "shadow": 0,
        "bold": 1,
        "alignment": 2,  # bottom center
        "margin_v": 120,
    },
    "white_outline": {
        "fontname": "Arial",
        "fontsize": 68,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "outline_width": 5,
        "shadow": 1,
        "bold": 1,
        "alignment": 2,
        "margin_v": 120,
    },
    "neon_pink": {
        "fontname": "Impact",
        "fontsize": 70,
        "primary": "&H00FF66FF",
        "outline": "&H00000000",
        "outline_width": 4,
        "shadow": 0,
        "bold": 1,
        "alignment": 2,
        "margin_v": 120,
    },
    "clean_white": {
        "fontname": "Helvetica",
        "fontsize": 64,
        "primary": "&H00FFFFFF",
        "outline": "&H00202020",
        "outline_width": 3,
        "shadow": 0,
        "bold": 0,
        "alignment": 2,
        "margin_v": 100,
    },
}


@dataclass
class Config:
    youtube_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    google_client_secrets: str = "client_secrets.json"
    channel_id: str = ""
    niche: str = "Education"
    category_id: str = "27"  # Education
    max_shorts: int = 10
    visibility: str = "private"  # private | unlisted | public
    caption_style: str = "bold_yellow"
    min_clip_seconds: int = 15
    max_clip_seconds: int = 59
    downloads_dir: Path = field(default_factory=lambda: DEFAULT_DOWNLOADS)
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUTPUT)
    tokens_dir: Path = field(default_factory=lambda: DEFAULT_TOKENS)
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
            google_client_secrets=os.getenv(
                "GOOGLE_CLIENT_SECRETS", "client_secrets.json"
            ),
            channel_id=os.getenv("CHANNEL_ID", ""),
            niche=os.getenv("NICHE", "Education"),
            category_id=os.getenv("CATEGORY", "27"),
            max_shorts=int(os.getenv("MAX_SHORTS", "10")),
            visibility=os.getenv("VISIBILITY", "private").lower(),
            caption_style=os.getenv("CAPTION_STYLE", "bold_yellow"),
            min_clip_seconds=int(os.getenv("MIN_CLIP_SECONDS", "15")),
            max_clip_seconds=int(os.getenv("MAX_CLIP_SECONDS", "59")),
            downloads_dir=Path(os.getenv("DOWNLOADS_DIR", str(DEFAULT_DOWNLOADS))),
            output_dir=Path(os.getenv("OUTPUT_DIR", str(DEFAULT_OUTPUT))),
            tokens_dir=Path(os.getenv("TOKENS_DIR", str(DEFAULT_TOKENS))),
        )

    def ensure_dirs(self) -> None:
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key or self.anthropic_api_key)

    def caption_preset(self) -> dict:
        return CAPTION_STYLES.get(self.caption_style, CAPTION_STYLES["bold_yellow"])
