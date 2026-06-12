# `aishorts` — Core Generation Library

`aishorts` is the engine behind pdftoreel: it turns a prompt and/or input documents into finished short-form videos (talking avatars, TTS, subtitles, b-roll images, LaTeX/Manim visuals, quiz motion graphics, AI songs). It is a pure Python library with no web concerns — the FastAPI backend (`api/`) and the CLI (`cli/`) are thin consumers of it.

Public API (re-exported from `aishorts/__init__.py`):

```python
from aishorts import (
    ShortsGenerator, ShortsConfig,                      # orchestrator
    ScriptConfig, SubtitleConfig, FFmpegConfig,         # per-module configs
    ImagesConfig, LatexConfig, ManimConfig,
    QuestionConfig, SongConfig,
    VideoTemplate, TemplateConfig, SubtitleStyle,       # video templates
    Avatar, Voice,                                      # avatar model
)
```

Minimal usage:

```python
generator = ShortsGenerator(shorts_config=ShortsConfig(avatars=[...], video_template=...))
output = generator.generate_shorts(amount=1, user_input="Explain photosynthesis")
# output: ReelSeriesOutput(topic=..., thumbnail_url=..., reels=[ReelOutput(presigned_url=...), ...])
```

---

## 1. Architecture Overview

```
                              ShortsGenerator (shorts_generator.py)
                              ───────────────────────────────────
 user_input / files / links ──► SCRIPT stage   ScriptGenerator ──► LLMProvider (gemini/chatgpt/...)
                              │                 produces a ReelSeries (Pydantic, validated JSON)
                              │
                        [checkpoint .pkl ──► R2]          (thumbnails generated concurrently)
                              │
                        PRIMARY stage     per reel, concurrently:
                              │             VoiceGenerator    (TTS audio per block)
                              │             ImageGenerator    (b-roll images)
                              │             LatexGenerator    (rendered formulas)
                              │             ManimGenerator    (LLM-written animations)
                              │             SongGenerator     (AI music)
                        [checkpoint]
                              │
                        SECONDARY stage   per reel, concurrently (depends on voice):
                              │             LipsyncGenerator  (talking-head video from audio)
                              │             SubtitleGenerator (word-level forced alignment)
                              │             QuestionGenerator (quiz motion-graphic video)
                        [checkpoint]
                              │
                        COMPOSE           EditTemplate.compose() builds one FFmpeg filter
                              │           graph per reel ──► FFmpegProvider renders it
                              │           (Modal GPU/CPU, RunPod, or local ffmpeg)
                              ▼
                        ReelSeriesOutput  final MP4s in R2 under generated/, then cleanup
```

Two patterns make up almost everything in this package:

1. **Provider registry** (`modules/provider.py`) — every pluggable backend (TTS, lipsync, LLM, FFmpeg renderer, even video edit templates) is a subclass of `Provider`. Each *direct* subclass of `Provider` (e.g. `TTSProvider`, `LLMProvider`, `EditTemplate`) opens its own registry; any concrete class that sets `provider_name = "..."` auto-registers itself via `__init_subclass__`. Lookup is `TTSProvider.get("f5tts")`, listing is `TTSProvider.list_names()`. Duplicate names raise at import time.

2. **Generator façades** (`XGenerator` classes) — each module exposes a small `*Generator` class that selects a provider from config, normalizes parameters, and exposes `populate_reel(reel)`. Providers may be sync or async; `utils/async_utils.await_or_thread` awaits coroutines directly and pushes sync functions to a thread, so the pipeline stays non-blocking either way.

**The `populate_reel` contract:** every generator/provider mutates the `Reel` *in place*, writing the produced artifacts into `block.assets` (a `BlockAssets`). Each asset is stored as a **pair**: a local `*_filepath` and a remote `*_url` (R2 or provider URL). Downstream consumers always prefer the local file and fall back to the URL — this is what makes checkpoint/resume work on ephemeral hosts (Railway), where local files are gone but URLs survive inside the pickle.

URLs may be plain strings or dicts of the form `{"url": "...", "cache_key": "..."}`. The dict form is understood everywhere (`download_from_url`, `FilterGraph.add_input`, remote FFmpeg workers); `cache_key` lets remote render workers cache large static inputs like background videos (see `utils/upload_asset.py`, which prints this snippet on upload).

---

## 2. Data Model (`modules/script/script.py`)

The `ReelSeries` is the single document that flows through the whole pipeline. The LLM produces it (it is also the structured-output JSON schema), every stage enriches it, checkpoints pickle it.

```
ReelSeries
├─ topic: str
├─ thumbnail_prompt / thumbnail_url
└─ reels: list[Reel]
   ├─ title, description, thumbnail_prompt / thumbnail_url
   └─ blocks: list[Block]            Block = DialogueBlock | QuestionBlock | SongBlock
      │                              (discriminated by the `type` field)
      ├─ DialogueBlock: avatar, text, media[]
      ├─ QuestionBlock: avatar, text (question), answer,
      │                 typing/thinking/answer_duration
      ├─ SongBlock:     text (lyrics), media[]
      └─ assets: BlockAssets         (SkipJsonSchema — invisible to the LLM)
```

- **`Media`** (`ImageMedia | LatexMedia | ManimMedia`) items live on dialogue/song blocks. Each has a UUID `id` and a `Trigger {start_word_index, end_word_index}` — word indices into the block's text (0-based, inclusive) that the edit templates later convert into absolute on-screen timing using the aligned subtitles. `ImageMedia` carries search `keywords`, `LatexMedia` raw `code`, `ManimMedia` an animation `prompt`.

- **`BlockAssets`** holds everything generated for a block: `voice_filepath/url`, `lipsync_filepath/url`, `staticface_filepath/url`, `subtitles` (an OpenAI `TranscriptionVerbose` with word timestamps), `question_filepath/url`, `song_filepath/url`, plus `media_map` / `media_url_map` (`Media.id → filepath / url` for images, latex, manim).

- **`AssetType`** (script, voice, lipsync, subtitles, images, latex, question, staticface, manim, song) names every producible artifact. Two filters decide what actually gets generated:
  - each Block class declares `valid_assets` (class-level) — what *can* attach to that block type;
  - the selected edit template declares what's *required* (section 4). A generator touches a block only when its asset type is in both sets.

- **`BlockType`** (dialogue, question, song) gates what the script LLM may emit — templates declare `allowed_blocks`, and `ShortsGenerator` additionally removes `question` blocks when the QUESTION asset tag is disabled (the two are coupled: a question block without a rendered question graphic would be a hole in the video).

- **Outputs**: `ReelOutput` (title, description, local_path, presigned_url, thumbnail_url, duration `"MM:SS"`) and `ReelSeriesOutput` (topic, thumbnail_url, reels) are the only things returned to callers.

### Avatar model (`modules/avatar.py`)

```python
Avatar(
    name,                 # referenced by blocks' `avatar` field; never invented by the LLM
    instructions,         # personality text injected into the script prompt
    voice=Voice(
        provider,         # TTS provider name: "f5tts" | "modal_f5tts" | "modal_chatterbox" | "lemonfox"
        voice_id,         # for hosted-voice providers (lemonfox)
        sample_url, sample_transcript,   # for voice-cloning providers (f5tts variants)
        exaggeration, cfg_weight,        # chatterbox tuning
    ),
    lipsync_provider,     # "float"
    face_url,             # still image animated by FLOAT
    face_video_url, pads, # legacy wav2lip fields (provider currently disabled)
    static_face_path/url, # fallback still shown when lipsync is missing/disabled
    a_cfg_scale, e_cfg_scale,            # FLOAT guidance scales
)
```

Per-avatar provider selection means one reel can mix TTS/lipsync backends: `VoiceGenerator`/`LipsyncGenerator` instantiate the *set* of provider classes used by the configured avatars, and each provider's `populate_reel` only claims blocks whose avatar belongs to it.

---

## 3. The Orchestrator (`shorts_generator.py`)

### Configuration

`ShortsConfig` is the single config object:

| Field | Default | Notes |
|---|---|---|
| `avatars` | — (required) | list of `Avatar` |
| `video_template` | — (required) | `VideoTemplate(edit_template=..., template_config=...)` |
| `enabled_tags` | `None` | user-toggled optional assets (`AssetType` string values); `None` = template defaults |
| `script_config` | provider `"gemini"` | `base_instructions` defaults to `resources/base_instructions_default.txt` |
| `subtitle_config` | provider `"modal_wav2vec_aligner"` | |
| `ffmpeg_config` | provider `"modal_ffmpeg"`, profile `"very_small"`, max bitrate `2M`, audio `96k` | |
| `images_config` | provider `"unsplash"` | |
| `latex_config` | provider `"real_latex"` | |
| `manim_config` | provider `"modal_manim"` | `base_instructions` from `resources/manim_instructions_default.txt` |
| `question_config` | provider `"motion_graphic"` | |
| `song_config` | provider `"minimax"` | |

Every sub-config carries a free-form `provider_config: dict` that is splatted into the provider constructor — that's the escape hatch for provider-specific knobs (`model`, `endpoint_url`, timeouts, ...).

`ShortsGenerator.__init__` also accepts optional API keys (`tts_f5tts_api_key`, `tts_lemonfox_api_key`, `lipsync_float_api_key`, `subtitles_api_key`, `image_api_key`, `ffmpeg_api_key`, `minimax_api_key`) which are forwarded to the matching providers. Every provider also falls back to environment variables (section 8), which is how the CLI/API normally configure things.

`update_config(shorts_config)` rebuilds all generators; it is called by the constructor and can be called again to re-point an existing instance.

Construction resolves the template class via `EditTemplate.get(name)` and computes:
- `required_assets = template.core_assets + enabled tag assets` (`resolve_required_assets`),
- `allowed_blocks` (template's, minus `question` if QUESTION isn't required),

then wires template-derived parameters into the generators (image/LaTeX max sizes and styles, question graphic class, song `style_prompt`, ...).

### `generate_shorts_async(...)`

```python
await generator.generate_shorts_async(
    amount=1,                # number of reels in the series
    files=None,              # input docs: local paths, URLs, or R2 keys (uploads/…)
    links=None,              # web URLs: websites, YouTube videos, Wikipedia, RSS, …
    user_input=None,         # free-text prompt (files, links and/or user_input required)
    resume_from=None,        # checkpoint reference, see below
    mock_script=None,        # path to a ReelSeries JSON — skips the LLM entirely
    keep_assets=False,       # skip the cleanup pass (debugging)
    status_callback=None,    # async (PipelineStage, ReelSeries|None) -> None, fired after each stage
) -> ReelSeriesOutput
```

`generate_shorts(...)` is the same thing wrapped in `asyncio.run()` (no `status_callback`).

Execution order:

1. **Session setup** — a session id `run_{YYYYMMDD_HHMMSS}_{8-hex}` is created; a `logging.FileHandler` mirrors all `ShortsGenerator.*` logs to `logs/{session_id}/run.log` (also uploaded to R2 at every checkpoint and at the end).
2. **Resume (optional)** — see below.
3. **SCRIPT stage** — `ScriptGenerator.generate_script()` (or `mock_script` JSON). Checkpoint + callback.
4. **Thumbnails** — kicked off as a background task running concurrently with stages 5–6 (only when IMAGES is required). Series thumbnail from `thumbnail_prompt`/`topic`, one per reel from `thumbnail_prompt`/`description`; uploaded to `generated/thumbnails/{uuid}.png`; URLs written back into the `ReelSeries` and the SCRIPT callback re-fired. Failures are logged and ignored.
5. **Static faces** — `populate_reel_static_faces` copies each avatar's static face path/URL onto its blocks (cheap, synchronous).
6. **PRIMARY stage** — for every reel concurrently, every required primary generator concurrently: voice, images, latex, manim, song. Checkpoint + callback.
7. **SECONDARY stage** — same fan-out for lipsync, subtitles, question graphics (these need the voice audio). Checkpoint + callback.
8. **COMPOSE** — per reel: `VideoGenerator.compose(reel, session_id, output_key="generated/{uuid}.mp4")`. Remote renderers upload straight to that R2 key; the local renderer's file is uploaded by the orchestrator. Results are wrapped in `ReelOutput`s (original order preserved).
9. **Cleanup (`finally`)** — unless `keep_assets`:
   - deletes local intermediates (any asset path under `output/`) and local final files;
   - deletes intermediate R2 objects parsed out of asset URLs — *except* keys under `generated/` (finals, thumbnails) and `staticface_url` (permanent shared assets);
   - deletes the `uploads/{session_id}/` and `uploads/audio/` prefixes (scratch uploads made for remote workers).
   The run log is uploaded one last time and the session log handler detached.

### Checkpoints & resume

After each stage the whole `ReelSeries` is pickled to `logs/{session_id}/{stage}_stage.pkl` and uploaded to R2 (`logs/{session_id}/...`). `resume_from` accepts, in priority order:

1. a local `.pkl` path;
2. a local session dir (`logs/{session_id}/` — picks the highest stage present);
3. an HTTP(S) URL to a `.pkl`;
4. an R2 key ending in `.pkl`;
5. a bare session id — lists `logs/{session_id}/` in R2 and picks the highest stage.

The stage is parsed from the filename; the pipeline resumes *after* the loaded stage. Before resuming, `VideoGenerator.ensure_assets_local` re-downloads every asset whose `*_filepath` is missing locally but has a `*_url` — required on ephemeral hosts. `_load_checkpoint` re-validates the unpickled object against the *current* Pydantic schema (with several fallbacks) so old checkpoints survive model evolution.

---

## 4. Module Catalog

Each module = one pipeline capability: a `*Generator` façade + a `*Provider` registry family.

### 4.1 LLM (`modules/llm/`)

Shared abstraction for text models; used by the script generator and the Manim code generator. `LLMProvider` defines `generate_structure(instructions, files, links, user_input, response_schema)` (returns a parsed Pydantic object) and `generate_response(...)` (plain text).

**All providers share one input path:** files and links are converted to Markdown by the ingest module (see 4.1b) in the `LLMProvider` base class and embedded in the prompt — no provider-native file uploads. `minimax`/`groq`/`fireworks` share an `OpenAICompatibleChat` base (OpenAI-compatible Chat Completions).

| Provider | Default model | Auth (env) | Notes |
|---|---|---|---|
| `gemini` | `gemini-3-pro-preview` | `GEMINI_API_KEY` | `temperature=0.7, top_p=0.9` |
| `chatgpt` | `gpt-5` | `OPENAI_API_KEY` (SDK default) | Responses API (`responses.parse`) |
| `minimax` | `minimaxai/minimax-m2.5` via NVIDIA NIM | `NVIDIA_API_KEY` | |
| `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` | auto-throttles reasoning models (`gpt-oss/qwen3/deepseek-r1` → `reasoning_effort=low`, hidden format) so thinking tokens don't starve the JSON budget |
| `fireworks` | `kimi-k2-thinking` | `FIREWORKS_API_KEY` | `reasoning_effort` passthrough |

### 4.1b Ingest (`modules/ingest/`)

`ContentIngestor` converts every input source to Markdown with [MarkItDown](https://github.com/microsoft/markitdown):

- **files** — local paths, http(s) URLs, or R2 keys (non-absolute non-URL strings are presigned from R2); remote refs are temp-downloaded first. Formats: pdf, docx, pptx, xlsx/xls, csv, json, xml, html, epub, ipynb, Outlook .msg, txt/md, images, audio (wav/mp3/m4a → transcription).
- **links** — web URLs converted in place so MarkItDown's URL-aware converters apply: YouTube (metadata + transcript), Wikipedia, RSS/Atom, Bing SERP, generic HTML. Fetched with a browser User-Agent (some sites 403 the python-requests default).
- **images** — described by a vision LLM plugged into MarkItDown's `llm_client` hook: `gemma-4-31b-it` through the Gemini API's OpenAI-compatible endpoint (`GEMINI_API_KEY`; override the model with `MARKITDOWN_VISION_MODEL`). Gemma's `<thought>…</thought>` reasoning blocks are stripped from captions. Without a key, images degrade to metadata only.

### 4.2 Script (`modules/script/`)

`ScriptGenerator` assembles the system prompt from: `base_instructions` (default `resources/base_instructions_default.txt` — the retention-focused house style: 350–450 words/reel, 6–10 blocks, hooks, **no exclamation marks** (breaks TTS), no em-dashes/ellipses (merge words during alignment), media trigger rules) + an AVATARS section (per-avatar `instructions`) + MEDIA SETTINGS (latex/manim ENABLED/DISABLED) + REEL CONFIGURATION (count) + ALLOWED BLOCKS — then calls `llm.generate_structure(..., response_schema=ReelSeries)`.

Quirk to be aware of: the images rule currently renders "ENABLED" for both states (`_bool_rule` got identical strings), so the prompt never tells the model images are off — disabled image media is simply never *generated* downstream because IMAGES isn't in `required_assets`.

### 4.3 TTS (`modules/tts/`)

`VoiceGenerator` instantiates one provider per distinct `avatar.voice.provider`. Before TTS it rewrites each block's text with `expand_numbers_for_speech` ("3.14" → "three point one four", "50 000" → "fifty thousand") so pronunciation matches the later forced alignment, then **restores the original digits** so subtitles display them. Results land in `assets.voice_filepath/voice_url` (local file under `output/tts/`).

| Provider | Backend | Config / env |
|---|---|---|
| `f5tts` | RunPod serverless endpoint (voice cloning from `sample_url` + `sample_transcript`) | `F5TTS_ENDPOINT_ID`, `RUNPOD_API_KEY` |
| `modal_f5tts` | Modal web endpoint; one HTTP call per reel (worker pipelines dialogues internally) | `MODAL_F5TTS_ENDPOINT_URL`, `MODAL_API_KEY` |
| `modal_chatterbox` | Modal Chatterbox TTS; per-voice `exaggeration` / `cfg_weight` | `MODAL_CHATTERBOX_ENDPOINT_URL`, `MODAL_API_KEY` |
| `lemonfox` | LemonFox hosted voices (`voice_id`); uploads audio to R2 `lemonfox/` | `LEMONFOX_API_KEY` |

### 4.4 Lipsync (`modules/lipsync/`)

Same per-avatar fan-out keyed on `avatar.lipsync_provider`.

| Provider | Backend | Notes |
|---|---|---|
| `float` | RunPod FLOAT endpoint (`FLOAT_ENDPOINT_ID`, `RUNPOD_API_KEY`) | animates `avatar.face_url` from `voice_url`; `emotion`/`seed` kwargs, `a_cfg_scale`/`e_cfg_scale` per avatar. If the worker returns no video for a block it logs and leaves the lipsync fields empty — the edit templates then fall back to the static face. |
| (`wav2lip`) | commented out, kept for reference | |

`populate_reel_static_faces(reel, avatars)` (module-level, called by the orchestrator outside any provider) fills `staticface_filepath/url` from `avatar.static_face_url/path`, falling back to `face_url`.

### 4.5 Subtitles (`modules/subtitles/`)

Produces an OpenAI `TranscriptionVerbose` (word-level timestamps) per voiced block, stored in `assets.subtitles`. The default provider is a **forced aligner** — it aligns the *known* script text to the audio rather than transcribing, so subtitles always match the script.

| Provider | Backend | Notes |
|---|---|---|
| `modal_wav2vec_aligner` (default) | Modal wav2vec2 forced alignment (`MODAL_WAV2VEC_ENDPOINT_URL`, batch URL auto-derived `…-batch.modal.run`, `MODAL_API_KEY`) | uploads audio to R2 `uploads/audio/` and sends a presigned URL. Builds an *alignment plan* (`_build_alignment_plan`): display tokens (digits intact, thousands groups kept whole) are mapped to the spelled-out words the character-level aligner actually sees, then each display token absorbs its N aligned spans — subtitles show "2026" with the timing of "two thousand twenty six". Gaps shorter than `min_silence_duration` are bridged. |
| `whisper` | Whisper `verbose_json` word timestamps via LemonFox (`use_lemonfox=True`, `LEMONFOX_API_KEY`) or OpenAI (`OPENAI_API_KEY`) | true transcription (output may drift from script) |
| `elevenlabs` | ElevenLabs forced alignment (`ELEVENLABS_API_KEY`) | options: `display_silence`, `min_silence_duration`, `remove_chars` |

`normalize_alignment_text` replaces em/en-dashes and ellipses with `", "` so glued words ("chaos—no") don't collapse into a single aligned token.

### 4.6 Images (`modules/image/`)

`ImageGenerator.populate_reel` fills `media_map/media_url_map` for `ImageMedia` items, then post-processes every image with `style_image` (template-driven `ImageStyle`: rounded corners, drop shadow) capped to the template's `max_image_width/height`.

| Provider | Backend | Notes |
|---|---|---|
| `unsplash` (default) | Unsplash search API (`UNSPLASH_API_KEY`) | picks the first result not already used in this reel (dedup), requests PNG at target size, keeps alt text |
| `runpod_ai` | RunPod public `z-image-turbo` text-to-image (`RUNPOD_API_KEY`) | async submit + status polling |

**Fallback chain:** any media item the primary provider couldn't satisfy is retried through `RunPodAI` automatically. The same applies to thumbnails (`generate_thumbnail`: provider → RunPodAI → center-crop 9:16 → JPEG q80).

### 4.7 LaTeX (`modules/latex/`)

Renders `LatexMedia.code` to PNGs (sized by template `latex_width/height`, styled like images). Results upload to R2 `latex/`.

| Provider | Backend | Notes |
|---|---|---|
| `real_latex` (default) | real `pdflatex` (standalone class; amsmath/amssymb/chemfig/mhchem preloaded) → PNG | compile hardened with `-no-shell-escape` + `-interaction=nonstopmode` in an isolated temp dir, because the LaTeX body is LLM-generated from user input |
| `matplotlib` | matplotlib mathtext | no TeX installation needed; auto-shrinks font until the formula fits |

### 4.8 Manim (`modules/manim/`)

`ManimGenerator` is a two-step pipeline: an LLM (its own `LLMGenerator`, default provider `minimax`; model overridable via `manim_config.provider_config`) writes Manim code from `ManimMedia.prompt` using `manim_instructions_default.txt`, the code is validated (must define `class GenScene`; `ast.parse` syntax check) and rendered. Up to 3 attempts, feeding the previous error back into the prompt. **Render failures are non-fatal** — the media item is skipped and the video composes without it.

| Provider | Backend |
|---|---|
| `modal_manim` (default) | Modal endpoint (`MODAL_MANIM_ENDPOINT_URL`, `MODAL_API_KEY`), quality `-qh` |
| `local_manim` | local `manim` CLI in a temp dir |

### 4.9 Questions & Motion Graphics (`modules/question/`, `modules/motion_graphic/`)

For each `QuestionBlock`, the `motion_graphic` provider renders an animated quiz card video: an HTML/CSS/JS `MotionGraphic` (currently `BasicQuestion` — typing effect → countdown → answer reveal, on a solid **magenta `#FF00FF`** background that the edit templates chroma-key out) is screenshotted frame-by-frame and stitched with ffmpeg.

- Renderer selection: injected instance → `ModalMotionGraphicRenderer` if `MODAL_MOTION_GRAPHIC_ENDPOINT_URL` is set → `LocalMotionGraphicRenderer` (Playwright/Chromium, parallel pages).
- The typing-phase duration is synced to the question's voiceover length; the actual durations are written back onto the block so the edit template computes the same segment length.
- Output goes to `output/question/` + R2 `question/`. Failures null the asset fields, and the block is simply skipped during compose.
- The graphic class comes from `TemplateConfig.question_graphic` (registry in `TemplateConfig.get_question_graphic_class`).

### 4.10 Songs (`modules/song/`)

For `SongBlock`s: `minimax` provider calls MiniMax `music-2.5` (`MINIMAX_API_KEY`) with `lyrics=block.text` and `prompt=TemplateConfig.style_prompt` (default "pop music, Female vocals"); mp3 saved to `output/songs/`, uploaded to R2 `songs/`.

---

## 5. Video Composition (`modules/video_edit/`)

### EditTemplate (the template family)

`EditTemplate` is itself a `Provider` family — registered by name, selected by `VideoTemplate.edit_template`. Each template declares its asset contract:

```python
core_assets: list[AssetType]        # always generated, hidden from users
tag_assets:  dict[AssetType, bool]  # user-toggleable tags with default state
allowed_blocks: list[BlockType]     # what the script LLM may emit
```

and implements two methods: `_get_block_segment(block)` (maps a block to a timeline segment `{type, video, audio, duration}`, resolving local-path-or-URL, with duration fallbacks from ffprobe → subtitles → question phase durations) and `compose(reel)` (returns an `FFmpegCommand`).

Built-in templates:

| Template | Core assets | Tags (default) | Blocks | Look |
|---|---|---|---|---|
| `gameplay` | script, voice, lipsync, subtitles, images, latex | manim ✓, question ✓ | dialogue, question | square avatar video pinned to top over 1080×1920 background gameplay footage |
| `alpha_gameplay` | same as gameplay | manim ✗, question ✗ | dialogue, question | avatar chroma-keyed (`TemplateConfig.chromakey_*`, despill) and composited at the bottom of the frame |
| `static_gameplay` | script, voice, **staticface**, subtitles, images, latex | manim ✗, question ✗ | dialogue, question | no lipsync at all — looped static face + voice audio (cheapest) |
| `song` | script, song, subtitles, images, latex | manim ✓ | song | background video + media overlays + karaoke-able subtitles over the generated song |

Shared composition flow (`compose`):
1. `collect_segments_and_timings(reel)` walks the blocks, builds the segment list, shifts each block's word timestamps by the running offset into one absolute timeline, appends a `.` to each block's last word (forces a subtitle-group boundary; `.` is also in `remove_chars` so it never displays), merges everything into one `TranscriptionVerbose`, and resolves every media trigger into `MediaTiming{filepath,url,start,end}` (out-of-range or missing triggers fall back to the whole block).
2. Subtitles are rendered to an `.ass` file (`transcription_to_ass`): 1080×1920 playfield, styled by `SubtitleStyle` (defaults: Poppins 250, white with black stroke, center alignment, `max_chars_per_line=1` ⇒ effectively one word per cue, optional karaoke per-word highlight in `secondary_color`).
3. A `FilterGraph` is built: per-segment scaling/keying/padding → `concat` → `loudnorm` audio → background video scaled/cropped to 1080×1920 → avatar overlay → one `overlay` per media item with fade + horizontal slide animations (`Animator` produces the FFmpeg `t`-expressions; manim videos get PTS-shifted and optionally rounded corners) → `ass` subtitles → optional background `music` at 0.2 volume.

`FilterGraph`/`FilterNode` are a tiny fluent builder that frees templates from manual `[0:v]`-index bookkeeping; `build()` returns an `FFmpegCommand{inputs, args, video_codec, input_labels}` whose inputs are resolved by the renderer.

### FFmpeg renderers (`ffmpeg_providers.py`)

`VideoGenerator` glues a template to a renderer: `compose()` calls `template.compose(reel)` then `renderer.render(cmd, filename, session_id, output_key)`. (For `local_ffmpeg` it first runs `ensure_assets_local`.)

| Provider | Where it runs | Input handling | Env |
|---|---|---|---|
| `modal_ffmpeg` (default) | Modal — **routes by codec**: NVENC jobs → GPU endpoint, libx264 → CPU endpoint | uploads local inputs *and local file paths found inside filter args* (`.ass/.srt/.png/...`) to R2 `uploads/{session}/`, replaces them with presigned URLs; worker uploads the result straight to `output_key` and returns its duration | `MODAL_FFMPEG_GPU_ENDPOINT_URL`, `MODAL_FFMPEG_CPU_ENDPOINT_URL` (legacy `MODAL_FFMPEG_ENDPOINT_URL`), `MODAL_API_KEY` |
| `runpod_ffmpeg` | RunPod serverless | same R2 upload dance for inputs | `FFMPEG_ENDPOINT_ID`, `RUNPOD_API_KEY` |
| `local_ffmpeg` | this machine | uses local paths, URLs passed straight to ffmpeg; probes NVENC with a real test encode, else libx264 | — |

Compression is centralized in `FFmpegProvider.get_compression_options`: `compression_profile` ∈ `high_quality | balanced | small | very_small` maps to CQ (NVENC: 21/26/30/35) or CRF (x264: 20/24/28/35), overridable via `quality_value` / `encoder_preset`, plus `max_video_bitrate` cap and `audio_bitrate` — all surfaced on `FFmpegConfig`. Explicit quality flags already present in the args win.

---

## 6. Utilities (`utils/`)

- **`r2_handler.CloudflareR2`** — the storage backbone (S3 API against Cloudflare R2): `upload_file` (returns public URL — `https://{R2_PUBLIC_DOMAIN}/key` or presigned fallback), `download_file`, `list_keys`, `create_presigned_url`, `copy_file`, `delete_file`, `delete_prefix`, `get_key_from_url`. On first construction it measures clock skew against the endpoint's `Date` header and patches botocore if it exceeds 10 s (fixes presign failures on machines with bad clocks). Configurable via `BucketConfiguration` or env. Module-level `download_from_url(url|{"url":...}, ...)` downloads with 3 retries and exponential backoff.
- **`runpod_caller.EndpointCaller`** — minimal RunPod serverless client (submit + 2 s status polling + timeout), used as a mixin by RunPod-backed providers.
- **`async_utils.await_or_thread(func, ...)`** — the sync/async bridge described above.
- **`image_utils`** — `ImageStyle` (corner_radius, shadow blur/offset/color/opacity), `style_image` (resize + rounded corners + drop shadow), `crop_to_aspect_ratio`/`crop_to_9_16`/`crop_to_16_9`.
- **`pydantic_helper`** — `load_pydantic(_dict)` for JSON config files (used by the CLI for `avatars.json` / `video_templates.json`), `find_by(items, name=...)`.
- **`upload_asset.py`** — `python -m aishorts.utils.upload_asset <file> [--key ...]` helper for pushing big static assets (background videos) to R2; prints the `{"url", "cache_key"}` snippet for template configs.
- **`provider.MediaFile`** — `{id, url, path}` with `ensure_local(_async)` lazy download.

---

## 7. Storage Layout

Local (all relative to CWD; everything under `output/` is deleted by cleanup):

| Path | Contents | Override env |
|---|---|---|
| `output/tts/` | TTS audio | `TTS_OUTPUT_DIR` |
| `output/lipsync/` | lipsync videos | `LIPSYNC_OUTPUT_DIR` |
| `output/image/` | b-roll images | `IMAGE_OUTPUT_DIR` |
| `output/latex/` | rendered formulas | `LATEX_OUTPUT_DIR` |
| `output/manim/` | manim renders | `MANIM_OUTPUT_DIR` |
| `output/question/` | question graphics | `QUESTION_OUTPUT_DIR` |
| `output/songs/` | songs | `SONG_OUTPUT_DIR` |
| `output/videos/` | final renders (when downloaded) | `VIDEO_OUTPUT_DIR` |
| `output/static_faces/` | downloaded static faces | — |
| `logs/{session_id}/` | `run.log` + `{stage}_stage.pkl` checkpoints | — |
| `logs/_resume/` | downloaded checkpoints | — |

R2 key prefixes:

| Prefix | Contents | Lifecycle |
|---|---|---|
| `generated/` | **final videos + thumbnails** | permanent; never deleted by cleanup |
| `logs/{session_id}/` | checkpoints + run log | kept for debugging/resume |
| `uploads/{session_id}/` | scratch inputs for remote renderers | deleted at end of run |
| `uploads/audio/` | aligner audio uploads | deleted at end of run |
| `lipsync/`, `latex/`, `question/`, `songs/`, `lemonfox/` | intermediate provider outputs | deleted at cleanup (via URL→key) |
| `assets/` | permanent shared assets (bg videos, faces) | manual, via `upload_asset.py` |

---

## 8. Environment Variables

Storage (required for almost everything): `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_DOMAIN` (optional — presigned URLs otherwise), `CLOUDFLARE_OUTPUT_DIR`.

| Concern | Variables |
|---|---|
| LLMs | `GEMINI_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY` (minimax/NIM), `GROQ_API_KEY`, `FIREWORKS_API_KEY` |
| Modal workers | `MODAL_API_KEY` + per-service URLs: `MODAL_F5TTS_ENDPOINT_URL`, `MODAL_CHATTERBOX_ENDPOINT_URL`, `MODAL_WAV2VEC_ENDPOINT_URL` (+`_BATCH_`), `MODAL_MANIM_ENDPOINT_URL`, `MODAL_MOTION_GRAPHIC_ENDPOINT_URL`, `MODAL_FFMPEG_GPU_ENDPOINT_URL`, `MODAL_FFMPEG_CPU_ENDPOINT_URL` |
| RunPod workers | `RUNPOD_API_KEY` + `F5TTS_ENDPOINT_ID`, `FLOAT_ENDPOINT_ID`, `FFMPEG_ENDPOINT_ID` |
| Hosted services | `UNSPLASH_API_KEY`, `LEMONFOX_API_KEY`, `ELEVENLABS_API_KEY`, `MINIMAX_API_KEY` |

Only the keys for providers actually selected in the config are needed.

---

## 9. Extending

**New provider** (e.g. a TTS backend):

```python
class MyTTS(TTSProvider):                      # subclass the family base
    provider_name = "my_tts"                   # auto-registers under this name

    def __init__(self, avatars, **kwargs): ...
    async def populate_reel(self, reel: Reel) -> None:
        # for each block where AssetType.VOICE in block.valid_assets
        # and the block's avatar uses this provider:
        #   set block.assets.voice_filepath AND block.assets.voice_url
```

Rules of the contract: mutate the reel in place; always set both the local path and a durable URL (upload to R2 if the backend doesn't give you one); only claim blocks that belong to you (asset validity + avatar/provider match); make the module importable from the package so registration runs (provider modules are star-imported by their generators).

**New edit template:** subclass `EditTemplate`, set `provider_name`, declare `core_assets` / `tag_assets` / `allowed_blocks`, implement `_get_block_segment` + `compose` using `FilterGraph`/`Animator`. The asset declaration automatically drives the upstream pipeline — script prompt rules, which generators run, and which user tags appear.

**New question graphic:** subclass `MotionGraphic` (HTML + `updateFrame`-style JS hook) and add it to the registry in `TemplateConfig.get_question_graphic_class`.

---

## 10. Consumers & Testing

- **CLI** (`cli/main.py`): `python cli/main.py --template gameplay --avatars Alice Bob --input "..." [--files ... --links ... --amount N --llm_provider gemini --model ... --resume_from ... --mock_script ... --keep_assets]`. Avatars/templates come from `cli/configs/avatars.json` and `cli/configs/video_templates.json` (loaded with `pydantic_helper`).
- **API** (`api/`): stores `Avatar`/`VideoTemplate` configs in the DB, builds a `ShortsConfig` per job, and runs `generate_shorts_async` in a background task with a `status_callback` updating job state. See `api/README.md`.
- **Tests**: `tests/` unit tests mock the providers; `tests/integration/` hits real backends (`test_pipeline.py` runs the full flow; `regenerate_video.py` re-composes from a checkpoint).

### Behavioral invariants worth knowing

- Script text must avoid exclamation marks, em-dashes and word-gluing ellipses — the TTS and alignment stages depend on it (enforced by prompt, normalized defensively in `subtitle_providers`).
- Digits are expanded only transiently for TTS; the canonical block text keeps digits, and the aligner's plan maps timings back onto digit tokens.
- Every stage is resumable; anything written to `block.assets` must therefore be URL-backed to survive resume on a fresh machine.
- Lipsync is best-effort: a missing lipsync video degrades to static-face-plus-audio, a failed question render drops the block, a failed manim render drops the overlay — composition never hard-fails on a single asset.
- `generated/` is the only R2 prefix treated as permanent output; put nothing temporary there.
