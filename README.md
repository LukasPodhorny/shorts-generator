# pdftoreel

AI short-form video generator. **One prompt/file → a finished engaging short** — talking avatars, TTS, subtitles, b-roll images, Manim/LaTeX, background music etc.

- Landing page: [pdftoreel.com](https://pdftoreel.com)
- App: [app.pdftoreel.com](https://app.pdftoreel.com)

## Layout

- `src/aishorts/` — core generation library (`ShortsGenerator` orchestrating script → TTS → avatar → images → subtitles → video edit). See `src/aishorts/README.md` for full documentation.
  - `modules/` — pipeline stages: `llm`, `script`, `tts`, `avatar`, `lipsync`, `image`, `manim`, `latex`, `subtitles`, `song`, `motion_graphic`, `video_edit`.
  - `resources/` — default prompts, fonts, configs.
- `api/` — FastAPI backend for `app.pdftoreel.com` (Firebase auth, credits, jobs, Cloudflare R2 storage, Stripe). See `api/README.md`.
- `cli/` — local CLI entry point (`cli/main.py`) for running generations without the API.
- `alembic/` — DB migrations (Postgres in prod, SQLite locally).
- `tests/` — pytest suite.