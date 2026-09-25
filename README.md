# yt-shorts-autoposter

**Turn long-form videos you own into captioned YouTube Shorts** — discover (optional) → download → AI/heuristic viral moments → 9:16 burn-in captions → upload.

Independent open-source pipeline built with **yt-dlp + ffmpeg + LLM + YouTube Data API v3**.  
It is **not** affiliated with Vugola or any closed Shorts SaaS, and it does **not** scrape third-party product APIs.

---

## ⚠ Legal / rights

> **Only use this on videos you own or have explicit rights to clip and re-upload.**  
> Re-uploading other creators’ content can violate copyright law and the [YouTube Terms of Service](https://www.youtube.com/t/terms).  
> This project does **not** instruct you to steal viral videos. Prefer `--url` pointing at **your** channel’s videos.  
> `discover` is for research / finding *your own* niche references — always confirm rights before `--yes`.

---

## Pipeline

| Step | Module | What it does |
|------|--------|----------------|
| **discover** | `shorts_bot/discover.py` | Trending (`videos.list` chart=mostPopular) or niche search |
| **fetch** | `shorts_bot/fetch.py` | yt-dlp download + youtube-transcript-api (Whisper optional) |
| **analyze** | `shorts_bot/analyze.py` | LLM scores hooks / peaks → JSON clips; **heuristic fallback** if no API key |
| **render** | `shorts_bot/render.py` | ffmpeg 9:16 crop, 15–59s cuts, ASS TikTok-style captions |
| **upload** | `shorts_bot/upload.py` | YouTube Data API v3 resumable upload as Shorts (`#Shorts`) |

End-to-end:

```bash
python -m shorts_bot run --url "https://www.youtube.com/watch?v=YOUR_VIDEO"
```

---

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on `PATH`
- Google Cloud project with **YouTube Data API v3** enabled
- (Optional) OpenAI-compatible or Anthropic API key for smarter clip picking

```bash
# Debian/Ubuntu
sudo apt-get install -y ffmpeg

git clone https://github.com/Dave-4u/yt-shorts-autoposter.git
cd yt-shorts-autoposter
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
```

---

## Setup

### 1. Environment

Copy `.env.example` → `.env`:

| Variable | Purpose |
|----------|---------|
| `YOUTUBE_API_KEY` | Data API key for discover/search |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM clip analysis (optional) |
| `GOOGLE_CLIENT_SECRETS` | Path to OAuth desktop client JSON |
| `CHANNEL_ID` | Your channel id (optional) |
| `NICHE` / `CATEGORY` | Discover defaults |
| `MAX_SHORTS` | Cap clips per source (default 10) |
| `VISIBILITY` | `private` \| `unlisted` \| `public` |
| `CAPTION_STYLE` | `bold_yellow` \| `white_outline` \| `neon_pink` \| `clean_white` |

### 2. Google Cloud — API key + OAuth

1. Create a project at [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **YouTube Data API v3**.
3. Create an **API key** → `YOUTUBE_API_KEY` (restrict to YouTube Data API).
4. Configure OAuth consent screen (External / Testing is fine for personal use).
5. Create **OAuth client ID → Desktop app**, download JSON → save as `client_secrets.json` (gitignored).
6. First upload opens a browser for consent; token is cached under `tokens/`.

### 3. LLM (optional)

Without an LLM key, analyze uses an **offline heuristic** (hook words, questions, length sweet-spot) so demos and CI work with zero paid APIs.

---

## Usage

```bash
# Offline demo (synthetic video + sample transcript → rendered Shorts, no upload)
python -m shorts_bot demo
python -m shorts_bot run --demo

# Analyze sample transcript only
python -m shorts_bot analyze --heuristic

# Your video → clips + render (no upload)
python -m shorts_bot clip --url "https://www.youtube.com/watch?v=YOUR_ID"

# Full pipeline (upload; default visibility=private)
python -m shorts_bot run --url "https://www.youtube.com/watch?v=YOUR_ID"

# Dry-run upload path
python -m shorts_bot run --url "..." --dry-run --skip-upload

# Upload already-rendered files
python -m shorts_bot upload-only output/YOUR_ID/*.mp4 --clips output/YOUR_ID/clips.json

# Discover only (research — do not reupload others' content)
python -m shorts_bot discover --search "python tutorials" --limit 5
```

### Caption styles

Set `CAPTION_STYLE` or `--caption-style`:

- `bold_yellow` — classic TikTok yellow + black outline  
- `white_outline` — white bold with thick outline  
- `neon_pink` — high-contrast pink  
- `clean_white` — lighter Helvetica look  

---

## Project layout

```
yt-shorts-autoposter/
├── shorts_bot/
│   ├── __main__.py
│   ├── cli.py          # discover | fetch | analyze | render | upload-only | clip | demo | run
│   ├── config.py
│   ├── discover.py
│   ├── fetch.py
│   ├── analyze.py
│   ├── render.py
│   └── upload.py
├── samples/
│   └── sample_transcript.json
├── tests/
├── .env.example
├── requirements.txt
└── ci/dry-run.yml          # copy → .github/workflows/
```

---

## GitHub Actions

`ci/dry-run.yml` (copy to `.github/workflows/` to enable) installs deps and runs:

```bash
python -m shorts_bot analyze --heuristic
python -m shorts_bot demo --max-shorts 2
```

No secrets required for the dry-run path.

---

## Scheduler (optional)

Cron example (daily, private uploads of *your* latest long-form — wire your own URL source):

```cron
0 9 * * * cd /path/to/yt-shorts-autoposter && . .venv/bin/activate && \
  python -m shorts_bot run --url "$MY_LATEST_VIDEO_URL" --visibility private
```

---

## License

MIT © Dave-4u — see [LICENSE](LICENSE).

Use responsibly. Own your content.
