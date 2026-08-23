#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 3B Runner (Instagram Feed via B2 Bridge)
Location: bin/run_shopee_post_instagram.py
Features:
- Imports core functions directly from src/shopee_Ai_persona_instagram.py
- Uploads local temporary image to Backblaze B2 Private Signed URL (600s)
- Generates cozy home decor copywriting (400 - 700 chars)
- Posts to Instagram Feed & triggers automatic ephemeral B2 cleanup
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
from src.shopee_Ai_persona_instagram import (
    get_instagram_config,
    upload_temp_image_to_b2_signed,
    delete_ephemeral_image_from_b2,
    generate_mama_instagram_copy,
    assemble_instagram_post,
    post_to_instagram_feed,
)

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"


def run_instagram_step():
    print("\n" + "=" * 75)
    print("📸 [STEP 3B] MENJALANKAN PEMPOSAN INSTAGRAM FEED (VIA B2 BRIDGE)")
    print("=" * 75)

    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tiada. Sila jalankan Step 1 & 2 dahulu.")
        sys.exit(1)

    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    account_id, access_token, auth_err = get_instagram_config()
    if auth_err:
        print(f"❌ [AUTH ERROR] {auth_err}")
        sys.exit(1)

    local_img = payload.get("local_image_path", "")
    print(f"🚀 [B2 BRIDGE] Memuat naik fail imej sementara ke Backblaze B2...")
    b2_ok, b2_signed_url, b2_file_id, b2_file_name, b2_api_url, b2_auth_token, b2_err = upload_temp_image_to_b2_signed(local_img)
    
    if not b2_ok:
        print(f"❌ [B2 ERROR] {b2_err}")
        sys.exit(1)

    success = False
    msg = ""
    post_info = {}
    final_caption = ""

    try:
        # 1. Jana Ulasan Santai Mama & Susun Kapsyen Deko Instagram (400 - 700 Aksara)
        mama_story_bm = generate_mama_instagram_copy(payload)
        final_caption = assemble_instagram_post(payload, mama_story_bm)

        print("\n" + "-" * 75)
        print("📝 [PRATONTON HANTARAN INSTAGRAM FEED]:")
        print(final_caption)
        print("-" * 75)
        print(f"📏 Jumlah Aksara Hantaran: {len(final_caption)} / 700 aksara")
        print("-" * 75)

        # 2. Hantar ke Instagram Feed
        print(f"\n📡 Menghantar hantaran ke akaun Instagram (Account ID: {account_id})...")
        success, post_info, msg = post_to_instagram_feed(
            account_id=account_id,
            access_token=access_token,
            image_url=b2_signed_url,
            caption=final_caption,
        )

    finally:
        # 3. Pembersihan Efemeral: Padam fail imej dari B2 Storage serta-merta
        print("\n🧹 [CLEANUP] Membersihkan fail imej sementara dari Backblaze B2...")
        delete_ephemeral_image_from_b2(b2_api_url, b2_auth_token, b2_file_id, b2_file_name)

    # 4. Rekod Hasil ke dalam State Payload
    if "post_results" not in payload:
        payload["post_results"] = {}
    if "ai_captions" not in payload:
        payload["ai_captions"] = {}

    if success:
        payload["post_results"]["instagram"] = {
            "status": "success",
            "media_id": post_info.get("media_id"),
            "char_count": len(final_caption),
        }
        print(f"\n🎉 [STEP 3B SUCCESS] {msg}")
    else:
        payload["post_results"]["instagram"] = {
            "status": "failed",
            "error": msg,
        }
        print(f"\n⚠️ [STEP 3B FAILED] {msg}")

    payload["ai_captions"]["instagram"] = final_caption

    # 5. Simpan Status Terkini ke shopee_payload.json
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"💾 [PAYLOAD UPDATED] Status Instagram direkodkan ke: {PAYLOAD_FILE.name}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_instagram_step()