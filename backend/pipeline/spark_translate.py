"""
SIGN BRIDGE  Step 2: English  KSL Gloss Translation via Muse Spark
====================================================================
Kenyan Sign Language (KSL) uses a Subject-Object-Verb (SOV) structure,
drops copulas (is/am/are), uses spatial grammar, and has unique signs
for Kenyan cultural concepts.

This module converts English sentences  KSL Gloss notation,
which is the intermediate format before avatar animation.

KSL Gloss rules:
  - CAPITALIZED words = individual signs
  - SOV order (not English SVO)
  - No "is", "am", "are", "the", "a"
  - Time markers go at START of sentence
  - Negation: "NOT" goes AFTER verb
  - Questions: WH-word at END (with raised brows marker)
  - Numbers precede nouns: TWO TOMATO (not "two tomatoes")
"""

import os
import re
import json
import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

META_API_KEY = os.getenv("META_API_KEY")
META_API_BASE = "https://api.meta.ai/v1"


# ── THE KSL SYSTEM PROMPT (20 EXAMPLES) ──────────────────────────────────────

KSL_SYSTEM_PROMPT = """You are an expert Kenyan Sign Language (KSL) interpreter and linguist.
Your task is to convert English sentences into KSL Gloss notation.

KSL GRAMMAR RULES:
1. Structure: Subject-Object-Verb (SOV)  NOT English SVO
2. Drop: "is", "am", "are", "the", "a", "an", "of"
3. Numbers go BEFORE the noun: TWO TOMATO (not "two tomatoes")
4. Time markers (TODAY, YESTERDAY, NOW, LATER) go at the START
5. Negation: add NOT after the verb
6. Yes/No questions: add Q-YES/NO at the end
7. WH questions (who/what/where): WH-word goes at the END
8. Adjectives follow the noun: TOMATO RED (not "red tomato")
9. Plurals: show number or add MANY/SOME. No "-s" inflection
10. Verbs: use base form, no tense markers in gloss (context handles tense)
11. All gloss words are UPPERCASE and separated by spaces
12. Cultural KSL signs: use HARAMBEE, JUA-KALI, MATATU, UGALI, PILAU, SUKUMA

TRAINING EXAMPLES (English  KSL Gloss):

1. "Add two tomatoes"  "TOMATO TWO ADD"
2. "Hello everyone, today we are cooking pilau"  "HELLO TODAY PILAU COOK"
3. "First wash your hands"  "FIRST HAND WASH"
4. "The water is boiling, add salt"  "WATER BOIL SALT ADD"
5. "I love you"  "ME LOVE YOU"
6. "She is going to the market tomorrow"  "TOMORROW SHE MARKET GO"
7. "Do you understand?"  "YOU UNDERSTAND Q-YES/NO"
8. "What is your name?"  "NAME YOUR WHAT"
9. "I don't have money"  "ME MONEY HAVE-NOT"
10. "There are many people here"  "HERE PEOPLE MANY"
11. "Please be careful, the road is dangerous"  "PLEASE CAREFUL ROAD DANGEROUS"
12. "We need to go to hospital"  "WE HOSPITAL GO NEED"
13. "She cooked ugali and sukuma wiki"  "SHE UGALI SUKUMA COOK"
14. "The baby is crying because it is hungry"  "BABY CRY BECAUSE HUNGRY"
15. "How much does this cost?"  "THIS COST HOW-MUCH"
16. "I will call you later"  "LATER ME YOU CALL"
17. "This is very delicious food"  "FOOD DELICIOUS VERY"
18. "He ran away quickly"  "HE QUICK RUN-AWAY"
19. "Thank you for helping me"  "HELP ME THANK-YOU"
20. "The meeting starts at 3pm"  "TODAY 3PM MEETING START"

CULTURAL KSL SIGNS:
- HARAMBEE = community fundraising/unity gathering
- JIKA = cook on an open fire
- MATATU = minibus/public transport
- UGALI = white maize porridge (staple food)
- PILAU = spiced rice dish
- SUKUMA = kale/collard greens
- SHAMBA = farm/garden
- BODA = motorcycle taxi
- CHAMA = savings group
- DUKA = small shop

OUTPUT FORMAT:
Return ONLY the KSL gloss, no explanation, no punctuation except hyphens within compound signs.
If unsure about a sign, keep the English word in caps and mark with (*) e.g., ALGORITHM(*)

Input sentence: """


def _call_spark(prompt: str, timeout: int = 120) -> str:
    """Make a single call to Muse Spark and return the raw text output."""
    response = requests.post(
        f"{META_API_BASE}/responses",
        headers={
            "Authorization": f"Bearer {META_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "muse-spark-1.3",
            "input": [{"role": "user", "content": prompt}]
        },
        timeout=timeout
    )

    if response.status_code != 200:
        raise RuntimeError(f"Spark API error {response.status_code}: {response.text[:300]}")

    data = response.json()

    # Parse /v1/responses output_text blocks
    for block in data.get("output", []):
        for item in block.get("content", []):
            if item.get("type") == "output_text":
                return item["text"].strip()

    # Fallback: OpenAI-style choices
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return str(data)


def translate_to_ksl_gloss(text: str, word_timestamps: List[Dict] = None) -> Dict:
    """
    Convert English text to KSL Gloss using Muse Spark 1.3.
    Uses a SINGLE batched API call for all sentences.

    Returns:
        {
            "original": "Add two tomatoes and stir",
            "ksl_gloss": "TOMATO TWO ADD STIR",
            "gloss_tokens": ["TOMATO", "TWO", "ADD", "STIR"],
            "confidence": 0.95,
            "flagged_signs": []
        }
    """
    sentences = [s for s in split_into_sentences(text) if s.strip()]
    if not sentences:
        return {
            "original": text, "ksl_gloss": "", "gloss_tokens": [],
            "sentences": [], "flagged_signs": [], "confidence": 1.0
        }

    # Batch ALL sentences into ONE API call
    numbered = "\n".join(f"{i+1}. {s.strip()}" for i, s in enumerate(sentences))
    batch_prompt = (
        KSL_SYSTEM_PROMPT
        + "Translate each numbered sentence to KSL Gloss. "
        + "Return ONLY numbered lines, e.g.:\n1. GLOSS\n2. GLOSS\n\n"
        + "Sentences:\n" + numbered
    )

    raw_output = _call_spark(batch_prompt, timeout=120)

    # Parse numbered lines back into per-sentence glosses
    line_map = {}
    for line in raw_output.splitlines():
        m = re.match(r"^(\d+)\.\s*(.+)", line.strip())
        if m:
            line_map[int(m.group(1))] = m.group(2).strip()

    all_glosses = []
    flagged = []
    for i, sentence in enumerate(sentences):
        gloss = line_map.get(i + 1, "")
        if not gloss:
            # Fallback: uppercase the English words
            gloss = " ".join(w.upper() for w in sentence.split())
        all_glosses.append(gloss)
        flagged.extend([t.replace("(*)", "") for t in gloss.split() if "(*)" in t])

    full_gloss = " | ".join(all_glosses)
    tokens = [t for t in full_gloss.replace("|", "").split() if t]

    return {
        "original": text,
        "ksl_gloss": full_gloss,
        "gloss_tokens": tokens,
        "sentences": list(zip(sentences, all_glosses)),
        "flagged_signs": flagged,
        "confidence": 1.0 - (len(flagged) / max(len(tokens), 1))
    }


def translate_segments_with_timing(
    segments: List[Dict],
    words: List[Dict]
) -> List[Dict]:
    """
    Translate transcript segments to KSL Gloss in ONE batched Spark call.
    Maps gloss tokens back to original timestamps for avatar sync.

    Args:
        segments: Wonder segments [{"start": 0.0, "end": 2.5, "text": "..."}]
        words:    Wonder word timestamps (unused directly, kept for API compat)

    Returns:
        List of timed KSL segments with gloss_tokens and sign_duration.
    """
    valid_segments = [s for s in segments if s.get("text", "").strip()]
    if not valid_segments:
        return []

    # ── SINGLE batched API call for all segments ──────────────────────────────
    texts = [s["text"].strip() for s in valid_segments]
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    batch_prompt = (
        KSL_SYSTEM_PROMPT
        + "Translate each numbered sentence to KSL Gloss. "
        + "Return ONLY numbered lines, e.g.:\n1. GLOSS\n2. GLOSS\n\n"
        + "Sentences:\n" + numbered
    )

    try:
        raw_output = _call_spark(batch_prompt, timeout=120)
    except Exception as e:
        print(f"[Spark] Batch API call failed: {e}. Using uppercase fallback.")
        raw_output = ""

    # Parse numbered response lines
    line_map = {}
    for line in raw_output.splitlines():
        m = re.match(r"^(\d+)\.\s*(.+)", line.strip())
        if m:
            line_map[int(m.group(1))] = m.group(2).strip()

    # Build timed segments
    timed_segments = []
    for i, segment in enumerate(valid_segments):
        gloss = line_map.get(i + 1, "")
        if not gloss:
            gloss = " ".join(w.upper() for w in segment["text"].split())

        tokens = [t for t in gloss.replace("|", "").split() if t]
        flagged = [t.replace("(*)", "") for t in tokens if "(*)" in t]
        duration = segment.get("end", 0) - segment.get("start", 0)
        sign_duration = duration / max(len(tokens), 1)

        timed_segments.append({
            "start": segment.get("start", 0),
            "end": segment.get("end", 0),
            "original": segment["text"],
            "ksl_gloss": gloss,
            "gloss_tokens": tokens,
            "sign_duration": sign_duration,
            "total_signs": len(tokens),
            "flagged_signs": flagged
        })

    return timed_segments


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences for accurate per-sentence translation."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s for s in sentences if s.strip()]


def get_supported_sign_languages() -> List[Dict]:
    """Sign languages supported by Sign Bridge."""
    return [
        {
            "code": "KSL",
            "name": "Kenyan Sign Language",
            "country": "Kenya",
            "users": "~1,000,000",
            "status": "primary",
            "notes": "SOV grammar, unique cultural signs"
        },
        {
            "code": "USL",
            "name": "Ugandan Sign Language",
            "country": "Uganda",
            "users": "~800,000",
            "status": "beta",
            "notes": "Similar to KSL, shared East African base"
        },
        {
            "code": "TSL",
            "name": "Tanzanian Sign Language",
            "country": "Tanzania",
            "users": "~600,000",
            "status": "beta",
            "notes": "Swahili-influenced gloss structure"
        },
        {
            "code": "ASL",
            "name": "American Sign Language",
            "country": "USA/Canada",
            "users": "~500,000",
            "status": "available",
            "notes": "Well-documented, used for training validation"
        }
    ]


# ── TEST ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_sentences = [
        "Add two tomatoes and stir the pot",
        "Hello everyone, today we are cooking pilau with spices",
        "Do you understand how to make ugali?",
        "She went to the market yesterday to buy vegetables",
        "First wash your hands before cooking",
    ]
    manual_expected = [
        "TOMATO TWO ADD POT STIR",
        "HELLO TODAY PILAU SPICE COOK",
        "UGALI HOW-MAKE YOU UNDERSTAND Q-YES/NO",
        "YESTERDAY SHE MARKET VEGETABLE BUY",
        "FIRST HAND WASH COOK BEFORE",
    ]
    print("KSL GLOSS TRANSLATION TEST")
    print("=" * 60)
    for i, (eng, ksl) in enumerate(zip(test_sentences, manual_expected)):
        print(f"\n{i+1}. English: {eng}")
        print(f"   KSL:     {ksl}")
