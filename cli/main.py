import warnings
import logging
from aishorts.shorts_generator import ScriptConfig

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
    SubtitleConfig,
)
import argparse
from dotenv import load_dotenv
from aishorts.utils.pydantic_helper import load_pydantic, load_pydantic_dict

load_dotenv()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=False)
    parser.add_argument("--resume_from", type=str, required=False)
    parser.add_argument("--mock_script", type=str, required=False)
    parser.add_argument("--files", type=str, nargs="+", required=False)
    parser.add_argument(
        "--avatars",
        type=str,
        nargs="+",
        required=False,
    )
    parser.add_argument("--amount", type=int, default=1, required=False)
    parser.add_argument("--template", type=str, required=True)
    parser.add_argument("--llm_provider", default="chatgpt", type=str)
    parser.add_argument("--model", default="gpt-5", type=str)
    parser.add_argument("--subtitle_provider", default="modal_wav2vec_aligner", type=str) # remember to change this back to elevenlabs
    parser.add_argument("--ffmpeg_provider", default="modal_ffmpeg", type=str)
    parser.add_argument(
        "--keep_assets",
        action="store_true",
        help="Keep intermediate assets (don't delete them after generation)",
    )

    args = parser.parse_args()

    video_templates = load_pydantic_dict(
        "cli/configs/video_templates.json", VideoTemplate
    )
    avatars = load_pydantic_dict("cli/configs/avatars.json", Avatar)

    video_template = video_templates[args.template]

    selected_avatars = [avatars[name] for name in args.avatars] if args.avatars else []

    from aishorts.shorts_generator import FFmpegConfig
    shorts_config = ShortsConfig(
        avatars=selected_avatars,
        video_template=video_template,
        subtitle_config=SubtitleConfig(provider=args.subtitle_provider),
        ffmpeg_config=FFmpegConfig(provider=args.ffmpeg_provider),
        script_config=ScriptConfig(
            provider="gemini", provider_config={"model": "gemini-3-pro-preview"}
        ),
    )

    shorts_generator = ShortsGenerator(shorts_config=shorts_config)
    shorts_generator.generate_shorts(
        amount=args.amount,
        files=args.files,
        user_input=args.input,
        resume_from=args.resume_from,
        mock_script=args.mock_script,
        keep_assets=args.keep_assets,
    )


if __name__ == "__main__":
    main()
