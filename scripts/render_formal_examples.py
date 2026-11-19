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

from aishorts.modules.script.script import DialogueBlock, ImageMedia, MediaAttribution, Reel, ReelSeries, SlideMedia, StockVideoMedia, Trigger
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.slides.slide_generator import SlideGenerator
from aishorts.modules.stock_video.stock_video_generator import StockVideoGenerator
from aishorts.modules.video_edit.video_edit import TemplateConfig, VideoTemplate
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.video_generator import VideoGenerator


PHOTOS = Path(__file__).resolve().parents[1] / "examples" / "formal" / "photos"
PHOTO_CREDITS = {
    "greenhouse": ("Bruce Dupree / Alabama Extension", "Plants_in_a_Greenhouse.jpg", "CC0 1.0"),
    "mist": ("Rosendahl", "Mist_over_lake_in_morning.jpg", "Public domain"),
    "droplets": ("Boris Maric", "Water_drops_on_a_leaf.jpg", "CC0 1.0"),
}


def scene(text, title, layout, *, subtitle="", items=None, chart=None, source="", unit="", stock=None, photo=None):
    trigger = Trigger(start_word_index=0, end_word_index=len(text.split()) - 1)
    media = [SlideMedia(type="slide", title=title, layout=layout, subtitle=subtitle,
                        items=items or [], chart=chart or [], unit=unit, source=source, trigger=trigger)]
    if stock:
        media.append(StockVideoMedia(type="stock_video", keywords=stock, trigger=trigger))
    if photo:
        media.append(ImageMedia(type="image", keywords=photo, trigger=trigger))
    return DialogueBlock(type="dialogue", avatar="Narrator", text=text, media=media)


def load_example_photos(reel):
    for block in reel.blocks:
        for media in block.media:
            if isinstance(media, ImageMedia):
                creator, source, license_name = PHOTO_CREDITS[media.keywords]
                block.assets.media_map[media.id] = str(PHOTOS / f"{media.keywords}.jpg")
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
            scene("Clouds reveal water moving through the atmosphere. Their visible shapes are made of tiny water droplets or ice crystals, rather than invisible water vapour.",
                  "Water, made visible", "bullets", items=[{"heading": "Water droplets", "body": "Tiny liquid particles."},
                      {"heading": "Ice crystals", "body": "Water in its solid form."}], stock="clouds sky atmosphere"),
            scene("Energy from the sun helps liquid water evaporate. As moist air rises and cools, water vapour can condense into droplets that form clouds.",
                  "From surface water to clouds", "process", items=[{"heading": "Evaporation", "body": "Liquid water becomes vapour."},
                      {"heading": "Cooling", "body": "Rising air often cools."},
                      {"heading": "Condensation", "body": "Droplets form in the air."}], photo="mist"),
            scene("Wind carries clouds across the sky. Droplets and crystals may grow large enough to fall as precipitation, returning water to the surface.",
                  "A moving part of the cycle", "title", subtitle="Air moves water. Gravity brings it back.", stock="clouds sky wind"),
            scene("The water cycle connects the surface and the atmosphere. Evaporation, condensation and precipitation are different processes in the same continuing movement of water.",
                  "One cycle, connected processes", "comparison", items=[{"heading": "Upward", "body": "Evaporation moves water into the air."},
                      {"heading": "Downward", "body": "Precipitation returns water to the surface."}]),
        ]),
        "briefing": Reel(title="Koloběh vody v kostce", description="Stručné české opakování pro mobil.", blocks=[
            scene("Voda se neustále pohybuje mezi zemským povrchem a atmosférou. Koloběh vody propojuje vypařování, kondenzaci a srážky do jednoho souvislého děje.",
                  "Voda je stále v pohybu", "title", subtitle="Koloběh vody v kostce", photo="mist"),
            scene("Při vypařování se kapalná voda mění na vodní páru. Při kondenzaci vznikají drobné kapičky. Srážky potom vracejí vodu zpátky na povrch.",
                  "Tři propojené děje", "process", items=[{"heading": "Vypařování", "body": "Voda přechází do vzduchu."},
                      {"heading": "Kondenzace", "body": "Vznikají drobné kapičky."},
                      {"heading": "Srážky", "body": "Voda se vrací na povrch."}]),
            scene("Vodní pára je neviditelná. Viditelný oblak tvoří drobné kapky vody nebo ledové krystalky. Pára a oblak proto nejsou totéž.",
                  "Pára není oblak", "comparison", items=[{"heading": "Vodní pára", "body": "Neviditelná plynná voda."},
                      {"heading": "Oblak", "body": "Viditelné kapičky nebo krystalky."}], stock="clouds"),
            scene("Zapamatujte si hlavní souvislost. Sluneční energie pomáhá vodu vypařovat a gravitace ji přivádí zpět. Jednotlivé děje společně udržují vodu v pohybu.",
                  "Co si zapamatovat", "bullets", items=[{"heading": "Sluneční energie", "body": "Pomáhá vodu vypařovat."},
                      {"heading": "Gravitace", "body": "Vrací vodu na povrch."}], photo="droplets"),
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
        template = EditTemplate.get(name)(TemplateConfig())
        with patch("aishorts.modules.script.script_generator.LLMProvider.get", return_value=lambda **kw: SimpleNamespace()):
            writer = ScriptGenerator(base_instructions="", avatars=[SimpleNamespace(name="Narrator", instructions="Calm")],
                                     generate_slides=True, generate_stock_video=True, slide_render_config=template.render_config)
        series = ReelSeries(topic=reel.title, reels=[reel])
        writer.validate_script(series, 1)
        (target / f"{name}.script.json").write_text(series.model_dump_json(indent=2), encoding="utf-8")
        assets = target / "assets" / name
        await asyncio.to_thread(narration, reel, assets, "cs" if name == "briefing" else "en-us")
        load_example_photos(reel)
        await StockVideoGenerator(provider="library", manifest_path=args.stock_manifest, upload=False,
                                  output_dir=assets / "stock").populate_reel(reel)
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
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", str(final),
                        "-frames:v", "1", "-y", str(target / f"{name}.png")], check=True)
        if args.previews:
            args.previews.mkdir(parents=True, exist_ok=True)
            scale = "scale=540:-2" if name == "briefing" else "scale=960:-2"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(target / f"{name}.png"), "-vf", scale,
                            "-frames:v", "1", "-y", str(args.previews / f"{name}.png")], check=True)
            scene_frame = 0
            excerpts = []
            for index, block in enumerate(reel.blocks):
                frames = math.ceil(block.assets.subtitles.duration * 30)
                if index < 4 or index == len(reel.blocks) - 1:
                    excerpts.append(f"between(n,{scene_frame},{scene_frame + min(frames, 120) - 1})")
                scene_frame += frames
            montage = f"select='{'+'.join(excerpts)}',setpts=N/(30*TB),{scale}"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-vf", montage,
                            "-an", "-c:v", "libx264", "-crf", "25", "-movflags", "+faststart", "-y", str(args.previews / f"{name}.mp4")], check=True)
        print(f"Rendered {final}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/formal-examples"))
    parser.add_argument("--previews", type=Path)
    parser.add_argument("--stock-manifest", type=Path)
    parser.add_argument("--template", choices=["lecture", "documentary", "briefing"])
    asyncio.run(run(parser.parse_args()))
