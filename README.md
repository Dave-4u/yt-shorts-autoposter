# yt-shorts-autoposter

**Turn long-form videos you own into captioned YouTube Shorts** — discover (optional) → download → AI/heuristic viral moments → 9:16 burn-in captions → upload.

Independent open-source pipeline built with **yt-dlp + ffmpeg + free LLMs + YouTube Data API v3**.  
It is **not** affiliated with Vugola or any closed Shorts SaaS, and it does **not** scrape third-party product APIs.

---

## Free setup (start here)

Designed to run on **free APIs by default**. Paid OpenAI/Anthropic are optional fallbacks.

### Minimal keys

| What you want | Free key needed? | Notes |
|---------------|------------------|-------|
| Clip your own video (`--url`) + heuristic analyze | **None** | Transcript via `youtube-transcript-api` (no key) |
| Better LLM clip picking | **`GROQ_API_KEY`** (preferred) or `GEMINI_API_KEY` | Free tiers |
| Discover / search trending | **`YOUTUBE_API_KEY`** | Data API ≈ **10 000 units/day** free quota |
| Upload Shorts | **OAuth** `client_secrets.json` | Personal Google Cloud project (free tier) |

**Recommended minimal free path for LLM clips:** only `GROQ_API_KEY`.  
**Upload path:** Groq (or none) + Google OAuth desktop client.  
`YOUTUBE_API_KEY` is **not** required when you pass `--url`.

### 1. Install

```bash
# Debian/Ubuntu
sudo apt-get install -y ffmpeg

git clone https://github.com/Dave-4u/yt-shorts-autoposter.git
cd yt-shorts-autoposter
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Free LLM (pick one)

Preference order in code:

1. **`GROQ_API_KEY`** — [console.groq.com/keys](https://console.groq.com/keys)  
   OpenAI-compatible: `https://api.groq.com/openai/v1`  
   Default model: `llama-3.3-70b-versatile` (or set `GROQ_MODEL=llama-3.1-8b-instant`)
2. **`GEMINI_API_KEY`** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)  
   OpenAI-compatible endpoint, or optional `google-generativeai`  
   Default model: `gemini-2.0-flash`
3. `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — paid optional
4. **No key** → offline **heuristic** (hook words, questions, length sweet-spot)

```bash
# .env — free Groq only
GROQ_API_KEY=gsk_...
```

### 3. YouTube

| Feature | Cost | Key |
|---------|------|-----|
| **Transcripts** | Free | None — `youtube-transcript-api` |
| **Download** | Free | None — `yt-dlp` |
| **Discover / search** | Free quota (~10k units/day) | `YOUTUBE_API_KEY` from [Google Cloud](https://console.cloud.google.com/apis/library/youtube.googleapis.com) |
| **Upload** | Free personal OAuth | Desktop OAuth client → `client_secrets.json` |

**Upload OAuth (free Google Cloud):**

1. Create a project at [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **YouTube Data API v3**.
3. OAuth consent screen (External / Testing is fine for personal use).
4. Create **OAuth client ID → Desktop app**, download JSON → `client_secrets.json` (gitignored).
5. First upload opens a browser; token is cached under `tokens/`.

Optional discover key (same API, API key restricted to YouTube Data API):

```bash
YOUTUBE_API_KEY=AIza...   # only needed for `discover` / search — skip if you use --url
```

### 4. Run with only free keys

```bash
# Zero keys — heuristic analyze + local demo render
python -m shorts_bot demo

# Free Groq LLM + your video (no upload)
# GROQ_API_KEY in .env
python -m shorts_bot clip --url "https://www.youtube.com/watch?v=YOUR_VIDEO"

# Free Groq + free OAuth upload (visibility defaults to private)
python -m shorts_bot run --url "https://www.youtube.com/watch?v=YOUR_VIDEO"
```

---

## ⚠ Legal / trademark

> **Only use this on videos you own or have explicit rights to clip and re-upload.**  
> Re-uploading other creators’ content can violate copyright law and the [YouTube Terms of Service](https://www.youtube.com/t/terms).  
> This project does **not** instruct you to steal viral videos. Prefer `--url` pointing at **your** channel’s videos.  
> `discover` is for research / finding *your own* niche references — always confirm rights before `--yes`.

---

## Pipeline

| Step | Module | What it does |
|------|--------|----------------|
| **discover** | `shorts_bot/discover.py` | Trending (`videos.list` chart=mostPopular) or niche search — needs free-quota API key |
| **fetch** | `shorts_bot/fetch.py` | yt-dlp download + youtube-transcript-api (Whisper optional) — **no key** |
| **analyze** | `shorts_bot/analyze.py` | Groq → Gemini → OpenAI → Anthropic → **heuristic** |
| **render** | `shorts_bot/render.py` | ffmpeg 9:16 crop, 15–59s cuts, ASS TikTok-style captions |
| **upload** | `shorts_bot/upload.py` | YouTube Data API v3 resumable upload as Shorts (`#Shorts`) — free OAuth |

End-to-end:

```bash
python -m shorts_bot run --url "https://www.youtube.com/watch?v=YOUR_VIDEO"
```

---

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on `PATH`
- (Recommended free) Groq or Gemini API key for LLM clips
- (Upload) Google Cloud project with **YouTube Data API v3** + OAuth desktop client
- (Optional) `YOUTUBE_API_KEY` only for discover/search (~10k units/day free)

---

## Environment reference

Copy `.env.example` → `.env`:

| Variable | Purpose | Free? |
|----------|---------|-------|
| `GROQ_API_KEY` | Preferred LLM (OpenAI-compatible) | Yes — Groq free tier |
| `GROQ_MODEL` | e.g. `llama-3.3-70b-versatile` | — |
| `GEMINI_API_KEY` | Alternate free LLM | Yes — AI Studio |
| `GEMINI_MODEL` | e.g. `gemini-2.0-flash` | — |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Paid LLM fallbacks | Paid |
| `YOUTUBE_API_KEY` | Discover/search only | Free quota (~10k/day) |
| `GOOGLE_CLIENT_SECRETS` | OAuth desktop JSON path | Free personal project |
| `CHANNEL_ID` | Your channel id (optional) | — |
| `NICHE` / `CATEGORY` | Discover defaults | — |
| `MAX_SHORTS` | Cap clips per source (default 10) | — |
| `VISIBILITY` | `private` \| `unlisted` \| `public` | — |
| `CAPTION_STYLE` | `bold_yellow` \| `white_outline` \| `neon_pink` \| `clean_white` | — |

---

## Usage

```bash
# Offline demo (synthetic video + sample transcript → rendered Shorts, no upload)
python -m shorts_bot demo
python -m shorts_bot run --demo

# Analyze sample transcript only (heuristic)
python -m shorts_bot analyze --heuristic

# Your video → clips + render (no upload)
python -m shorts_bot clip --url "https://www.youtube.com/watch?v=YOUR_ID"

# Full pipeline (upload; default visibility=private)
python -m shorts_bot run --url "https://www.youtube.com/watch?v=YOUR_ID"

# Dry-run upload path
python -m shorts_bot run --url "..." --dry-run --skip-upload

# Upload already-rendered files
python -m shorts_bot upload-only output/YOUR_ID/*.mp4 --clips output/YOUR_ID/clips.json

# Discover only (research — do not reupload others' content; needs YOUTUBE_API_KEY)
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
