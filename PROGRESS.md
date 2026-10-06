# PROGRESS

## 2026-10-07 — retired free-tier model ids (scan of Dave's repos)
- Groq default `llama-3.3-70b-versatile` -> `openai/gpt-oss-120b`: Groq retired the Llama 3.x ids for free/developer tiers on 2026-08-16
  (console.groq.com/docs/deprecations). gpt-oss is a reasoning model, so requests send `reasoning_effort: low`.
- Gemini default `gemini-2.0-flash` -> `gemini-2.5-flash`: 2.0 Flash was shut down on 2026-06-01 (ai.google.dev/gemini-api/docs/deprecations);
  2.5 Flash is stable, has no shutdown date announced and keeps a free tier.
- Not changed: `gpt-4o-mini` / `claude-3-5-haiku-latest` defaults are paid providers (only used if you add those keys) — set
  OPENAI_MODEL / ANTHROPIC_MODEL in .env if they stop working.
- Tests: 12 passed (2 new: retired-id guard, gpt-oss request shape). Not run against the live APIs (no keys used).
