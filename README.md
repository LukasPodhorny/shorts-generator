# 📚 PDF-to-Brainrot

PDF-to-Brainrot (knihovna **aishorts**) je modulární AI pipeline, která převádí PDF, DOCX, PPTX nebo text na krátká vertikální videa ve stylu TikTok/Instagram Reels. Projekt generuje skript pomocí GPT-5, vytváří hlas přes TTS, provádí lipsync, vykresluje titulky a skládá výsledné video s hudbou a gameplay backgroundem.

---

## ✨ Features
- 📄 Extrakce textu z PDF/DOCX/PPTX  
- 🤖 Brainrot skripty generované GPT-5  
- 🔊 TTS (F5-TTS, LemonFox, ElevenLabs)  
- 👄 Lipsync (FLOAT / Wav2Lip)  
- 📝 Titulky (Whisper / ElevenLabs alignment)  
- 🎬 Video rendering (MoviePy)  
- 👤 Avataři a šablony videí  
- 🧩 Modulární architektura  
- ⚙️ CLI + library použitelná v backendu i mobilní aplikaci  

---

# 📦 Installation

## 1) Clone repository
```bash
git clone https://github.com/USERNAME/pdf-to-brainrot.git
cd pdf-to-brainrot
```

## 2) Create virtual environment
```bash
python -m venv venv
source venv/bin/activate     # Linux/macOS
venv\Scripts\activate        # Windows
```

## 3) Install dependencies
```bash
pip install aiohttp==3.13.1 \
            boto3==1.40.61 \
            elevenlabs==2.22.0 \
            moviepy==2.2.1 \
            openai==2.7.1 \
            pypdf==6.2.0 \
            python_docx==1.2.0 \
            python_pptx==1.0.2 \
            Requests==2.32.5 \
            runpod==1.7.13
```

Or:
```bash
pip install -r requirements.txt
```

## 4) Install project locally
```bash
pip install -e .
```

## 5) Set environment variables
```bash
export OPENAI_API_KEY="your_key"
export ELEVENLABS_API_KEY="your_key"
export RUNPOD_API_KEY="your_key"
```

Optional:
```bash
export R2_ACCESS_KEY=""
export R2_SECRET_KEY=""
export R2_BUCKET_NAME=""
export R2_ENDPOINT=""
```

---

# 🚀 Usage (CLI)

### Basic example
```bash
ai-shorts \
    --input "Explain quantum physics in Fortnite terms" \
    --files examples/notes.pdf \
    --avatar biden \
    --template basic_gameplay
```

### Only text
```bash
ai-shorts --input "Explain WW2 like a TikTok meme"
```

### Multiple files
```bash
ai-shorts --files one.pdf two.pdf three.pdf
```

### Output
Výstupy najdeš v:

```
cli/output/
    ├── lipsync/
    ├── tts/
    └── videos/
```

---

# 🧩 Project Structure
```
.
├── assets/
│   ├── bg_video/
│   ├── fonts/
│   └── music/
├── cli/
│   ├── main.py
│   └── output/
├── src/
│   └── aishorts/
│       ├── script/
│       ├── tts/
│       ├── lipsync/
│       ├── subtitles/
│       ├── video_edit/
│       ├── avatar/
│       └── utils/
└── pyproject.toml
```

---

# 🧠 Architecture

`ShortsGenerator` orchestrace celého pipeline:

1. Extrakce textu  
2. Generování skriptu (GPT-5)  
3. TTS → zvukový výstup  
4. Lipsync přes FLOAT / Wav2Lip  
5. Vytvoření titulků  
6. Složení videa pomocí MoviePy  
7. Export výsledného vertical shortu  

Každý modul je samostatně rozšiřitelný a registrovaný přes registry.

---

# 🎭 Avatars

Příklad avataru:
```python
Avatar(
    name="biden",
    tts_voice="biden_v1",
    lipsync_model="float"
)
```

---

# 🎬 Templates

Příklad template konfigurace:
```python
TemplateConfig(
    bg_video="assets/bg_video/gameplay.mp4",
    music="assets/music/music.mp3",
    subtitle_style=SubtitleStyle(font="NotoSans-Bold.ttf")
)
```

---

# ⚙️ ShortsConfig Example
```python
config = ShortsConfig(
    avatar="biden",
    template="basic_gameplay",
    script=ScriptConfig(model="gpt-5"),
    subtitles=SubtitleConfig(provider="elevenlabs")
)
```

---

# 🧪 Testing

Run all tests:
```bash
pytest -q
```

Skip integration tests:
```bash
pytest -m "not integration"
```

---

# 🐳 RunPod Deployment (optional)

Projekt podporuje GPU kontejnery:

- FLOAT lipsync  
- F5-TTS  
- Wav2Lip  

Environment variables:
```
RUNPOD_FLOAT_ENDPOINT=
RUNPOD_F5_ENDPOINT=
RUNPOD_WAVLIP_ENDPOINT=
```

---

# 📘 Roadmap
- Template editor (web + mobile)  
- Více avatarů ve videu  
- Lepší volume normalization  
- Async CLI orchestrace  
- Local GPU acceleration  
- Public API server  

---

# 🤝 Contributing
Contribution vítány: nové moduly, template systémy, optimalizace pipeline.

---

# 📄 License
MIT License.
