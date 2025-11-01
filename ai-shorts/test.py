# example.py
import os
from io import BytesIO
from elevenlabs.client import ElevenLabs

elevenlabs = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
)

with open("test_files/trump.wav", "rb") as f:
    audio_data = BytesIO(f.read())

# Perform the text-to-speech conversion
transcription = elevenlabs.forced_alignment.create(
    file=audio_data,
    text="A short time ago, the U.S. military carried out massive, precision strikes on the three key nuclear facilities in the Iranian regime.",
)

print(transcription)
