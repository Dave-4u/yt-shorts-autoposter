"""Configuration loaded from environment / .env file.

Free-first defaults: Groq → Gemini → OpenAI → Anthropic → heuristic.
"""

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

# Free-tier OpenAI-compatible endpoints
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

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
    # Free-first LLM keys (preference: groq → gemini → openai → anthropic)
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    # Endpoint / model overrides
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.0-flash"
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
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            groq_model=os.getenv(
                "GROQ_MODEL", "llama-3.3-70b-versatile"
            ),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
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
        return bool(
            self.groq_api_key
            or self.gemini_api_key
            or self.openai_api_key
            or self.anthropic_api_key
        )

    def resolve_llm(self) -> Optional[tuple[str, str, str]]:
        """Pick first available provider.

        Returns (provider, api_key, model) where provider is one of:
        groq | gemini | openai | anthropic.
        Preference: GROQ → GEMINI → OPENAI → ANTHROPIC.
        """
        if self.groq_api_key:
            return ("groq", self.groq_api_key, self.groq_model)
        if self.gemini_api_key:
            return ("gemini", self.gemini_api_key, self.gemini_model)
        if self.openai_api_key:
            return ("openai", self.openai_api_key, self.openai_model)
        if self.anthropic_api_key:
            return ("anthropic", self.anthropic_api_key, self.anthropic_model)
        return None

    def caption_preset(self) -> dict:
        return CAPTION_STYLES.get(self.caption_style, CAPTION_STYLES["bold_yellow"])
