#!/usr/bin/env python3
"""
Shopee Vision & Mama English Persona Review Engine (Chic & Lightweight Edition)
Impian Rumahku Ecosystem (Step 2 Pipeline)
Features:
- Encodes compressed JPEG image (<60KB) to prevent socket timeouts
- Persona: Educated 30-something English lifestyle creator (sharp, versatile insights)
- Strict character limit: strictly <= 500 characters total
- Mojibake & Glitch Scrubber: cleans corrupted UTF-8 byte encodings
- Removes max_tokens constraint from request payload
- 3x Retry mechanism with strict socket timeout (8s, 25s)
- 100% Code-Locked: shopee_affiliate_link & shopee_price remain immutable
- Saves structured payload to temp/shopee_vision_ocr.json & temp/shopee_payload.json
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


def clean_and_scrub_vision_text(text: str) -> str:
    """
    Membersihkan tag pemikiran, ralat simbol mojibake, dan mengehadkan teks <= 500 aksara.
    """
    if not text:
        return ""

    # 1. Buang tag pemikiran AI & kod markdown
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    # 2. Rawat simbol rosak (Mojibake & Glitch Encodings)
    replacements = {
        "Ã©": "e", "Ã¨": "e", "Ã ": "a", "Ã¡": "a", "Ã±": "n",
        "â€™": "'", "â€˜": "'", "â€œ": '"', "â€": '"',
        "â€‘": "-", "â€”": "-", "â€“": "-", "â€¦": "...",
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    # 3. Buang sebarang simbol kawalan yang tidak standard
    cleaned = re.sub(r"[\x80-\x9f]", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")

    # 4. Kawalan Had Keras: Maksimum 500 aksara (Potong pada tanda noktah terakhir)
    if len(cleaned) > 500:
        trimmed = cleaned[:500]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        if match:
            cleaned = match.group(1).strip()
        else:
            cleaned = trimmed.rstrip() + "..."

    return cleaned


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
    Mengecilkan resolusi dan memampatkan imej ke Base64 (~40KB - 60KB).
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
    Ulasan sandaran Bahasa Inggeris bergaya dan ringkas jika Vision API gagal.
    """
    return (
        f"I really admire the thoughtful design and versatile utility of this {product_name[:40]} from {brand}. "
        f"It effortlessly combines practical everyday functionality with a clean, modern aesthetic. "
        f"At only RM{price:.2f}, it is a delightful and budget-friendly upgrade for keeping spaces tidy and organized."
    ).strip()


def analyze_product_image_with_vision(
    product: Dict[str, Any],
    max_attempts: int = 3,
    delay_seconds: int = 2
) -> Dict[str, Any]:
    """
    Step 2: Enjin Vision Persona Wanita English Terpelajar (Maksimum 500 aksara).
    """
    product_id = str(product.get("shopee_product_id") or product.get("product_id") or "").strip()
    product_name = str(product.get("shopee_product_name") or product.get("product_name") or "").strip()
    product_brand = str(product.get("shopee_brand") or product.get("brand") or "Shopee Preferred").strip()
    locked_price = float(product.get("shopee_price") or product.get("price") or 0.0)
    picture_url = str(product.get("shopee_picture_url") or product.get("picture_url") or "").strip()
    locked_affiliate_link = str(product.get("shopee_affiliate_link") or product.get("affiliate_link") or "").strip()

    print(f"\n🖼️ [STEP 2: VISION PROMOTION REVIEW] Memulakan ulasan visual untuk ID: {product_id}...")
    print(f"   📦 Produk: {product_name[:60]}...")
    print(f"   💰 Harga Terkunci: RM{locked_price:.2f}")

    # 1. Muat turun imej dan mampatkan ke Base64 ringan
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

        # Prompt Persona Wanita Terpelajar 30-an (Fokus Visual & Kepelbagaian Kegunaan)
        system_prompt = (
            "You are an articulate, educated 30-something English lifestyle creator and social media curator.\n"
            "Your style is vibrant, clever, chic, and observant. You love sharing versatile home and lifestyle finds.\n\n"
            "TASK:\n"
            "Look closely at the product photo and title. Write a polished, engaging micro-review in ENGLISH.\n"
            "Describe the visible aesthetic (colors, materials, form factor) and explain its versatile practical uses in daily living.\n\n"
            "STRICT RULES:\n"
            "1. Write strictly in natural, eloquent ENGLISH.\n"
            "2. Total length MUST be between 250 and 500 characters.\n"
            "3. Focus on real visual details and smart versatile utility.\n"
            "4. NEVER include URLs, affiliate links, hashtags, emojis, or conversational intros.\n"
            "5. Return ONLY the review paragraph with clean punctuation."
        )

        user_content = [
            {
                "type": "text",
                "text": (
                    f"Product Title: {product_name}\n"
                    f"Brand: {product_brand}\n"
                    f"Price: RM{locked_price:.2f}\n\n"
                    f"Write your versatile visual review in English (strictly under 500 characters):"
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": base64_image},
            },
        ]

        # Payload ringan tanpa had max_tokens manual
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.35,
        }

        for attempt in range(1, max_attempts + 1):
            print(f"   📡 [Vision Attempt {attempt}/{max_attempts}] Menghantar ke model: {model_name}...")
            try:
                res = requests.post(endpoint_url, headers=headers, json=payload, timeout=(8, 25))
                if res.status_code == 200:
                    res_json = res.json()
                    raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_and_scrub_vision_text(raw_text)

                    if len(clean_text) >= 180:
                        mama_english_review = clean_text
                        used_model = model_name
                        is_fallback = False
                        print(f"   ✅ [Vision Berjaya] Ulasan dijana ({len(mama_english_review)} aksara): \"{mama_english_review[:65]}...\"")
                        break
                    else:
                        print(f"   ⚠️ [Ulasan Terlalu Pendek] ({len(clean_text)} aksara). Mencuba semula...")
                else:
                    print(f"   ⚠️ [Vision HTTP {res.status_code}] {res.text[:100]}")
            except requests.exceptions.Timeout:
                print(f"   ⚠️ [Vision Timeout ({attempt}/{max_attempts})] Sambungan tamat masa (8s/25s).")
            except Exception as e:
                print(f"   ⚠️ [Vision Error ({attempt}/{max_attempts})]: {e}")

            if attempt < max_attempts:
                time.sleep(delay_seconds)

    # 3. Fallback jika Vision gagal
    if not mama_english_review:
        print("   🛡️ [FALLBACK AKTIF] Menggunakan ulasan sandaran Bahasa Inggeris asas.")
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

    # 5. Simpan ke fail sementara temp/shopee_vision_ocr.json
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
    print("🧪 [TEST RUN] Menguji Enjin Vision Persona (Step 2)...")
    print("=" * 70)

    sample_candidate = {
        "shopee_product_id": "22355433182",
        "shopee_product_name": "Scentify Fabric Perfume Sparkling Fruite 370ml | 2X Long-Lasting",
        "shopee_brand": "Wipro Unza Official Store",
        "shopee_price": 9.50,
        "shopee_picture_url": "https://down-my.img.susercontent.com/file/my-11134207-7rash-mam2t6c3p0rv4e",
        "shopee_affiliate_link": "https://s.shopee.com.my/4VcDe9OWtV",
    }

    result = analyze_product_image_with_vision(sample_candidate, max_attempts=3, delay_seconds=2)
    print("\n📦 Hasil Payload JSON Siap (Pratonton):")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n📏 Panjang Ulasan English: {result.get('review_char_count')} aksara (Maksimum 500)")
    print("=" * 70)