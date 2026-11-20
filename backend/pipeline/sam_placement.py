"""
SIGN BRIDGE  Step 3: SAM 3.1 Smart Avatar Placement
=====================================================
Meta's SAM 3.1 (Segment Anything Model) analyzes each frame of the Reel
to find where the speaker's face and hands are, then calculates the
BEST corner to place the KSL avatar without covering important content.

Priority:
  1. Never cover the speaker's face
  2. Never cover active hands (cooking demos, etc.)
  3. Prefer bottom-right corner (Instagram UI convention)
  4. Fallback order: bottom-right  bottom-left  top-right  top-left
"""

import os
import re
import json
import tempfile
import requests
import base64
from typing import Tuple, List, Dict, Optional
from PIL import Image
import io

META_API_KEY = os.getenv("META_API_KEY")
META_API_BASE = "https://api.meta.ai/v1"

AVATAR_SIZE_RATIO = 0.28  # Avatar = 28% of video width
PADDING = 0.02            # 2% padding from edges


def encode_frame_to_base64(frame_path: str) -> str:
    """Encode a video frame as base64 for SAM 3.1 API."""
    with open(frame_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _extract_json_from_text(text: str) -> Dict:
    """
    Robustly extract the first JSON object from text.
    Handles markdown code fences (```json ... ```) and inline JSON.
    Returns empty dict on failure.
    """
    if not text:
        return {}

    # Strip markdown fences
    if "```" in text:
        parts = text.split("```")
        for part in parts[1::2]:  # Odd parts are inside fences
            cleaned = re.sub(r"^json\s*", "", part.strip(), flags=re.IGNORECASE)
            try:
                return json.loads(cleaned)
            except Exception:
                pass

    # Find first {...} block in free text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return {}


def segment_frame_with_sam(frame_base64: str, video_width: int, video_height: int) -> Dict:
    """
    Call SAM 3.1 to analyze a frame and identify safe corners for avatar placement.
    Uses /v1/responses endpoint.
    Falls back gracefully to empty segments on timeout, connection error, or bad response.
    """
    try:
        response = requests.post(
            f"{META_API_BASE}/responses",
            headers={
                "Authorization": f"Bearer {META_API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=15,  # Hard cap per frame
            json={
                "model": "sam-3.1",
                "input": [{
                    "role": "user",
                    "content": f"data:image/jpeg;base64,{frame_base64}"
                }],
                "text": (
                    "Analyze this video frame. Return JSON with bounding boxes "
                    "(x, y, width, height as 0.0-1.0 fractions of image size) for: "
                    "person, face, hands, text_overlay. "
                    'Example: {"segments":{"face":{"x":0.3,"y":0.1,"w":0.4,"h":0.3}}}'
                )
            }
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        raise RuntimeError(f"SAM 3.1 request failed: {e}")

    if response.status_code != 200:
        raise RuntimeError(f"SAM 3.1 error {response.status_code}: {response.text[:200]}")

    # Robustly extract JSON from response
    data = response.json()
    raw_text = ""
    try:
        for block in data.get("output", []):
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    raw_text = item["text"].strip()
                    break
    except Exception:
        pass

    segments = _extract_json_from_text(raw_text) if raw_text else {}

    # Calculate safe avatar placement zones
    safe_regions = calculate_safe_zones(segments, video_width, video_height)
    segments["safe_regions"] = safe_regions

    return segments


def calculate_safe_zones(segments: Dict, width: int, height: int) -> Dict:
    """
    Determine which corners are safe for avatar placement.
    A corner is UNSAFE if face/hands overlap with the avatar bounding box there.
    """
    avatar_w = int(width * AVATAR_SIZE_RATIO)
    avatar_h = int(height * AVATAR_SIZE_RATIO)
    pad_x = int(width * PADDING)
    pad_y = int(height * PADDING)

    corners = {
        "bottom_right": [
            width - avatar_w - pad_x, height - avatar_h - pad_y,
            width - pad_x,            height - pad_y
        ],
        "bottom_left": [
            pad_x,             height - avatar_h - pad_y,
            avatar_w + pad_x,  height - pad_y
        ],
        "top_right": [
            width - avatar_w - pad_x, pad_y,
            width - pad_x,            avatar_h + pad_y
        ],
        "top_left": [
            pad_x,            pad_y,
            avatar_w + pad_x, avatar_h + pad_y
        ]
    }

    # Collect critical regions (face + hands + text) that avatar must not cover
    critical_regions = []
    detections = segments.get("detections", segments.get("segments", {}))

    if "face" in detections:
        face = detections["face"]
        # Convert normalized 0-1 bbox to pixel bbox if needed
        critical_regions.append(_normalize_bbox(face, width, height))

    if "hands" in detections:
        hands = detections["hands"]
        if isinstance(hands, list):
            for h in hands:
                critical_regions.append(_normalize_bbox(h, width, height))
        elif isinstance(hands, dict):
            critical_regions.append(_normalize_bbox(hands, width, height))

    if "text_overlay" in detections:
        critical_regions.append(_normalize_bbox(detections["text_overlay"], width, height))

    # Also handle SAM safe_corners hint if returned directly
    sam_safe_corners = segments.get("safe_corners", {})

    safe_results = {}
    for corner_name, corner_box in corners.items():
        # First check SAM's own safe_corners hint
        if corner_name in sam_safe_corners:
            is_safe = bool(sam_safe_corners[corner_name])
        else:
            overlaps = any(
                boxes_overlap(corner_box, region)
                for region in critical_regions
                if region
            )
            is_safe = not overlaps

        safe_results[corner_name] = {
            "position": corner_box,
            "safe": is_safe,
            "x_norm": corner_box[0] / max(width, 1),
            "y_norm": corner_box[1] / max(height, 1)
        }

    return safe_results


def _normalize_bbox(bbox_dict: Dict, width: int, height: int) -> List[int]:
    """
    Convert a bbox dict to [x1, y1, x2, y2] pixel coords.
    Handles both normalized (0-1) and pixel coordinate formats.
    Keys tried: x/y/w/h, x/y/width/height, x1/y1/x2/y2.
    """
    if not bbox_dict or not isinstance(bbox_dict, dict):
        return []
    try:
        if "x1" in bbox_dict:
            x1, y1 = bbox_dict["x1"], bbox_dict["y1"]
            x2, y2 = bbox_dict["x2"], bbox_dict["y2"]
        else:
            x = bbox_dict.get("x", 0)
            y = bbox_dict.get("y", 0)
            w = bbox_dict.get("w", bbox_dict.get("width", 0))
            h = bbox_dict.get("h", bbox_dict.get("height", 0))
            x2, y2 = x + w, y + h
            x1, y1 = x, y

        # If values are 0-1 fractions, convert to pixels
        if all(0.0 <= v <= 1.0 for v in [x1, y1, x2, y2]):
            x1, x2 = int(x1 * width), int(x2 * width)
            y1, y2 = int(y1 * height), int(y2 * height)
        else:
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

        return [x1, y1, x2, y2]
    except Exception:
        return []


def boxes_overlap(box1: List[int], box2: List[int], margin: int = 20) -> bool:
    """Check if two bounding boxes overlap (with safety margin)."""
    if not box2 or len(box2) < 4:
        return False

    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2 = box2[0] - margin
    y1_2 = box2[1] - margin
    x2_2 = box2[2] + margin
    y2_2 = box2[3] + margin

    if x2_1 < x1_2 or x1_1 > x2_2:
        return False
    if y2_1 < y1_2 or y1_1 > y2_2:
        return False
    return True


def get_best_avatar_position(safe_regions: Dict) -> List[int]:
    """
    Select the best corner for avatar placement.
    Priority: bottom_right > bottom_left > top_right > top_left
    Returns [x1, y1, x2, y2] pixel coordinates.
    """
    priority_order = ["bottom_right", "bottom_left", "top_right", "top_left"]
    for corner in priority_order:
        if safe_regions.get(corner, {}).get("safe", False):
            return safe_regions[corner]["position"]
    print("[SAM] Warning: All corners have overlap. Using bottom_right.")
    return safe_regions.get("bottom_right", {}).get("position", [0, 0, 100, 100])


def analyze_video_placement(video_path: str, sample_rate: int = 30) -> Dict:
    """
    Analyze a video to determine stable avatar placement.
    Samples every N frames (max 10 API calls) to find the most safe corner.
    Falls back to bottom_right if no frames can be analyzed.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"[SAM] Video: {width}x{height}, {fps:.1f}fps, {total_frames} frames")

    corner_safe_counts = {
        "bottom_right": 0, "bottom_left": 0,
        "top_right": 0, "top_left": 0
    }
    frames_analyzed = 0
    MAX_FRAMES = 10

    frame_idx = 0
    while cap.isOpened() and frames_analyzed < MAX_FRAMES:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_rate == 0:
            temp_path = os.path.join(tempfile.gettempdir(), f"sb_frame_{frame_idx}.jpg")
            try:
                import cv2 as _cv2
                _cv2.imwrite(temp_path, frame)
                frame_b64 = encode_frame_to_base64(temp_path)
                result = segment_frame_with_sam(frame_b64, width, height)

                # Safely iterate safe_regions
                for corner, data in result.get("safe_regions", {}).items():
                    if data.get("safe", False):
                        corner_safe_counts[corner] = corner_safe_counts.get(corner, 0) + 1

                frames_analyzed += 1
                print(f"[SAM] Analyzed frame {frame_idx} ({frames_analyzed}/{MAX_FRAMES})")
            except Exception as e:
                print(f"[SAM] Frame {frame_idx} skipped: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        frame_idx += 1

    cap.release()

    if frames_analyzed == 0:
        print("[SAM] No frames analyzed. Defaulting to bottom_right.")
        return _default_placement(width, height)

    # Calculate safe percentages and pick best corner
    safe_pct = {
        corner: count / frames_analyzed
        for corner, count in corner_safe_counts.items()
    }
    priority = ["bottom_right", "bottom_left", "top_right", "top_left"]
    best_corner = next(
        (c for c in priority if safe_pct[c] > 0.60),
        "bottom_right"
    )

    avatar_w = int(width * AVATAR_SIZE_RATIO)
    avatar_h = int(height * AVATAR_SIZE_RATIO)
    pad_x = int(width * PADDING)
    pad_y = int(height * PADDING)

    positions = {
        "bottom_right": [width - avatar_w - pad_x, height - avatar_h - pad_y, width - pad_x, height - pad_y],
        "bottom_left":  [pad_x, height - avatar_h - pad_y, avatar_w + pad_x, height - pad_y],
        "top_right":    [width - avatar_w - pad_x, pad_y, width - pad_x, avatar_h + pad_y],
        "top_left":     [pad_x, pad_y, avatar_w + pad_x, avatar_h + pad_y],
    }

    print(f"[SAM] Best corner: {best_corner} ({safe_pct[best_corner]*100:.0f}% safe)")
    return {
        "recommended_corner": best_corner,
        "position": positions[best_corner],
        "confidence": safe_pct[best_corner],
        "video_width": width,
        "video_height": height,
        "avatar_width": avatar_w,
        "avatar_height": avatar_h,
        "safe_percentage": safe_pct
    }


def _default_placement(width: int, height: int) -> Dict:
    """Default bottom-right placement when SAM analysis is unavailable."""
    avatar_w = int(width * AVATAR_SIZE_RATIO)
    avatar_h = int(height * AVATAR_SIZE_RATIO)
    pad_x = int(width * PADDING)
    pad_y = int(height * PADDING)
    return {
        "recommended_corner": "bottom_right",
        "position": [width - avatar_w - pad_x, height - avatar_h - pad_y, width - pad_x, height - pad_y],
        "confidence": 0.5,
        "video_width": width,
        "video_height": height,
        "avatar_width": avatar_w,
        "avatar_height": avatar_h,
        "safe_percentage": {"bottom_right": 0.5, "bottom_left": 0.5, "top_right": 0.5, "top_left": 0.5}
    }
