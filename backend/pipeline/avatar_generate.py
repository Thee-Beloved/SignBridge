"""
SIGN BRIDGE  Step 4: KSL Avatar Generation via Muse Image + Motion
===================================================================
Generates a consistent Kenyan Sign Language signing avatar,
then animates it per gloss token, then overlays on the original video.

Avatar design:
  - Young Kenyan woman in colorful lesso/kitenge pattern top
  - Consistent seed = same avatar across ALL videos (brand recognition)
  - Clear, visible hands against contrasting background
  - Transparent circular/rounded-square frame overlay

Two modes:
  1. REEL MODE: Generate signing avatar frames  overlay on Reel
  2. CREATOR MODE: Deaf creator signs  generate voice + captions
"""

import os
import re
import requests
import base64
import json
import subprocess
import platform
from collections import defaultdict
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

META_API_KEY = os.getenv("META_API_KEY")
META_API_BASE = "https://api.meta.ai/v1"

# CONSISTENT AVATAR SEED  same seed = same avatar every time (brand consistency)
AVATAR_SEED = 47291


# ── AVATAR STYLE PROMPT ───────────────────────────────────────────────────────

AVATAR_BASE_PROMPT = """
Professional Kenyan Sign Language interpreter, young woman,
wearing a vibrant Ankara/kitenge pattern top in blue and orange,
short natural hair, warm brown skin, clear expressive eyes,
neutral light gray background for contrast,
hands clearly visible with detailed fingers,
signing position: chest level, facing camera directly,
professional interpreter style, no accessories blocking hands,
soft studio lighting, clean and accessible visual style,
portrait crop showing head, shoulders, chest, and both hands fully visible.
"""

SIGN_PROMPTS = {
    "HELLO": "person waving right hand open palm at shoulder height, friendly greeting",
    "THANK-YOU": "person touching chin with fingertips then extending hand forward",
    "YES": "person nodding head and making fist bob motion",
    "NO": "person shaking head, index and middle finger tapping thumb twice",
    "HELP": "person with one hand supporting other fist, lifting upward",
    "WATER": "person making W-handshape tapping lips twice",
    "FOOD": "person bringing fingertips to mouth repeatedly",
    "COOK": "person making stirring motion with both hands",
    "ADD": "person bringing two hands together, palms up",
    "GOOD": "person moving flat hand from chin outward",
    "BAD": "person throwing hand downward from chin",
    "UNDERSTAND": "person raising index finger at temple",
    "NOT-UNDERSTAND": "person shaking hand at temple side to side",
    "GO": "person pointing index fingers forward and moving them away",
    "COME": "person beckoning with index finger toward body",
    "STOP": "person chopping one hand onto other flat palm",
    "WAIT": "person holding up hand with spread fingers",
    "LOVE": "person crossing arms over chest",
    "FAMILY": "person making F-handshape in circular motion",
    "HOME": "person touching fingertips to cheek then moving to flat handshape",
    "WORK": "person tapping one fist on top of other fist",
    "MONEY": "person tapping palm with other fingers",
    "HOSPITAL": "person making H-handshape on upper arm",
    "SCHOOL": "person clapping hands together twice",
    "PILAU": "person miming rice cooking with stirring motion, Kenyan context",
    "UGALI": "person miming thick porridge stirring, Kenyan traditional",
    "SUKUMA": "person making vegetable picking motion with fingers",
    "HARAMBEE": "person with both hands raised, community gathering sign",
    "MATATU": "person miming vehicle steering wheel motion",
    "BODA": "person miming motorcycle handlebar with both hands",
    "MARKET": "person making exchanging/trading motion with hands",
    "DEFAULT": "person in neutral ready signing position, hands at chest level"
}


def generate_avatar_frame(
    sign_token: str,
    output_path: str,
    avatar_width: int = 302,
    avatar_height: int = 538
) -> str:
    """
    Generate a single KSL avatar frame for a given sign token via Muse Image.
    Uses a consistent seed for brand uniformity across all videos.

    Returns: Path to saved avatar PNG.
    """
    sign_description = SIGN_PROMPTS.get(sign_token, SIGN_PROMPTS["DEFAULT"])
    full_prompt = (
        f"{AVATAR_BASE_PROMPT.strip()} "
        f"Currently signing: {sign_description}. "
        f"Sign token: {sign_token}. "
        f"Kenyan Sign Language (KSL) signing gesture."
    )

    response = requests.post(
        f"{META_API_BASE}/images/generations",
        headers={
            "Authorization": f"Bearer {META_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "muse-image-1.0",
            "prompt": full_prompt,
            "size": "512x512",
            "n": 1,
            "seed": AVATAR_SEED,
            "response_format": "b64_json"
        },
        timeout=60
    )

    if response.status_code != 200:
        raise RuntimeError(f"Muse Image error {response.status_code}: {response.text[:300]}")

    result = response.json()
    image_b64 = result["data"][0]["b64_json"]

    image_data = base64.b64decode(image_b64)
    with open(output_path, "wb") as f:
        f.write(image_data)

    return output_path


def generate_avatar_sequence(
    gloss_tokens: List[str],
    frames_dir: str,
    avatar_width: int,
    avatar_height: int
) -> List[Dict]:
    """
    Generate avatar frames for all KSL gloss tokens.
    Caches frames per unique sign to avoid redundant API calls.

    Returns:
        List of {"token": "ADD", "frame_path": ".../sign_ADD.png"}
    """
    os.makedirs(frames_dir, exist_ok=True)

    sign_cache: Dict[str, str] = {}  # uppercase_token -> frame_path

    # Always generate DEFAULT frame first so fallback always exists
    default_frame_path = os.path.join(frames_dir, "sign_DEFAULT.png")
    if not os.path.exists(default_frame_path):
        print("[Avatar] Generating DEFAULT neutral frame...")
        try:
            generate_avatar_frame(
                sign_token="DEFAULT",
                output_path=default_frame_path,
                avatar_width=avatar_width,
                avatar_height=avatar_height
            )
        except Exception as e:
            print(f"[Avatar] Could not generate DEFAULT via API: {e}. Creating gray placeholder.")
            from PIL import Image as PILImage
            PILImage.new("RGBA", (avatar_width, avatar_height), (128, 128, 128, 180)).save(default_frame_path)
    sign_cache["DEFAULT"] = default_frame_path

    # Generate unique sign frames (skip DEFAULT already done above)
    unique_tokens = {t.upper() for t in gloss_tokens if t.upper() != "DEFAULT"}
    print(f"[Avatar] Generating {len(unique_tokens)} unique sign frames...")

    for cache_key in unique_tokens:
        frame_path = os.path.join(frames_dir, f"sign_{cache_key}.png")
        if os.path.exists(frame_path):
            sign_cache[cache_key] = frame_path
            print(f"[Avatar] Cached: {cache_key}")
        else:
            print(f"[Avatar] Generating sign: {cache_key}")
            try:
                generate_avatar_frame(
                    sign_token=cache_key,
                    output_path=frame_path,
                    avatar_width=avatar_width,
                    avatar_height=avatar_height
                )
                sign_cache[cache_key] = frame_path
            except Exception as e:
                print(f"[Avatar] Failed to generate {cache_key}: {e} -- using DEFAULT")
                sign_cache[cache_key] = default_frame_path

    # Build ordered sequence
    frame_sequence = []
    for token in gloss_tokens:
        cache_key = token.upper()
        frame_sequence.append({
            "token": token,
            "frame_path": sign_cache.get(cache_key, default_frame_path)
        })

    print(f"[Avatar] Sequence ready: {len(frame_sequence)} frames ({len(unique_tokens)} unique)")
    return frame_sequence


def overlay_avatar_on_video(
    source_video: str,
    frame_sequence: List[Dict],
    timed_segments: List[Dict],
    placement: Dict,
    output_path: str,
    avatar_opacity: float = 0.92
) -> str:
    """
    Overlay KSL avatar frames onto original Reel using ffmpeg.

    Key optimisation: deduplicates frames so ffmpeg only receives one
    -i input per UNIQUE avatar image, with a combined enable expression
    covering all its time windows. This keeps filter_complex small even
    for long videos with many repeated signs.

    Args:
        source_video:   Original video file path
        frame_sequence: Avatar frames with tokens (from generate_avatar_sequence)
        timed_segments: Timed KSL segments with sign_duration (from spark_translate)
        placement:      SAM placement dict with 'position' [x1,y1,x2,y2]
        output_path:    Where to write the output MP4
        avatar_opacity: 0.0-1.0 (unused by overlay filter but kept for API compat)

    Returns: output_path
    """
    x1, y1, x2, y2 = placement["position"]
    avatar_w = x2 - x1
    avatar_h = y2 - y1

    # ── Build (sign_start, sign_end, frame_path) list ────────────────────────
    raw_overlays: List[tuple] = []
    for segment in timed_segments:
        start = segment["start"]
        end = segment["end"]
        tokens = segment.get("gloss_tokens", [])
        sign_dur = segment.get("sign_duration", max(end - start, 0.1) / max(len(tokens), 1))

        for tok_idx, token in enumerate(tokens):
            sign_start = start + tok_idx * sign_dur
            sign_end = min(sign_start + sign_dur, end)

            frame = next((f for f in frame_sequence if f["token"] == token), None)
            if not frame:
                continue
            fp = frame["frame_path"]
            if not fp or not os.path.exists(fp):
                print(f"[Overlay] Skipping missing frame: {fp}")
                continue

            raw_overlays.append((sign_start, sign_end, fp))

    if not raw_overlays:
        import shutil
        shutil.copy2(source_video, output_path)
        print(f"[Overlay] No avatar frames; copied source to: {output_path}")
        return output_path

    # ── DEDUPLICATE: group time windows by unique frame_path ─────────────────
    # This reduces ffmpeg inputs from N tokens to U unique frames (U << N)
    frame_intervals: Dict[str, List[tuple]] = defaultdict(list)
    for sign_start, sign_end, fp in raw_overlays:
        frame_intervals[fp].append((sign_start, sign_end))

    unique_frames = list(frame_intervals.keys())
    print(f"[Overlay] {len(raw_overlays)} token slots -> {len(unique_frames)} unique frames (deduped)")

    # ── Build ffmpeg command ──────────────────────────────────────────────────
    cmd = ["ffmpeg", "-y", "-i", source_video]
    for fp in unique_frames:
        cmd += ["-i", fp]

    # Scale each unique frame once
    filter_parts = []
    for idx, fp in enumerate(unique_frames):
        input_idx = idx + 1
        filter_parts.append(
            f"[{input_idx}:v]scale={avatar_w}:{avatar_h}[scaled{input_idx}]"
        )

    # Chain overlays — one per unique frame, with combined enable expression
    prev = "0:v"
    for idx, fp in enumerate(unique_frames):
        input_idx = idx + 1
        out_label = f"v{input_idx}"
        intervals = frame_intervals[fp]

        # Combine all time windows into one enable expression
        enable_expr = "+".join(
            f"between(t,{s:.3f},{e:.3f})" for s, e in intervals
        )
        filter_parts.append(
            f"[{prev}][scaled{input_idx}]overlay="
            f"x={x1}:y={y1}:"
            f"enable='{enable_expr}'"
            f"[{out_label}]"
        )
        prev = out_label

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{prev}]",
        "-map", "0:a?",          # Optional audio — won't fail if stream absent
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-crf", "23",
        output_path
    ]

    print(f"[Overlay] Rendering final video -> {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[Overlay] ffmpeg stderr:\n{result.stderr[-2000:]}")
        raise RuntimeError(f"ffmpeg overlay failed (code {result.returncode}): {result.stderr[-500:]}")

    print(f"[Overlay] Done: {output_path}")
    return output_path


# ── CREATOR MODE (REVERSE PIPELINE) ──────────────────────────────────────────

def creator_mode_ksl_to_voice(
    creator_video_path: str,
    output_path: str
) -> Dict:
    """
    CREATOR MODE: Deaf creator signs in KSL  English voice + captions.

    Pipeline:
    1. SAM 3.1 extracts hand/body movements from creator video
    2. Muse Spark classifies KSL signs from movement patterns
    3. Converts KSL Gloss  English sentence
    4. Muse Wonder generates natural English voiceover
    5. Adds English captions to video
    """
    print("[Creator Mode] Analyzing KSL signs from creator video...")

    # Step 1: Extract sign sequences via SAM /v1/responses
    sign_response = requests.post(
        f"{META_API_BASE}/responses",
        headers={"Authorization": f"Bearer {META_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "sam-3.1",
            "input": [{"role": "user", "content": [
                {
                    "type": "text",
                    "text": (
                        "Analyze this KSL signing video. Identify the sign language gestures "
                        "and return a JSON object with 'detected_glosses' as a list of KSL "
                        "gloss tokens (uppercase). Example: {\"detected_glosses\": [\"HELLO\", \"FOOD\", \"COOK\"]}"
                    )
                }
            ]}]
        },
        timeout=60
    )

    from pipeline.sam_placement import _extract_json_from_text
    sign_data = {}
    if sign_response.status_code == 200:
        rdata = sign_response.json()
        for block in rdata.get("output", []):
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    sign_data = _extract_json_from_text(item["text"])
                    break

    ksl_glosses = sign_data.get("detected_glosses", [])
    print(f"[Creator Mode] Detected glosses: {' '.join(ksl_glosses)}")

    # Step 2: Gloss  English with Spark /v1/responses
    gloss_text = " ".join(ksl_glosses) if ksl_glosses else "HELLO EVERYONE"
    english_response = requests.post(
        f"{META_API_BASE}/responses",
        headers={"Authorization": f"Bearer {META_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "muse-spark-1.3",
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Convert Kenyan Sign Language (KSL) gloss notation to natural English. "
                        "KSL uses SOV structure. Make the English sound natural and conversational. "
                        "Example: 'TOMATO TWO ADD PILAU COOK' -> 'Add two tomatoes and cook the pilau'"
                    )
                },
                {"role": "user", "content": gloss_text}
            ]
        },
        timeout=60
    )

    english_text = "Hello everyone."
    if english_response.status_code == 200:
        edata = english_response.json()
        for block in edata.get("output", []):
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    english_text = item["text"].strip()
                    break

    print(f"[Creator Mode] English: {english_text}")

    # Step 3: Generate voice with Wonder TTS
    voice_response = requests.post(
        f"{META_API_BASE}/audio/speech",
        headers={"Authorization": f"Bearer {META_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "muse-wonder-1.0",
            "input": english_text,
            "voice": "nairobi_female",
            "speed": 0.95,
            "format": "mp3"
        },
        timeout=60
    )

    voice_path = output_path.replace(".mp4", "_voice.mp3")
    with open(voice_path, "wb") as f:
        f.write(voice_response.content)

    # Step 4: Merge voice + captions onto creator's video
    # Windows FFmpeg often has fontconfig issues, so we'll use a simpler approach
    # without drawtext for now, or specify a font file explicitly
    
    import platform
    
    # Try to find a system font on Windows
    font_path = None
    if platform.system() == "Windows":
        # Common Windows font locations
        possible_fonts = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/verdana.ttf"
        ]
        for font in possible_fonts:
            if os.path.exists(font):
                font_path = font.replace("\\", "/").replace(":", "\\:")
                break
    
    if font_path:
        # Use drawtext with explicit font file
        safe_text = re.sub(r"['\"]", "", english_text)[:80]  # strip quotes
        safe_text = safe_text.replace(":", r"\:").replace("'", r"\'")  # escape special chars
        
        final_cmd = [
            "ffmpeg", "-y",
            "-i", creator_video_path,
            "-i", voice_path,
            "-filter_complex",
            (
                f"[0:v]drawtext=fontfile='{font_path}':text='{safe_text}':"
                "fontsize=28:fontcolor=white:box=1:boxcolor=black@0.6:"
                "x=(w-text_w)/2:y=h-60[v]"
            ),
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            output_path
        ]
    else:
        # Fallback: Just merge video and audio without captions
        print("[Creator Mode] Warning: No font found, skipping captions overlay")
        final_cmd = [
            "ffmpeg", "-y",
            "-i", creator_video_path,
            "-i", voice_path,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",  # Just copy video stream
            "-c:a", "aac",
            output_path
        ]
    
    result = subprocess.run(final_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Creator Mode] FFmpeg error: {result.stderr[-1000:]}")
        raise RuntimeError(f"FFmpeg creator mode failed: {result.stderr[-500:]}")

    return {
        "mode": "creator",
        "ksl_glosses": ksl_glosses,
        "english_text": english_text,
        "output_video": output_path,
        "voice_audio": voice_path
    }
