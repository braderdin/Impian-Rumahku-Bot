#!/usr/bin/env python3
"""
Test Pipeline Runner: Local Qwen2.5-VL 3B GGUF (Q5_K_M) on GitHub Actions
Location: experiments/local_llm/test_pipeline_local_qwen_vl.py

Pipeline Flow:
1. Fetch candidate from Supabase & verify Redis (No locking)
2. Download product image into temp/ folder
3. Direct Image + Text Analysis using Local Qwen2.5-VL 3B (Q5_K_M GGUF)
4. Send Telegram Audit (Photo + Affiliate Link + Local Persona BM Copy)
5. Clean-up temp files (Zero DB locks & Zero social media posts)
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from dotenv import load_dotenv

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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

from bin.run_shopee_prepare_and_generate import run_preparation_and_generation
from experiments.local_llm.qwen_vl_local_engine import generate_local_qwen_vl_copy


def print_banner(text: str):
    print("\n" + "═" * 78)
    print(f"🧪 {text.upper()}")
    print("═" * 78)


def download_test_image(image_url: str, product_id: str) -> Tuple[bool, str]:
    """Memuat turun imej produk ke folder temp/."""
    local_path = TEMP_DIR / f"shopee_vl_{product_id}.jpg"
    if local_path.exists() and local_path.stat().st_size > 1000:
        return True, str(local_path)

    if not image_url or not image_url.startswith("http"):
        return False, ""

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(image_url, headers=headers, timeout=20)
        if res.status_code == 200 and len(res.content) > 1000:
            with open(local_path, "wb") as f:
                f.write(res.content)
            return True, str(local_path)
    except Exception as e:
        print(f"⚠️ [DOWNLOAD ERROR] {e}")
    return False, ""


def send_telegram_vl_audit(
    local_image_path: str,
    product_name: str,
    brand: str,
    price: float,
    affiliate_link: str,
    bm_review: str,
    inference_sec: float,
    char_count: int
) -> Tuple[bool, str]:
    """Menghantar foto produk dan laporan audit teks ke Telegram Bot."""
    bot_token = (
        os.getenv("IRCM_TELEGRAM_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    chat_id = (
        os.getenv("IRCM_TELEGRAM_CHAT_ID", "").strip()
        or os.getenv("TELEGRAM_CHAT_ID", "").strip()
    )

    if not bot_token or not chat_id:
        return False, "Kredensial Telegram (BOT_TOKEN / CHAT_ID) tidak lengkap."

    caption = (
        f"🧪 <b>[TEST BENCHMARK] Qwen2.5-VL 3B (Q5_K_M GGUF)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {product_name[:60]}...\n"
        f"🏷️ <b>Jenama:</b> {brand} | 💰 <b>Harga:</b> RM{price:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🇲🇾 <b>Hasil Ulasan Visual Persona Mama (100% Local VLM):</b>\n"
        f"\"{bm_review}\"\n\n"
        f"📏 <b>Panjang:</b> {char_count} aksara (Sasaran: 350-550)\n"
        f"⏱️ <b>Masa Inferens Vision + Teks:</b> {inference_sec:.2f} saat\n"
        f"🔗 <b>Pautan Shopee:</b> {affiliate_link}\n\n"
        f"🛡️ <i>Mod Ujian: Tiada penguncian pangkalan data & tiada siaran media sosial.</i>"
    )

    # 1. Hantar Photo bersama Caption jika fail gambar wujud
    if local_image_path and os.path.exists(local_image_path) and len(caption) <= 1024:
        send_photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        try:
            with open(local_image_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                res = requests.post(send_photo_url, data=data, files=files, timeout=30)
                if res.status_code == 200:
                    return True, "Gambar dan laporan audit berjaya dihantar ke Telegram!"
        except Exception as e:
            print(f"⚠️ [TELEGRAM PHOTO ERROR] {e}")

    # 2. Fallback: Hantar sebagai Text Message
    send_msg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(send_msg_url, json=payload, timeout=20)
        if res.status_code == 200:
            return True, "Laporan mesej berjaya dihantar ke Telegram!"
        return False, f"Telegram HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return False, f"Ralat sambungan Telegram: {e}"


def run_local_qwen_vl_pipeline():
    start_total = time.time()
    print_banner("Mula Ujian Saluran: Qwen2.5-VL 3B (Q5_K_M GGUF) 100% Local Vision AI")

    # -------------------------------------------------------------------------
    # STEP 1: PENGAMBILAN PRODUK DARI SUPABASE
    # -------------------------------------------------------------------------
    print("\n📦 [STEP 1] Mengambil calon produk dari Supabase...")
    payload = run_preparation_and_generation()
    if not payload:
        print("❌ Gagal mendapatkan data calon produk.")
        return

    product_id = payload.get("shopee_product_id")
    product_name = payload.get("shopee_product_name", "Produk Shopee")
    brand = payload.get("shopee_brand", "Shopee Preferred")
    price = float(payload.get("shopee_price", 0.0))
    picture_url = payload.get("shopee_picture_url", "")
    affiliate_link = payload.get("shopee_affiliate_link", "")

    print(f"   ✔ Calon Diperoleh: ID {product_id} | {product_name[:50]}... (RM{price:.2f})")

    # -------------------------------------------------------------------------
    # STEP 2: MUAT TURUN GAMBAR PRODUK
    # -------------------------------------------------------------------------
    print("\n🖼️ [STEP 2] Memuat turun gambar produk secara fizikal...")
    dl_ok, local_img = download_test_image(picture_url, str(product_id))
    if not dl_ok:
        print("❌ Gagal memuat turun imej produk.")
        return
    print(f"   ✔ Imej disimpan: {Path(local_img).name}")

    # -------------------------------------------------------------------------
    # STEP 3: PENJANAAN OLAHAN VISION LOCAL (QWEN2.5-VL Q5_K_M)
    # -------------------------------------------------------------------------
    print("\n👁️ [STEP 3] Memproses Gambar + Teks Menggunakan Qwen2.5-VL Q5_K_M (CPU)...")
    bm_copy, inf_time, char_count = generate_local_qwen_vl_copy(
        product_name=product_name,
        brand=brand,
        price=price,
        local_image_path=local_img
    )

    print("-" * 78)
    print("📝 [HASIL OLAHAN PERSONA MAMA 100% LOCAL VISION AI]")
    print(bm_copy)
    print("-" * 78)
    print(f"📊 Statistik: {char_count} aksara | Masa inferens: {inf_time:.2f} saat")

    # -------------------------------------------------------------------------
    # STEP 4: HANTAR AUDIT TELEGRAM (GAMBAR + TEKS)
    # -------------------------------------------------------------------------
    print("\n📲 [STEP 4] Menghantar Laporan Bergambar ke Telegram...")
    tg_ok, tg_msg = send_telegram_vl_audit(
        local_image_path=local_img,
        product_name=product_name,
        brand=brand,
        price=price,
        affiliate_link=affiliate_link,
        bm_review=bm_copy,
        inference_sec=inf_time,
        char_count=char_count
    )
    print(f"   ✔ Status Telegram: {'✅ Berjaya' if tg_ok else '⚠️ ' + tg_msg}")

    # -------------------------------------------------------------------------
    # STEP 5: PEMBERSIHAN FAIL (TANPA KUNCI PANGKALAN DATA)
    # -------------------------------------------------------------------------
    print("\n🛡️ [STEP 5] Kawalan Keselamatan Pengujian:")
    print("   ✔ Pengeposan media sosial: DILANGKAU (Ujian dalaman).")
    print("   ✔ Status Supabase, Redis & Vector: KEKAL UNUSED (Tiada penguncian).")

    if local_img and os.path.exists(local_img):
        try:
            os.remove(local_img)
            print(f"   🧹 Fail imej sementara dipadam: {Path(local_img).name}")
        except Exception:
            pass

    total_time = time.time() - start_total
    print_banner(f"Ujian VLM Selesai Sepenuhnya Dalam {total_time:.2f} Saat")


if __name__ == "__main__":
    run_local_qwen_vl_pipeline()