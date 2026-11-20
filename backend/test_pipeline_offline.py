"""
SIGN BRIDGE  Offline Pipeline Test Harness
============================================
Tests the FULL pipeline with mocked Meta API responses.
Run this WITHOUT an API key to validate all logic before Oct 26.

Usage:
    python test_pipeline_offline.py

All Meta API calls are mocked with realistic Kenyan Reel data.
"""

import os
import sys
import json
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock

#  MOCK META API RESPONSES 

MOCK_WONDER_RESPONSE = {
    "text": "Sawa guys, today we cook pilau. First add maji then two nyanya. Leo tutafanya harambee ya chakula.",
    "text_normalized": "okay guys, today we cook pilau. First add water then two nyanya. today harambee food.",
    "segments": [
        {"start": 0.0,  "end": 3.2,  "text": "Sawa guys, today we cook pilau.",           "speaker": 0},
        {"start": 3.2,  "end": 5.8,  "text": "First add maji then two nyanya.",            "speaker": 0},
        {"start": 5.8,  "end": 9.0,  "text": "Leo tutafanya harambee ya chakula.",         "speaker": 0},
    ],
    "words": [
        {"word": "Sawa",  "start": 0.0, "end": 0.3},
        {"word": "guys",  "start": 0.3, "end": 0.6},
        {"word": "today", "start": 0.7, "end": 1.0},
        {"word": "cook",  "start": 1.1, "end": 1.5},
        {"word": "pilau", "start": 1.5, "end": 2.0},
    ],
    "detected_language": "sw-en",
    "confidence": 0.94,
}

MOCK_SAM_RESPONSE = {
    "detections": {
        "face":   {"bbox": [400, 100, 700, 450]},
        "hands":  [{"bbox": [300, 700, 780, 900]}],
        "person": {"bbox": [200, 50, 900, 1800]},
    }
}


#  TEST CLASSES 

class TestNormalizeSheng(unittest.TestCase):
    """Test Sheng/Swahili to English normalization -- no API needed."""

    def setUp(self):
        from pipeline.wonder_transcribe import normalize_sheng
        self.normalize = normalize_sheng

    def test_basic_swahili(self):
        result = self.normalize("sawa poa mambo")
        self.assertEqual(result, "okay cool what's up")

    def test_food_words(self):
        result = self.normalize("leo chakula maji")
        self.assertIn("today", result)
        self.assertIn("food", result)
        self.assertIn("water", result)

    def test_mixed_english_swahili(self):
        result = self.normalize("Sawa guys, today we cook pilau.")
        self.assertIn("okay", result)         # sawa -> okay
        self.assertIn("spiced rice", result)  # pilau -> spiced rice (Kenyan food)

    def test_punctuation_preserved(self):
        result = self.normalize("asante! tafadhali, karibu.")
        self.assertIn("thank you", result)
        self.assertIn("please", result)
        self.assertIn("welcome", result)

    def test_unknown_words_preserved(self):
        result = self.normalize("algorithm blockchain matatu")
        self.assertIn("algorithm", result)
        self.assertIn("blockchain", result)

    def test_kenyan_context_words(self):
        # gari=car, shamba=farm, boda=motorcycle taxi
        result = self.normalize("gari shamba boda nyanya")
        self.assertIn("car", result)
        self.assertIn("farm", result)
        self.assertIn("motorcycle taxi", result)
        self.assertIn("tomato", result)


class TestKSLGrammarRules(unittest.TestCase):
    """Test KSL grammar logic -- the heart of Sign Bridge."""

    def setUp(self):
        from pipeline.spark_translate import split_into_sentences, KSL_SYSTEM_PROMPT
        self.split = split_into_sentences
        self.prompt = KSL_SYSTEM_PROMPT

    def test_sentence_splitting(self):
        text = "Add two tomatoes. Hello everyone. Do you understand?"
        parts = self.split(text)
        self.assertEqual(len(parts), 3)

    def test_prompt_has_20_examples(self):
        import re
        examples = re.findall(r'^\d+\.', self.prompt, re.MULTILINE)
        self.assertGreaterEqual(len(examples), 20, "Need at least 20 KSL training examples")

    def test_prompt_has_kenyan_signs(self):
        for sign in ["HARAMBEE", "UGALI", "PILAU", "MATATU", "SUKUMA"]:
            self.assertIn(sign, self.prompt, f"Missing Kenyan sign: {sign}")

    def test_prompt_has_sov_rule(self):
        self.assertIn("SOV", self.prompt)

    def test_split_handles_exclamation(self):
        parts = self.split("First wash hands! Then cook.")
        self.assertEqual(len(parts), 2)

    def test_confidence_calculation(self):
        from pipeline.spark_translate import translate_to_ksl_gloss
        with patch("pipeline.spark_translate.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "TOMATO TWO ADD PILAU(*) COOK"}}]
            }
            mock_post.return_value = mock_resp
            result = translate_to_ksl_gloss("Add two tomatoes and cook pilau.")
            self.assertIn("ksl_gloss", result)
            self.assertIn("PILAU", result["flagged_signs"])
            self.assertLess(result["confidence"], 1.0)


class TestSAMPlacement(unittest.TestCase):
    """Test avatar placement geometry -- no API needed."""

    def setUp(self):
        from pipeline.sam_placement import (
            boxes_overlap, calculate_safe_zones,
            get_best_avatar_position, _default_placement
        )
        self.boxes_overlap = boxes_overlap
        self.calculate_safe_zones = calculate_safe_zones
        self.get_best = get_best_avatar_position
        self.default_placement = _default_placement

    def test_overlapping_boxes(self):
        self.assertTrue(self.boxes_overlap([800, 1400, 1058, 1878], [850, 1500, 950, 1700]))

    def test_non_overlapping_boxes(self):
        self.assertFalse(self.boxes_overlap([800, 1400, 1058, 1878], [0, 0, 100, 100]))

    def test_margin_safety(self):
        box1 = [800, 800, 1000, 1000]
        box2 = [1005, 800, 1200, 1000]  # 5px gap, within 20px margin
        self.assertTrue(self.boxes_overlap(box1, box2, margin=20))

    def test_default_placement_1080x1920(self):
        result = self.default_placement(1080, 1920)
        self.assertEqual(result["recommended_corner"], "bottom_right")
        x1, y1, x2, y2 = result["position"]
        avatar_width = x2 - x1
        self.assertAlmostEqual(avatar_width / 1080, 0.28, delta=0.01)

    def test_priority_order(self):
        mock_regions = {
            "bottom_right": {"position": [750, 1360, 1058, 1898], "safe": True},
            "bottom_left":  {"position": [22, 1360, 302, 1898],   "safe": True},
            "top_right":    {"position": [750, 22, 1058, 560],     "safe": True},
            "top_left":     {"position": [22, 22, 302, 560],       "safe": True},
        }
        self.assertEqual(self.get_best(mock_regions), [750, 1360, 1058, 1898])

    def test_fallback_to_bottom_left(self):
        mock_regions = {
            "bottom_right": {"position": [750, 1360, 1058, 1898], "safe": False},
            "bottom_left":  {"position": [22, 1360, 302, 1898],   "safe": True},
            "top_right":    {"position": [750, 22, 1058, 560],     "safe": False},
            "top_left":     {"position": [22, 22, 302, 560],       "safe": False},
        }
        self.assertEqual(self.get_best(mock_regions), [22, 1360, 302, 1898])


class TestFullPipelineMocked(unittest.TestCase):
    """Mock the full pipeline end-to-end."""

    def test_transcribe_reel_mock(self):
        from pipeline.wonder_transcribe import transcribe_reel
        with patch("pipeline.wonder_transcribe.extract_audio_from_video") as mock_audio, \
             patch("pipeline.wonder_transcribe.transcribe_with_wonder") as mock_wonder, \
             patch("os.remove"):
            mock_audio.return_value = "/tmp/test_audio.wav"
            mock_wonder.return_value = dict(MOCK_WONDER_RESPONSE)
            result = transcribe_reel("test_reel.mp4")
            self.assertIn("text", result)
            self.assertIn("segments", result)
            self.assertEqual(result["confidence"], 0.94)

    def test_spark_translation_with_timing(self):
        from pipeline.spark_translate import translate_segments_with_timing
        with patch("pipeline.spark_translate.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "HELLO TODAY PILAU COOK"}}]
            }
            mock_post.return_value = mock_resp
            result = translate_segments_with_timing(
                MOCK_WONDER_RESPONSE["segments"],
                MOCK_WONDER_RESPONSE["words"]
            )
            self.assertEqual(len(result), 3)
            for seg in result:
                self.assertIn("ksl_gloss", seg)
                self.assertGreater(seg["sign_duration"], 0)

    def test_avatar_caching(self):
        """HELLO appears twice -- should only generate ONE frame."""
        from pipeline.avatar_generate import generate_avatar_sequence
        tokens = ["HELLO", "TODAY", "PILAU", "COOK", "HELLO"]
        with patch("pipeline.avatar_generate.generate_avatar_frame") as mock_gen, \
             patch("os.path.exists", return_value=False), \
             patch("os.makedirs"):
            mock_gen.return_value = "/tmp/test_frame.png"
            result = generate_avatar_sequence(tokens, "/tmp/frames", 302, 538)
            self.assertEqual(len(result), 5)
            # Extract sign_token from keyword args (generate_avatar_frame uses kwargs)
            unique_calls = {
                call.kwargs.get("sign_token") or call.args[0]
                for call in mock_gen.call_args_list
            }
            self.assertEqual(len(unique_calls), 4)  # 4 unique tokens, HELLO cached


class TestSignBridgeAPI(unittest.TestCase):
    """Test Flask API endpoints -- no real API calls."""

    def setUp(self):
        os.environ["META_API_KEY"] = "test_key_offline"
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "ok")

    def test_languages_endpoint(self):
        resp = self.client.get("/api/languages")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        langs = {l["code"] for l in data["languages"]}
        self.assertIn("KSL", langs)

    def test_process_reel_no_file_returns_400(self):
        # POST with no file and no JSON body should return 400
        resp = self.client.post(
            "/api/process-reel",
            content_type="multipart/form-data"  # Correct type, but no file
        )
        self.assertEqual(resp.status_code, 400)

    def test_status_unknown_job_returns_404(self):
        resp = self.client.get("/api/status/nonexistent-job-id")
        self.assertEqual(resp.status_code, 404)

    def test_download_missing_returns_404(self):
        resp = self.client.get("/api/download/nonexistent")
        self.assertEqual(resp.status_code, 404)


#  RUN 

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  SIGN BRIDGE -- OFFLINE TEST SUITE")
    print("  Built in Nairobi Kenya | Meta Hackathon 2026")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for cls in [
        TestNormalizeSheng,
        TestKSLGrammarRules,
        TestSAMPlacement,
        TestFullPipelineMocked,
        TestSignBridgeAPI,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    if result.wasSuccessful():
        print("ALL TESTS PASSED -- Pipeline is ready for Oct 26!")
        sys.exit(0)
    else:
        print(f"FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
        sys.exit(1)
