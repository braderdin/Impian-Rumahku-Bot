#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Step 2 Runner (Multi-Platform AI Content Generator)
Location: bin/run_persona_lifestyle_generate.py

Features:
- Reads state context from temp/lifestyle_payload.json.
- Dispatches prompt to local Qwen3.5-4B VLM/LLM with automatic OpenRouter cascading fallback.
- Enforces strict character limits:
  * Facebook  : 300 - 500 chars
  * Instagram : 300 - 500 chars
  * Threads   : 300 - 480 chars
  * Bluesky   : 200 - 280 chars
- Validates clean Latin alphabet, zero Indonesian slang, and zero emojis.
- Updates and preserves payload in temp/lifestyle_payload.json.
"""

import sys
import json
import time
from pathlib import Path
from typing import Any, Dict

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin AI Teras dari src/
from src.persona_lifestyle_ai_engine import generate_all_lifestyle_captions

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"


def print_banner(text: str):
    print("\n" + "═" * 78)
    print(f"🧠 {text.upper()}")
    print("═" * 78)


def run_lifestyle_generate_step() -> bool:
    start_time = time.time()
    print_banner("[STEP 2] PENJANAAN AYAT PERSONA MAMA MERENTASI 4 PLATFORM")

    # 1. Semak kewujudan fail state Step 1
    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tidak ditemui. Sila jalankan Step 1 dahulu.")
        sys.exit(1)

    try:
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"❌ [ABORT] Gagal membaca fail payload: {e}")
        sys.exit(1)

    dt_info = payload.get("datetime", {})
    niche_info = payload.get("niche", {})
    mood_info = payload.get("mood", {})
    local_image = payload.get("local_image_path", "")

    print(f"🕒 Waktu Siaran   : {dt_info.get('formatted_full', '')} ({dt_info.get('period', '')})")
    print(f"🎭 Mood Terpilih  : {mood_info.get('mood_name', '')}")
    print(f"🌿 Niche Kandungan: {niche_info.get('niche_title', '')}")
    if local_image:
        print(f"🖼️ Mod Visual     : Menggunakan imej '{Path(local_image).name}'")
    else:
        print(f"📝 Mod Visual     : Hantaran Teks Santai Sahaja (Tanpa Imej)")

    # 2. Panggil Enjin AI (Local Qwen3.5-4B -> OpenRouter Fallback -> Rule-Based)
    print("\n⏳ Menjalankan inferens AI dwi-mod dengan kawalan had aksara...")
    captions, engine_used = generate_all_lifestyle_captions(
        context_payload=payload,
        local_image_path=local_image if local_image else None
    )

    elapsed = time.time() - start_time

    # 3. Paparan Pratonton Lengkap 4 Platform
    print("\n" + "-" * 78)
    print(f"📝 [HASIL JANAAN AI PERSONA MAMA] (Enjin: {engine_used} | Masa: {elapsed:.2f}s)")
    print("-" * 78)

    print(f"\n📘 1. FACEBOOK FEED ({len(captions['facebook'])} aksara | Sasaran: 300-500):")
    print(f"\"{captions['facebook']}\"")

    print(f"\n📸 2. INSTAGRAM FEED ({len(captions['instagram'])} aksara | Sasaran: 300-500):")
    print(f"\"{captions['instagram']}\"")

    print(f"\n🧵 3. META THREADS FEED ({len(captions['threads'])} aksara | Sasaran: 300-480):")
    print(f"\"{captions['threads']}\"")

    print(f"\n🦋 4. BLUESKY FEED ({len(captions['bluesky'])} aksara | Sasaran: 200-280):")
    print(f"\"{captions['bluesky']}\"")
    print("-" * 78)

    # 4. Kemas kini State Payload
    payload["step"] = 2
    payload["ai_captions"] = captions
    payload["engine_used"] = engine_used
    payload["generation_duration_sec"] = round(elapsed, 2)

    try:
        with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n💾 [PAYLOAD UPDATED] Teks 4 platform berjaya direkodkan ke: {PAYLOAD_FILE.name}")
        print_banner(f"STEP 2 SELESAI ({elapsed:.2f}S)")
        return True
    except Exception as e:
        print(f"❌ [PAYLOAD WRITE ERROR] {e}")
        return False


if __name__ == "__main__":
    run_lifestyle_generate_step()