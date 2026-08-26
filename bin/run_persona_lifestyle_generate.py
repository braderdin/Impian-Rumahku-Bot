#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Step 2 & 4 AI Multi-Platform Copywriting Generator
Location: bin/run_persona_lifestyle_generate.py
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load Environment Variables (.env.local priority)
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"
STEP4_OUTPUT_FILE = TEMP_DIR / "step4_final_captions.json"

# Import Router Modular AI
from src.persona_lifestyle_ai_engine import generate_all_lifestyle_captions


def run_lifestyle_generate_step() -> bool:
    """
    Membaca payload penyediaan, menjana kapsyen 4 platform oleh Persona Mama,
    dan merekodkannya kembali ke dalam fail state JSON.
    """
    if not PAYLOAD_FILE.exists():
        print(f"❌ [GENERATE ERROR] Fail {PAYLOAD_FILE.name} tidak dijumpai. Jalankan step prepare dahulu.")
        return False

    try:
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"❌ [GENERATE LOAD ERROR] Gagal membaca payload: {e}")
        return False

    dt = payload.get("datetime", {})
    mood = payload.get("mood", {})
    niche = payload.get("niche", {})
    local_image = payload.get("local_image_path", "")

    print("═" * 78)
    print("🧠 [STEP 4] PENJANAAN AYAT PERSONA MAMA MERENTASI 4 PLATFORM")
    print("═" * 78)
    print(f"🕒 Waktu Siaran   : {dt.get('formatted_full', '')} ({dt.get('period', '')})")
    print(f"🎭 Mood Terpilih  : {mood.get('mood_name', '')}")
    print(f"🌿 Niche Kandungan: {niche.get('niche_title', '')}")
    print(f"📝 Mod Visual     : {'Gambar Unsplash Tersedia' if local_image else 'Hantaran Teks Santai Sahaja'}\n")

    start_time = time.time()
    captions, engine_used = generate_all_lifestyle_captions(
        context_payload=payload,
        local_image_path=local_image if local_image else None
    )
    duration = time.time() - start_time

    if not captions:
        print("❌ [GENERATE ERROR] Gagal menghasilkan ayat ulasan bagi semua platform.")
        return False

    print("-" * 78)
    print(f"📝 [HASIL JANAAN AI PERSONA MAMA] (Enjin: {engine_used} | Masa: {duration:.2f}s)")
    print("-" * 78)

    platform_meta = [
        ("facebook", "📘 1. FACEBOOK FEED", 300, 500),
        ("instagram", "📸 2. INSTAGRAM FEED", 300, 500),
        ("threads", "🧵 3. META THREADS FEED", 300, 480),
        ("bluesky", "🦋 4. BLUESKY FEED", 200, 280),
    ]

    for key, label, min_c, max_c in platform_meta:
        txt = captions.get(key, "")
        print(f"\n{label} ({len(txt)} aksara | Sasaran: {min_c}-{max_c}):")
        print(f'"{txt}"')

    print("\n" + "-" * 78)

    # Simpan output step 4
    step4_payload = {
        "engine_used": engine_used,
        "generation_time_seconds": round(duration, 2),
        "ai_captions": captions
    }

    try:
        with open(STEP4_OUTPUT_FILE, "w", encoding="utf-8") as f_out:
            json.dump(step4_payload, f_out, indent=2, ensure_ascii=False)
        print(f"💾 [STEP 4 PAYLOAD] Kapsyen disimpan ke: {STEP4_OUTPUT_FILE.name}")
    except Exception:
        pass

    # Kemas kini state payload utama
    payload["ai_captions"] = captions
    payload["ai_engine_used"] = engine_used

    try:
        with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"💾 [PAYLOAD UPDATED] Teks 4 platform direkodkan ke: {PAYLOAD_FILE.name}")
    except Exception as e:
        print(f"❌ [GENERATE SAVE ERROR] {e}")
        return False

    print("═" * 78)
    return True


if __name__ == "__main__":
    run_lifestyle_generate_step()