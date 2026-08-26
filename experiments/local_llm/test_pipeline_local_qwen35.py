#!/usr/bin/env python3
"""
Test Pipeline Runner: Qwen3.5-4B GGUF Dual-Stage Vision + Telegram Photo Audit
Location: experiments/local_llm/test_pipeline_local_qwen35.py
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from typing import Tuple
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

from bin.run_shopee_prepare_and_generate import run_preparation_and_generation
from experiments.local_llm.qwen35_vl_engine import (
    stage_1_analyze_vision_english,
    stage_2_generate_bm_copy_from_json,
)


def print_banner(text: str):
    print("\n" + "═" * 78)
    print(f"🧪 {text.upper()}")
    print("═" * 78)


def download_test_image(image_url: str, product_id: str) -> Tuple[bool, str]:
    """Muat turun imej mentah sebelum pemampatan."""
    local_path = TEMP_DIR / f"raw_shopee_{product_id}.jpg"
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


def send_telegram_dual_audit(
    image_path: str,
    product_name: str,
    brand: str,
    price: float,
    affiliate_link: str,
    english_review: str,
    bm_review: str,
    gen_mode: str,
    total_infer_sec: float
) -> Tuple[bool, str]:
    """Menghantar foto produk bersama ulasan BI & BM terus ke Telegram."""
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
        f"🧪 <b>[TEST BENCHMARK] Qwen3.5-4B (Q4_K_M GGUF)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {product_name[:55]}...\n"
        f"🏷️ <b>Jenama:</b> {brand} | 💰 <b>Harga:</b> RM{price:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👁️ <b>1. Stage 1 OCR Vision (English):</b>\n"
        f"<i>\"{english_review}\"</i>\n"
        f"📏 <i>{len(english_review)} aksara</i>\n\n"
        f"🇲🇾 <b>2. Stage 2 Persona Mama (BM - {gen_mode}):</b>\n"
        f"\"{bm_review}\"\n"
        f"📏 <i>{len(bm_review)} aksara (Sasaran: 300-600)</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ <b>Masa Inferens Keseluruhan:</b> {total_infer_sec:.2f} saat\n"
        f"🔗 <b>Pautan Shopee:</b> {affiliate_link}\n\n"
        f"🛡️ <i>Mod Ujian: Tiada penguncian DB Supabase/Redis & tiada pos media sosial.</i>"
    )

    # Cuba hantar gambar fizikal + caption
    if image_path and os.path.exists(image_path) and len(caption) <= 1024:
        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        try:
            with open(image_path, "rb") as photo_file:
                res = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": photo_file},
                    timeout=30
                )
                if res.status_code == 200:
                    return True, "Audit bergambar berjaya dihantar ke Telegram!"
        except Exception as e:
            print(f"⚠️ [TELEGRAM PHOTO ERROR] {e}")

    # Fallback: Hantar mesej teks biasa
    url_msg = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(url_msg, json=payload, timeout=20)
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)


def run_test_pipeline():
    total_start = time.time()
    print_banner("Mula Ujian Saluran: Qwen3.5-4B GGUF Vision Dual-Stage Engine")

    # 1. Ambil calon produk (status tidak dikunci)
    print("\n📦 [LANGKAH 1] Mengambil calon produk dari Supabase & Redis...")
    payload = run_preparation_and_generation()
    if not payload:
        print("❌ Gagal mendapatkan data calon produk.")
        return

    product_id = str(payload.get("shopee_product_id"))
    product_name = payload.get("shopee_product_name", "Produk Shopee")
    brand = payload.get("shopee_brand", "Shopee Preferred")
    price = float(payload.get("shopee_price", 0.0))
    picture_url = payload.get("shopee_picture_url", "")
    affiliate_link = payload.get("shopee_affiliate_link", "")

    print(f"   ✔ Calon: ID {product_id} | {product_name[:50]}... (RM{price:.2f})")

    # 2. Muat turun gambar produk mentah
    print("\n🖼️ [LANGKAH 2] Memuat turun gambar produk mentah...")
    dl_ok, raw_img_path = download_test_image(picture_url, product_id)
    if not dl_ok:
        print("❌ Gagal memuat turun imej.")
        return

    # 3. Stage 1: Vision English OCR (3x Try, 2s Delay) -> temp/.json
    s1_ok, en_review, json_path = stage_1_analyze_vision_english(
        product_id=product_id,
        product_name=product_name,
        brand=brand,
        price=price,
        affiliate_link=affiliate_link,
        image_path=raw_img_path,
        max_retries=3,
        delay_sec=2
    )

    if not s1_ok:
        print(f"❌ Stage 1 Gagal: {en_review}")
        return

    # 4. Stage 2: Olah BM Persona Mama daripada JSON (5x Try, 2s Delay + Fallback)
    bm_copy, stage2_sec, char_len, gen_mode = stage_2_generate_bm_copy_from_json(
        json_file_path=json_path,
        max_retries=5,
        delay_sec=2
    )

    total_time = time.time() - total_start

    print("-" * 78)
    print("📝 [HASIL AKHIR PERSONA MAMA BM]")
    print(bm_copy)
    print("-" * 78)
    print(f"📊 Statistik: {char_len} aksara | Mod: {gen_mode} | Jumlah Masa: {total_time:.2f}s")

    # 5. Hantar Audit ke Telegram
    print("\n📲 [LANGKAH 5] Menghantar Laporan Ujian ke Telegram...")
    tg_ok, tg_msg = send_telegram_dual_audit(
        image_path=raw_img_path,
        product_name=product_name,
        brand=brand,
        price=price,
        affiliate_link=affiliate_link,
        english_review=en_review,
        bm_review=bm_copy,
        gen_mode=gen_mode,
        total_infer_sec=total_time
    )
    print(f"   ✔ Status Telegram: {'✅ Berjaya' if tg_ok else '⚠️ ' + tg_msg}")

    # 6. Pembersihan Fail Sementara
    print("\n🧹 [LANGKAH 6] Pembersihan fail sementara...")
    for f in [raw_img_path, json_path]:
        if f and os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    print_banner(f"Ujian Selesai Sepenuhnya ({total_time:.2f}s) - Zero DB Locks")


if __name__ == "__main__":
    run_test_pipeline()