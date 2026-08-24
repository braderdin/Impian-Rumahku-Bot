#!/usr/bin/env python3
"""
Diagnostic Test Runner: Shopee Pipeline Candidate -> Vision v2 -> Mesolitica NanoT5
Location: experiments/test_shopee_vision_reader_v2.py

Sequence:
1. Fetch 300 candidates from Supabase & Auto-Reset check
2. Filter through Redis MGET (30-day deduplication)
3. Filter through Upstash Vector DB (2-day semantic threshold 0.80)
4. Execute src/shopee_vision_reader_v2.py on the winning candidate
5. Display English Review & Malay Translation for inspection
6. Zero social media posting & Zero database commit (Safe diagnostic)
"""

import os
import sys
import json
import time
from pathlib import Path
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

# Import Komponen Saluran Paip Shopee Sedia Ada
from src.shopee_supabase_db import fetch_shopee_candidate_batch, check_and_reset_shopee_status
from src.shopee_redis_filter import filter_unposted_shopee_products
from src.shopee_vector_filter import find_first_vector_unique_product
from src.shopee_vision_reader_v2 import analyze_shopee_product_vision_v2


def print_section(title: str):
    print("\n" + "═" * 78)
    print(f"🔹 {title.upper()}")
    print("═" * 78)


def run_shopee_vision_v2_diagnostic():
    print("=" * 78)
    print("🧪 [DIAGNOSTIC TEST] SHOPEE VISION v2 + MESOLITICA NANOT5 TRANSLATION")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 78)

    # =========================================================================
    # STEP 1: PENGAMBILAN & TAPISAN CALON PRODUK SHOPEE
    # =========================================================================
    print_section("Step 1: Pengambilan & Tapisan Produk (Supabase -> Redis -> Vector)")

    reset_ok, reset_msg = check_and_reset_shopee_status()
    print(f"ℹ️ [SUPABASE STATUS] {reset_msg}")

    chosen_candidate = None
    batch_size = 300

    for attempt in range(1, 4):
        offset = (attempt - 1) * batch_size
        print(f"\n📡 [Pusingan {attempt}/3] Menarik {batch_size} calon produk dari Supabase (Offset: {offset})...")
        fetch_ok, batch_candidates, fetch_msg = fetch_shopee_candidate_batch(limit=batch_size, offset=offset)

        if not fetch_ok or not batch_candidates:
            print(f"  ⚠️ {fetch_msg}")
            continue

        print(f"  ✅ Diperoleh {len(batch_candidates)} produk.")

        # Tapis Redis 30 Hari
        print("  🛡️ [TAPISAN REDIS] Menyemak penduaan 30 hari...")
        redis_passed = filter_unposted_shopee_products(batch_candidates, chunk_size=100)
        if not redis_passed:
            print(f"  ⏭️ Kesemua calon dalam kelompok ini pernah dipos. Mencuba offset seterusnya...")
            continue

        print(f"  ✅ {len(redis_passed)} produk LULUS tapisan Redis.")

        # Tapis Vector DB 2 Hari
        print("  🧠 [TAPISAN VECTOR] Menyemak keserupaan semantik tajuk (Threshold 0.80)...")
        winner = find_first_vector_unique_product(redis_passed, threshold=0.80, window_seconds=172800)
        if winner:
            chosen_candidate = winner
            print(f"\n🎉 [CALON TERPILIH] Berjaya memilih calon segar!")
            break

    if not chosen_candidate:
        print("\n❌ Gagal memilih calon produk yang sah selepas 3 pusingan.")
        return

    # =========================================================================
    # STEP 2: JALANKAN ENJIN VISION v2 & MESOLITICA TRANSLATION
    # =========================================================================
    print_section("Step 2: Analisis Vision v2 & Terjemahan Tempatan Mesolitica")

    result_payload = analyze_shopee_product_vision_v2(chosen_candidate, max_attempts=3, delay_seconds=2)

    if not result_payload:
        print("❌ Analisis Vision v2 gagal.")
        return

    # =========================================================================
    # PAPARAN HASIL LENGKAP PADA TERMINAL UNTUK KAJIAN
    # =========================================================================
    print("\n" + "═" * 78)
    print("📊 [LAPORAN KEPUTUSAN KAJIAN AYAT TERMINAL]")
    print("═" * 78)
    print(f"📦 ID Produk       : {result_payload.get('shopee_product_id')}")
    print(f"🏷️ Tajuk Bersih    : {result_payload.get('shopee_product_clean_title')}")
    print(f"🏢 Jenama          : {result_payload.get('shopee_brand')}")
    print(f"💰 Harga           : RM {result_payload.get('shopee_price'):.2f}")
    print(f"⏰ Konteks Waktu   : {result_payload.get('myt_time_context')}")
    print(f"🌸 Mood Hari Ini   : {result_payload.get('day_mood')}")
    print(f"🧠 Model Vision    : {result_payload.get('vision_model_used')}")
    print(f"🤖 Enjin Terjemah  : {result_payload.get('translation_engine')}")
    print("-" * 78)
    print("📄 [1] ULASAN ASAL VISION (ENGLISH):")
    print(f"\"{result_payload.get('vision_english_review')}\"")
    print(f"📏 Panjang Teks EN : {result_payload.get('review_char_count_en')} Aksara")
    print("-" * 78)
    print("🇲🇾 [2] HASIL TERJEMAHAN MESOLITICA NANOT5 (BM MALAYSIA):")
    print(f"\"{result_payload.get('translated_bm_review')}\"")
    print(f"📏 Panjang Teks BM : {result_payload.get('review_char_count_bm')} Aksara")
    print("═" * 78)
    print("🛡️ [DIAGNOSTIC SELESAI] Data tersimpan di temp/shopee_vision_v2_payload.json (Tiada data dipos / dikunci).")
    print("═" * 78 + "\n")


if __name__ == "__main__":
    run_shopee_vision_v2_diagnostic()