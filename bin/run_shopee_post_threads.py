#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 3C Runner (Meta Threads Feed via B2 Bridge)
Location: bin/run_shopee_post_threads.py
Features:
- Imports core functions directly from src/shopee_Ai_persona_threads.py
- Lightweight Mini-Payload (caps reference text to 100 chars to avoid OpenRouter timeouts)
- Retrieves active token dynamically from Upstash Redis (fallback .env)
- Uploads local temporary image to Backblaze B2 Private Signed URL (600s)
- Generates natural Mama storytelling caption (Hard Cap <= 490 chars)
- Posts to Meta Threads API & triggers automatic ephemeral B2 cleanup
- Updates temp/shopee_payload.json with status and AI caption
"""

import sys
import json
from pathlib import Path

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Teras Tanpa Mengubah src/
from src.shopee_Ai_persona_threads import (
    get_threads_config,
    upload_temp_image_to_b2_signed,
    delete_ephemeral_image_from_b2,
    generate_mama_threads_copy,
    assemble_threads_post,
    post_to_threads_api,
)

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"


def run_threads_step():
    print("\n" + "=" * 75)
    print("🧵 [STEP 3C] MENJALANKAN PEMPOSAN META THREADS (VIA B2 BRIDGE)")
    print("=" * 75)

    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tiada. Sila jalankan Step 1 & 2 dahulu.")
        sys.exit(1)

    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    user_id, access_token, auth_err = get_threads_config()
    if auth_err:
        print(f"❌ [AUTH ERROR] {auth_err}")
        sys.exit(1)

    # 1. Bina Mini-Payload Ringan (Elak AI Hang / Context Overflow)
    raw_name = payload.get("shopee_product_name", "")
    vision_text = payload.get("mama_english_review", "") or ""

    mini_payload = {
        "shopee_product_id": payload.get("shopee_product_id", ""),
        "shopee_product_name": raw_name[:35],
        "shopee_brand": payload.get("shopee_brand", "Shopee"),
        "shopee_price": float(payload.get("shopee_price", 0.0)),
        "shopee_affiliate_link": payload.get("shopee_affiliate_link", ""),
        "local_image_path": payload.get("local_image_path", ""),
        "mama_english_review": vision_text[:100],  # Maksimum 100 aksara context
    }

    # 2. Muat naik imej ke Backblaze B2 (Signed Mode)
    local_img = payload.get("local_image_path", "")
    print(f"🚀 [B2 BRIDGE] Memuat naik fail imej sementara ke Backblaze B2 (Signed Mode)...")
    b2_ok, b2_signed_url, b2_file_id, b2_file_name, b2_api_url, b2_auth_token, b2_err = upload_temp_image_to_b2_signed(local_img)

    if not b2_ok:
        print(f"❌ [B2 ERROR] {b2_err}")
        sys.exit(1)

    success = False
    msg = ""
    post_info = {}
    final_caption = ""

    try:
        # 3. Jana Ulasan Santai Mama & Susun Kapsyen Threads (<= 490 Aksara)
        mama_story_bm = generate_mama_threads_copy(mini_payload)
        final_caption = assemble_threads_post(payload, mama_story_bm)

        print("\n" + "-" * 75)
        print("📝 [PRATONTON HANTARAN META THREADS]:")
        print(final_caption)
        print("-" * 75)
        print(f"📏 Jumlah Aksara Hantaran: {len(final_caption)} / 500 aksara")
        print("-" * 75)

        # 4. Hantar ke Threads API
        print(f"\n📡 Menghantar hantaran ke akaun Threads (User ID: {user_id})...")
        success, post_info, msg = post_to_threads_api(
            user_id=user_id,
            access_token=access_token,
            image_url=b2_signed_url,
            caption=final_caption,
        )

    finally:
        # 5. Pembersihan Efemeral B2 serta-merta
        print("\n🧹 [CLEANUP] Membersihkan fail imej sementara dari Backblaze B2...")
        delete_ephemeral_image_from_b2(b2_api_url, b2_auth_token, b2_file_id, b2_file_name)

    # 6. Rekod Hasil ke dalam State Payload
    if "post_results" not in payload:
        payload["post_results"] = {}
    if "ai_captions" not in payload:
        payload["ai_captions"] = {}

    if success:
        payload["post_results"]["threads"] = {
            "status": "success",
            "thread_id": post_info.get("thread_id"),
            "char_count": len(final_caption),
        }
        print(f"\n🎉 [STEP 3C SUCCESS] {msg}")
    else:
        payload["post_results"]["threads"] = {
            "status": "failed",
            "error": msg,
        }
        print(f"\n⚠️ [STEP 3C FAILED] {msg}")

    payload["ai_captions"]["threads"] = final_caption

    # 7. Simpan Status Terkini ke shopee_payload.json
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"💾 [PAYLOAD UPDATED] Status Threads direkodkan ke: {PAYLOAD_FILE.name}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_threads_step()