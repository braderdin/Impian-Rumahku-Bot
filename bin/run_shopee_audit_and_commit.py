#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 4 - 8 Runner (Audit & Transaction Commit)
Location: bin/run_shopee_audit_and_commit.py

Workflow:
- Step 4: Sends full audit report to Telegram Bot (Photo Summary Card + AI Captions).
- Gatekeeper: Verifies if at least ONE (1) social media platform succeeded.
  * If ALL failed: Aborts immediately without committing keys to avoid wasting the product.
- Step 5: Commits product ID to Upstash Redis (Key: 'shopee:product:<id>', TTL 30 Days).
- Step 6: Upserts title embedding to Upstash Vector DB (ID: 'sp_<id>', 2-Day window).
- Step 7: Updates Supabase record (shopee_status_used = true).
- Step 8: Cleans up temporary payload and image files in temp/.
"""

import sys
import json
from pathlib import Path

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Teras Tanpa Mengubah src/
from src.shopee_telegram_audit import send_shopee_audit_report, has_successful_post
from src.shopee_redis_filter import mark_shopee_product_posted
from src.shopee_vector_filter import mark_shopee_vector_posted
from src.shopee_supabase_db import mark_shopee_product_as_used

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"
VISION_OCR_FILE = TEMP_DIR / "shopee_vision_ocr.json"


def cleanup_temp_files(local_image_path: str = ""):
    """
    Step 8: Memadam fail sementara payload dan imej fizikal selepas transaksi selesai.
    """
    # 1. Padam shopee_payload.json
    try:
        if PAYLOAD_FILE.exists():
            PAYLOAD_FILE.unlink()
            print(f"   🧹 [CLEANUP] Fail payload '{PAYLOAD_FILE.name}' berjaya dipadam.")
    except Exception as e:
        print(f"   ⚠️ [CLEANUP WARN] Gagal memadam payload: {e}")

    # 2. Padam shopee_vision_ocr.json jika ada
    try:
        if VISION_OCR_FILE.exists():
            VISION_OCR_FILE.unlink()
            print(f"   🧹 [CLEANUP] Fail sync '{VISION_OCR_FILE.name}' berjaya dipadam.")
    except Exception as e:
        print(f"   ⚠️ [CLEANUP WARN] Gagal memadam vision ocr json: {e}")

    # 3. Padam fail gambar tempatan
    if local_image_path:
        img_p = Path(local_image_path)
        try:
            if img_p.exists():
                img_p.unlink()
                print(f"   🧹 [CLEANUP] Fail imej '{img_p.name}' berjaya dipadam.")
        except Exception as e:
            print(f"   ⚠️ [CLEANUP WARN] Gagal memadam imej fizikal: {e}")


def run_audit_and_commit():
    print("\n" + "=" * 75)
    print("📊 [STEP 4 - 8] AUDIT TELEGRAM, GATEKEEPER & TRANSAKSI KOMIT PANGKALAN DATA")
    print("=" * 75)

    # 1. Semak kewujudan fail payload
    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tidak dijumpai. Tiada data untuk diaudit.")
        sys.exit(1)

    try:
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"❌ [ABORT] Gagal membaca fail payload: {e}")
        sys.exit(1)

    product_id = str(payload.get("shopee_product_id") or payload.get("product_id") or "").strip()
    product_name = str(payload.get("shopee_product_name") or payload.get("product_name") or "Produk Shopee").strip()
    local_img = str(payload.get("local_image_path", "")).strip()
    post_results = payload.get("post_results", {})

    print(f"📦 ID Produk       : {product_id}")
    print(f"🏷️ Nama Produk     : {product_name[:65]}...")

    # =========================================================================
    # STEP 4: HANTAR LAPORAN AUDIT LENGKAP KE TELEGRAM
    # =========================================================================
    print("\n📢 [STEP 4] Menghantar laporan audit terperinci ke Telegram Bot...")
    audit_ok, audit_msg = send_shopee_audit_report(payload)
    if audit_ok:
        print("✅ [AUDIT SUCCESS] Laporan audit berjaya dihantar ke saluran Telegram.")
    else:
        print(f"⚠️ [AUDIT WARN] Telegram Audit: {audit_msg}")

    # =========================================================================
    # PINTU KESELAMATAN (SAFETY GATEKEEPER)
    # =========================================================================
    success_any = has_successful_post(payload)

    if not success_any:
        print("\n" + "!" * 75)
        print("❌ [GATEKEEPER BLOCKED] Semua platform media sosial gagal membuat hantaran!")
        print("🛑 Transaksi ke Redis, Vector DB, dan Supabase DIBATALKAN.")
        print("ℹ️  Produk ini TIDAK akan ditandakan 'used' supaya boleh dicuba semula pada sesi hadapan.")
        print("!" * 75)

        for platform, res in post_results.items():
            err_detail = res.get("error", "Status bukan success") if isinstance(res, dict) else "Tiada maklumat"
            print(f"   • {platform.capitalize()}: {err_detail}")

        # Kekalkan fail untuk rujukan debug tempatan
        sys.exit(1)

    print("\n✅ [GATEKEEPER PASSED] Sekurang-kurangnya 1 platform berjaya pos. Meneruskan transaksi...")

    # =========================================================================
    # STEP 5: REKOD KUNCI KE UPSTASH REDIS (30 HARI TTL)
    # =========================================================================
    print(f"\n💾 [STEP 5] Merekodkan kunci ID produk ke Upstash Redis...")
    redis_ok = mark_shopee_product_posted(product_id)
    if redis_ok:
        print(f"✅ Redis: Kunci 'shopee:product:{product_id}' dikunci selama 30 hari.")
    else:
        print(f"⚠️ [REDIS WARN] Gagal merekodkan kunci ke Redis.")

    # =========================================================================
    # STEP 6: REKOD EMBEDDING KE UPSTASH VECTOR DB (2 HARI WINDOW)
    # =========================================================================
    print(f"\n🟢 [STEP 6] Menyimpan embedding tajuk ke Upstash Vector DB...")
    vector_ok = mark_shopee_vector_posted(product_id, product_name)
    if vector_ok:
        print(f"✅ Vector: Embedding 'sp_{product_id}' berjaya direkodkan.")
    else:
        print(f"⚠️ [VECTOR WARN] Gagal merekodkan embedding ke Vector DB.")

    # =========================================================================
    # STEP 7: TANDAKAN STATUS DI SUPABASE (shopee_status_used = true)
    # =========================================================================
    print(f"\n⚡ [STEP 7] Mengemas kini status rekod di Supabase Cloud...")
    sb_ok, sb_msg = mark_shopee_product_as_used(product_id)
    if sb_ok:
        print(f"✅ Supabase: {sb_msg}")
    else:
        print(f"⚠️ [SUPABASE WARN] {sb_msg}")

    # =========================================================================
    # STEP 8: PEMBERSIHAN FAIL SEMENTARA
    # =========================================================================
    print(f"\n🧹 [STEP 8] Membersihkan fail sementara...")
    cleanup_temp_files(local_img)

    print("\n" + "=" * 75)
    print("🎉 [SUCCESS] Seluruh aliran pemposan Feed automatik selesai dengan jayanya!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_audit_and_commit()