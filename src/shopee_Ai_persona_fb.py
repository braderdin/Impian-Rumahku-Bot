#!/usr/bin/env python3
"""
Shopee AI Persona Facebook Generator & Auto-Poster (MYT-Time Aware & Emoji-Scrubbed)
Impian Rumahku Ecosystem (Step 3 & 4 Facebook Pipeline)
Features:
- Reads temp/shopee_vision_ocr.json
- Time-Aware Context: Injects Malaysian Time (MYT / UTC+8) for natural storytelling
- Title Cleaner: Removes raw emojis and foreign CJK characters automatically
- Raw Payload: No max_tokens restriction for fluid, unclipped completions
- Post Length: Target 500 - 750 characters total post caption
- AI Model Cascading: Primary (2x) -> Fallback 1 (2x) -> Fallback 2 (2x) -> Rule-based fallback
- Facebook Strategy: Posts photo + caption to FB Page, posts locked affiliate link in 1st comment
"""

import os
import re
import sys
import time
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
INPUT_JSON_FILE = TEMP_DIR / "shopee_vision_ocr.json"


def get_myt_time_context() -> Tuple[str, str]:
    """
    Mendapatkan maklumat tarikh, hari, masa dan suasana waktu Malaysia (MYT / UTC+8).
    """
    myt_zone = timezone(timedelta(hours=8))
    now = datetime.now(myt_zone)

    days_bm = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
    months_bm = [
        "Januari", "Februari", "Mac", "April", "Mei", "Jun",
        "Julai", "Ogos", "September", "Oktober", "November", "Disember"
    ]

    day_name = days_bm[now.weekday()]
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

    time_context = f"{day_name}, {now.day} {month_name} {now.year}, {now.strftime('%I:%M %p')} (Waktu {period})"
    return time_context, period


def get_fb_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca tetapan API Facebook Page daripada persekitaran (.env / GitHub Secrets).
    """
    page_id = (
        os.getenv("IRCM_FB_META_PAGE_ID", "").strip()
        or os.getenv("FB_PAGE_ID", "").strip()
    )
    page_token = (
        os.getenv("IRCM_FB_META_PAGE_ACCESS_TOKEN", "").strip()
        or os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
    )

    if not page_id or not page_token:
        return None, None, "Kunci IRCM_FB_META_PAGE_ID atau IRCM_FB_META_PAGE_ACCESS_TOKEN tidak lengkap."

    return page_id, page_token, ""


def get_openrouter_config() -> Tuple[Optional[str], Optional[str], List[str], str]:
    """
    Membaca tetapan OpenRouter dan senarai model mengikut hierarki keutamaan.
    """
    base_url = (
        os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
        or os.getenv("OPENROUTER_BASE_URL", "").strip()
    )
    api_key = (
        os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )

    models = [
        os.getenv("IRCM_MODEL_PRIMARY", "").strip(),
        os.getenv("IRCM_MODEL_FALLBACK_1", "").strip(),
        os.getenv("IRCM_MODEL_FALLBACK_2", "").strip(),
    ]
    valid_models = [m for m in models if m]

    if not base_url or not api_key:
        return None, None, [], "Kunci IRCM_OPENROUTER_BASE_URL atau IRCM_OPENROUTER_API_KEY tidak lengkap."

    endpoint_url = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
    return endpoint_url, api_key, valid_models, ""


def clean_shopee_title_for_prompt(title: str) -> str:
    """
    Membuang emoji mentah, aksara Cina/asing, dan simbol kurungan daripada tajuk produk.
    """
    if not title:
        return "Barangan Rumah Praktikal"

    # 1. Buang emoji mentah
    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", title)

    # 2. Buang aksara CJK (Cina, Jepun, Korea) & simbol kurungan
    cleaned = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", "", cleaned)
    cleaned = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned if cleaned else title[:55]


def trim_to_last_sentence(text: str) -> str:
    """
    Memastikan teks berakhir dengan tanda noktah atau tanda seruan yang lengkap.
    """
    if not text:
        return ""
    match = re.search(r"^([\s\S]*[.!?])", text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def clean_ai_output(text: str) -> str:
    """
    Membersihkan tag pemikiran, menormalkan tanda baca, membuang emoji AI, dan memotong ayat tergantung.
    """
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")
    cleaned = trim_to_last_sentence(cleaned)

    return cleaned.strip()


def validate_text_quality(text: str) -> Tuple[bool, str]:
    """
    Menyemak kualiti teks AI (panjang teks dan abjad standard).
    """
    if not text or len(text) < 180:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima 180)."

    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan simbol atau aksara tidak sah (bukan abjad Latin / tanda baca standard)."

    words = re.findall(r"\b\w+\b", text.lower())
    if words:
        word_counts: Dict[str, int] = {}
        for w in words:
            if len(w) > 3:
                word_counts[w] = word_counts.get(w, 0) + 1
                if word_counts[w] > 10:
                    return False, f"Glitch dikesan: Perkataan '{w}' berulang lebih 10 kali."

    return True, ""


def generate_fallback_fb_story(product_name: str, brand: str) -> str:
    """
    Ulasan santai persona Mama sandaran jika panggilan AI tergendala.
    """
    clean_name = clean_shopee_title_for_prompt(product_name)
    return (
        f"Mama nak kongsi satu penemuan praktikal untuk kemaskan rumah kita iaitu {clean_name[:35]}. "
        f"Barang daripada {brand} ni memang memudahkan urusan harian suri rumah. "
        f"Senang nak guna, ringan, dan sangat membantu bila nak kemaskan ruang rumah tanpa rasa renyah. "
        f"Rekaan yang kemas dan kukuh ni memang elok ada untuk kegunaan harian sekeluarga."
    )


def generate_mama_fb_copy(payload: Dict[str, Any]) -> str:
    """
    Menghasilkan ulasan santai Bahasa Melayu bagi Facebook dengan kefahaman masa MYT.
    """
    raw_name = payload.get("shopee_product_name", "")
    clean_name = clean_shopee_title_for_prompt(raw_name)
    brand = payload.get("shopee_brand", "Shopee Preferred")
    vision_en = payload.get("mama_english_review", "") or payload.get("visual_analysis_en", {}).get("summary_text", "")
    time_context, period = get_myt_time_context()

    endpoint_url, api_key, models, cfg_err = get_openrouter_config()

    if cfg_err or not models:
        print(f"⚠️ [CONFIG WARN] {cfg_err}. Menggunakan teks sandaran asas.")
        return generate_fallback_fb_story(raw_name, brand)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "Anda adalah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang peramah, "
        "bijak, dan suka berkongsi idea hiasan serta kemas rumah bersama rakan media sosial.\n\n"
        "Tugasan Utama:\n"
        "1. Teliti nama produk dan ulasan visual Bahasa Inggeris yang diberikan.\n"
        "2. Olah nama produk menjadi lebih ringkas, menarik, dan selesa disebut dalam ulasan.\n"
        "3. Tulis 1 perenggan ulasan santai dalam Bahasa Melayu Malaysia tulen (sekitar 40 hingga 65 patah perkataan).\n"
        "4. Sesuaikan sedikit nada pembuka mengikut waktu siaran jika sesuai.\n\n"
        "Pantangan Ketat:\n"
        "- DILARANG sebut harga atau perkataan 'RM' (harga dipasang automatik oleh sistem).\n"
        "- DILARANG letak sebarang URL atau pautan Shopee di dalam ayat.\n"
        "- DILARANG guna emoji sama sekali (emoji diuruskan oleh kod).\n"
        "- DILARANG guna perkataan Indonesia (seperti bisa, banget, nggak, yuk, bikin, gampang).\n"
        "- Pastikan perenggan diakhiri dengan tanda noktah yang lengkap.\n"
        "- Terus berikan teks ulasan tanpa sebarang mukadimah atau tag pemikiran."
    )

    user_prompt = (
        f"Konteks Waktu Siaran: {time_context}\n"
        f"Nama Asal Produk: {clean_name}\n"
        f"Jenama: {brand}\n"
        f"Rujukan Visual: {vision_en}\n\n"
        f"Sila olah ulasan santai Mama dalam Bahasa Melayu Malaysia:"
    )

    for model_name in models:
        print(f"\n🧠 [AI PERSONA FB] Mencuba Model: {model_name}...")
        for attempt in range(1, 3):
            try:
                post_payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.40,
                }

                res = requests.post(endpoint_url, headers=headers, json=post_payload, timeout=40)
                if res.status_code == 200:
                    res_json = res.json()
                    raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_ai_output(raw_text)

                    is_valid, err_msg = validate_text_quality(clean_text)
                    if is_valid:
                        print(f"   ✅ [Model Berjaya: {model_name}] Teks diterima ({len(clean_text)} aksara).")
                        return clean_text
                    else:
                        print(f"   ⚠️ [Kualiti Teks Gagal ({attempt}/2)]: {err_msg}")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:100]}")
            except Exception as e:
                print(f"   ⚠️ [Ralat Rangkaian Model ({attempt}/2)]: {e}")

            time.sleep(2)

    print("🛡️ [FALLBACK AKTIF] Kesemua model AI gagal. Menggunakan penceritaan sandaran asas.")
    return generate_fallback_fb_story(raw_name, brand)


def assemble_fb_post_and_comment(payload: Dict[str, Any], mama_story_bm: str) -> Tuple[str, str]:
    """
    Menggabungkan teks hantaran FB (500-750 aksara) dan teks komen affiliate secara terkunci:
    - Post Caption: Tajuk pendek ringkas + Emoji kod + Cerita Mama + Harga Terkunci + Hashtags
    - Comment: Pautan Affiliate Shopee asli
    """
    product_name = payload.get("shopee_product_name", "")
    clean_title = clean_shopee_title_for_prompt(product_name)
    price = float(payload.get("shopee_price", 0.0))
    affiliate_link = payload.get("shopee_affiliate_link", "").strip()

    # Potong tajuk pendek kemas
    short_title = clean_title.split("|")[0].split("-")[0].strip()
    if len(short_title) > 55:
        short_title = short_title[:52] + "..."

    hashtags = "#ImpianRumahku #CeritaMama #KemasRumah #TipsSuriRumah #RacunShopee"

    post_caption = (
        f"✨ {short_title}\n\n"
        f"{mama_story_bm}\n\n"
        f"💰 Harga Mesra Poket: RM{price:.2f}\n"
        f"📌 Mama dah letak link barang ni di ruangan komen pertama di bawah ya! 👇\n\n"
        f"{hashtags}"
    )

    comment_text = (
        f"🛒 Untuk yang tanya mana Mama beli, boleh tengok link Shopee di sini ya:\n"
        f"👉 {affiliate_link}\n\n"
        f"Semoga bermanfaat untuk kemaskan rumah korang! ❤️"
    )

    return post_caption.strip(), comment_text.strip()


def post_to_facebook_page(
    image_path: str,
    image_url: str,
    post_caption: str,
    comment_text: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menghantar gambar dan teks ke Facebook Page Feed, kemudian membalas komen pautan affiliate.
    """
    page_id, page_token, err = get_fb_config()
    if err:
        return False, {}, err

    print(f"\n🚀 [FB DISPATCHER] Menghantar hantaran ke FB Page ID: {page_id}...")

    fb_photo_url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
    photo_post_id = None
    post_id = None

    try:
        if image_path and os.path.exists(image_path):
            print(f"   📤 Memuat naik fail imej fizikal: {os.path.basename(image_path)}")
            with open(image_path, "rb") as img_file:
                files = {"source": img_file}
                data = {
                    "access_token": page_token,
                    "caption": post_caption,
                }
                res = requests.post(fb_photo_url, data=data, files=files, timeout=40)
        else:
            print(f"   📤 Memuat naik menggunakan URL imej...")
            data = {
                "access_token": page_token,
                "url": image_url,
                "caption": post_caption,
            }
            res = requests.post(fb_photo_url, data=data, timeout=40)

        if res.status_code != 200:
            return False, {}, f"Gagal membuat hantaran FB (HTTP {res.status_code}): {res.text}"

        res_data = res.json()
        photo_post_id = res_data.get("id")
        post_id = res_data.get("post_id") or photo_post_id
        print(f"   🎉 [FB POST BERJAYA] ID Hantaran: {post_id}")

    except Exception as e:
        return False, {}, f"Ralat sambungan semasa pos ke FB: {str(e)}"

    # Hantar Komen Pertama
    if post_id and comment_text:
        print(f"   💬 Menghantar komen pautan affiliate ke post ID: {post_id}...")
        fb_comment_url = f"https://graph.facebook.com/v21.0/{post_id}/comments"
        comment_data = {
            "access_token": page_token,
            "message": comment_text,
        }

        try:
            comment_res = requests.post(fb_comment_url, data=comment_data, timeout=25)
            if comment_res.status_code == 200:
                comment_id = comment_res.json().get("id")
                print(f"   ✅ [FB KOMEN BERJAYA] ID Komen: {comment_id}")
            else:
                print(f"   ⚠️ [FB KOMEN AMARAN] Gagal menghantar komen (HTTP {comment_res.status_code}): {comment_res.text}")
        except Exception as e:
            print(f"   ⚠️ [FB KOMEN ERROR] Ralat semasa hantar komen: {e}")

    result_info = {
        "platform": "facebook",
        "post_id": post_id,
        "photo_id": photo_post_id,
        "char_count": len(post_caption),
    }

    return True, result_info, "Hantaran Facebook Page dan komen affiliate berjaya disiarkan!"


def run_facebook_pipeline() -> Tuple[bool, str]:
    """
    Fungsi Pengendali Utama Modul FB Persona.
    """
    if not INPUT_JSON_FILE.exists():
        return False, f"Fail input {INPUT_JSON_FILE.name} tidak ditemui dalam folder temp/. Sila jalankan Step 2 dahulu."

    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    mama_story_bm = generate_mama_fb_copy(payload)
    post_caption, comment_text = assemble_fb_post_and_comment(payload, mama_story_bm)

    char_len = len(post_caption)
    print("\n" + "=" * 70)
    print("📝 [PRATONTON HANTARAN FACEBOOK PAGE]")
    print("=" * 70)
    print(post_caption)
    print("-" * 70)
    print(f"📏 Jumlah Aksara Hantaran: {char_len} aksara (Sasaran: 500-750 aksara)")
    print("\n💬 [PRATONTON KOMEN PERTAMA AFFILIATE]")
    print("-" * 70)
    print(comment_text)
    print("=" * 70)

    img_path = payload.get("local_image_path", "")
    img_url = payload.get("shopee_picture_url", "")

    success, info, msg = post_to_facebook_page(
        image_path=img_path,
        image_url=img_url,
        post_caption=post_caption,
        comment_text=comment_text,
    )

    if success:
        print(f"\n🎉 {msg}")
        return True, msg
    else:
        print(f"\n❌ {msg}")
        return False, msg


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST & LIVE POST] Menjalankan Enjin Persona Mama untuk Facebook...")
    print("=" * 70)
    ok, message = run_facebook_pipeline()
    print("=" * 70)