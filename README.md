# 📚 PDF-to-Reel

PDF-to-Reel is application that converts PDF, DOCX, PPTX, or plain text into short vertical videos in the style of TikTok/Instagram Reels. The system generates a script using LLM, produces voice using TTS, performs lipsync, creates subtitles, and assembles the final video with music and gameplay background.

<div align="center">
  <video src="https://github.com/user-attachments/assets/ea777806-23dc-4195-b9e3-8a3efe98392f" width="320" controls></video>
</div>


---

## ✨ Features
- 📄 Text extraction from PDF/DOCX/PPTX  
- 🤖 Script generation (GPT-5)
- 🔊 TTS (F5-TTS, LemonFox)  
- 👄 Lipsync (FLOAT, Wav2Lip)  
- 📝 .ASS Subtitles (ElevenLabs forced alignment, Whisper)  
- 🎬 Video rendering with FFMPEG
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
    --input "explain it simply" \
    --files tests/test_files/Photosynthesis.pdf \
    --avatars "biden" "trump" \
    --template "basic_gameplay" \
    --amount 3 
```

### Output
Generated files will appear in:

```
output/
    ├── lipsync/
    ├── tts/
    └── videos/
```
