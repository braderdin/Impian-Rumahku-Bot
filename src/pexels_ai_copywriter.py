#!/usr/bin/env python3
"""
Step 3: AI Copywriter Persona Mama Engine (MYT-Aware & 300-500 Chars)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- SIFAR MODEL HARDCODE: Reads IRCM_MODEL_PRIMARY and fallback models strictly from environment variables
- Translates & adapts English Vision review into warm, genuine Malaysian Malay (Persona Mama)
- Target length: 300 to 500 characters
"""

import re
import sys
import time
import requests
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_openrouter_config, get_myt_time_context
from src.pexels_vector_db import is_similar_story_posted

DEFAULT_HASHTAGS = "#ImpianRumahku #CeritaMama #KemasRumah #DekoRumah #ReelsMalaysia #AestheticHome"


def clean_ai_copywriting_output(text: str) -> str:
    """Membersihkan tag pemikiran LLM, mukadimah AI, dan memotong ayat tergantung."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    cleaned = re.sub(r"(?i)^\s*(?:yo|hai|salam|hello)?[^\n]*?(?:cadangan|kapsyen|caption)[^\n]*?\n+", "", cleaned)
    cleaned = re.sub(r"(?i)\*\*caption\s*(?:reels?)?\s*:\*\*", "", cleaned)
    cleaned = re.sub(r"\*\*\*", "", cleaned)

    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")

    match = re.search(r"^([\s\S]*[.!?])", cleaned)
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def validate_copywriting_quality(text: str) -> Tuple[bool, str]:
    """Menyemak kualiti penulisan BM dan sekatan slanga asing."""
    if not text or len(text) < 180:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima 180)."

    forbidden_words = ["bisa", "banget", "nggak", "yuk", "bikin", "gampang", "ngga", "bangt"]
    words = re.findall(r"\b\w+\b", text.lower())
    for w in words:
        if w in forbidden_words:
            return False, f"Dikesan perkataan slanga tidak dibenarkan: '{w}'."

    return True, ""


def generate_fallback_mama_copy(video_title: str, music_meta: Dict[str, Any]) -> str:
    """Kapsyen BM Persona Mama sandaran sekiranya panggilan AI gagal."""
    song_title = music_meta.get("title", "alunan muzik santai")
    return (
        f"Bila ruang rumah tersusun kemas dan disinari cahaya matahari lembut, "
        f"suasana terus bertukar jadi terapi paling menenangkan sambil melayan {song_title}. "
        f"Susun atur yang praktikal bukan saja sedap dipandang mata, tapi sangat memudahkan rutin harian kita sekeluarga."
    )


def assemble_final_reel_caption(body_text: str, video_title: str) -> str:
    """Menyusun teks hantaran lengkap (300 hingga 500 aksara)."""
    clean_title = video_title.split("|")[0].strip()
    if len(clean_title) > 40:
        clean_title = clean_title[:37] + "..."

    header = f"✨ {clean_title}\n\n"
    footer = f"\n\n{DEFAULT_HASHTAGS}"

    max_body_len = 500 - len(header) - len(footer)
    trimmed_body = body_text.strip()

    if len(trimmed_body) > max_body_len:
        trimmed = trimmed_body[:max_body_len]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        trimmed_body = match.group(1).strip() if match else trimmed.rstrip() + "..."

    full_caption = f"{header}{trimmed_body}{footer}".strip()
    return full_caption


def generate_mama_reel_story(
    vision_review: str,
    video_title: str,
    music_meta: Dict[str, Any],
    max_vector_retries: int = 2
) -> Tuple[str, str, str]:
    """Menjana kapsyen penceritaan Bahasa Melayu Persona Mama (300–500 aksara)."""
    base_url, api_key, models_dict, cfg_err = get_openrouter_config()
    time_context, period, day_mood = get_myt_time_context()

    music_title = music_meta.get("title", "Aesthetic Melody")
    music_vibe = music_meta.get("vibe", "Santai & Tenang")

    print(f"\n✍️ [STEP 3: AI COPYWRITER] Mengolah ulasan Vision ke Bahasa Melayu Persona Mama...")
    print(f"   ⏰ Konteks Waktu: {time_context} ({period})")

    if cfg_err or not base_url or not api_key:
        print(f"   ⚠️ [CONFIG WARN] {cfg_err}. Menggunakan kapsyen sandaran.")
        raw_story = generate_fallback_mama_copy(video_title, music_meta)
        full_cap = assemble_final_reel_caption(raw_story, video_title)
        return full_cap, raw_story, "rule_based_fallback"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }

    system_prompt = (
        "Anda adalah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang peramah, "
        "bijak, dan suka berkongsi idea susun atur serta dekorasi rumah di media sosial.\n\n"
        "TUGASAN:\n"
        "1. Teliti ulasan visual Bahasa Inggeris dan suasana muzik yang diberikan.\n"
        "2. Tulis TEPAT 1 perenggan penceritaan santai dan berjiwa dalam Bahasa Melayu Malaysia tulen (sekitar 35 hingga 50 patah perkataan).\n"
        "3. Tekankan keindahan susun atur rumah yang kemas, tenang, dan praktikal untuk sekeluarga.\n\n"
        "PANTANGAN KETAT:\n"
        "- DILARANG meletakkan sebarang harga atau pautan link/URL.\n"
        "- DILARANG meletakkan emoji (kod Python akan menyusun emoji).\n"
        "- DILARANG guna perkataan slanga Indonesia (seperti bisa, banget, nggak, yuk, bikin, gampang).\n"
        "- Pastikan perenggan diakhiri tanda noktah (.) yang lengkap.\n"
        "- Terus berikan teks penceritaan tanpa mukadimah atau tag pemikiran."
    )

    user_prompt = (
        f"Waktu Siaran: {time_context} ({period})\n"
        f"Mood Hari: {day_mood}\n"
        f"Tema Visual: {video_title}\n"
        f"Muzik Latar: '{music_title}' (Vibe: {music_vibe})\n"
        f"Rujukan Ulasan Visual: {vision_review}\n\n"
        f"Sila olah penceritaan santai Mama dalam Bahasa Melayu Malaysia:"
    )

    model_hierarchy = [
        (models_dict.get("primary", "").strip(), "Primary Model"),
        (models_dict.get("fallback_1", "").strip(), "Fallback Model 1"),
        (models_dict.get("fallback_2", "").strip(), "Fallback Model 2"),
        (models_dict.get("fallback_3", "").strip(), "Fallback Model 3"),
    ]
    model_hierarchy = [(m, label) for m, label in model_hierarchy if m]

    endpoint_url = f"{base_url}/chat/completions"
    best_story_bm = ""
    used_model = "rule_based_fallback"

    for model_name, model_label in model_hierarchy:
        print(f"\n🧠 [COPYWRITER AI] Mencuba {model_label}: '{model_name}'...")
        for attempt in range(1, 3):
            try:
                post_payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.40,
                }
                res = requests.post(endpoint_url, headers=headers, json=post_payload, timeout=(8, 30))
                if res.status_code == 200:
                    raw_text = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_ai_copywriting_output(raw_text)

                    is_valid, err_msg = validate_copywriting_quality(clean_text)
                    if is_valid:
                        if is_similar_story_posted(clean_text):
                            print(f"   ⚠️ [VECTOR SIMILARITY WARN] Kapsyen mirip dikesan. Menjana semula...")
                            continue

                        best_story_bm = clean_text
                        used_model = model_name
                        print(f"   ✅ [{model_label} Berjaya] Teks diterima ({len(best_story_bm)} aksara).")
                        break
                    else:
                        print(f"   ⚠️ [Kualiti Teks Gagal ({attempt}/2)]: {err_msg}")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:80]}")
            except Exception as e:
                print(f"   ⚠️ [Copywriter Exception ({attempt}/2)]: {e}")

            time.sleep(2)

        if best_story_bm:
            break

    if not best_story_bm:
        print("   🛡️ [FALLBACK AKTIF] Menggunakan penceritaan sandaran asas.")
        best_story_bm = generate_fallback_mama_copy(video_title, music_meta)

    final_caption = assemble_final_reel_caption(best_story_bm, video_title)
    print(f"\n📏 [JUMLAH AKSARA KAPSYEN]: {len(final_caption)} aksara (Sasaran: 300-500 aksara)")
    return final_caption, best_story_bm, used_model