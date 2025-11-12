from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import json
import tempfile
from aishorts import (
    ShortsGenerator,
    ShortsConfig,
    Avatar,
    VideoTemplate,
    ScriptConfig,
    SubtitleConfig,
)

app = FastAPI(title="PDF-to-Brainrot API")


def load_avatars(path="configs/avatars.json") -> dict[str, Avatar]:
    with open(path, "r") as f:
        data = json.load(f)
    return {name: Avatar.from_dict(a) for name, a in data.items()}


def load_video_templates(
    path="configs/video_templates.json",
) -> dict[str, VideoTemplate]:
    with open(path, "r") as f:
        data = json.load(f)
    return {name: VideoTemplate.from_dict(cfg) for name, cfg in data.items()}


@app.post("/generate")
async def generate_video(
    avatar: str = Form(...),
    template: str = Form(...),
    input_text: str = Form(None),
    model: str = Form("gpt-5"),
    builtin_reader: bool = Form(False),
    subtitle_provider: str = Form("elevenlabs"),
    files: list[UploadFile] = File(None),
):
    """Generate a short video using the AI Shorts pipeline."""
    try:
        avatars = load_avatars()
        video_templates = load_video_templates()

        if avatar not in avatars:
            return JSONResponse(
                {"error": f"Avatar '{avatar}' not found."}, status_code=400
            )
        if template not in video_templates:
            return JSONResponse(
                {"error": f"Template '{template}' not found."}, status_code=400
            )

        # Save uploaded files temporarily
        file_paths = []
        if files:
            for f in files:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f.filename)
                tmp.write(await f.read())
                tmp.close()
                file_paths.append(tmp.name)

        shorts_config = ShortsConfig(
            avatar=avatars[avatar],
            video_template=video_templates[template],
            script_config=ScriptConfig(model=model, builtin_reader=builtin_reader),
            subtitle_config=SubtitleConfig(provider=subtitle_provider),
        )

        shorts_generator = ShortsGenerator(shorts_config)
        await shorts_generator.generate_short_async(
            files=file_paths or None, user_input=input_text
        )

        return {"status": "ok", "message": "Video generated successfully."}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
