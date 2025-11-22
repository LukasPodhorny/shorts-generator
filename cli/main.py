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
from aishorts.utils.pydantic_helper import load_pydantic, load_pydantic_dict


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

    video_templates = load_pydantic_dict(
        "cli/configs/video_templates.json", VideoTemplate
    )
    avatars = load_pydantic_dict("cli/configs/avatars.json", Avatar)
    script_config = load_pydantic("cli/configs/script_config.json", ScriptConfig)

    video_template = video_templates[args.template]
    avatar = avatars[args.avatar]

    shorts_config = ShortsConfig(
        avatar=avatar,
        video_template=video_template,
        script_config=ScriptConfig(
            base_instructions=script_config.base_instructions,
            provider=args.llm_provider or script_config.provider,
            provider_config={
                "model": args.model
                or script_config.provider_config.get("model", "gpt-5")
            },
        ),
        subtitle_config=SubtitleConfig(provider=args.subtitle_provider),
    )

    shorts_generator = ShortsGenerator(shorts_config=shorts_config)
    shorts_generator.generate_short(files=args.files, user_input=args.input)


if __name__ == "__main__":
    main()
