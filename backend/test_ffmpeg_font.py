"""
Test FFmpeg font detection and drawtext functionality
"""
import os
import platform
import subprocess

print("Testing FFmpeg font configuration...")
print(f"Platform: {platform.system()}")
print()

# Check if FFmpeg is available
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
    print("✅ FFmpeg found")
except Exception as e:
    print(f"❌ FFmpeg not found: {e}")
    exit(1)

# Find available fonts on Windows
if platform.system() == "Windows":
    print("\nSearching for Windows fonts...")
    possible_fonts = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/verdana.ttf",
        "C:/Windows/Fonts/calibri.ttf"
    ]
    
    found_fonts = []
    for font in possible_fonts:
        if os.path.exists(font):
            print(f"  ✅ Found: {font}")
            found_fonts.append(font)
        else:
            print(f"  ❌ Missing: {font}")
    
    if found_fonts:
        print(f"\n✅ Using font: {found_fonts[0]}")
        font_path = found_fonts[0].replace("\\", "/").replace(":", "\\:")
        
        # Test drawtext with explicit font
        print("\nTesting drawtext filter with font...")
        test_cmd = [
            "ffmpeg",
            "-f", "lavfi",
            "-i", "color=c=blue:s=320x240:d=1",
            "-vf", f"drawtext=fontfile='{font_path}':text='Test':fontsize=24:fontcolor=white:x=10:y=10",
            "-frames:v", "1",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Drawtext with font works!")
        else:
            print(f"❌ Drawtext failed: {result.stderr[-500:]}")
    else:
        print("\n⚠️  No fonts found - will use fallback mode (no captions)")

else:
    print(f"\n⚠️  Non-Windows platform - font handling may differ")

print("\n" + "="*50)
print("Font configuration test complete")
