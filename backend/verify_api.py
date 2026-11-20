"""
SIGN BRIDGE -- API Verification Script
=======================================
Tests every Meta API model the pipeline depends on.
Usage:  python verify_api.py
"""

import os, sys, json, tempfile, wave, struct, base64
import requests
from dotenv import load_dotenv

load_dotenv()
KEY  = os.getenv("META_API_KEY", "")
BASE = "https://api.meta.ai/v1"
HDR  = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []

def test(name, fn):
    try:
        status, detail = fn()
        results.append((status, name, detail))
        icon = "[OK]" if status == PASS else ("[--]" if status == SKIP else "[!!]")
        print(f"  {icon} {name}: {detail}")
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  [!!] {name}: EXCEPTION -- {e}")

def make_silent_wav():
    path = os.path.join(tempfile.gettempdir(), "sb_test_silence.wav")
    with wave.open(path, "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 8000, *([0] * 8000)))
    return path

def extract_content(data):
    """Extract text from /chat/completions OR /v1/responses format."""
    # /chat/completions
    try:
        c = data["choices"][0]["message"]["content"]
        if c is not None:
            return c
    except (KeyError, IndexError, TypeError):
        pass
    # /v1/responses output blocks
    try:
        for block in data.get("output", []):
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    return item["text"]
    except Exception:
        pass
    return data.get("content") or data.get("text") or None

def post_responses(model, input_list, extra=None):
    """POST to /v1/responses endpoint (SAM, Spark, Wonder use this)."""
    body = {"model": model, "input": input_list}
    if extra:
        body.update(extra)
    return requests.post(BASE + "/responses", headers=HDR, timeout=25, json=body)


print()
print("=" * 56)
print("  SIGN BRIDGE -- API VERIFICATION")
print("=" * 56)
print(f"  Key: {KEY[:8]}...{KEY[-4:]}")
print()

#  1. Models list 
print("[1/6] Checking available models...")
def check_models():
    r = requests.get(BASE + "/models", headers=HDR, timeout=10)
    if r.status_code != 200:
        return FAIL, f"HTTP {r.status_code}: {r.text[:100]}"
    models = [m["id"] for m in r.json().get("data", [])]
    required = ["muse-voice-transcribe-1.0", "muse-spark-1.3", "sam-3.1", "muse-image-1.0"]
    missing  = [m for m in required if m not in models]
    print(f"    Available models: {models}")
    if missing:
        return FAIL, f"Missing models: {missing}"
    return PASS, f"{len(models)} models available, all required present"
test("Models endpoint", check_models)

#  2. Muse Spark 1.3 via /v1/responses 
# muse-spark-1.3 is a reasoning model -- must use /v1/responses
print("\n[2/6] Testing Muse Spark 1.3 (KSL translation)...")
def check_spark():
    r = post_responses("muse-spark-1.3", [{
        "role": "user",
        "content": (
            "Convert to KSL Gloss (Kenyan Sign Language). "
            "SOV order, UPPERCASE, drop articles. Output gloss only.\n"
            "Sentence: Add two tomatoes and stir the pot"
        )
    }])
    if r.status_code == 402:
        return FAIL, "BILLING NOT ACTIVATED"
    if r.status_code != 200:
        return FAIL, f"HTTP {r.status_code}: {r.text[:200]}"
    gloss = extract_content(r.json())
    if gloss is None:
        return FAIL, f"content None. resp: {str(r.json())[:250]}"
    return PASS, f"KSL gloss: {gloss.strip()[:80]}"
test("Muse Spark 1.3 -- KSL translation", check_spark)

#  3. Audio transcription 
# muse-wonder-1.0 is listed in models; muse-voice-transcribe-1.0 also listed
print("\n[3/6] Testing audio transcription...")
def check_transcribe():
    wav_path = make_silent_wav()
    with open(wav_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()
    os.remove(wav_path)

    # Try models that are actually in the models list
    audio_models = ["muse-wonder-1.0", "muse-voice-transcribe-1.0"]
    # Try different content type names Meta might use
    audio_content_types = [
        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
        {"type": "audio",       "audio":        {"data": audio_b64, "format": "wav"}},
    ]

    last_status, last_text = 0, ""
    for model_name in audio_models:
        for content_item in audio_content_types:
            r = post_responses(model_name, [{
                "role": "user",
                "content": [content_item]
            }])
            last_status, last_text = r.status_code, r.text
            if r.status_code in [200, 422]:
                return PASS, f"Audio OK via /v1/responses model={model_name} (HTTP {r.status_code})"
            if r.status_code == 402:
                return FAIL, "BILLING NOT ACTIVATED"

        # Also try /audio/transcriptions multipart
        wav_path2 = make_silent_wav()
        with open(wav_path2, "rb") as f:
            ra = requests.post(
                BASE + "/audio/transcriptions",
                headers={"Authorization": "Bearer " + KEY},
                data={"model": model_name, "response_format": "json"},
                files={"file": ("test.wav", f, "audio/wav")},
                timeout=20
            )
        os.remove(wav_path2)
        last_status, last_text = ra.status_code, ra.text
        if ra.status_code in [200, 422]:
            return PASS, f"Audio OK via /audio/transcriptions model={model_name} (HTTP {ra.status_code})"
        if ra.status_code == 402:
            return FAIL, "BILLING NOT ACTIVATED"

    return FAIL, f"All audio combos failed. Last HTTP {last_status}: {last_text[:120]}"
test("Audio transcription", check_transcribe)

#  4. SAM 3.1 via /v1/responses 
print("\n[4/6] Testing SAM 3.1 (vision/segment)...")
def check_sam():
    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    r = post_responses("sam-3.1", [{"role": "user", "content": [
        {"type": "text", "text": "Detect people. Return bounding boxes."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny_png_b64}"}}
    ]}])
    if r.status_code == 402:
        return FAIL, "BILLING NOT ACTIVATED"
    if r.status_code in [200, 400, 422]:
        return PASS, f"SAM 3.1 via /v1/responses OK (HTTP {r.status_code})"
    return FAIL, f"HTTP {r.status_code}: {r.text[:200]}"
test("SAM 3.1 -- video segmentation", check_sam)

#  5. Muse Image 1.0 
print("\n[5/6] Testing muse-image-1.0 (avatar)...")
def check_image():
    r = requests.post(BASE + "/images/generations", headers=HDR, timeout=30, json={
        "model": "muse-image-1.0",
        "prompt": "Professional KSL interpreter, waving hello, clear hands visible",
        "n": 1, "size": "256x256"
    })
    if r.status_code == 402:
        return FAIL, "BILLING NOT ACTIVATED"
    if r.status_code == 200:
        return PASS, f"Image generated! Has data: {'b64_json' in r.text or 'url' in r.text}"
    return FAIL, f"HTTP {r.status_code}: {r.text[:150]}"
test("muse-image-1.0 -- avatar generation", check_image)

#  6. Full KSL via /v1/responses 
print("\n[6/6] Testing full KSL prompt with Kenyan context...")
def check_full_ksl():
    r = post_responses("muse-spark-1.3", [{
        "role": "user",
        "content": (
            "You are a KSL (Kenyan Sign Language) expert interpreter.\n"
            "Convert to KSL Gloss: SOV order, UPPERCASE, drop articles/copulas, "
            "time markers first, numbers before nouns. Output gloss ONLY.\n\n"
            "Sentence: Sawa guys, today we cook ugali and sukuma wiki for the family"
        )
    }])
    if r.status_code == 402:
        return FAIL, "BILLING NOT ACTIVATED"
    if r.status_code != 200:
        return FAIL, f"HTTP {r.status_code}: {r.text[:200]}"
    gloss = extract_content(r.json())
    if gloss is None:
        return FAIL, f"content None. resp: {str(r.json())[:250]}"
    return PASS, f"Full KSL gloss: {gloss.strip()[:80]}"
test("Full KSL system prompt -- Kenyan sentence", check_full_ksl)


#  SUMMARY 
print()
print("=" * 56)
passed  = sum(1 for s, _, _ in results if s == PASS)
failed  = sum(1 for s, _, _ in results if s == FAIL)
skipped = sum(1 for s, _, _ in results if s == SKIP)
print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
print()

if failed == 0:
    print("  ALL SYSTEMS GO -- Ready to test with a real Reel!")
    print()
    print("  Next:")
    print("    yt-dlp -o uploads/test_reel.mp4 --format mp4 <REEL_URL>")
    print("    curl -X POST http://localhost:5000/api/process-reel -F video=@uploads/test_reel.mp4")
    sys.exit(0)
else:
    print("  FAILED TESTS:")
    for status, name, detail in results:
        if status == FAIL:
            print(f"  [!!] {name}")
            print(f"       {detail}")
    sys.exit(1)
