#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Step 1 Runner (Context, Topic Curation & Payload Preparation)
Location: bin/run_persona_lifestyle_prepare.py

Usage:
  python bin/run_persona_lifestyle_prepare.py                 # Mod Harian Santai (Teks Tulen)
  python bin/run_persona_lifestyle_prepare.py --reddit        # Mod Reddit Curated (Dengan Gambar)
  python bin/run_persona_lifestyle_prepare.py --niche makanan # Paksa Niche Tertentu
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Any, Dict, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Teras src/
from src.persona_lifestyle_context import build_lifestyle_context_payload
from src.persona_lifestyle_reddit_reader import fetch_curated_reddit_post
from src.persona_lifestyle_filter import is_lifestyle_topic_duplicate

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"


def run_lifestyle_prepare_step(
    use_reddit: bool = False,
    force_niche: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    print("\n" + "=" * 78)
    print("🚀 [STEP 1] PERSEDIAAN KONTEKS, MOOD & PENAPISAN TOPIK LIFESTYLE MAMA")
    print("=" * 78)

    # 1. Bina Konteks Asas (Masa MYT, Mood 7 Hari, 7 Niche, Memori Redis)
    context = build_lifestyle_context_payload(force_niche=force_niche)
    dt_info = context["datetime"]
    mood_info = context["mood"]
    niche_info = context["niche"]

    print(f"🕒 Waktu Semasa   : {dt_info['formatted_full']} ({dt_info['period']})")
    print(f"🎭 Mood Persona   : {mood_info['mood_name']}")
    print(f"🌿 Niche Terpilih : {niche_info['niche_title']}")
    print(f"💡 Memori Topik   : {len(context['recent_memories'])} topik terdahulu disuntik.")

    reddit_source = {}
    local_image_path = ""
    topic_id = f"life_{int(time.time())}_{dt_info['day_index']}_{dt_info['hour']}"
    topic_text_for_lock = f"{niche_info['niche_title']} - {niche_info['prompt_hook']}"

    # 2. Ambil Pos Reddit Jika Mod Reddit Diaktifkan
    if use_reddit:
        print(f"\n📡 [MOD REDDIT AKTIF] Mengimbas komuniti: {niche_info['suggested_subreddits']}...")
        reddit_post = fetch_curated_reddit_post(
            subreddits=niche_info["suggested_subreddits"],
            require_image=True
        )

        if reddit_post:
            reddit_source = reddit_post
            topic_text_for_lock = f"{reddit_post['title']} {reddit_post['description'][:80]}"
            topic_id = f"reddit_{reddit_post['post_id']}_{int(time.time())}"
            if reddit_post.get("local_images"):
                local_image_path = reddit_post["local_images"][0]["local_path"]
                print(f"🖼️ Imej Reddit Utama : {Path(local_image_path).name}")
            print(f"✅ Topik Reddit Ditemui: \"{reddit_post['title'][:60]}...\"")
        else:
            print("⚠️ Tiada pos Reddit dengan imej ditemui. Beralih ke mod penceritaan santai biasa.")

    # 3. Semak Penapis Dwi-Lapisan (Redis 10 Hari & Vector 2 Hari)
    print(f"\n🛡️ [PENAPIS DWI-LAPISAN] Menyemak keunikan topik...")
    is_dup, dup_reason = is_lifestyle_topic_duplicate(topic_text_for_lock)
    if is_dup:
        print(f"⚠️ [TOPIK PENDUA] {dup_reason}")
        print("🔄 Menyesuaikan variasi hook penceritaan alternatif...")
        topic_text_for_lock = f"{topic_text_for_lock} variasi {dt_info['time_str']}"

    # 4. Bina Payload Penuh
    payload = {
        "step": 1,
        "topic_id": topic_id,
        "topic_lock_text": topic_text_for_lock,
        "datetime": dt_info,
        "mood": mood_info,
        "niche": niche_info,
        "recent_memories": context["recent_memories"],
        "reddit_source": reddit_source,
        "local_image_path": local_image_path,
        "engine_used": "PENDING",
        "total_duration_sec": 0.0,
        "ai_captions": {
            "facebook": "",
            "instagram": "",
            "threads": "",
            "bluesky": "",
        },
        "post_results": {
            "facebook": {"status": "pending"},
            "instagram": {"status": "pending"},
            "threads": {"status": "pending"},
            "bluesky": {"status": "pending"},
        },
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    }

    # 5. Simpan ke fail state temp/lifestyle_payload.json
    try:
        with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n💾 [PAYLOAD SIAP] Fail disimpan ke: {PAYLOAD_FILE.name}")
        print("=" * 78 + "\n")
        return payload
    except Exception as e:
        print(f"\n❌ [RALAT SIMPAN PAYLOAD] {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 1 Runner: Lifestyle Mama Context & Topic Preparer")
    parser.add_argument("--reddit", action="store_true", help="Aktifkan sumber inspirasi komuniti Reddit bergambar.")
    parser.add_argument("--niche", type=str, default=None, help="Paksa niche tertentu (tanaman, makanan, diy, affiliate_santai, movie_drama, hal_semasa, santai_keluarga).")
    args = parser.parse_args()

    run_lifestyle_prepare_step(use_reddit=args.reddit, force_niche=args.niche)