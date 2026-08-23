#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 3D Runner (Bluesky AT-Protocol Feed)
Location: bin/run_shopee_post_blsky.py
Features:
- Imports core functions directly from src/shopee_Ai_persona_bluesky.py
- Lightweight Mini-Payload (caps reference text to avoid OpenRouter timeouts)
- Hard Safety Cap: strictly <= 280 characters total (prevents truncated posts)
- Uploads direct binary image blob to AT-Protocol repository
- Configures clickable UTF-8 byte facets for Shopee affiliate link
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
from src.shopee_Ai_persona_bluesky import (
    generate_mama_bluesky_copy,
    assemble_bluesky_post,
    post_to_bluesky,
)

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"


def run_bluesky_step():
    print("\n" + "=" * 75)
    print("🦋 [STEP 3D] MENJALANKAN PEMPOSAN BLUESKY FEED (AT-PROTOCOL)")
    print("=" * 75)

    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tiada. Sila jalankan Step 1 & 2 dahulu.")
        sys.exit(1)

    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # 1. Bina Mini-Payload Ringan (Keringanan Inference OpenRouter)
    raw_name = payload.get("shopee_product_name", "")
    vision_text = payload.get("mama_english_review", "") or ""

    mini_payload = {
        "shopee_product_id": payload.get("shopee_product_id", ""),
        "shopee_product_name": raw_name[:35],
        "shopee_brand": payload.get("shopee_brand", "Shopee Preferred"),
        "shopee_price": float(payload.get("shopee_price", 0.0)),
        "shopee_affiliate_link": payload.get("shopee_affiliate_link", ""),
        "local_image_path": payload.get("local_image_path", ""),
        "mama_english_review": vision_text[:100],
    }

    # 2. Jana Ulasan Mikro Persona Mama (BM)
    micro_story_bm = generate_mama_bluesky_copy(mini_payload)

    # 3. Cantumkan Kapsyen Had Keras (<= 280 Aksara) & Kira Byte Facets
    full_text, aff_link, b_start, b_end = assemble_bluesky_post(payload, micro_story_bm)

    print("\n" + "-" * 75)
    print("📝 [PRATONTON HANTARAN BLUESKY]:")
    print(full_text)
    print("-" * 75)
    print(f"📏 Jumlah Aksara Hantaran: {len(full_text)} / 280 aksara (Kalis Terpotong)")
    print("-" * 75)

    # 4. Hantar ke Bluesky Feed
    img_path = payload.get("local_image_path", "")
    success, post_info, msg = post_to_bluesky(
        full_text=full_text,
        affiliate_link=aff_link,
        byte_start=b_start,
        byte_end=b_end,
        image_path=img_path,
    )

    # 5. Rekod Hasil ke dalam State Payload
    if "post_results" not in payload:
        payload["post_results"] = {}
    if "ai_captions" not in payload:
        payload["ai_captions"] = {}

    if success:
        payload["post_results"]["bluesky"] = {
            "status": "success",
            "uri": post_info.get("uri"),
            "char_count": len(full_text),
        }
        print(f"\n🎉 [STEP 3D SUCCESS] {msg}")
    else:
        payload["post_results"]["bluesky"] = {
            "status": "failed",
            "error": msg,
        }
        print(f"\n⚠️ [STEP 3D FAILED] {msg}")

    payload["ai_captions"]["bluesky"] = full_text

    # 6. Simpan Status Terkini ke shopee_payload.json
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"💾 [PAYLOAD UPDATED] Status Bluesky direkodkan ke: {PAYLOAD_FILE.name}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_bluesky_step()