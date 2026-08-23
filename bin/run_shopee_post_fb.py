#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 3A Runner (Facebook Page Feed & Comment)
Location: bin/run_shopee_post_fb.py
Features:
- Imports core functions directly from src/shopee_Ai_persona_fb.py
- Smart Sentence-Boundary Trimmer (guarantees overall caption strictly 500 - 750 chars)
- Posts physical image to FB Page Feed
- Dispatches code-locked Shopee affiliate link to the first comment
- Updates temp/shopee_payload.json with status & generated caption
"""

import re
import sys
import json
from pathlib import Path

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Fungsi Teras Tanpa Mengubah src/
from src.shopee_Ai_persona_fb import (
    generate_mama_fb_copy,
    assemble_fb_post_and_comment,
    post_to_facebook_page,
)

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"
MAX_FB_HARD_CAP = 750


def enforce_fb_character_limit(post_caption: str, comment_text: str, payload: dict) -> str:
    """
    Memastikan teks hantaran FB tidak melebihi had 750 aksara dengan
    memotong teks pada noktah ayat terakhir yang lengkap.
    """
    if len(post_caption) <= MAX_FB_HARD_CAP:
        return post_caption

    # Asingkan bahagian header, body, dan footer
    title_raw = str(payload.get("shopee_product_name", "")).strip()
    price = float(payload.get("shopee_price", 0.0))

    header = f"✨ {title_raw[:45]}...\n\n" if len(title_raw) > 45 else f"✨ {title_raw}\n\n"
    footer = (
        f"\n\n💰 Harga Mesra Poket: RM{price:.2f}\n"
        f"📌 Mama dah letak link barang ni di ruangan komen pertama di bawah ya! 👇\n\n"
        f"#ImpianRumahku #CeritaMama #KemasRumah #TipsSuriRumah #RacunShopee"
    )

    fixed_len = len(header) + len(footer)
    max_story_space = MAX_FB_HARD_CAP - fixed_len

    # Dapatkan teks asal ulasan AI
    story_raw = post_caption.replace(header, "").replace(footer, "").strip()

    if len(story_raw) > max_story_space:
        trimmed = story_raw[:max_story_space]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        if match:
            story_raw = match.group(1).strip()
        else:
            story_raw = trimmed.rstrip() + "..."

    return f"{header}{story_raw}{footer}".strip()


def run_facebook_step():
    print("\n" + "=" * 75)
    print("🔵 [STEP 3A] MENJALANKAN PEMPOSAN FACEBOOK PAGE & KOMEN AFFILIATE")
    print("=" * 75)

    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tiada. Sila jalankan Step 1 & 2 dahulu.")
        sys.exit(1)

    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # 1. Jana Ulasan Santai Mama FB (BM) menggunakan enjin src/
    mama_story_bm = generate_mama_fb_copy(payload)

    # 2. Cantumkan Kapsyen FB & Komen Affiliate
    post_caption_raw, comment_text = assemble_fb_post_and_comment(payload, mama_story_bm)

    # 3. Kawalan Had Aksara (Enforce 500 - 750 Aksara)
    post_caption = enforce_fb_character_limit(post_caption_raw, comment_text, payload)

    print("\n" + "-" * 75)
    print("📝 [PRATONTON HANTARAN FB PAGE]:")
    print(post_caption)
    print("-" * 75)
    print(f"📏 Jumlah Aksara Hantaran: {len(post_caption)} / 750 aksara (Kalis Terlebih Panjang)")
    print("\n💬 [PRATONTON KOMEN PERTAMA]:")
    print(comment_text)
    print("-" * 75)

    # 4. Hantar ke Facebook Page Feed
    img_path = payload.get("local_image_path", "")
    img_url = payload.get("shopee_picture_url", "")

    success, post_info, msg = post_to_facebook_page(
        image_path=img_path,
        image_url=img_url,
        post_caption=post_caption,
        comment_text=comment_text,
    )

    # 5. Rekod Hasil ke dalam State Payload
    if "post_results" not in payload:
        payload["post_results"] = {}
    if "ai_captions" not in payload:
        payload["ai_captions"] = {}

    if success:
        payload["post_results"]["facebook"] = {
            "status": "success",
            "post_id": post_info.get("post_id"),
            "photo_id": post_info.get("photo_id"),
            "char_count": len(post_caption),
        }
        print(f"\n🎉 [STEP 3A SUCCESS] {msg}")
    else:
        payload["post_results"]["facebook"] = {
            "status": "failed",
            "error": msg,
        }
        print(f"\n⚠️ [STEP 3A FAILED] {msg}")

    payload["ai_captions"]["facebook"] = post_caption

    # 6. Simpan Status Terkini ke shopee_payload.json
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"💾 [PAYLOAD UPDATED] Status Facebook direkodkan ke: {PAYLOAD_FILE.name}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_facebook_step()