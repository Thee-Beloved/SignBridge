"""
Test Creator Mode with font fix
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.avatar_generate import creator_mode_ksl_to_voice

# Find a test video
uploads = Path("uploads")
test_videos = list(uploads.glob("*creator*.mp4"))

if not test_videos:
    print("❌ No creator mode test videos found in uploads/")
    print("Please upload a KSL signing video first")
    sys.exit(1)

test_video = str(test_videos[0])
output_path = "outputs/test_creator_output.mp4"

print(f"Testing Creator Mode...")
print(f"Input: {test_video}")
print(f"Output: {output_path}")
print()

try:
    result = creator_mode_ksl_to_voice(test_video, output_path)
    print("\n✅ Creator Mode completed successfully!")
    print(f"Mode: {result.get('mode')}")
    print(f"KSL Glosses: {result.get('ksl_glosses')}")
    print(f"English Text: {result.get('english_text')}")
    print(f"Output Video: {result.get('output_video')}")
    print(f"Voice Audio: {result.get('voice_audio')}")
    
    # Check output file exists
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"\n✅ Output file created: {size_mb:.2f} MB")
    else:
        print(f"\n⚠️  Output file not found: {output_path}")
        
except Exception as e:
    print(f"\n❌ Creator Mode failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
