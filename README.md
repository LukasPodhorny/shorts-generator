# 📚 PDF-to-Reel

PDF-to-Reel is application that converts PDF, DOCX, PPTX, or plain text into short vertical videos in the style of TikTok/Instagram Reels. The system generates a script using OpenAI API, produces voice using TTS, performs lipsync, creates subtitles, and assembles the final video with music and gameplay background.

<video src="https://files.catbox.moe/i6xmkb.mp4" controls width="500">
  Your browser does not support the video tag.
</video>

---

## ✨ Features
- 📄 Text extraction from PDF/DOCX/PPTX  
- 🤖 Script generation using GPT-5  
- 🔊 TTS (F5-TTS, LemonFox, ElevenLabs)  
- 👄 Lipsync (FLOAT / Wav2Lip)  
- 📝 Subtitles (Whisper / ElevenLabs forced alignment)  
- 🎬 Video rendering with MoviePy  
- 👤 Avatars and video templates  
- 🧩 Modular and extensible architecture  

---

# 📦 Installation

## 1) Clone the repository
```bash
git clone https://github.com/LukasPodhorny/shorts-generator
cd shorts-generator
```

## 2) Create virtual environment
```bash
conda create -n shorts-generator python=3.14.0
conda activate shorts-generator
```

## 3) Install dependencies
```bash
pip install -r requirements.txt
```

## 4) Install the project locally
```bash
pip install -e .
```

## 5) Set environment variables
```bash
# API Keys
export OPENAI_API_KEY="your_key"
export RUNPOD_API_KEY="your_key"
export ELEVENLABS_API_KEY="your_key"
export LEMONFOX_API_KEY="your_key"

# RunPod Endpoint IDs
export F5TTS_ENDPOINT_ID="your_key"
export FLOAT_ENDPOINT_ID="your_key"
export WAV2LIP_ENDPOINT_ID="your_key"

# Cloudflare R2 Storage
export R2_ACCESS_KEY="your_key"
export R2_SECRET_KEY="your_key"
export R2_BUCKET_NAME="your_key"
export R2_ENDPOINT="your_key"
```

---

# 🚀 Usage (CLI)

### Basic example
```bash
python cli/main.py \
    --input "explain in fortnite terms" \
    --files "path/to/file" "path/to/second/file" \
    --avatar "biden" \
    --template "basic_gameplay"
```

### Output
Generated files will appear in:

```
output/
    ├── lipsync/
    ├── tts/
    └── videos/
```
