# Výstup 2: nové video šablony a moduly

Výstup rozšiřuje generátor o výuková a komentovaná videa ve formátech 16:9 a 9:16. Čtyři šablony využívají strukturované výukové snímky; Math umí také animace Manim přes celou obrazovku. Stock Story přehrává videozáběry přes celou obrazovku s hlasovým komentářem. Backend vybírá šablonu podle tématu, cílové skupiny a požadovaného formátu; ruční volba uživatele má přednost. Součástí jsou reprodukovatelné ukázky, testy skutečného renderování a tento popis zapojení.

## Templates

- **`lecture`**: 1920 × 1080. Warm paper palette, aligned text and photo columns, and horizontal layouts for short processes and comparisons. For courses, academic explanations and workplace training.
- **`documentary`**: 1920 × 1080. A matte linen background with a large panel for footage or illustration. Stock footage is enabled by default. A missed search produces a complete teaching slide without an empty footage panel.
- **`briefing`**: 1080 × 1920. A matte evergreen background with stacked photography and teaching notes. The renderer uses larger text and figures for short, text-only scenes. Bundled Inter and DejaVu Sans fonts support Czech diacritics.
- **`math`**: 1920 × 1080. A focused lesson with clean teaching slides, equations, and full-screen Manim animations during the relevant spoken words. The slide returns after each animation. Best for a worked example, graph, construction, or changing quantity.
- **`stock_story`**: 1920 × 1080. Stock footage fills every frame while the selected avatar's voice narrates. Optional subtitles sit over the footage. No visible avatar, slides, sidebars or title cards. Every scene requires a matching clip; a missing clip fails generation with a clear error.

All five use the selected avatar's **voice** without a visible avatar, lipsync or gameplay. The formal writing brief replaces the default entertainment brief; Math adds a worked-example brief and Stock Story has a separate voiceover and footage brief. Additional custom script instructions are retained.

The Edit tab shows the template name and aspect ratio. Hover over the info icon or activate it to see the description. Widescreen previews and video thumbnails keep their original aspect ratio. The player's Details & credits view includes clickable footage attribution.

## Install the catalog entries

Deploy the backend and web changes together. No database schema migration is required: template specifications remain JSON, and the public catalog's new description/width/height fields are computed from the registered template class.

```bash
# Inspect additions without changing the database.
python -m api.install_formal_templates

# Add only missing formal templates; preserve existing configurations and prices.
python -m api.install_formal_templates --apply
```

The installer reads the existing `DATABASE_URL`. It inserts the five entries at **1 credit per video**, matching the existing default; adjust prices through the existing admin interface if required. If a `field_guide` row was installed earlier, it is renamed to `stock_story` with its price preserved and its old preview URLs cleared. Existing CLI configurations also include the new names.

The web build includes small preview MP4s and PNGs. For absolute preview URLs usable by API/MCP clients, upload these through the existing R2 configuration during initial installation:

```bash
python -m api.install_formal_templates --apply --previews web/public/template-previews
```

To refresh preview URLs for existing entries while preserving their configuration and price, run:

```bash
python -m api.install_formal_templates --apply --previews web/public/template-previews --refresh-previews
```

Preview URLs contain a content hash so cached originals do not mask a new design.

## Slide module

The `slides` module turns typed `SlideMedia` into PNG assets. It uses the same provider registry as other modules:

- `pillow` (default): deterministic CPU rendering in the application worker. No API key, GPU, browser, or additional service is needed.
- `modal_slides`: optional remote execution of the same renderer, returning a PNG over authenticated HTTP.

The renderer supports `title`, `bullets`, `process`, `comparison`, `chart`, and `quote`, plus seven layouts the script writer can select by content.

- `spotlight` gives a photo, illustration, or clip a larger crop beside a headline or above it in portrait videos.
- `timeline` aligns two to four chronological milestones on a rail that changes orientation to fit the available width.
- `metrics` gives one to three figures large type with supporting labels. Set each item's `heading` to the value including units and `body` to what the figure measures.
- `donut` plots two to five positive `chart` values as shares of a whole. The renderer derives the percentages from their total.
- `line_chart` plots two to six ordered observations at their numeric `x` positions. It uses `x_unit`, `unit`, and a required source, so uneven intervals remain visually uneven.
- `proportion` shows two to five positive parts on one horizontal scale. It is a simpler view of shares than a donut when comparing lengths helps the explanation.
- `cycle` connects three or four short stages that repeat. Use `process` for steps with an end.

Comparisons contain two equally styled alternatives. Process steps are numbered. Bar charts support positive and negative values and share a zero baseline. Charts and metrics require a source label. The writing instructions prohibit invented factual data and citations and require illustrative figures to be labelled.

Text uses actual glyph measurements, wrapping and bounded font reduction. Dense content fails validation instead of being silently cropped or made unreadably small. Before paid assets are generated, the formal script validator checks both the visual-panel layout and the full-slide fallback. The LLM gets a validation error and a corrective retry; Math allows up to four total attempts because structured lessons can need more correction. The renderer accepts structured data only, with no model-generated HTML or executable code.

Each narration block in Lecture, Documentary, Briefing and Math contains exactly one slide. In the first three templates, one supporting visual fills the scene, while two share it. The backend can use a valid word index for the changeover and otherwise divides the scene in script order. A single remaining visual fills the panel if the other asset is unavailable. Math permits one supporting visual per scene. Manim starts from a visible first frame at its narration cue, plays in full, holds the result, and then reveals the block's recap slide. The small markers in the header identify scenes; elapsed playback time is shown by the video player's controls.

Images and equations are available on Lecture, Documentary and Briefing. The script writer uses them where they support the narration. Unsplash remains the default image provider, with photographer credit and a profile link. Documentary and Briefing request editorial compositions when a profile selects `runpod_ai`. Profiles can set `images_config.provider_config.scene_style` to replace the default art direction. Photos and footage fill the panel with a centred crop. Equations and teaching animations are fitted to preserve labels. Missing images fall back to the slide. [Unsplash API guidelines](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines)

Math aims for a complete 3-5 minute lesson around one worked problem unless the user requests a short recap. For a broad topic, the writer chooses a representative question instead of listing every related formula. With Manim enabled, the storyboard needs roughly one animation per three scenes, normally four to six, and the renderer retries clips shorter than eight seconds. List-like Manim recap slides are reduced to a single takeaway; consecutive or excessive bullet/process slides trigger a rewrite. A slide-only scene ends with two seconds of reading time. In a Manim scene, the first frame remains on screen until the spoken cue, the complete animation plays, the final frame stays for at least three seconds, and the recap slide remains for at least three seconds. Voice stays at its natural speed, while audio is padded with quiet review time and captions remain aligned to spoken words. Animations fit the whole frame without cropping and leave the caption area clear. Slide validation checks the full slide and the equation-panel version so the slide remains readable if an optional equation is absent. A Manim render or upload failure stops generation instead of silently omitting a promised animation. The animation is uploaded to R2 so a restored checkpoint can compose the final video on another worker.

For Math, configure the existing `modal_manim` provider with `MODAL_MANIM_ENDPOINT_URL` (and `MODAL_API_KEY` if your endpoint requires it), or select `local_manim` on a worker with the `manim` command installed. The worker checks availability before starting. The Manim code writer uses the existing `manim_config.provider_config.llm_provider` setting, defaulting to `minimax`; configure its credentials and model as for other Manim jobs. The default Math palette is paper with teal highlights. The Manim prompt receives the chosen presentation palette and accent colour. Disable the Manim tag to make a slides-and-equations-only Math lesson without a Manim service.

Example block (the trigger covers its six narration words):

```json
{
  "type": "dialogue",
  "avatar": "Narrator",
  "text": "Observe a pattern and test it.",
  "media": [{
    "type": "slide",
    "layout": "process",
    "title": "From observation to evidence",
    "subtitle": "",
    "items": [
      {"heading": "Observe", "body": "Notice a pattern."},
      {"heading": "Test", "body": "Check your explanation."}
    ],
    "trigger": {"start_word_index": 0, "end_word_index": 5}
  }]
}
```

`PresentationStyle` in `template_config.presentation_style` controls the palette (`paper`, `midnight`, `slate`, `linen`), six-digit hex accent colour, caption visibility, and background music volume. The narration reads the opening slide headline before the introduction. Captions appear on a translucent dark background only while text is displayed. Output dimensions are fixed per template to preserve readable layouts. Alignment still runs when captions are hidden because visual triggers use word timestamps.

Stock Story has no slide content or on-screen headline. It uses the selected voice, full-frame video crops and larger captions; the subtitle visibility and music volume settings still apply. Each dialogue block contains exactly one `stock_video` media item. The script is checked before asset generation, and a missing stock provider or clip stops the job rather than replacing footage with a slide. Footage sources are reserved across a video, including when different searches return the same source. If no unused clip remains, generation fails rather than repeating a shot. Configure `PIXABAY_API_KEY` and `REDIS_URL`, `PEXELS_API_KEY`, or a licensed local `STOCK_VIDEO_MANIFEST` before selecting it.

## Stock video module

`StockVideoMedia` contains only `keywords` and the existing word trigger. The script cannot choose a file path or download URL.

- **`auto`** (default): use Pexels when `PEXELS_API_KEY` is present, otherwise Pixabay when `PIXABAY_API_KEY` is present, otherwise the local library.
- **`library`**: search an operator-curated JSON manifest of licensed local files. Requires no external service. Other templates omit footage when the library is empty; Stock Story requires a populated library.
- **`pixabay`**: search the [Pixabay video API](https://pixabay.com/api/docs/) for age-safe film footage. Requires `PIXABAY_API_KEY`; Redis caches API searches for 24 hours when `REDIS_URL` is set, and API generation uses the app database for the same cache when Redis is absent. Each search requests up to 100 results, and scenes reserve distinct source videos across a reel. The provider selects a bounded HD rendition in the video's orientation, retries rate limits/server errors, checks download hosts and redirects, caps downloads at 120 MiB, and verifies the video stream with ffprobe. The API key is sent only to Pixabay's search endpoint. The app downloads selected clips to its own storage and records the contributor, source page, and license.
- **`pexels`**: search the [Pexels video API](https://www.pexels.com/api/documentation/) with the video's orientation. Explicit selection requires `PEXELS_API_KEY`. The provider selects a bounded HD rendition, retries rate limits/server errors, checks download hosts and redirects, caps downloads at 120 MiB, and verifies the video stream with ffprobe. Authentication is sent only to the API endpoint.

For Heroku, create a Pixabay account, sign in to the [API documentation](https://pixabay.com/api/docs/), and copy the key displayed beside the video search endpoint. Add `PIXABAY_API_KEY` in the app's Dashboard Settings → Config Vars. API generation caches searches in Postgres when Redis is absent. Then install the Stock Story catalog entry and preview with `heroku run --app pdftoreel-api -- python -m api.install_formal_templates --apply --previews web/public/template-previews`. Keep the key out of source control and browser code.

Downloads use a 45-second request timeout and at most two simultaneous clip requests by default. Stock audio is never mixed into narration. Short clips hold their final frame; long clips are trimmed to their trigger window. Source identity and license are stored with the checkpoint. Slide templates show creator/provider credit in the video footer; all templates include full attribution and links in the final description. Preserve these credits when redistributing a video. Pixabay allows use of edited footage with narration, but not redistribution of raw clips or certain uses involving recognizable people, brands, or misleading claims. See the [Pixabay API rules](https://pixabay.com/api/docs/), [Pixabay Content License](https://pixabay.com/service/terms/), [Pexels API guidelines](https://www.pexels.com/api/documentation/), and [Pexels license](https://www.pexels.com/license/).

Library example:

```json
[
  {
    "path": "laboratory.mp4",
    "keywords": ["laboratory", "microscope", "research"],
    "creator": "Your organisation",
    "source_url": "https://example.org/media/laboratory",
    "license": "Owned by your organisation"
  }
]
```

Set `STOCK_VIDEO_MANIFEST` to its path, or pass `manifest_path` in the provider configuration. Clip paths must stay inside the manifest's directory. Originals are copied to managed output paths, so pipeline cleanup cannot delete library masters. Library selection uses matching keyword tokens; curate tags in English to match the script's search terms. The included cloud library is for the examples, not a generic fallback for unrelated topics.

Stock Story enforces `failure_mode: "error"`; other templates default to `"fallback"` and continue with a slide when optional footage fails. Storage upload failures remain fatal so an apparently successful checkpoint cannot lose its assets on an ephemeral worker.

## Backend integration and providers

```mermaid
flowchart LR
    A[Request and source material] --> B[Intent parser: template and tags]
    B --> C{Selected template}
    C -->|Lecture, Documentary, Briefing, Math| D[Script and slide layout validation]
    C -->|Stock Story| E[Voiceover and required clip validation]
    D --> F[TTS, requested media and alignment]
    E --> G[TTS, stock footage and alignment]
    F --> H[Slide rendering]
    H --> K[Math: optional Manim animation]
    K --> I[FFmpeg composition]
    G --> I
    I --> J[R2 video, thumbnail and credits]
```

Template descriptions enter the existing REST/MCP intent parser catalog. It can distinguish formal widescreen lessons, footage-led explainers, portrait briefings and entertainment formats. Manual selections retain priority.

`StockVideoGenerator` runs in PRIMARY alongside TTS and other media. `SlideGenerator` runs in SECONDARY for the slide templates, after footage availability is known. Both write into `BlockAssets.media_map` and `media_url_map`, using the normal local/remote asset-pair contract. Provenance is stored in `media_attributions`. Slide templates render a slide thumbnail; Stock Story extracts a 16:9 cover frame from its first clip. Neither needs an image API. Checkpoint JSON, restoration on a fresh worker, final descriptions and cleanup include these new artifacts.

The worker instantiates the providers for the selected template and asset tags. The image provider runs when the script calls for images. Narration and word alignment continue to use your existing providers. Formal exports default to the high-quality compression profile with a 6 Mbps video cap unless explicitly overridden. FFmpeg normalises audio channels/sample rates, pads each scene to a video-frame boundary, and keeps captions outside the teaching content. A scene is trimmed **after** overlay composition, avoiding the framesync EOF stall reproduced during longer-footage testing. Local renders have a configurable 1800-second timeout and terminate their subprocess on timeout/cancellation.

The live script smoke check exposed a retired existing Gemini default. The provider now defaults to `gemini-3.1-pro-preview`, following [Google's migration guidance](https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-preview). Generation profiles that explicitly pin `gemini-3-pro-preview` must also be updated; explicit model selections are preserved.

A live check also passed through the existing Groq provider using `openai/gpt-oss-120b`: it generated three formal scenes, exercised the corrective retry, and passed the slide/trigger/overflow validator. To use that configuration with `GROQ_API_KEY`, include the following in the generation profile:

```json
{
  "script_config": {
    "provider": "groq",
    "provider_config": {"model": "openai/gpt-oss-120b"}
  }
}
```

This model supports the strict structured-output contract used by the existing provider; see [Groq structured outputs](https://console.groq.com/docs/structured-outputs). Live validation checks the script contract, not independent factual or linguistic accuracy.

New `ShortsConfig` fields are also accepted by database `GenerationConfig` profiles:

```json
{
  "slides_config": {
    "provider": "pillow",
    "provider_config": {"max_concurrent": 3}
  },
  "stock_video_config": {
    "provider": "auto",
    "provider_config": {"max_concurrent": 2, "failure_mode": "fallback"}
  }
}
```

Keep `upload: true` (the default) for production checkpoints. `upload: false` is intended for local demos/tests only. Provider API keys belong in environment variables, not script JSON or the public catalog.

CLI example using an existing configured voice:

```bash
python cli/main.py --template lecture --avatars YOUR_EXISTING_AVATAR \
  --input "Create a formal lesson on the water cycle"
```

## Optional Modal deployment

The default Pillow renderer runs in the normal worker and needs no deployment. To offload it:

1. Install the Modal CLI in your deployment environment and authenticate it.
2. Create a Modal secret named `aishorts-slides` with a randomly generated `MODAL_SLIDES_API_KEY`.
3. From the repository root, run `modal deploy scripts/modal_slides.py`.
4. Set `MODAL_SLIDES_ENDPOINT_URL` to the returned ASGI endpoint URL (including `/`) and set the matching `MODAL_SLIDES_API_KEY` on the application worker.
5. Set `slides_config.provider` to `modal_slides` in the selected generation profile.

The service uses one CPU, 1 GiB of memory, a 90-second execution timeout and at most four containers. It installs the same package and bundled fonts, accepts at most 64 KiB of structured input, validates the bearer token, and returns image/png. It mounts only project source, packaging metadata and README, never `.env`. The client enforces its own timeout, PNG size limit and image-dimension checks. No R2 credentials are needed in the slide service; the application uploads its result.

Redeploy the slide service with the worker when updating the slide design so the generated slide and composited media use the same coordinates.

Existing Modal FFmpeg endpoints can render the new filter graphs. Ensure their FFmpeg build includes `ass`, `loop`, `overlay`, `tpad`, `concat`, `dynaudnorm` and the standard audio/scale filters, plus `fonts-dejavu-core` for captions. Your existing endpoint URLs and selection remain unchanged. Reference: [Modal images](https://modal.com/docs/guide/images), [Modal web endpoints](https://modal.com/docs/guide/webhooks), [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html).

## Samples and verification

The reproducible examples use local `espeak-ng` speech and estimated word timing to avoid paid APIs. Production retains your existing TTS and forced-alignment providers. These samples demonstrate templates/modules and rendering; they do not establish the quality of any live speech service.

```bash
python scripts/render_formal_examples.py \
  --stock-manifest examples/formal/stock/manifest.json \
  --previews web/public/template-previews
```

Outputs are `output/formal-examples/{lecture,documentary,briefing,math,stock_story}.mp4`, their thumbnails, editable `.script.json` examples and populated `.checkpoint.json` files. The previews include short excerpts from the scenes. The Math example opens on a slide, then uses a deterministic local stand-in animation with a held first frame, a held final frame, and a recap chart. Production Math jobs generate the clip with Manim. Omitting `--stock-manifest` exercises the no-footage fallback for the slide templates and skips Stock Story. The portrait example is in Czech. Source credits accompany the [photographs and AI illustration](../examples/formal/photos/CREDITS.md) and [cloud footage](../examples/formal/stock/CREDITS.md).

Run the affected offline suite and web build:

```bash
python -m pytest tests/test_formal_video.py tests/test_mcp.py \
  tests/test_plan_service.py tests/test_api_guards.py tests/test_script_generator.py -q
cd web
npm run build
```

The affected suite covers each layout in both orientations, visual timing recovery and handover, image attribution and fallback, stock retrieval, real FFmpeg rendering, and restoring the pipeline from a checkpoint.

Live Pexels credentials, a deployed Modal slide endpoint, and a configured Manim renderer require a staging smoke test in your environment before enabling those optional providers. They are not needed for the default slide renderer or local library. The local Math preview verifies composition and design with a stand-in clip; it does not prove that your Manim service can generate an animation.

At verification time, the local Gemini account returned a zero-quota response, the OpenAI credential was rejected, and NVIDIA reported its configured `minimaxai/minimax-m2.5` model had reached end of life. These external configurations must be corrected if selected for deployment. No credentials, billing settings or database generation profiles were changed.

Some older repository tests predate the current APIs (for example, `test_ffmpeg_providers.py` imports the removed `FFmpegAPI` class). These unrelated legacy failures are not evidence that the whole historical suite passes; the commands above identify the verified affected set.
