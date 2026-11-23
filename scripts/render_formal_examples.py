"""Render reproducible examples without LLM, cloud storage, or paid APIs.

Requires ffmpeg, ffprobe and espeak-ng. Narration is deliberately offline demo
speech; production uses the application's existing TTS and forced aligner.
Pass --stock-manifest to exercise real local footage, or omit it to test fallback.
"""

import argparse
import asyncio
import math
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from PIL import Image, ImageDraw, ImageFont

from aishorts.modules.script.script import DialogueBlock, ImageMedia, ManimMedia, MediaAttribution, Reel, ReelSeries, SlideMedia, StockVideoMedia, Trigger
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.slides.slide_generator import SlideGenerator
from aishorts.modules.slides.renderer import render_slide
from aishorts.modules.slides.style import layout_regions
from aishorts.modules.stock_video.stock_video_generator import StockVideoGenerator
from aishorts.modules.video_edit.formal_templates import MATH_SLIDE_REVIEW_SECONDS, timed_media_window
from aishorts.modules.video_edit.video_edit import TemplateConfig, VideoTemplate
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.video_generator import VideoGenerator


PHOTOS = Path(__file__).resolve().parents[1] / "examples" / "formal" / "photos"
PHOTO_CREDITS = {
    "greenhouse": ("Bruce Dupree / Alabama Extension", "Plants_in_a_Greenhouse.jpg", "CC0 1.0"),
    "mist": ("Rosendahl", "Mist_over_lake_in_morning.jpg", "Public domain"),
    "droplets": ("Boris Maric", "Water_drops_on_a_leaf.jpg", "CC0 1.0"),
}


def scene(text, title, layout, *, subtitle="", items=None, chart=None, source="", unit="", x_unit="", stock=None, photo=None):
    trigger = Trigger(start_word_index=0, end_word_index=len(text.split()) - 1)
    media = [SlideMedia(type="slide", title=title, layout=layout, subtitle=subtitle,
                        items=items or [], chart=chart or [], unit=unit, x_unit=x_unit, source=source, trigger=trigger)]
    if stock:
        media.append(StockVideoMedia(type="stock_video", keywords=stock, trigger=trigger))
    if photo:
        media.append(ImageMedia(type="image", keywords=photo, trigger=trigger))
    return DialogueBlock(type="dialogue", avatar="Narrator", text=text, media=media)


def stock_scene(text, keywords):
    trigger = Trigger(start_word_index=0, end_word_index=len(text.split()) - 1)
    return DialogueBlock(type="dialogue", avatar="Narrator", text=text,
                         media=[StockVideoMedia(type="stock_video", keywords=keywords, trigger=trigger)])


def tangent_animation(output: Path):
    """Deterministic stand-in clip for the compositor preview, without a Manim service."""
    width, height, fps, frames = 960, 540, 24, 144
    font_path = Path(__file__).resolve().parents[1] / "src" / "aishorts" / "resources" / "fonts" / "InterDisplay-Bold.ttf"
    title_font = ImageFont.truetype(str(font_path), 32)
    value_font = ImageFont.truetype(str(font_path), 27)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
               "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
               "-pix_fmt", "yuv420p", "-y", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    origin_x, origin_y = width // 2, 415
    scale_x, scale_y = 154, 58
    try:
        for frame in range(frames):
            image = Image.new("RGB", (width, height), "#F7F4EC")
            draw = ImageDraw.Draw(image)
            draw.text((58, 38), "A moving tangent", font=title_font, fill="#142423")
            draw.line((62, origin_y, width - 62, origin_y), fill="#C9D2C8", width=2)
            draw.line((origin_x, 125, origin_x, 452), fill="#C9D2C8", width=2)
            points = [(origin_x + scale_x * (-2.3 + i * 4.6 / 160),
                       origin_y - scale_y * (-2.3 + i * 4.6 / 160) ** 2)
                      for i in range(161)]
            draw.line(points, fill="#475A55", width=4, joint="curve")
            progress = frame / max(1, frames - 1)
            x0 = round(-1.5 + 3.0 * progress, 2)
            tangent = lambda x: x0 * x0 + 2 * x0 * (x - x0)
            draw.line([(origin_x + scale_x * x, origin_y - scale_y * tangent(x))
                       for x in (x0 - 1.0, x0 + 1.0)], fill="#087F8C", width=5)
            cx, cy = origin_x + scale_x * x0, origin_y - scale_y * x0 * x0
            draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill="#087F8C")
            draw.text((572, 42), f"x = {x0:+.2f}   slope = {2*x0:+.2f}", font=value_font, fill="#142423")
            process.stdin.write(image.tobytes())
        process.stdin.close()
        stderr = process.stderr.read()
        if process.wait() != 0:
            raise RuntimeError(f"Could not render the sample animation: {stderr.decode(errors='replace')}")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def load_example_photos(reel):
    for block in reel.blocks:
        for media in block.media:
            if isinstance(media, ImageMedia):
                block.assets.media_map[media.id] = str(PHOTOS / f"{media.keywords}.jpg")
                if media.keywords == "lake-illustration":
                    continue
                creator, source, license_name = PHOTO_CREDITS[media.keywords]
                block.assets.media_attributions[media.id] = MediaAttribution(
                    creator=creator, provider="Wikimedia Commons",
                    source_url=f"https://commons.wikimedia.org/wiki/File:{source}", license=license_name,
                )


def examples():
    return {
        "lecture": Reel(title="From observation to evidence", description="A short lesson in fair testing.", blocks=[
            scene("How do we turn an interesting observation into reliable knowledge? Start with a question, build an explanation, and design a test that could show it is wrong.",
                  "From observation to evidence", "title", subtitle="How to design a fair test", photo="greenhouse"),
            scene("A useful investigation has three parts. Observe a pattern, propose an explanation, and predict what you should see if that explanation is correct.",
                  "Build a testable explanation", "process", items=[
                      {"heading": "Observe", "body": "Notice a pattern."},
                      {"heading": "Explain", "body": "Suggest a possible cause."},
                      {"heading": "Predict", "body": "State what a test should reveal."}]),
            scene("An observation describes what happened. An explanation proposes why it happened. Keeping these separate helps us avoid treating an attractive story as established evidence.",
                  "What happened, and why?", "comparison", items=[
                      {"heading": "Observation", "body": "The shaded plant grew more slowly."},
                      {"heading": "Explanation", "body": "Less light may have limited its growth."}]),
            scene("Imagine a classroom experiment with two groups of plants. These invented numbers illustrate a comparison. They do not establish a general rule about plant growth.",
                  "Compare the measurements", "chart", chart=[{"label": "Group A", "value": 12}, {"label": "Group B", "value": 19}],
                  unit="cm", source="Illustrative example, not measured research data"),
            scene("The purpose of a test is to challenge an explanation. When the results disagree with a prediction, revise the explanation and look for a better one.",
                  "Let evidence change the explanation", "quote", subtitle="A useful explanation makes a testable prediction.", source="Lesson takeaway"),
            scene("Before accepting a conclusion, ask three questions. Was the comparison fair? Were measurements repeated? And could another explanation account for the same result?",
                  "Three questions to take away", "bullets", items=[{"heading": "Fair comparison", "body": "Change one relevant factor."},
                      {"heading": "Repeated measurements", "body": "Check whether the pattern persists."},
                      {"heading": "Alternative explanations", "body": "Consider other possible causes."}]),
        ]),
        "documentary": Reel(title="Why clouds form", description="A footage-led introduction to the water cycle.", blocks=[
            scene("A lake and the air above it are connected. Follow the water as it moves from the surface to the atmosphere and back.",
                  "Water, made visible", "spotlight", subtitle="From the lake to the clouds and back.",
                  photo="lake-illustration", source="AI illustration"),
            scene("Energy from the sun helps liquid water evaporate. As moist air rises and cools, water vapour can condense into droplets that form clouds.",
                  "From surface water to clouds", "process", items=[{"heading": "Evaporation", "body": "Liquid water becomes vapour."},
                      {"heading": "Cooling", "body": "Rising air often cools."},
                      {"heading": "Condensation", "body": "Droplets form in the air."}], photo="mist"),
            scene("Wind carries clouds across the sky. Droplets and crystals may grow large enough to fall as precipitation, returning water to the surface.",
                  "A moving part of the cycle", "title", subtitle="Air moves water. Gravity brings it back.", stock="clouds sky wind"),
            scene("The water cycle connects the surface and the atmosphere. Evaporation, condensation and precipitation are different processes in the same continuing movement of water.",
                  "One cycle, connected processes", "comparison", items=[{"heading": "Upward", "body": "Evaporation moves water into the air."},
                      {"heading": "Downward", "body": "Precipitation returns water to the surface."}]),
            scene("Imagine one hundred drops of rain reaching a hillside. In this example, fifty soak into the ground, thirty run off, and twenty evaporate.",
                  "Where the rain goes", "donut", chart=[{"label": "Soaks in", "value": 50},
                      {"label": "Runs off", "value": 30}, {"label": "Evaporates", "value": 20}],
                  source="Illustrative example · 100 drops of rain"),
        ]),
        "stock_story": Reel(title="A cloud is not vapor", description="A voiceover about the droplets that make clouds visible.", blocks=[
            stock_scene("Look up at a cloud. It may seem like water vapor, but vapor is invisible. What you see is a huge collection of tiny water droplets or ice crystals scattering sunlight.",
                        "clouds sky wind"),
        ]),
        "briefing": Reel(title="Koloběh vody v kostce", description="Stručné české opakování pro mobil.", blocks=[
            scene("Voda se neustále pohybuje mezi zemským povrchem a atmosférou. Koloběh vody propojuje vypařování, kondenzaci a srážky do jednoho souvislého děje.",
                  "Voda je stále v pohybu", "spotlight", subtitle="Koloběh vody v kostce",
                  photo="lake-illustration", source="Ilustrace vytvořená pomocí AI"),
            scene("Při vypařování se kapalná voda mění na vodní páru. Při kondenzaci vznikají drobné kapičky. Srážky potom vracejí vodu zpátky na povrch.",
                  "Tři propojené děje", "timeline", items=[{"heading": "Vypařování", "body": "Voda přechází do vzduchu."},
                      {"heading": "Kondenzace", "body": "Vznikají drobné kapičky."},
                      {"heading": "Srážky", "body": "Voda se vrací na povrch."}]),
            scene("Vodní pára je neviditelná. Viditelný oblak tvoří drobné kapky vody nebo ledové krystalky. Pára a oblak proto nejsou totéž.",
                  "Pára není oblak", "comparison", items=[{"heading": "Vodní pára", "body": "Neviditelná plynná voda."},
                      {"heading": "Oblak", "body": "Viditelné kapičky nebo krystalky."}], stock="clouds"),
            scene("Představme si sto kapek deště. V modelovém příkladu se čtyřicet vsákne do půdy, zatímco šedesát odteče po povrchu.",
                  "Kam se poděje déšť", "metrics", items=[{"heading": "40 %", "body": "Vsákne se do půdy"},
                      {"heading": "60 %", "body": "Odteče po povrchu"}], source="Modelový příklad · 100 kapek"),
        ]),
        "math": Reel(title="What a derivative measures", description="A short visual lesson on the slope of a curve.", blocks=[
            scene("A straight line has one slope. A curve changes direction, so its slope depends on where you look. The derivative names the slope of the tangent at a chosen point. Watch how that tangent turns as the point moves along the curve.",
                  "The slope of a curve", "title", subtitle="A tangent measures the change at one point"),
            scene("For the curve y equals x squared, the tangent slopes downward on the left, becomes flat at zero, and slopes upward on the right. The derivative is two x, so the slope changes continuously with position.",
                  "Slope changes with position", "line_chart",
                  chart=[{"label": "−2", "x": -2, "value": -4}, {"label": "−1", "x": -1, "value": -2},
                         {"label": "0", "x": 0, "value": 0}, {"label": "1", "x": 1, "value": 2},
                         {"label": "2", "x": 2, "value": 4}],
                  unit="slope", x_unit="x", source="Computed from y = x²"),
            scene("To estimate a slope, choose two nearby points. Divide the rise by the run. Move the points closer together. The ratio approaches the slope of the tangent at the point you care about.",
                  "From secant to tangent", "process", items=[
                      {"heading": "Choose nearby points", "body": "Measure the rise and the run."},
                      {"heading": "Divide", "body": "Slope is rise over run."},
                      {"heading": "Move closer", "body": "The ratio approaches a tangent slope."}]),
            scene("At x equals one, the derivative two x gives a slope of two. That means a small step to the right raises the curve by about twice as much. The word about matters because the curve keeps bending.",
                  "A useful local estimate", "comparison", items=[
                      {"heading": "Exact at the point", "body": "The tangent slope is 2."},
                      {"heading": "Approximate nearby", "body": "A small step in x changes y by about 2 times that step."}]),
        ]),
    }


def narration(reel, output, language):
    """Demo timing is estimated; the production pipeline uses forced alignment."""
    output.mkdir(parents=True, exist_ok=True)
    for i, block in enumerate(reel.blocks):
        path = output / f"voice-{i}.wav"
        subprocess.run(["espeak-ng", "-v", language, "-s", "155", "-w", str(path), "--stdin"], input=block.text, text=True, check=True)
        duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))
        block.assets.voice_filepath = str(path)
        words = block.text.split()
        # Allocate time by word length, retaining a little pause at each end.
        weights = [max(2, len(w)) for w in words]
        usable, now = max(0.1, duration - 0.3), 0.1
        timings = []
        for word, weight in zip(words, weights):
            end = now + usable * weight / sum(weights)
            timings.append(TranscriptionWord(word=word, start=now, end=end))
            now = end
        block.assets.subtitles = TranscriptionVerbose(duration=duration, language=language, text=block.text, words=timings)


async def run(args):
    target = args.output.resolve()
    target.mkdir(parents=True, exist_ok=True)
    for name, reel in examples().items():
        if args.template and name != args.template:
            continue
        if name == "stock_story" and not args.stock_manifest:
            if args.template:
                raise ValueError("Stock Story example requires --stock-manifest")
            print("Skipping stock_story without --stock-manifest", flush=True)
            continue
        template = EditTemplate.get(name)(TemplateConfig())
        with patch("aishorts.modules.script.script_generator.LLMProvider.get", return_value=lambda **kw: SimpleNamespace()):
            writer = ScriptGenerator(base_instructions="", avatars=[SimpleNamespace(name="Narrator", instructions="Calm")],
                                     generate_slides=name != "stock_story", generate_stock_video=True,
                                     require_stock_video=name == "stock_story",
                                     generate_manim=name == "math",
                                     slide_render_config=template.render_config if name != "stock_story" else None)
        if name == "math":
            animated = reel.blocks[1]
            animated.media.append(ManimMedia(type="manim", prompt="Show a moving tangent on the graph y = x squared.",
                trigger=Trigger(start_word_index=8, end_word_index=23)))
        series = ReelSeries(topic=reel.title, reels=[reel])
        writer.validate_script(series, 1)
        (target / f"{name}.script.json").write_text(series.model_dump_json(indent=2), encoding="utf-8")
        assets = target / "assets" / name
        narration(reel, assets, "cs" if name == "briefing" else "en-us")
        if name == "math":
            clip = assets / "tangent.mp4"
            tangent_animation(clip)
            reel.blocks[1].assets.media_map[reel.blocks[1].media[1].id] = str(clip)
        load_example_photos(reel)
        await StockVideoGenerator(provider="library", manifest_path=args.stock_manifest, upload=False,
                                  output_dir=assets / "stock", failure_mode="error" if name == "stock_story" else "fallback").populate_reel(reel)
        if name == "math":
            for index, block in enumerate(reel.blocks):
                graphic = next(media for media in block.media if isinstance(media, SlideMedia))
                config = template.render_config.model_copy(update={"chapter": index + 1, "chapters": len(reel.blocks)})
                path = assets / "slides" / f"scene-{index + 1}.png"
                render_slide(graphic, config, path)
                block.assets.media_map[graphic.id] = str(path)
                _, block.assets.slide_viewport = layout_regions(config, graphic.layout)
        elif name != "stock_story":
            await SlideGenerator(render_config=template.render_config, upload=False, output_dir=assets / "slides").populate_reel(reel)
        (target / f"{name}.checkpoint.json").write_text(series.model_dump_json(indent=2), encoding="utf-8")
        video = VideoGenerator(VideoTemplate(edit_template=name, template_config={}), provider="local_ffmpeg",
                               compression_profile="high_quality", max_video_bitrate="6M", encoder_preset="fast")
        video.render.video_codec = "libx264"
        video.render.OUTPUT_DIR = str(target)
        result = await video.compose(reel)
        final = target / f"{name}.mp4"
        Path(result.filepath).replace(final)
        # Capture the composed opening, including the photo or footage.
        if name == "math":
            intro_end = math.ceil(reel.blocks[0].assets.subtitles.duration * 30) / 30 + MATH_SLIDE_REVIEW_SECONDS
            animated = reel.blocks[1]
            speech = math.ceil(animated.assets.subtitles.duration * 30) / 30
            cue, _ = timed_media_window(animated, animated.media[1], speech)
            poster_time = intro_end + cue + 2
        else:
            poster_time = 2
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(poster_time), "-i", str(final),
                        "-frames:v", "1", "-y", str(target / f"{name}.png")], check=True)
        if args.previews:
            args.previews.mkdir(parents=True, exist_ok=True)
            scale = "scale=540:-2" if name == "briefing" else "scale=960:-2"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(target / f"{name}.png"), "-vf", scale,
                            "-frames:v", "1", "-y", str(args.previews / f"{name}.png")], check=True)
            if name == "math":
                excerpts = f"between(t,0,4)+between(t,{intro_end},{intro_end + 22})"
            else:
                scene_frame = 0
                excerpts = []
                for index, block in enumerate(reel.blocks):
                    frames = math.ceil(block.assets.subtitles.duration * 30)
                    if index < 4 or index == len(reel.blocks) - 1:
                        excerpts.append(f"between(n,{scene_frame},{scene_frame + min(frames, 120) - 1})")
                    scene_frame += frames
                excerpts = "+".join(excerpts)
            montage = f"select='{excerpts}',setpts=N/(30*TB),{scale}"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-vf", montage,
                            "-an", "-c:v", "libx264", "-crf", "25", "-movflags", "+faststart", "-y", str(args.previews / f"{name}.mp4")], check=True)
        print(f"Rendered {final}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/formal-examples"))
    parser.add_argument("--previews", type=Path)
    parser.add_argument("--stock-manifest", type=Path)
    parser.add_argument("--template", choices=["lecture", "documentary", "briefing", "math", "stock_story"])
    asyncio.run(run(parser.parse_args()))
