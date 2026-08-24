#!/usr/bin/env python3
"""
Multi-Keyframe OpenRouter Vision Synthesis Engine
Impian Rumahku & Cerita Mama Ecosystem
Features:
- SIFAR MODEL HARDCODE: Strictly reads IRCM_MODEL_VISION and IRCM_MODEL_VISION_FALLBACK_1 from env
- Ingests 4 chronological keyframe snapshots + music metadata + MYT time context
- 3x Retry loop per model with 2s delay
- Temperature: 0.40, strict output target: 350 to 500 characters
"""

import re
import sys
import time
import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_openrouter_config, get_myt_time_context

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
VISION_PAYLOAD_FILE = TEMP_DIR / "pexels_vision_payload.json"


def clean_vision_text(text: str) -> str:
    """Membersihkan tag pemikiran LLM, blok kod markdown, dan memotong pada tanda noktah terakhir (<= 500 aksara)."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
        "Ã©": "e", "Ã¨": "e", "Ã ": "a", "Ã¡": "a",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    cleaned = re.sub(r"[\x80-\x9f]", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")

    if len(cleaned) > 500:
        trimmed = cleaned[:500]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        cleaned = match.group(1).strip() if match else trimmed.rstrip() + "..."

    return cleaned


def generate_fallback_vision_review(video_title: str, music_meta: Dict[str, Any]) -> str:
    """Ulasan sandaran Bahasa Inggeris sekiranya panggilan model Vision tidak berjaya."""
    song_title = music_meta.get("title", "Aesthetic Melody")
    return (
        f"This beautifully composed home aesthetic reel gracefully highlights the calming rhythm of daily domestic organization. "
        f"From thoughtfully arranged surfaces to warm natural lighting, each scene seamlessly showcases practical lifestyle utility and modern cozy elegance. "
        f"Harmonized with the gentle cadence of {song_title}, it inspires mindful decluttering and serene living."
    ).strip()


def analyze_video_keyframes_with_vision(
    keyframes_list: List[Dict[str, Any]],
    video_title: str,
    music_meta: Dict[str, Any],
    max_attempts: int = 3,
    delay_seconds: int = 2
) -> Tuple[str, str, Dict[str, Any]]:
    """Menghantar 4 snapshot gambar termampat ke OpenRouter Vision API."""
    base_url, api_key, models_dict, cfg_err = get_openrouter_config()
    time_context, period, day_mood = get_myt_time_context()

    primary_model = models_dict.get("vision_primary", "").strip()
    fallback_model = models_dict.get("vision_fallback", "").strip()

    music_title = music_meta.get("title", "Aesthetic Melody")
    music_artist = music_meta.get("artist", "Impian Rumahku Composer")
    music_vibe = music_meta.get("vibe", "Muzik Estetik Santai")

    print(f"\n👁️ [STEP 2: VISION SYNTHESIS] Menganalisis {len(keyframes_list)} bingkai foto video...")
    print(f"   🎬 Tema Video : '{video_title}'")
    print(f"   🎵 Trek Muzik : '{music_title}' ({music_artist}) | Vibe: {music_vibe}")
    print(f"   ⏰ Konteks MYT: {time_context}")

    if cfg_err or not base_url or not api_key or not keyframes_list or not primary_model:
        print(f"   ⚠️ [VISION CONFIG WARN] {cfg_err or 'Model Vision tidak dikonfigurasi'}. Mengaktifkan teks sandaran.")
        fallback_review = generate_fallback_vision_review(video_title, music_meta)
        payload_data = {
            "video_title": video_title,
            "vision_review": fallback_review,
            "model_used": "rule_based_fallback",
            "music_metadata": music_meta,
            "char_count": len(fallback_review),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        return fallback_review, "rule_based_fallback", payload_data

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }

    system_prompt = (
        "You are an articulate, educated 30-something English lifestyle creator and passionate home aesthetic curator.\n"
        "TASK:\n"
        "You are given 4 chronological keyframe snapshots capturing different scenes of an aesthetic home and living video reel.\n"
        "Observe the visual flow across these scenes and write a polished, cohesive micro-review in natural ENGLISH.\n"
        "Synthesize the visual aesthetic (warm lighting, clean surfaces, smart organization) with the relaxing lifestyle mood.\n\n"
        "STRICT RULES:\n"
        "1. Write strictly in natural, eloquent ENGLISH.\n"
        "2. Total length MUST be between 350 and 500 characters.\n"
        "3. Synthesize the chronological frames into ONE smooth, engaging paragraph.\n"
        "4. NEVER include conversational intros, greetings, hashtags, or emojis.\n"
        "5. Return ONLY the review paragraph with clean punctuation."
    )

    user_text = (
        f"Broadcast Time: {time_context} ({day_mood})\n"
        f"Video Theme: {video_title}\n"
        f"Background Music: '{music_title}' by {music_artist}\n"
        f"Music Vibe: {music_vibe}\n\n"
        f"Review these 4 sequential scenes and provide your versatile English aesthetic review (strictly 350-500 characters):"
    )

    user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
    for kf in keyframes_list:
        data_uri = kf.get("data_uri", "")
        if data_uri:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": data_uri}
            })

    models_to_try = [
        (primary_model, "Primary Vision Model"),
        (fallback_model, "Fallback Vision Model 1"),
    ]
    # Tapis model yang wujud dalam ENV sahaja
    models_to_try = [(m, label) for m, label in models_to_try if m]

    endpoint_url = f"{base_url}/chat/completions"
    final_review = ""
    used_model = "rule_based_fallback"

    for model_name, model_label in models_to_try:
        print(f"\n🧠 [VISION ENGINE] Mencuba {model_label}: '{model_name}'...")
        post_payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.40,
        }

        for attempt in range(1, max_attempts + 1):
            print(f"   📡 [Percubaan {attempt}/{max_attempts}] Menghantar permintaan 4-Frame ke {model_name}...")
            try:
                res = requests.post(endpoint_url, headers=headers, json=post_payload, timeout=(10, 40))
                if res.status_code == 200:
                    res_json = res.json()
                    raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    cleaned = clean_vision_text(raw_text)

                    if len(cleaned) >= 200:
                        final_review = cleaned
                        used_model = model_name
                        print(f"   ✅ [{model_label} Berjaya] Ulasan sintesis ({len(final_review)} aksara): \"{final_review[:65]}...\"")
                        break
                    else:
                        print(f"   ⚠️ [Ulasan Terlalu Pendek] ({len(cleaned)} aksara). Mencuba semula...")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:80]}")
            except requests.exceptions.Timeout:
                print(f"   ⚠️ [Vision Timeout ({attempt}/{max_attempts})] Sambungan tamat masa.")
            except Exception as e:
                print(f"   ⚠️ [Vision Exception ({attempt}/{max_attempts})]: {e}")

            if attempt < max_attempts:
                time.sleep(delay_seconds)

        if final_review:
            break

    if not final_review:
        print("   🛡️ [FALLBACK AKTIF] Kesemua model Vision gagal. Menggunakan teks sandaran asas.")
        final_review = generate_fallback_vision_review(video_title, music_meta)

    payload_result = {
        "status": "success",
        "video_title": video_title,
        "vision_review": final_review,
        "model_used": used_model,
        "music_metadata": music_meta,
        "char_count": len(final_review),
        "time_context": time_context,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    try:
        with open(VISION_PAYLOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(payload_result, f, indent=2, ensure_ascii=False)
        print(f"   💾 [PAYLOAD DISIMPAN] Status Vision sedia di: {VISION_PAYLOAD_FILE.name}")
    except Exception as e:
        print(f"   ⚠️ [RALAT SIMPAN JSON]: {e}")

    return final_review, used_model, payload_result