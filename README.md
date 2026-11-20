# Sign Bridge 🤝

> **The first AI that turns any Instagram Reel into Kenyan Sign Language — in real-time.**

Built for the **Meta Global AI Hackathon 2026** | Powered by Meta Muse Wonder · Spark 1.3 · SAM 3.1 · Muse Image

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-black)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## The Problem

**70 million** Deaf people globally are locked out of social media content — including **1 million Deaf Kenyans**. Instagram Reels have no sign language support. Creators have no easy way to make their content accessible.

## The Solution

Sign Bridge takes any Instagram Reel and overlays a live **Kenyan Sign Language (KSL)** signing avatar — automatically, in under 3 minutes.

```
Instagram Reel URL
        ↓
  Muse Wonder 1.0        — Transcribes audio to English text
        ↓
  Muse Spark 1.3         — Converts English → KSL Gloss (SOV grammar)
        ↓
  SAM 3.1                — Analyzes frames, picks best avatar corner
        ↓
  Muse Image 1.0         — Generates KSL signing avatar frames
        ↓
  FFmpeg                 — Composites avatar onto original video
        ↓
  Accessible Reel MP4    ← Download & share
```

---

## Demo

| Original Reel | With KSL Avatar |
|---|---|
| Speaker talks | Avatar signs in KSL |
| No accessibility | Deaf-inclusive |

---

## Quick Start

### Prerequisites
- Python 3.10+
- FFmpeg (`winget install Gyan.FFmpeg` on Windows)
- Meta AI API key from [dev.meta.ai](https://dev.meta.ai)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/Thee-Beloved/SignBridge.git
cd SignBridge

# 2. Install Python dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env and add your META_API_KEY

# 4. Run the server
cd backend
python app.py

# 5. Open in browser
# http://localhost:5000
```

### Using Sign Bridge

**Option A — Instagram URL:**
1. Paste any Instagram Reel URL into the input field
2. Click **Generate KSL**
3. Watch the 4-stage pipeline progress bar
4. Download your accessible Reel MP4

**Option B — Upload video:**
1. Drop any MP4/MOV file onto the upload zone
2. Click **Generate KSL**
3. Download the output

---

## Project Structure

```
sign-bridge/
├── backend/
│   ├── app.py                    # Flask API server (security-hardened)
│   ├── requirements.txt          # Python dependencies
│   ├── .env.example              # Environment template (copy to .env)
│   └── pipeline/
│       ├── wonder_transcribe.py  # Step 1: Audio → English (Muse Wonder)
│       ├── spark_translate.py    # Step 2: English → KSL Gloss (Muse Spark)
│       ├── sam_placement.py      # Step 3: Frame analysis (SAM 3.1)
│       └── avatar_generate.py   # Step 4: Avatar + ffmpeg composite
└── frontend/
    ├── index.html                # Single-page app
    ├── app.js                    # Pipeline UI + polling
    └── styles.css                # Dark-mode design system
```

---

## KSL Gloss Examples

| English | KSL Gloss |
|---|---|
| "Add two tomatoes" | `TOMATO TWO ADD` |
| "She went to the market" | `SHE MARKET GO` |
| "Do you understand?" | `YOU UNDERSTAND Q-YES/NO` |
| "Hello everyone, today we cook pilau" | `HELLO TODAY PILAU COOK` |

KSL uses **Subject-Object-Verb (SOV)** order, drops copulas (is/am/are), and has unique signs for Kenyan cultural concepts: `HARAMBEE`, `UGALI`, `MATATU`, `BODA`, `SHAMBA`.

---

## Security

- API key loaded from `.env` only — never hardcoded, never committed
- File uploads validated by extension + MIME type
- 200 MB upload limit enforced at server level
- Path traversal prevented on all download endpoints
- Security headers on every response (CSP, X-Frame-Options, nosniff)
- Job IDs validated before lookup
- Error messages sanitized (no internal paths exposed)

---

## Supported Sign Languages

| Code | Language | Country | Status |
|---|---|---|---|
| KSL | Kenyan Sign Language | Kenya | Primary |
| USL | Ugandan Sign Language | Uganda | Beta |
| TSL | Tanzanian Sign Language | Tanzania | Beta |
| ASL | American Sign Language | USA/Canada | Available |

---

## Impact

- **70M** Deaf people globally lack social media access
- **1M** Deaf Kenyans underserved by existing tools
- Sign Bridge is the **first open-source KSL video accessibility tool**
- Built to scale across all East African sign languages

---

## Built With

| Technology | Role |
|---|---|
| [Meta Muse Wonder 1.0](https://ai.meta.com) | Audio transcription |
| [Meta Muse Spark 1.3](https://ai.meta.com) | NLP + KSL translation |
| [Meta SAM 3.1](https://ai.meta.com) | Video frame segmentation |
| [Meta Muse Image 1.0](https://ai.meta.com) | Avatar image generation |
| Flask | Backend API |
| FFmpeg | Video compositing |
| yt-dlp | Instagram Reel download |

---

## License

MIT © 2026 Sign Bridge — Built for Meta Global AI Hackathon

---

> *"Accessibility is not a feature — it's a right."*
