"""
SIGN BRIDGE  Flask API Backend
================================
Main API server orchestrating the full pipeline:
  Wonder -> Spark -> SAM 3.1 -> Muse Image -> ffmpeg output

Routes:
  POST /api/process-reel       Main pipeline (Reel -> KSL video)
  POST /api/creator-mode       Reverse pipeline (KSL video -> English voice)
  GET  /api/status/<job_id>    Check processing status
  GET  /api/languages          List supported sign languages
  GET  /api/health             Health check
"""

import os
import uuid
import json
import threading
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()  # Must be before pipeline imports so env vars are set

# ── Startup security check ────────────────────────────────────────────────────
META_API_KEY = os.getenv("META_API_KEY", "")
if not META_API_KEY or META_API_KEY == "your_meta_api_key_here":
    raise RuntimeError(
        "META_API_KEY is not set. Copy backend/.env.example to backend/.env "
        "and add your key from dev.meta.ai"
    )

from pipeline.wonder_transcribe import transcribe_reel
from pipeline.spark_translate import translate_segments_with_timing, get_supported_sign_languages
from pipeline.sam_placement import analyze_video_placement
from pipeline.avatar_generate import (
    generate_avatar_sequence,
    overlay_avatar_on_video,
    creator_mode_ksl_to_voice
)

# ── App setup ─────────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path=""
)

# CORS: allow frontend origin only (localhost in dev, set ALLOWED_ORIGIN in prod)
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:5000")
CORS(app, origins=[ALLOWED_ORIGIN], supports_credentials=False)

# ── File upload limits ────────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024  # 200 MB hard cap

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
ALLOWED_VIDEO_MIMES = {
    "video/mp4", "video/quicktime", "video/webm",
    "video/x-matroska", "video/x-msvideo"
}

# ── Storage dirs ──────────────────────────────────────────────────────────────
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))
FRAMES_DIR = Path(os.getenv("FRAMES_CACHE_DIR", "frames_cache"))

for d in [UPLOAD_DIR, OUTPUT_DIR, FRAMES_DIR]:
    d.mkdir(exist_ok=True)

# In-memory job store (swap for Redis in production)
jobs = {}


# ── Security headers (applied to every response) ─────────────────────────────
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Only set CSP for HTML responses to avoid breaking video/json
    if "text/html" in response.content_type:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "media-src 'self' blob:; "
            "connect-src 'self';"
        )
    return response


# ── Input validation helpers ──────────────────────────────────────────────────
def validate_video_file(file_obj):
    """Validate uploaded file is a real video by extension and MIME type."""
    filename = file_obj.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return False, f"File type '{ext}' not allowed. Use: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}"
    mime = file_obj.mimetype or ""
    if mime and mime not in ALLOWED_VIDEO_MIMES:
        return False, f"MIME type '{mime}' not allowed."
    return True, None


def validate_url(url: str):
    """Basic URL validation — must be http/https Instagram or direct video link."""
    if not url:
        return False, "URL is empty."
    if not url.startswith(("http://", "https://")):
        return False, "URL must start with http:// or https://"
    if len(url) > 2048:
        return False, "URL is too long."
    return True, None


def safe_job_id():
    """Generate a short, filesystem-safe job ID."""
    return str(uuid.uuid4())[:8]


# ── Pipeline orchestrator ─────────────────────────────────────────────────────
def run_full_pipeline(job_id: str, video_path: str, language: str = "KSL"):
    """
    Full Sign Bridge pipeline (runs in a background thread):
      Step 1: Wonder  transcription
      Step 2: Spark   KSL translation
      Step 3: SAM     placement analysis
      Step 4: Avatar  frame generation
      Step 5: ffmpeg  video overlay
    """
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 5
        jobs[job_id]["step"] = "Transcribing audio with Muse Wonder..."

        # Step 1 — Wonder
        transcript = transcribe_reel(video_path)
        jobs[job_id]["progress"] = 25
        jobs[job_id]["step"] = "Translating to KSL with Muse Spark..."
        jobs[job_id]["transcript"] = transcript.get("text_normalized", "")

        # Step 2 — Spark (single batched call)
        timed_segments = translate_segments_with_timing(
            transcript.get("segments", [
                {"start": 0, "end": 10, "text": transcript.get("text_normalized", "")}
            ]),
            transcript.get("words", [])
        )
        all_tokens = [t for seg in timed_segments for t in seg["gloss_tokens"]]
        jobs[job_id]["progress"] = 50
        jobs[job_id]["step"] = "Analyzing video with SAM 3.1..."
        jobs[job_id]["ksl_gloss"] = " | ".join(seg["ksl_gloss"] for seg in timed_segments)

        # Step 3 — SAM (graceful fallback built-in)
        placement = analyze_video_placement(video_path)
        jobs[job_id]["progress"] = 65
        jobs[job_id]["step"] = "Generating KSL avatar with Muse Image..."
        jobs[job_id]["avatar_corner"] = placement["recommended_corner"]

        # Step 4 — Avatar frames (cached per sign)
        frame_sequence = generate_avatar_sequence(
            gloss_tokens=all_tokens,
            frames_dir=str(FRAMES_DIR),
            avatar_width=placement["avatar_width"],
            avatar_height=placement["avatar_height"]
        )
        jobs[job_id]["progress"] = 85
        jobs[job_id]["step"] = "Rendering final video..."

        # Step 5 — Overlay
        output_path = str(OUTPUT_DIR / f"{job_id}_ksl.mp4")
        overlay_avatar_on_video(
            source_video=video_path,
            frame_sequence=frame_sequence,
            timed_segments=timed_segments,
            placement=placement,
            output_path=output_path
        )

        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["step"] = "Complete!"
        jobs[job_id]["output_path"] = output_path

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["step"] = f"Error: {str(e)}"
        print(f"[Pipeline] Job {job_id} FAILED: {e}")


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    """Health check — confirms API key is loaded (never returns the key itself)."""
    return jsonify({
        "status": "ok",
        "api_key_set": bool(META_API_KEY),
        "version": "1.0.0"
    })


@app.route("/api/languages", methods=["GET"])
def languages():
    """List supported sign languages."""
    return jsonify(get_supported_sign_languages())


@app.route("/api/process-reel", methods=["POST"])
def process_reel():
    """
    Start processing a Reel -> KSL video.
    Accepts:
      - multipart/form-data with 'video' file field
      - JSON with 'video_url' (Instagram/TikTok URL, requires yt-dlp)
    Returns: { job_id, status, message }
    """
    job_id = safe_job_id()
    video_path = None
    language = "KSL"

    # ── File upload path ──────────────────────────────────────────────────────
    if request.content_type and "multipart/form-data" in request.content_type:
        if "video" not in request.files:
            return jsonify({"error": "No 'video' file in request"}), 400

        video_file = request.files["video"]
        language = request.form.get("language", "KSL")

        ok, err = validate_video_file(video_file)
        if not ok:
            return jsonify({"error": err}), 400

        # Save with sanitized filename (never use original filename on disk)
        video_path = str(UPLOAD_DIR / f"{job_id}_input.mp4")
        video_file.save(video_path)

    # ── URL input path ────────────────────────────────────────────────────────
    else:
        req_json = request.get_json(silent=True) or {}
        video_url = req_json.get("video_url", "").strip()
        language = req_json.get("language", "KSL")

        ok, err = validate_url(video_url)
        if not ok:
            return jsonify({"error": err}), 400

        video_path = str(UPLOAD_DIR / f"{job_id}_input.mp4")
        dl_result = subprocess.run(
            ["python", "-m", "yt_dlp",
             "-o", video_path,
             "--format", "mp4",
             "--max-filesize", f"{MAX_UPLOAD_MB}m",
             "--no-playlist",
             video_url],
            capture_output=True, text=True, timeout=120
        )
        if dl_result.returncode != 0:
            return jsonify({"error": f"Could not download video: {dl_result.stderr[:300]}"}), 400

    # ── Validate language ─────────────────────────────────────────────────────
    allowed_languages = {"KSL", "USL", "TSL", "ASL"}
    if language not in allowed_languages:
        language = "KSL"

    # ── Queue job ─────────────────────────────────────────────────────────────
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "step": "Queued...",
        "language": language,
        "input_path": video_path
    }

    thread = threading.Thread(
        target=run_full_pipeline,
        args=(job_id, video_path, language)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": f"Processing started. Poll /api/status/{job_id}"
    }), 202


@app.route("/api/creator-mode", methods=["POST"])
def creator_mode():
    """Reverse pipeline: KSL signing video -> English voice + captions."""
    if "video" not in request.files:
        return jsonify({"error": "Provide 'video' file"}), 400

    video_file = request.files["video"]
    ok, err = validate_video_file(video_file)
    if not ok:
        return jsonify({"error": err}), 400

    job_id = safe_job_id()
    video_path = str(UPLOAD_DIR / f"{job_id}_creator.mp4")
    video_file.save(video_path)
    output_path = str(OUTPUT_DIR / f"{job_id}_voiced.mp4")

    try:
        result = creator_mode_ksl_to_voice(video_path, output_path)
        return jsonify({
            "job_id": job_id,
            "status": "done",
            "ksl_glosses": result["ksl_glosses"],
            "english_text": result["english_text"],
            "download_url": f"/api/download/{job_id}_voiced"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    """Poll job processing status."""
    # Validate job_id format (8 hex chars only)
    if not job_id or not all(c in "0123456789abcdef-" for c in job_id) or len(job_id) > 36:
        return jsonify({"error": "Invalid job ID"}), 400

    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    job = jobs[job_id]
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "step": job.get("step", ""),
        "language": job.get("language", "KSL")
    }

    if job["status"] == "done":
        response["transcript"] = job.get("transcript", "")
        response["ksl_gloss"] = job.get("ksl_gloss", "")
        response["avatar_corner"] = job.get("avatar_corner", "")
        response["download_url"] = f"/api/download/{job_id}"

    if job["status"] == "error":
        # Return sanitized error (no internal paths)
        raw_err = job.get("error", "Unknown error")
        safe_err = raw_err.replace(str(UPLOAD_DIR), "[uploads]").replace(str(OUTPUT_DIR), "[outputs]")
        response["error"] = safe_err

    return jsonify(response)


@app.route("/api/download/<job_id>", methods=["GET"])
def download_result(job_id: str):
    """Download processed video — strict path traversal prevention."""
    # Validate job_id: only alphanumeric + hyphen + underscore
    if not job_id or not all(c in "0123456789abcdefghijklmnopqrstuvwxyz_-" for c in job_id):
        return jsonify({"error": "Invalid job ID"}), 400

    # Resolve and confirm path stays within OUTPUT_DIR (prevent path traversal)
    for suffix in ("_ksl.mp4", "_voiced.mp4"):
        candidate = (OUTPUT_DIR / f"{job_id}{suffix}").resolve()
        try:
            candidate.relative_to(OUTPUT_DIR.resolve())  # raises if outside
        except ValueError:
            return jsonify({"error": "Access denied"}), 403

        if candidate.exists():
            return send_file(
                str(candidate),
                as_attachment=True,
                download_name="sign_bridge_output.mp4",
                mimetype="video/mp4"
            )

    return jsonify({"error": "Output not found"}), 404


@app.errorhandler(413)
def file_too_large(e):
    return jsonify({"error": f"File too large. Maximum size is {MAX_UPLOAD_MB}MB."}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    is_dev = os.getenv("FLASK_ENV", "development") == "development"
    print("=" * 50)
    print("  SIGN BRIDGE API  v1.0.0")
    print("  Turning Reels into Kenyan Sign Language")
    print("  Built on: Wonder + Spark + SAM 3.1 + Image")
    print("=" * 50)
    print(f"  META_API_KEY : SET")
    print(f"  Uploads dir  : {UPLOAD_DIR.resolve()}")
    print(f"  Outputs dir  : {OUTPUT_DIR.resolve()}")
    print(f"  Frontend     : http://localhost:5000/")
    print(f"  API          : http://localhost:5000/api/health")
    print(f"  Mode         : {'DEVELOPMENT' if is_dev else 'PRODUCTION'}")
    print("=" * 50)
    print()
    app.run(
        debug=is_dev,
        port=int(os.getenv("PORT", 5000)),
        host="0.0.0.0",
        use_reloader=False
    )
