#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 1 Runner (Fetch, Filter & Prepare Candidate)
Location: bin/run_shopee_prepare_and_generate.py
"""

import sys
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Teras dari src/
from src.shopee_supabase_db import fetch_shopee_candidate_batch, check_and_reset_shopee_status
from src.shopee_redis_filter import filter_unposted_shopee_products
from src.shopee_vector_filter import find_first_vector_unique_product

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"
MAX_ATTEMPTS = 5
BATCH_SIZE = 300


def run_preparation_and_generation() -> Optional[Dict[str, Any]]:
    print("\n" + "=" * 75)
    print("🚀 [STEP 1] PENGAMBILAN & PENAPISAN CALON PRODUK SHOPEE (SUPABASE / REDIS / VECTOR)")
    print("=" * 75)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Semak & Auto-Reset status Supabase jika baki produk kosong
    reset_ok, reset_msg = check_and_reset_shopee_status()
    print(f"ℹ️ [SUPABASE STATUS] {reset_msg}")

    chosen_candidate = None

    # 2. Gelung Fallback 5x Percubaan
    for attempt in range(1, MAX_ATTEMPTS + 1):
        offset = (attempt - 1) * BATCH_SIZE
        print(f"\n📡 [PERCUBAAN {attempt}/{MAX_ATTEMPTS}] Menarik {BATCH_SIZE} calon produk (Offset: {offset})...")

        fetch_ok, batch_candidates, fetch_msg = fetch_shopee_candidate_batch(limit=BATCH_SIZE, offset=offset)
        if not fetch_ok or not batch_candidates:
            print(f"  ⚠️ {fetch_msg}")
            continue

        print(f"  ✅ Diterima {len(batch_candidates)} calon produk dari Supabase.")

        # 3. Tapisan 1: Upstash Redis (Kunci 30 Hari)
        print("  🛡️ [FILTER 1/2: REDIS] Menyemak penduaan 30 hari via MGET Batch...")
        redis_passed = filter_unposted_shopee_products(batch_candidates, chunk_size=100)
        if not redis_passed:
            print(f"  ⏭️ Kesemua {len(batch_candidates)} produk pernah dipos. Beralih ke kelompok seterusnya...")
            continue

        print(f"  ✅ {len(redis_passed)} produk LULUS tapisan Redis.")

        # 4. Tapisan 2: Upstash Vector DB (Keserupaan 2 Hari / 80% Threshold)
        print("  🧠 [FILTER 2/2: VECTOR] Menyemak keserupaan semantik tajuk...")
        winner = find_first_vector_unique_product(redis_passed, threshold=0.80, window_seconds=172800)
        if winner:
            chosen_candidate = winner
            print(f"\n🎉 [PEMILIHAN BERJAYA] Calon produk terpilih pada Percubaan #{attempt}!")
            break

    if not chosen_candidate:
        print(f"\n❌ [ABORT] Gagal memilih calon bersih selepas {MAX_ATTEMPTS} percubaan.")
        sys.exit(1)

    # 5. Bina dan Simpan State Payload Rasmi
    product_id = str(chosen_candidate.get("shopee_product_id", "")).strip()
    product_name = str(chosen_candidate.get("shopee_product_name", "")).strip()
    brand = str(chosen_candidate.get("shopee_brand", "Shopee Preferred")).strip()
    price = float(chosen_candidate.get("shopee_price", 0.0))
    pic_url = str(chosen_candidate.get("shopee_picture_url", "")).strip()
    aff_link = str(chosen_candidate.get("shopee_affiliate_link", "")).strip()

    payload = {
        "step": 1,
        "shopee_product_id": product_id,
        "shopee_product_name": product_name,
        "shopee_brand": brand,
        "shopee_price": price,
        "shopee_picture_url": pic_url,
        "shopee_affiliate_link": aff_link,
        "local_image_path": str(TEMP_DIR / f"shopee_{product_id}.jpg"),
        "mama_english_review": "",
        "review_char_count": 0,
        "vision_model_used": "",
        "post_results": {
            "facebook": {"status": "pending"},
            "threads": {"status": "pending"},
            "instagram": {"status": "pending"},
            "bluesky": {"status": "pending"},
        },
        "ai_captions": {
            "facebook": "",
            "threads": "",
            "instagram": "",
            "bluesky": "",
        },
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n💾 [PAYLOAD DISIMPAN] Fail state sedia di: {PAYLOAD_FILE.name}")
    print("-" * 75)
    print(f"📦 ID Produk       : {product_id}")
    print(f"🏷️ Nama Produk     : {product_name[:60]}...")
    print(f"🏢 Jenama          : {brand}")
    print(f"💰 Harga Terkunci  : RM {price:.2f}")
    print(f"🔗 Pautan Asli     : {aff_link}")
    print("=" * 75 + "\n")
    return payload


if __name__ == "__main__":
    run_preparation_and_generation()