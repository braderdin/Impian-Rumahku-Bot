#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Step 1 Context, Reddit Topic & Step 3 Unsplash Preparator
Location: bin/run_persona_lifestyle_prepare.py
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
TEMP_DIR.mkdir(parents=True, exist_ok=True)
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"

# Import Context, Reddit Reader & Unsplash Engine
from src.persona_lifestyle_context import build_lifestyle_context_payload
from src.persona_lifestyle_reddit_reader import fetch_curated_reddit_post
from src.persona_lifestyle_image_engine import select_and_curate_unsplash_image
from src.persona_lifestyle_filter import is_lifestyle_topic_duplicate


def run_lifestyle_prepare_step(
    use_reddit: bool = False,
    force_niche: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Menyelaraskan penyediaan konteks, penapisan teks Reddit, dan visual Unsplash.
    """
    print("=" * 78)
    print("🚀 [STEP 1 & 3] PERSEDIAAN KONTEKS, IDEA REDDIT & VISUAL UNSPLASH MAMA")
    print("=" * 78)

    base_context = build_lifestyle_context_payload(force_niche=force_niche)
    dt = base_context["datetime"]
    mood = base_context["mood"]
    niche = base_context["niche"]

    print(f"🕒 Waktu Semasa   : {dt['formatted_full']} ({dt['period']})")
    print(f"🎭 Mood Persona   : {mood['mood_name']}")
    print(f"🌿 Niche Terpilih : {niche['niche_title']}")
    print(f"💡 Memori Topik   : {len(base_context.get('recent_memories', []))} topik terdahulu disuntik.\n")

    reddit_data = None
    image_data = None
    local_image_path = None

    # 1. Pengekstrakan Teks Reddit (Jika Mod Reddit Aktif)
    if use_reddit:
        suggested_subs = niche.get("suggested_subreddits", ["MalaysianFood", "houseplants", "DIY"])
        print(f"📡 [MOD REDDIT AKTIF] Mengimbas idea teks komuniti: {suggested_subs}...")
        reddit_data = fetch_curated_reddit_post(suggested_subs)

        if reddit_data:
            print(f"✅ [IDEA REDDIT DITERIMA]: '{reddit_data['title'][:60]}...'")
            # 2. Ingestion Visual Unsplash Berdasarkan Idea Reddit (Langkah 3)
            print("🎨 [UNSPLASH ENGINE] Memulakan penarikan visual 40-Pool & Anti-Face Filter...")
            image_data = select_and_curate_unsplash_image()
            if image_data:
                local_image_path = image_data.get("local_path")
        else:
            print("⚠️ Tiada pos Reddit baharu yang melepasi tapisan. Beralih ke mod penceritaan santai biasa.")

    # 3. Tentukan Teks Kunci Topik & Semak Penapis Dwi-Lapisan
    topic_lock_text = f"{niche['niche_title']} - {reddit_data.get('title', niche['prompt_hook'])}" if reddit_data else f"{niche['niche_title']} - {niche['prompt_hook']}"
    
    is_dup, dup_reason = is_lifestyle_topic_duplicate(topic_lock_text)
    if is_dup:
        print("🔄 Menyesuaikan variasi hook penceritaan alternatif...")
        topic_lock_text += f" (Variasi Waktu {dt['period']})"

    topic_id = f"life_{int(time.time())}_{dt['day_index']}_{dt['hour']}"

    # 4. Bina Payload Penuh
    full_payload = {
        "topic_id": topic_id,
        "topic_lock_text": topic_lock_text,
        "datetime": dt,
        "mood": mood,
        "niche": niche,
        "recent_memories": base_context.get("recent_memories", []),
        "reddit_source": reddit_data or {},
        "unsplash_image": image_data or {},
        "local_image_path": local_image_path,
        "persona_profile": base_context["persona_profile"],
        "created_at": int(time.time())
    }

    try:
        with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(full_payload, f, indent=2, ensure_ascii=False)
        print(f"\n💾 [PAYLOAD SIAP] Fail disimpan ke: {PAYLOAD_FILE.name}")
    except Exception as e:
        print(f"❌ [PAYLOAD SAVE ERROR] {e}")
        return None

    print("=" * 78)
    return full_payload


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 1 & 3: Lifestyle Preparator Runner")
    parser.add_argument("--reddit", action="store_true", help="Aktifkan sumber teks Reddit & Unsplash Visual.")
    parser.add_argument("--niche", type=str, default=None, help="Paksa niche tertentu.")
    args = parser.parse_args()

    run_lifestyle_prepare_step(use_reddit=args.reddit, force_niche=args.niche)