#!/usr/bin/env python3
"""
Shopee Vision Reader v2 (Optimized Plain-English Vision + Mesolitica NanoT5 Translator)
Impian Rumahku & Cerita Mama Ecosystem
Location: src/shopee_vision_reader_v2.py

Features:
- Plain English Directive: Generates structured, simple English tailored for accurate ML translation
- Smart BM Post-Processor: Fixes Home & Living domain terms, removes word stutters and trailing glitches
- Time & Mood Aware: Injects Malaysian Time (MYT UTC+8) & Day-Mood context
- Output Target: 300 - 500 characters
- Storage: Saves to temp/shopee_vision_v2_payload.json
"""

import os
import re
import sys
import time
import json
import base64
import requests
from io import BytesIO
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from PIL import Image
from dotenv import load_dotenv
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

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

TEMP_DIR = PROJECT_ROOT / "temp"
OUTPUT_V2_PAYLOAD = TEMP_DIR / "shopee_vision_v2_payload.json"
LOCAL_TRANSLATION_MODEL = "mesolitica/nanot5-base-malaysian-translation-v2.1"

# Cache Global untuk Model Terjemahan
_TRANSLATOR_TOKENIZER = None
_TRANSLATOR_MODEL = None

# Kamus Pembaikan Istilah Home & Living (English -> BM Translation Fixes)
GLOSARI_PEMBETULAN_BM = {
    r"\bketua mikrofiber\b": "kepala pembersih mikrofiber",
    r"\bketua pembersih\b": "bahagian berus pembersih",
    r"\bpengaturcaraan\b": "susun atur kemas",
    r"\bmudah dicemari\b": "mudah dibersihkan habuknya",
    r"\bdicemari\b": "dibersihkan",
    r"\btidak mudah\b": "mudah dan ringkas",
    r"\bmurah hati\b": "luas dan banyak",
    r"\bmencampur dengan cantik\b": "nampak kemas dan sepadan",
    r"\bbahagian harian\b": "pakaian harian",
    r"\bkeluli dua lapisan\b": "rak besi dua tingkat",
    r"\bbersemangat\b": "menarik",
    r"\btempat perlindungan kayu\b": "ruang kayu yang kemas",
    r"\bhiasan almari pakaian yang bermakna\b": "susunan almari pakaian yang kemas",
    r"\bpagar putih\b": "permukaan kaunter",
    r"\bjambul yang anggun\b": "kepala paip moden",
    r"\blilin yang selamat\b": "penutup yang kemas dan ketat",
    r"\blilin\b": "penutup botol",
    r"\bbahan pengalir\b": "bahan penebat suhu yang tahan lasak",
    r"\btidak kelihatan\b": "sentiasa bersih dan kering",
    r"\byang mudah dan berfungsi yang mudah\b": "yang ringkas dan praktikal",
}


def get_myt_time_and_mood() -> Tuple[str, str, str]:
    """Mendapatkan konteks waktu Malaysia (MYT / UTC+8) dan mood harian."""
    myt_zone = timezone(timedelta(hours=8))
    now = datetime.now(myt_zone)

    days_bm = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
    months_bm = [
        "Januari", "Februari", "Mac", "April", "Mei", "Jun",
        "Julai", "Ogos", "September", "Oktober", "November", "Disember"
    ]

    day_idx = now.weekday()
    day_name = days_bm[day_idx]
    month_name = months_bm[now.month - 1]
    hour = now.hour

    if 5 <= hour < 12:
        period = "Pagi"
    elif 12 <= hour < 14:
        period = "Tengah Hari"
    elif 14 <= hour < 19:
        period = "Petang"
    else:
        period = "Malam"

    moods = [
        "Semangat menyusun dan menyegarkan ruang rumah di awal minggu",
        "Rutin praktikal mengurus ruang harian dengan kemas dan teratur",
        "Ketenangan di pertengahan minggu dengan sentuhan deko yang estetik",
        "Persediaan kemas rumah yang ringkas dan menenangkan jiwa",
        "Suasana santai dan penuh barakah menjelang hujung minggu",
        "Masa berkualiti bersama keluarga menata ruang kediaman idaman",
        "Rehat dan ketenangan dalam rumah yang bersih dan nyaman",
    ]
    day_mood = moods[day_idx]
    time_context = f"{day_name}, {now.day} {month_name} {now.year}, {now.strftime('%I:%M %p')} ({period})"

    return time_context, period, day_mood


def get_vision_v2_config() -> Tuple[Optional[str], Optional[str], str, str, str]:
    """Membaca konfigurasi OpenRouter Vision API & Model Fallback."""
    base_url = (
        os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
        or os.getenv("OPENROUTER_BASE_URL", "").strip()
    )
    api_key = (
        os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    primary_model = (
        os.getenv("IRCM_MODEL_VISION", "").strip()
        or os.getenv("MODEL_VISION", "").strip()
        or "dots-studio/dots-3-note-preview:free"
    )
    fallback_model = (
        os.getenv("IRCM_MODEL_VISION_FALLBACK_1", "").strip()
        or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    )

    if not base_url or not api_key:
        return None, None, primary_model, fallback_model, "Kunci IRCM_OPENROUTER_BASE_URL atau IRCM_OPENROUTER_API_KEY tidak lengkap."

    endpoint_url = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
    return endpoint_url, api_key, primary_model, fallback_model, ""


def clean_shopee_title_for_vision(title: str, max_len: int = 45) -> str:
    """Membersihkan emoji, aksara Cina/asing, dan memendekkan tajuk produk."""
    if not title:
        return "Home Living Organizer"

    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", title)
    cleaned = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", "", cleaned)
    cleaned = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    words = cleaned.split()
    chosen_words = []
    curr_len = 0
    for w in words:
        addition = len(w) if not chosen_words else len(w) + 1
        if curr_len + addition <= max_len:
            chosen_words.append(w)
            curr_len += addition
        else:
            break

    return " ".join(chosen_words) if chosen_words else cleaned[:max_len]


def download_and_compress_image(image_url: str, product_id: str, max_size: int = 512, quality: int = 75) -> Tuple[bool, str, Optional[str], str]:
    """Memuat turun imej produk dan memampatkan ke Base64 (<60KB)."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    local_path = TEMP_DIR / f"shopee_{product_id}.jpg"

    if not (local_path.exists() and local_path.stat().st_size > 1000):
        if not image_url or not image_url.startswith("http"):
            return False, "", None, "URL imej produk tidak sah."

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            res = requests.get(image_url, headers=headers, timeout=20)
            if res.status_code == 200 and len(res.content) > 1000:
                with open(local_path, "wb") as f:
                    f.write(res.content)
            else:
                return False, "", None, f"Gagal muat turun imej (HTTP {res.status_code})"
        except Exception as e:
            return False, "", None, f"Ralat muat turun imej: {e}"

    try:
        with Image.open(local_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            compressed_bytes = buffer.getvalue()
            encoded_str = base64.b64encode(compressed_bytes).decode("utf-8")
            kb_size = len(compressed_bytes) / 1024
            print(f"   🖼️ [IMEJ TERMAMPAT] Resolusi: {img.size} | Saiz: {kb_size:.1f} KB")
            return True, str(local_path), f"data:image/jpeg;base64,{encoded_str}", ""
    except Exception as e:
        return False, str(local_path), None, f"Ralat memproses imej: {e}"


def clean_and_trim_raw_text(text: str) -> str:
    """Membersihkan tag pemikiran dan ralat aksara asing mentah."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    replacements = {
        "Ã©": "e", "Ã¨": "e", "Ã ": "a", "Ã¡": "a", "Ã±": "n",
        "â€™": "'", "â€˜": "'", "â€œ": '"', "â€ ": '"',
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    cleaned = re.sub(r"[\x80-\x9f]", "", cleaned)
    return cleaned.strip().strip('"').strip("'")


def post_process_bm_translation(text: str, max_chars: int = 480) -> str:
    """
    Membersihkan hasil terjemahan BM:
    1. Membetulkan istilah Home & Living yang tersasar
    2. Menghapuskan perkataan berulang (stutter removal)
    3. Merapikan tanda baca dan memotong pada noktah terakhir yang sempurna
    """
    if not text:
        return ""

    cleaned = clean_and_trim_raw_text(text)

    # 1. Aplikasi Glosari Gantian Istilah
    for pattern, replacement in GLOSARI_PEMBETULAN_BM.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # 2. Pembersihan Frasa / Kata Berulang (Deduplication)
    cleaned = re.sub(r"\bbiru\s+biru\b", "biru", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bwarna-warna\s+ceria\s+yang\s+ceria\b", "warna ceria", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbersih\s+dan\s+bersih\b", "bersih dan kemas", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\blancar\s+dan\s+lancar\b", "lancar", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\b\w+\b)\s+\1\b", r"\1", cleaned, flags=re.IGNORECASE)  # Hapus sebarang perkataan berulang 2x berturut

    # 3. Buang tanda titik lewah di penamat (seperti . . . atau ..)
    cleaned = re.sub(r"[\s.]+$", "", cleaned).strip()

    # 4. Potong pada noktah terakhir jika panjang melebihi had
    if len(cleaned) > max_chars:
        trimmed = cleaned[:max_chars]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        cleaned = match.group(1).strip() if match else trimmed.rstrip() + "."
    else:
        if not cleaned.endswith((".", "!", "?")):
            cleaned += "."

    return cleaned


def translate_with_mesolitica_nanot5(english_text: str) -> Tuple[str, float]:
    """Menterjemah teks ulasan English ke Bahasa Melayu menggunakan model tempatan Mesolitica NanoT5-Base."""
    global _TRANSLATOR_TOKENIZER, _TRANSLATOR_MODEL
    start_t = time.time()

    if _TRANSLATOR_TOKENIZER is None or _TRANSLATOR_MODEL is None:
        print(f"⏳ [MESOLITICA] Memuatkan model tempatan '{LOCAL_TRANSLATION_MODEL}'...")
        _TRANSLATOR_TOKENIZER = AutoTokenizer.from_pretrained(LOCAL_TRANSLATION_MODEL)
        _TRANSLATOR_MODEL = AutoModelForSeq2SeqLM.from_pretrained(LOCAL_TRANSLATION_MODEL)

    prompt = f"terjemah ke Melayu: {english_text.strip()}"
    inputs = _TRANSLATOR_TOKENIZER(prompt, return_tensors="pt", max_length=512, truncation=True)

    with torch.no_grad():
        outputs = _TRANSLATOR_MODEL.generate(
            **inputs,
            max_new_tokens=512,
            num_beams=2,
            no_repeat_ngram_size=3,
            repetition_penalty=1.2,
            early_stopping=True
        )

    raw_bm = _TRANSLATOR_TOKENIZER.decode(outputs[0], skip_special_tokens=True).strip()
    
    # Rawat output BM melalui Smart Post-Processor
    refined_bm = post_process_bm_translation(raw_bm, max_chars=480)
    duration = time.time() - start_t

    return refined_bm, duration


def analyze_shopee_product_vision_v2(
    product: Dict[str, Any],
    max_attempts: int = 3,
    delay_seconds: int = 2
) -> Dict[str, Any]:
    """
    Fungsi Utama: Menjalankan Vision v2 (Plain English Machine-Friendly) + Terjemahan Mesolitica.
    """
    product_id = str(product.get("shopee_product_id") or product.get("product_id") or "").strip()
    raw_name = str(product.get("shopee_product_name") or product.get("product_name") or "").strip()
    clean_name = clean_shopee_title_for_vision(raw_name, max_len=40)
    brand = str(product.get("shopee_brand") or product.get("brand") or "Shopee Preferred").strip()
    price = float(product.get("shopee_price") or product.get("price") or 0.0)
    pic_url = str(product.get("shopee_picture_url") or product.get("picture_url") or "").strip()
    aff_link = str(product.get("shopee_affiliate_link") or product.get("affiliate_link") or "").strip()

    time_context, period, day_mood = get_myt_time_and_mood()

    print("\n" + "=" * 75)
    print(f"👁️ [VISION v2] Memulakan Analisis Produk: '{clean_name}' (RM{price:.2f})")
    print(f"⏰ Konteks Waktu MYT : {time_context}")
    print(f"🌸 Mood Hari Ini     : {day_mood}")
    print("=" * 75)

    dl_ok, local_path, b64_img, dl_err = download_and_compress_image(pic_url, product_id)
    if not dl_ok or not b64_img:
        print(f"❌ {dl_err}")
        return {}

    endpoint_url, api_key, primary_model, fallback_model, cfg_err = get_vision_v2_config()
    if cfg_err:
        print(f"❌ {cfg_err}")
        return {}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # PROMPT TERPILIH: Menghalang kosa kata puitis/idiom yang merosakkan penterjemah mesin
    system_prompt = (
        "You are an observant Malaysian lifestyle curator and home living reviewer.\n"
        "TASK: Write a clear, simple, and practical review of this product in plain English.\n\n"
        "STRICT WRITING RULES FOR MACHINE TRANSLATION COMPATIBILITY:\n"
        "1. Write strictly 2 to 3 simple and direct sentences (around 40 to 55 words / 260-380 characters).\n"
        "2. State the item's material, functional color, and its exact practical benefit for keeping the home clean and tidy.\n"
        "3. FORBIDDEN WORDS & IDIOMS (DO NOT USE THESE):\n"
        "   - DO NOT use the word 'head' (use 'brush', 'cloth', or 'part').\n"
        "   - DO NOT use 'dust' as a verb (use 'clean dust from' or 'wipe dust').\n"
        "   - DO NOT use 'organizing routine' (use 'daily cleaning routine' or 'daily home care').\n"
        "   - DO NOT use 'vibrant', 'cheerful pop', 'effortless', 'pristine', or 'generous volume'.\n"
        "4. DO NOT mention prices, RM, links, hashtags, or emojis.\n"
        "5. Return ONLY the clean, simple English review ending with a period."
    )

    user_content = [
        {
            "type": "text",
            "text": (
                f"Product: {clean_name}\n"
                f"Brand: {brand}\n\n"
                f"Write a simple, clear, and direct English review optimized for easy translation:"
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": b64_img},
        },
    ]

    candidate_models = [primary_model, fallback_model]
    vision_english_review = ""
    used_model = ""

    for model_name in candidate_models:
        print(f"\n🧠 [VISION MODEL] Mencuba: '{model_name}'...")
        for attempt in range(1, max_attempts + 1):
            print(f"   📡 [Percubaan {attempt}/{max_attempts}] Menghantar permintaan Vision...")
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.40,
            }

            try:
                res = requests.post(endpoint_url, headers=headers, json=payload, timeout=(10, 30))
                if res.status_code == 200:
                    res_json = res.json()
                    raw_content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_review = clean_and_trim_raw_text(raw_content)

                    if len(clean_review) >= 140:
                        vision_english_review = clean_review
                        used_model = model_name
                        print(f"   ✅ [Vision Berjaya] Diterima ({len(vision_english_review)} aksara).")
                        break
                    else:
                        print(f"   ⚠️ [Ulasan Terlalu Pendek] ({len(clean_review)} aksara).")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:90]}")
            except Exception as e:
                print(f"   ⚠️ [Ralat Sambungan ({attempt}/{max_attempts})]: {e}")

            time.sleep(delay_seconds)

        if vision_english_review:
            break

    # Sandaran jika Vision gagal
    if not vision_english_review:
        print("🛡️ [VISION FALLBACK] Menjana teks ulasan sandaran Bahasa Inggeris mudah...")
        vision_english_review = (
            f"This practical {clean_name} from {brand} makes daily home cleaning much simpler. "
            f"Its sturdy design helps clean hard-to-reach spaces easily, keeping the entire home neat and comfortable."
        )
        used_model = "hardcoded_rule_fallback"

    # =========================================================================
    # TERJEMAHAN TEMPATAN MESOLITICA + SMART POST-PROCESSOR
    # =========================================================================
    print(f"\n🚀 [MESOLITICA TRANSLATOR] Menterjemahkan ulasan Vision ke Bahasa Melayu...")
    translated_bm, trans_duration = translate_with_mesolitica_nanot5(vision_english_review)
    print(f"✅ Terjemahan siap dalam {trans_duration:.2f} saat.")

    # =========================================================================
    # SIMPAN KE FAIL SEMENTARA BERASINGAN
    # =========================================================================
    final_payload = {
        "step": 2,
        "shopee_product_id": product_id,
        "shopee_product_name": raw_name,
        "shopee_product_clean_title": clean_name,
        "shopee_brand": brand,
        "shopee_price": price,
        "shopee_picture_url": pic_url,
        "shopee_affiliate_link": aff_link,
        "local_image_path": local_path,
        "myt_time_context": time_context,
        "day_mood": day_mood,
        "vision_english_review": vision_english_review,
        "review_char_count_en": len(vision_english_review),
        "translated_bm_review": translated_bm,
        "review_char_count_bm": len(translated_bm),
        "vision_model_used": used_model,
        "translation_engine": LOCAL_TRANSLATION_MODEL,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_V2_PAYLOAD, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    print(f"\n💾 [PAYLOAD V2 DISIMPAN] Fail sementara disimpan di: {OUTPUT_V2_PAYLOAD.name}")
    return final_payload