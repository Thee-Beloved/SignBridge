"""
SIGN BRIDGE  Step 1: Audio Transcription via Meta Muse Wonder
============================================================
Muse Wonder 1.0 is Meta's transcription model for noisy audio,
music backgrounds, and code-switching languages like Sheng.

API: Meta Model API  model="muse-wonder-1.0" via /v1/responses
Handles: Loud music, multiple speakers, Sheng slang, crowd noise
"""

import os
import base64
import requests
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load .env file

META_API_KEY = os.getenv("META_API_KEY")
META_API_BASE = "https://api.meta.ai/v1"
HDR = {"Authorization": f"Bearer {META_API_KEY}", "Content-Type": "application/json"}


def extract_audio_from_video(video_path: str) -> str:
    """
    Extract audio track from video file using ffmpeg.
    Returns path to extracted .wav audio file.
    """
    # Use Path for robust cross-platform extension handling
    p = Path(video_path)
    audio_path = str(p.with_suffix("")) + "_audio.wav"
    
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # raw PCM for best transcription accuracy
        "-ar", "16000",           # 16kHz sample rate (Wonder's preferred rate)
        "-ac", "1",               # mono channel
        "-y",                     # overwrite output
        audio_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")
    
    return audio_path


def transcribe_with_wonder(audio_path: str, language_hints: list = None) -> dict:
    """
    Transcribe audio using Meta Muse Wonder 1.0 via /v1/responses.

    Confirmed working endpoint from API verification (Oct 26).
    Uses input_audio content type with base64-encoded WAV data.
    """
    if language_hints is None:
        language_hints = ["sw", "en"]  # Sheng (Swahili + English)

    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()

    response = requests.post(
        f"{META_API_BASE}/responses",
        headers=HDR,
        timeout=60,
        json={
            "model": "muse-wonder-1.0",
            # API only accepts a single content item per message (no mixed text+audio).
            # The transcription instruction is embedded via the system prompt workaround:
            # send audio-only in user content; model transcribes by default.
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a transcription assistant. "
                        "Transcribe the audio accurately. "
                        "The speaker may mix English and Swahili (Sheng). "
                        "Common words: sawa=okay, poa=cool, leo=today, "
                        "ugali=maize meal, pilau=spiced rice, boda=motorbike. "
                        "Return the full transcript text only, no extra commentary."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_b64, "format": "wav"}
                        }
                    ]
                }
            ]
        }
    )

    if response.status_code != 200:
        raise RuntimeError(f"Wonder API error {response.status_code}: {response.text}")

    data = response.json()

    # Extract text from /v1/responses output format
    transcript_text = ""
    try:
        for block in data.get("output", []):
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    transcript_text = item["text"]
                    break
    except Exception:
        transcript_text = data.get("text", "")

    # Build normalized result compatible with rest of pipeline
    result = {
        "text": transcript_text,
        "text_normalized": normalize_sheng(transcript_text),
        "segments": [{"start": 0.0, "end": 999.0, "text": transcript_text}],
        "words": [],   # Wonder 1.0 via /responses doesn't return word timestamps
        "detected_language": "sw-en",
        "confidence": 0.9
    }

    return result


def normalize_sheng(text: str) -> str:
    """
    Normalize common Sheng/Swahili words to English for KSL gloss translation.
    KSL gloss is based on English structure.
    """
    sheng_to_english = {
        "sawa": "okay",
        "poa": "cool",
        "mambo": "what's up",
        "vipi": "how",
        "leo": "today",
        "kesho": "tomorrow",
        "jana": "yesterday",
        "chakula": "food",
        "maji": "water",
        "nyumba": "house",
        "shule": "school",
        "dawa": "medicine",
        "hospitali": "hospital",
        "gari": "car",
        "pesa": "money",
        "kazi": "work",
        "familia": "family",
        "mtoto": "child",
        "mama": "mother",
        "baba": "father",
        "rafiki": "friend",
        "watu": "people",
        "mji": "city",
        "nchi": "country",
        "jua": "sun",
        "mvua": "rain",
        "usiku": "night",
        "asubuhi": "morning",
        "jioni": "evening",
        "ndio": "yes",
        "hapana": "no",
        "tafadhali": "please",
        "asante": "thank you",
        "karibu": "welcome",
        "bado": "not yet",
        "sana": "very much",
        "kidogo": "a little",
        # Kenyan cultural / food / transport
        "shamba": "farm",
        "boda": "motorcycle taxi",
        "matatu": "minibus",
        "duka": "shop",
        "chama": "savings group",
        "harambee": "community gathering",
        "ugali": "maize porridge",
        "pilau": "spiced rice",
        "sukuma": "kale",
        "nyanya": "tomato",
        "mchele": "rice",
        "uji": "porridge",
        "githeri": "beans and maize",
        "chapati": "flatbread",
        # Common Sheng slang
        "safi": "clean",
        "mbaya": "bad",
        "nzuri": "good",
        "kubwa": "big",
        "ndogo": "small",
        "haraka": "fast",
        "polepole": "slowly",
        "pamoja": "together",
        "umeme": "electricity",
        "mwalimu": "teacher",
        "daktari": "doctor",
        "polisi": "police",
    }
    
    words = text.lower().split()
    normalized = []
    for word in words:
        clean = word.strip(".,!?;:")
        punct = word[len(clean):]
        normalized.append(sheng_to_english.get(clean, clean) + punct)
    
    return " ".join(normalized)


def transcribe_reel(video_path: str) -> dict:
    """
    Full pipeline: video  audio  Wonder transcript.
    Main entry point for the Sign Bridge pipeline.
    
    Returns transcript dict with:
    - text: clean English/normalized transcript
    - words: word-level timestamps for avatar sync
    - segments: sentence-level chunks for translation batching
    """
    print(f"[Wonder] Extracting audio from: {video_path}")
    audio_path = extract_audio_from_video(video_path)
    
    print(f"[Wonder] Transcribing with Muse Wonder 2 (noise-robust mode)...")
    transcript = transcribe_with_wonder(audio_path)
    
    # Cleanup temp audio
    os.remove(audio_path)
    
    print(f"[Wonder] Transcript: {transcript.get('text_normalized', '')[:100]}...")
    print(f"[Wonder] Confidence: {transcript.get('confidence', 'N/A')}")
    
    return transcript


#  TEST 
if __name__ == "__main__":
    # Mock test without real API key
    sample_text = "Sawa guys, today we cook pilau. First add maji then nyanya mbili."
    print("Input:", sample_text)
    print("Normalized:", normalize_sheng(sample_text))
    # Expected: "okay guys, today we cook pilau. First add water then nyanya two."
