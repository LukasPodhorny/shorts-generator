"""Optional CPU slide service: modal deploy scripts/modal_slides.py.

Create a Modal secret named `aishorts-slides` containing MODAL_SLIDES_API_KEY.
Only src/, pyproject.toml and README.md enter the image; local .env is excluded.
"""

from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgomp1", "fonts-dejavu-core")
    .add_local_dir(ROOT / "src", "/opt/project/src", copy=True, ignore=["**/__pycache__/**", "**/*.pyc"])
    .add_local_file(ROOT / "pyproject.toml", "/opt/project/pyproject.toml", copy=True)
    .add_local_file(ROOT / "README.md", "/opt/project/README.md", copy=True)
    .run_commands("pip install --no-cache-dir /opt/project")
)
app = modal.App("aishorts-slides")


@app.function(image=image, cpu=1, memory=1024, timeout=90,
              secrets=[modal.Secret.from_name("aishorts-slides")], max_containers=4)
@modal.asgi_app()
def serve():
    import hmac
    import io
    import os
    from fastapi import FastAPI, HTTPException, Request, Response
    from pydantic import ValidationError
    from aishorts.modules.script.script import SlideMedia
    from aishorts.modules.slides.renderer import render_slide, SlideOverflowError
    from aishorts.modules.slides.style import SlideRenderConfig

    web = FastAPI(docs_url=None, redoc_url=None)

    @web.post("/")
    async def render(request: Request):
        secret = os.environ.get("MODAL_SLIDES_API_KEY", "")
        if not secret or not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {secret}"):
            raise HTTPException(401, "Invalid slide service token")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Slide request exceeds 64 KiB")
        import json
        import asyncio
        try:
            payload = json.loads(body)
            slide = SlideMedia.model_validate(payload["slide"])
            config = SlideRenderConfig.model_validate(payload["config"])
            def png():
                rendered = render_slide(slide, config)
                output = io.BytesIO()
                rendered.save(output, "PNG")
                return output.getvalue()
            data = await asyncio.to_thread(png)
        except (ValidationError, ValueError, KeyError, TypeError, SlideOverflowError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return Response(data, media_type="image/png")

    return web
