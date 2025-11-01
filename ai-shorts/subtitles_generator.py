from openai import OpenAI
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
import os
from io import BytesIO
from elevenlabs.client import ElevenLabs


def whisper_subtitles(audio_file: str):
    client = OpenAI()
    with open(audio_file, "rb") as audio:
        transcription = client.audio.transcriptions.create(
            file=audio,
            model="gpt-4o-transcribe",
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    return transcription


def elevenlabs_subtitles(
    audio_file: str,
    transcription_text: str,
    display_silence: bool = False,
    min_silence_duration: float = 0.8,
    remove_chars=".,",
    api_key: str | None = None,
):
    api_key = api_key or os.getenv("ELEVENLABS_API_KEY")

    elevenlabs = ElevenLabs(api_key=api_key)

    with open(audio_file, "rb") as f:
        audio_data = BytesIO(f.read())

    # Perform the text-to-speech conversion
    transcription = elevenlabs.forced_alignment.create(
        file=audio_data,
        text=transcription_text,
    )

    transcription_verbose = TranscriptionVerbose(
        duration=transcription.words[-1].end,
        language="english",
        text=transcription_text,
        words=[],
    )

    prev_word = None
    for subtitle in transcription.words:
        word = subtitle.text.replace(" ", "")

        if word == "" and not display_silence:

            if prev_word is not None:

                silence_duration = subtitle.end - subtitle.start
                if silence_duration < min_silence_duration:
                    prev_word.end = subtitle.end
                    continue

        transcription_word = TranscriptionWord(
            start=subtitle.start,
            end=subtitle.end,
            word=subtitle.text.translate({ord(x): "" for x in remove_chars}),
        )
        transcription_verbose.words.append(transcription_word)
        prev_word = transcription_word

    return transcription_verbose


if __name__ == "__main__":
    transcription = "You get to face a lot of shit, young man. You got a long journey ahead of you, cuz you're gonna find out, that while your dad did a lot of shit to you, you're gonna have to make it on your own."
    subtitles = elevenlabs_subtitles("test_files/goggins-10.wav", transcription)
    print(subtitles)
