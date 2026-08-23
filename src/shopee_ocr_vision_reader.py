#!/usr/bin/env python3
"""
Shopee Vision & Mama English Persona Review Engine (Lightweight & Anti-Hang Edition)
Impian Rumahku Ecosystem (Step 2 Pipeline)
Features:
- Compresses and resizes product images with Pillow (under 80KB) before Base64 encoding
- Ultra-lightweight payload to prevent OpenRouter/Cloudflare socket stalls
- Strict Socket Timeout: timeout=(8, 25) to trigger fast fallback instead of hanging
- Persona: "Mama" English (warm, observant homemaker storytelling, 400 - 700 chars)
- 3x Retry mechanism with 2-second delay per attempt
- 100% Code-Locked: shopee_affiliate_link & shopee_price remain immutable
- Saves structured payload to temp/shopee_vision_ocr.json and syncs temp/shopee_payload.json
"""

import os
import re
import sys
import time
import json
import base64
import requests
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from PIL import Image
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

# Folder Simpanan Sementara
TEMP_DIR = PROJECT_ROOT / "temp"
OUTPUT_JSON_FILE = TEMP_DIR / "shopee_vision_ocr.json"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"


def get_vision_config() -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    Membaca tetapan sambungan OpenRouter Vision API daripada persekitaran.
    """
    base_url = (
        os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
        or os.getenv("OPENROUTER_BASE_URL", "").strip()
    )
    api_key = (
        os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    vision_model = (
        os.getenv("IRCM_MODEL_VISION", "").strip()
        or os.getenv("MODEL_VISION", "").strip()
        or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    )

    if not base_url or not api_key:
        return None, None, None, "Kunci IRCM_OPENROUTER_BASE_URL atau IRCM_OPENROUTER_API_KEY tidak lengkap."

    endpoint_url = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
    return endpoint_url, api_key, vision_model, ""


def clean_thinking_output(text: str) -> str:
    """
    Membuang sebarang tag pemikiran dalaman model AI (<think>...</think>)
    serta format markdown tambahan supaya teks ulasan kekal bersih.
    """
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)
    return cleaned.strip().strip('"').strip("'")


def download_temp_image(image_url: str, product_id: str) -> Tuple[bool, str, str]:
    """
    Memuat turun imej produk Shopee ke dalam folder temp/.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    local_path = TEMP_DIR / f"shopee_{product_id}.jpg"

    if local_path.exists() and local_path.stat().st_size > 1000:
        return True, str(local_path), ""

    if not image_url or not image_url.startswith("http"):
        return False, "", "URL imej produk tidak sah."

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        res = requests.get(image_url, headers=headers, timeout=20)
        if res.status_code == 200 and len(res.content) > 1000:
            with open(local_path, "wb") as f:
                f.write(res.content)
            return True, str(local_path), ""
        return False, "", f"Gagal muat turun imej. HTTP {res.status_code}"
    except Exception as e:
        return False, "", f"Ralat muat turun imej: {str(e)}"


def compress_and_encode_image(file_path: str, max_size: int = 512, quality: int = 75) -> Optional[str]:
    """
    Mengecilkan dimensi dan memampatkan imej ke Base64 (~50KB - 80KB)
    untuk mengelakkan sekatan masa (timeout/hang) pada pelayan OpenRouter.
    """
    try:
        with Image.open(file_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            compressed_bytes = buffer.getvalue()

            encoded_str = base64.b64encode(compressed_bytes).decode("utf-8")
            kb_size = len(compressed_bytes) / 1024
            print(f"   🖼️ [IMEJ DIMAMPATKAN] Resolusi: {img.size} | Saiz: {kb_size:.1f} KB (Ringan)")
            return f"data:image/jpeg;base64,{encoded_str}"
    except Exception as e:
        print(f"⚠️ [IMAGE COMPRESS ERROR] {e}")
        return None


def generate_fallback_mama_english(product_name: str, brand: str, price: float) -> str:
    """
    Menjana ulasan Bahasa Inggeris persona Mama secara automatik
    sekiranya panggilan Vision API gagal selepas 3 percubaan.
    """
    return (
        f"Mama really loves how practical this {product_name[:45]} from {brand} looks for our daily home routine! "
        f"The neat design and sturdy build make it so easy to keep our living space tidy without any hassle. "
        f"At only RM{price:.2f}, it is super budget-friendly for the family, lightweight to handle, and fits right "
        f"into any cozy corner of the house. A must-have little helper for busy moms!"
    ).strip()


def analyze_product_image_with_vision(
    product: Dict[str, Any],
    max_attempts: int = 3,
    delay_seconds: int = 2
) -> Dict[str, Any]:
    """
    Langkah 2: Persona Mama English Vision
    - Meneliti gambar sebenar, nama, dan harga produk.
    - Menjana ulasan santai suri rumah (400-700 aksara) dalam Bahasa Inggeris.
    - Mengunci pautan affiliate & harga secara mutlak.
    - Menyimpan payload ke temp/shopee_vision_ocr.json & temp/shopee_payload.json.
    """
    # 1. Kunci Data Asal (Immutability Lock)
    product_id = str(product.get("shopee_product_id") or product.get("product_id") or "").strip()
    product_name = str(product.get("shopee_product_name") or product.get("product_name") or "").strip()
    product_brand = str(product.get("shopee_brand") or product.get("brand") or "Shopee Preferred").strip()
    locked_price = float(product.get("shopee_price") or product.get("price") or 0.0)
    picture_url = str(product.get("shopee_picture_url") or product.get("picture_url") or "").strip()
    locked_affiliate_link = str(product.get("shopee_affiliate_link") or product.get("affiliate_link") or "").strip()

    print(f"\n🖼️ [STEP 2: MAMA VISION EN] Memulakan ulasan visual untuk ID: {product_id}...")
    print(f"   📦 Produk: {product_name[:60]}...")
    print(f"   💰 Harga Terkunci: RM{locked_price:.2f}")

    # 2. Muat turun imej dan mampatkan ke Base64 ringan
    dl_ok, local_img_path, dl_err = download_temp_image(picture_url, product_id)
    base64_image = compress_and_encode_image(local_img_path) if dl_ok else None

    endpoint_url, api_key, model_name, cfg_err = get_vision_config()

    mama_english_review = ""
    used_model = "fallback_engine"
    is_fallback = True

    if not cfg_err and base64_image and endpoint_url and api_key:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = (
            "You are 'Mama' from 'Impian Rumahku & Cerita Mama' — a warm, observant, and relatable homemaker.\n"
            "Look closely at the product photo along with its name and price, then write a cozy visual review in ENGLISH.\n"
            "Describe the visual details (colors, shape, practical household usage, cleaning, organizing).\n\n"
            "STRICT CONSTRAINTS:\n"
            "1. Write strictly in ENGLISH from Mama's perspective.\n"
            "2. Total review length MUST be between 400 and 700 characters (including spaces).\n"
            "3. Focus on genuine homemaker storytelling, visual details, and practical home value.\n"
            "4. NEVER mention URLs, affiliate links, hashtags, or markdown formatting.\n"
            "5. Return ONLY the review paragraph without thinking tags (<think>)."
        )

        user_content = [
            {
                "type": "text",
                "text": (
                    f"Product Name: {product_name}\n"
                    f"Brand: {product_brand}\n"
                    f"Price: RM{locked_price:.2f}\n\n"
                    f"Write Mama's visual review in English (strictly 400 to 700 characters):"
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": base64_image},
            },
        ]

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 400,
            "temperature": 0.35,
        }

        for attempt in range(1, max_attempts + 1):
            print(f"   📡 [Mama Vision Attempt {attempt}/{max_attempts}] Menghantar ke model: {model_name}...")
            try:
                # Timeout ketat (8s connect, 25s read) mengelakkan terminal jem
                res = requests.post(endpoint_url, headers=headers, json=payload, timeout=(8, 25))
                if res.status_code == 200:
                    res_json = res.json()
                    raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_thinking_output(raw_text)

                    if len(clean_text) >= 280:
                        mama_english_review = clean_text
                        used_model = model_name
                        is_fallback = False
                        print(f"   ✅ [Mama Vision Berjaya] Ulasan dijana ({len(mama_english_review)} aksara): \"{mama_english_review[:65]}...\"")
                        break
                    else:
                        print(f"   ⚠️ [Ulasan Terlalu Pendek] ({len(clean_text)} aksara). Mencuba semula...")
                else:
                    print(f"   ⚠️ [Vision HTTP {res.status_code}] {res.text[:100]}")
            except requests.exceptions.Timeout:
                print(f"   ⚠️ [Vision Timeout ({attempt}/{max_attempts})] Sambungan tamat masa (8s/25s).")
            except Exception as e:
                print(f"   ⚠️ [Vision Network Error ({attempt}/{max_attempts})]: {e}")

            if attempt < max_attempts:
                time.sleep(delay_seconds)

    # 3. Fallback automatik jika Vision API gagal
    if not mama_english_review:
        print("   🛡️ [FALLBACK AKTIF] Menggunakan ulasan sandaran Mama English asas.")
        mama_english_review = generate_fallback_mama_english(product_name, product_brand, locked_price)

    # 4. Susun Payload Bersih
    final_payload = {
        "shopee_product_id": product_id,
        "shopee_product_name": product_name,
        "shopee_brand": product_brand,
        "shopee_price": locked_price,
        "shopee_picture_url": picture_url,
        "shopee_affiliate_link": locked_affiliate_link,
        "local_image_path": local_img_path if dl_ok else "",
        "mama_english_review": mama_english_review,
        "review_char_count": len(mama_english_review),
        "vision_model_used": used_model,
        "is_fallback": is_fallback,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    # 5. Simpan ke temp/shopee_vision_ocr.json
    try:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(final_payload, f, indent=2, ensure_ascii=False)
        print(f"   💾 [PAYLOAD DISIMPAN] Fail JSON sedia di: {OUTPUT_JSON_FILE.name}")
    except Exception as e:
        print(f"   ⚠️ [RALAT SIMPAN JSON] {e}")

    # 6. Selaraskan bersama temp/shopee_payload.json jika wujud
    if PAYLOAD_FILE.exists():
        try:
            with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
                state_payload = json.load(f)

            state_payload["step"] = 2
            state_payload["mama_english_review"] = mama_english_review
            state_payload["local_image_path"] = local_img_path if dl_ok else ""
            state_payload["review_char_count"] = len(mama_english_review)
            state_payload["vision_model_used"] = used_model
            state_payload["is_fallback"] = is_fallback

            with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
                json.dump(state_payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   ⚠️ [RALAT SYNC PAYLOAD] {e}")

    return final_payload


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST RUN] Menguji Enjin Mama English Vision (Step 2)...")
    print("=" * 70)

    sample_candidate = {
        "shopee_product_id": "24182640092",
        "shopee_product_name": "Garden Hose Holder Heavy Duty Wall-Mounted Water Hose Hanger",
        "shopee_brand": "Docooler Official Shop",
        "shopee_price": 43.04,
        "shopee_picture_url": "https://down-my.img.susercontent.com/file/my-11134207-7r98r-lktq7786t0a623",
        "shopee_affiliate_link": "https://s.shopee.com.my/7Acyp3ENUn",
    }

    result = analyze_product_image_with_vision(sample_candidate, max_attempts=3, delay_seconds=2)
    print("\n📦 Hasil Payload JSON Siap (Pratonton):")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n📏 Panjang Ulasan Mama English: {result.get('review_char_count')} aksara")
    print("=" * 70)