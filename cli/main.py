import warnings
import logging

warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from aishorts import (
    ShortsGenerator,
    ShortsConfig,
    Avatar,
    VideoTemplate,
    ScriptConfig,
    SubtitleConfig,
)
import argparse
import json


def load_avatars(path="cli/configs/avatars.json") -> dict[str, Avatar]:
    with open(path, "r") as f:
        data = json.load(f)
    return {name: Avatar.from_dict(a) for name, a in data.items()}


def load_video_templates(
    path="cli/configs/video_templates.json",
) -> dict[str, VideoTemplate]:
    with open(path, "r") as f:
        data = json.load(f)
    return {name: VideoTemplate.from_dict(cfg) for name, cfg in data.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=False)
    parser.add_argument("--files", type=str, nargs="+", required=False)
    parser.add_argument("--avatar", type=str, required=True)
    parser.add_argument("--template", type=str, required=True)
    parser.add_argument("--llm_provider", default="chatgpt", type=str)
    parser.add_argument("--model", default="gpt-5", type=str)
    parser.add_argument("--subtitle_provider", default="elevenlabs", type=str)

    args = parser.parse_args()

    video_templates = load_video_templates()
    avatars = load_avatars()

    video_template = video_templates[args.template]
    avatar = avatars[args.avatar]

    shorts_config = ShortsConfig(
        avatar=avatar,
        video_template=video_template,
        script_config=ScriptConfig(
            provider=args.llm_provider, provider_config={"model": args.model}
        ),
        subtitle_config=SubtitleConfig(provider=args.subtitle_provider),
    )

    shorts_generator = ShortsGenerator(shorts_config=shorts_config)
    shorts_generator.generate_short(files=args.files, user_input=args.input)


if __name__ == "__main__":
    main()
