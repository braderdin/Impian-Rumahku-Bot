#!/usr/bin/env python3
"""
Test Pipeline Runner: Local Qwen 2.5 3B GGUF on GitHub Actions
Location: experiments/local_llm/test_pipeline_local_qwen.py

Pipeline Stages:
1. Fetch candidate from Supabase (Unchanged status, no locking)
2. Vision Analysis via OpenRouter Vision (Simple English A2/B1 review)
3. Translation & Adaptation using Local Qwen 2.5 3B GGUF on CPU
4. Detailed Telegram Audit Report (Comparison: English vs BM Translation)
5. Strict Clean-up: NO posting to social media & NO database status locks (Redis/Supabase)
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

# Load .env.local jika wujud
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

# Import komponen Vision & Local LLM
from src.shopee_ocr_vision_reader import analyze_product_image_with_vision
from bin.run_shopee_prepare_and_generate import run_preparation_and_generation
from experiments.local_llm.qwen_local_engine import translate_and_adapt_to_mama_bm


def print_banner(text: str):
    print("\n" + "═" * 78)
    print(f"🧪 {text.upper()}")
    print("═" * 78)


def send_telegram_test_audit(
    product_name: str,
    brand: str,
    price: float,
    picture_url: str,
    affiliate_link: str,
    vision_model: str,
    english_review: str,
    bm_review: str,
    inference_sec: float,
    char_count: int
) -> Tuple[bool, str]:
    """
    Menghantar laporan perbandingan ulasan BI vs Terjemahan Qwen 2.5 3B ke Telegram.
    """
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
        f"🧪 <b>[TEST BENCHMARK] Qwen 2.5 3B GGUF on CPU</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {product_name[:60]}...\n"
        f"🏷️ <b>Jenama:</b> {brand} | 💰 <b>Harga:</b> RM{price:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👁️ <b>1. Original Vision Review ({vision_model}):</b>\n"
        f"<i>\"{english_review}\"</i>\n"
        f"📏 <i>Panjang: {len(english_review)} aksara</i>\n\n"
        f"🇲🇾 <b>2. Terjemahan & Olahan Qwen 2.5 3B BM:</b>\n"
        f"\"{bm_review}\"\n"
        f"📏 <i>Panjang: {char_count} aksara (Sasaran: 350-600)</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ <b>Masa Inferens CPU:</b> {inference_sec:.2f} saat\n"
        f"🔗 <b>Link Produk:</b> {affiliate_link}\n"
        f"🛡️ <i>Nota: Status pangkalan data TIDAK dikunci & Tiada hantaran ke media sosial.</i>"
    )

    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        res = requests.post(send_url, json=payload, timeout=20)
        if res.status_code == 200:
            return True, "Laporan berjaya dihantar ke Telegram!"
        return False, f"Telegram API Error HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return False, f"Ralat sambungan Telegram: {e}"


def run_local_qwen_test():
    start_total = time.time()
    print_banner("Mula Ujian Saluran: Qwen 2.5 3B GGUF Local Translation Engine")

    # -------------------------------------------------------------------------
    # STEP 1: PENGAMBILAN PRODUK SHOPEE
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
    # STEP 2: OPENROUTER VISION (PLAIN ENGLISH A2/B1)
    # -------------------------------------------------------------------------
    print("\n👁️ [STEP 2] Memproses Imej & Menjana Vision Review (Simple English)...")
    vision_payload = analyze_product_image_with_vision(payload, max_attempts=3, delay_seconds=2)
    english_review = vision_payload.get("mama_english_review", "")
    vision_model_used = vision_payload.get("vision_model_used", "Vision Model")
    local_img_path = vision_payload.get("local_image_path", "")

    print(f"   ✔ Model Vision Digunakan: {vision_model_used}")
    print(f"   ✔ Ulasan Asal BI ({len(english_review)} aksara):\n     \"{english_review}\"")

    # -------------------------------------------------------------------------
    # STEP 3: OLAHAN TERJEMAHAN LOCAL LLM (QWEN 2.5 3B GGUF)
    # -------------------------------------------------------------------------
    print("\n🇲🇾 [STEP 3] Menjana Olahan BM Menggunakan Qwen 2.5 3B GGUF (CPU)...")
    bm_review, inf_time, char_count = translate_and_adapt_to_mama_bm(
        product_name=product_name,
        brand=brand,
        price=price,
        english_review=english_review
    )

    print("-" * 78)
    print("📝 [HASIL OLAHAN BAHASA MELAYU PERSONA MAMA]")
    print(bm_review)
    print("-" * 78)
    print(f"📊 Statistik: {char_count} aksara | Masa inferens: {inf_time:.2f} saat")

    # -------------------------------------------------------------------------
    # STEP 4: HANTAR LAPORAN AUDIT KE TELEGRAM
    # -------------------------------------------------------------------------
    print("\n📲 [STEP 4] Menghantar Laporan Ujian Perbandingan ke Telegram...")
    tg_ok, tg_msg = send_telegram_test_audit(
        product_name=product_name,
        brand=brand,
        price=price,
        picture_url=picture_url,
        affiliate_link=affiliate_link,
        vision_model=vision_model_used,
        english_review=english_review,
        bm_review=bm_review,
        inference_sec=inf_time,
        char_count=char_count
    )
    print(f"   ✔ Status Telegram: {'✅ Berjaya' if tg_ok else '⚠️ ' + tg_msg}")

    # -------------------------------------------------------------------------
    # STEP 5: PEMBERSIHAN FAIL (TANPA KUNCI DATABASE)
    # -------------------------------------------------------------------------
    print("\n🛡️ [STEP 5] Kawalan Keselamatan Pengujian:")
    print("   ✔ Pengeposan media sosial: DILANGKAU (Ujian dalaman).")
    print("   ✔ Status Supabase, Redis & Vector: KEKAL UNUSED (Tiada penguncian).")

    if local_img_path and os.path.exists(local_img_path):
        try:
            os.remove(local_img_path)
            print(f"   🧹 Fail imej sementara dipadam: {Path(local_img_path).name}")
        except Exception:
            pass

    total_time = time.time() - start_total
    print_banner(f"Ujian Selesai Sepenuhnya Dalam {total_time:.2f} Saat")


if __name__ == "__main__":
    run_local_qwen_test()