#!/usr/bin/env python3
"""
Shopee AI Persona Bluesky Generator & Auto-Poster (MYT-Time Aware & Lightweight Edition)
Impian Rumahku Ecosystem (Step 3 & 4 Bluesky Pipeline)
Features:
- Reads temp/shopee_vision_ocr.json
- Time-Aware Context: Injects Malaysian Time (MYT / UTC+8) for natural storytelling
- Title Cleaner: Strips raw emojis, CJK symbols, and brackets automatically
- Strict Micro-storytelling: ~15 to 25 words for Mama review body
- Temperature: 0.45 without max_tokens constraint
- Hard safety cap: Strictly <= 280 characters total (AT-Protocol post limit)
- AT-Protocol native session authentication & direct binary blob image upload
- Automatic UTF-8 byte facet generation for clickable Shopee affiliate links
- Immutably locks product price and affiliate link
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

TEMP_DIR = PROJECT_ROOT / "temp"
INPUT_JSON_FILE = TEMP_DIR / "shopee_vision_ocr.json"
MAX_HARD_CHAR_CAP = 280


# ==============================================================================
# 1. KONFIGURASI WAKTU MALAYSIA (MYT / UTC+8)
# ==============================================================================

def get_myt_time_context() -> Tuple[str, str]:
    """Mendapatkan maklumat tarikh, hari, masa dan suasana waktu Malaysia (MYT / UTC+8)."""
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


# ==============================================================================
# 2. KONFIGURASI KREDENSIAL BLUESKY & OPENROUTER
# ==============================================================================

def get_bluesky_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan akaun Bluesky daripada persekitaran."""
    handle = os.getenv("IRCM_BLUESKY_HANDLE", "").strip()
    app_password = os.getenv("IRCM_BLUESKY_APP_PASSWORD", "").strip()

    if not handle or not app_password:
        return None, None, "Kunci IRCM_BLUESKY_HANDLE atau IRCM_BLUESKY_APP_PASSWORD tidak lengkap."

    return handle, app_password, ""


def get_openrouter_config() -> Tuple[Optional[str], Optional[str], List[str], str]:
    """Membaca tetapan OpenRouter dan senarai model mengikut hierarki keutamaan."""
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


# ==============================================================================
# 3. PENJANAAN AYAT PERSONA MAMA (BLUESKY: <= 280 AKSARA TOTAL)
# ==============================================================================

def clean_shopee_title(title: str, max_len: int = 26) -> str:
    """Membuang emoji mentah, aksara Cina/asing, dan memotong tajuk pendek mengikut sempadan perkataan."""
    if not title:
        return "Barang Rumah Praktikal"

    # 1. Buang emoji mentah
    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", title)

    # 2. Buang aksara CJK & simbol kurungan
    cleaned = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", "", cleaned)
    cleaned = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    words = cleaned.split()
    chosen_words: List[str] = []
    current_length = 0

    for w in words:
        addition = len(w) if not chosen_words else len(w) + 1
        if current_length + addition <= max_len:
            chosen_words.append(w)
            current_length += addition
        else:
            break

    if not chosen_words and words:
        return words[0][:max_len]

    return " ".join(chosen_words)


def clean_ai_output(text: str) -> str:
    """Membersihkan teks AI: buang thinking tags, normalkan tanda baca, dan buang emoji AI."""
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
    cleaned = emoji_pattern.sub("", cleaned).strip().strip('"').strip("'")

    match = re.search(r"^([\s\S]*[.!?])", cleaned.strip())
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def validate_bluesky_micro_text(text: str) -> Tuple[bool, str]:
    """Menyemak kualiti teks mikro ulasan Bluesky (50 hingga 160 aksara)."""
    if not text or len(text) < 50:
        return False, f"Teks terlalu pendek ({len(text)} aksara)."
    if len(text) > 165:
        return False, f"Teks terlalu panjang untuk Bluesky ({len(text)} aksara)."

    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan simbol atau aksara tidak sah."

    return True, ""


def generate_fallback_bluesky_story(product_name: str) -> str:
    """Teks sandaran mikro khas Bluesky sekiranya panggilan AI gagal."""
    clean_name = clean_shopee_title(product_name, max_len=24)
    return f"Mama suka betul guna {clean_name} ni. Ringan, praktikal dan sangat memudahkan kerja harian kemaskan rumah."


def generate_mama_bluesky_copy(payload: Dict[str, Any]) -> str:
    """Menjana penceritaan mikro BM Persona Mama (15-25 patah perkataan) dengan masa MYT."""
    raw_name = payload.get("shopee_product_name", "")
    clean_name = clean_shopee_title(raw_name, max_len=26)
    brand = payload.get("shopee_brand", "Shopee Preferred")
    vision_en = payload.get("mama_english_review", "") or payload.get("visual_analysis_en", {}).get("summary_text", "")
    short_vision = vision_en[:120]
    time_context, _ = get_myt_time_context()

    endpoint_url, api_key, models, cfg_err = get_openrouter_config()
    if cfg_err or not models:
        return generate_fallback_bluesky_story(raw_name)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "Anda adalah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang peramah dan bersahaja di Bluesky.\n\n"
        "Tugasan Utama:\n"
        "1. Teliti nama produk dan ulasan visual Bahasa Inggeris.\n"
        "2. Tulis TEPAT 1 ayat mikro ulasan santai dalam Bahasa Melayu Malaysia tulen (sekitar 15 hingga 25 patah perkataan sahaja).\n"
        "3. Tekankan kemudahan praktikal produk untuk kemas ruang rumah.\n\n"
        "Pantangan Ketat:\n"
        "- DILARANG sebut harga atau 'RM'.\n"
        "- DILARANG letak sebarang link/URL.\n"
        "- DILARANG letak emoji.\n"
        "- DILARANG guna perkataan Indonesia (seperti bisa, banget, nggak, yuk, bikin, gampang).\n"
        "- Pastikan ayat lengkap diakhiri tanda noktah (.).\n"
        "- Terus berikan teks ulasan tanpa mukadimah atau tag pemikiran."
    )

    user_prompt = (
        f"Konteks Waktu: {time_context}\n"
        f"Produk: {clean_name}\n"
        f"Jenama: {brand}\n"
        f"Rujukan Visual: {short_vision}\n\n"
        f"Sila olah mikro ulasan Mama untuk Bluesky:"
    )

    for model_name in models:
        print(f"\n🧠 [AI BLUESKY] Mencuba Model: {model_name}...")
        for attempt in range(1, 3):
            try:
                post_payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.45,
                }
                res = requests.post(endpoint_url, headers=headers, json=post_payload, timeout=(6, 20))
                if res.status_code == 200:
                    raw_text = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_ai_output(raw_text)

                    is_valid, err_msg = validate_bluesky_micro_text(clean_text)
                    if is_valid:
                        print(f"   ✅ [Model Berjaya: {model_name}] ({len(clean_text)} aksara).")
                        return clean_text
                    print(f"   ⚠️ [Kualiti Gagal ({attempt}/2)]: {err_msg}")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:60]}")
            except Exception as e:
                print(f"   ⚠️ [Ralat Model ({attempt}/2)]: {e}")

            time.sleep(1)

    return generate_fallback_bluesky_story(raw_name)


def assemble_bluesky_post(payload: Dict[str, Any], micro_story: str) -> Tuple[str, str, int, int]:
    """Menyusun teks hantaran Bluesky dengan had keras <= 280 aksara dan indeks bait UTF-8."""
    raw_name = payload.get("shopee_product_name", "")
    short_title = clean_shopee_title(raw_name, max_len=26)
    price = float(payload.get("shopee_price", 0.0))
    affiliate_link = payload.get("shopee_affiliate_link", "").strip()

    header = f"✨ {short_title}\n\n"
    price_tag = f"\n\n💰 RM{price:.2f}\n🛒 Shopee: "
    footer = affiliate_link

    fixed_length = len(header) + len(price_tag) + len(footer)
    max_story_len = MAX_HARD_CHAR_CAP - fixed_length

    if len(micro_story) > max_story_len:
        trimmed = micro_story[:max_story_len]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        if match:
            micro_story = match.group(1).strip()
        else:
            micro_story = trimmed.rstrip() + "..."

    full_text = f"{header}{micro_story}{price_tag}{footer}"

    text_before_link = f"{header}{micro_story}{price_tag}"
    byte_start = len(text_before_link.encode("utf-8"))
    byte_end = byte_start + len(footer.encode("utf-8"))

    return full_text, affiliate_link, byte_start, byte_end


# ==============================================================================
# 4. DISPATCHER & PENERBITAN BLUESKY API
# ==============================================================================

def create_bluesky_session(handle: str, app_password: str) -> Tuple[bool, str, str, str]:
    """Membina sesi autentikasi AT-Protocol ke bsky.social."""
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    payload = {"identifier": handle, "password": app_password}
    try:
        res = requests.post(url, json=payload, timeout=12)
        if res.status_code == 200:
            data = res.json()
            return True, data.get("accessJwt", ""), data.get("did", ""), ""
        return False, "", "", f"Gagal login Bluesky (HTTP {res.status_code}): {res.text[:80]}"
    except Exception as e:
        return False, "", "", f"Ralat sambungan Bluesky: {e}"


def upload_image_to_bluesky(jwt_token: str, image_path: str) -> Tuple[bool, Dict[str, Any], str]:
    """Memuat naik fail gambar fizikal terus ke Bluesky blob storage."""
    if not image_path or not os.path.exists(image_path):
        return False, {}, "Fail imej fizikal tidak wujud untuk dimuat naik ke Bluesky."

    url = "https://bsky.social/xrpc/com.atproto.repo.uploadBlob"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "image/jpeg",
    }

    try:
        with open(image_path, "rb") as img_file:
            img_bytes = img_file.read()

        res = requests.post(url, headers=headers, data=img_bytes, timeout=(6, 20))
        if res.status_code == 200:
            blob_data = res.json().get("blob", {})
            return True, blob_data, ""
        return False, {}, f"Gagal upload blob Bluesky (HTTP {res.status_code}): {res.text[:80]}"
    except Exception as e:
        return False, {}, f"Ralat upload imej ke Bluesky: {e}"


def post_to_bluesky(
    full_text: str,
    affiliate_link: str,
    byte_start: int,
    byte_end: int,
    image_path: str
) -> Tuple[bool, Dict[str, Any], str]:
    """Menyiarkan hantaran lengkap bersama gambar dan link facets ke Bluesky feed."""
    handle, app_pwd, cfg_err = get_bluesky_config()
    if cfg_err:
        return False, {}, cfg_err

    print(f"\n🚀 [BLUESKY DISPATCHER] Memulakan sesi hantaran ke @{handle}...")

    # 1. Login Sesi
    auth_ok, jwt_token, user_did, auth_err = create_bluesky_session(handle, app_pwd)
    if not auth_ok:
        return False, {}, auth_err

    # 2. Upload Gambar Blob
    print(f"   📤 Memuat naik imej fail: {os.path.basename(image_path)}...")
    img_ok, blob_obj, img_err = upload_image_to_bluesky(jwt_token, image_path)
    if not img_ok:
        return False, {}, img_err

    # 3. Bina Facets Link
    facets = [
        {
            "index": {
                "byteStart": byte_start,
                "byteEnd": byte_end,
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": affiliate_link,
                }
            ],
        }
    ]

    # 4. Bina Record Pos
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "$type": "app.bsky.feed.post",
        "text": full_text,
        "createdAt": now_iso,
        "facets": facets,
        "embed": {
            "$type": "app.bsky.embed.images",
            "images": [
                {
                    "alt": "Shopee Home Living Product Recommendation",
                    "image": blob_obj,
                }
            ],
        },
    }

    post_url = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
    post_headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "repo": user_did,
        "collection": "app.bsky.feed.post",
        "record": record,
    }

    try:
        res = requests.post(post_url, headers=post_headers, json=payload, timeout=(6, 20))
        if res.status_code == 200:
            res_data = res.json()
            post_uri = res_data.get("uri", "")
            print(f"   🎉 [BLUESKY BERJAYA] Pos disiarkan! URI: {post_uri}")
            return True, {"platform": "bluesky", "uri": post_uri, "char_count": len(full_text)}, "Hantaran Bluesky berjaya!"
        return False, {}, f"Gagal membuat pos Bluesky (HTTP {res.status_code}): {res.text[:80]}"
    except Exception as e:
        return False, {}, f"Ralat sambungan pos Bluesky: {e}"


def run_bluesky_pipeline() -> Tuple[bool, str]:
    """Fungsi Pengendali Utama Modul Bluesky."""
    if not INPUT_JSON_FILE.exists():
        return False, f"Fail input {INPUT_JSON_FILE.name} tidak ditemui dalam folder temp/."

    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    micro_story = generate_mama_bluesky_copy(payload)
    full_text, aff_link, b_start, b_end = assemble_bluesky_post(payload, micro_story)

    print("\n" + "=" * 70)
    print("📝 [PRATONTON HANTARAN BLUESKY (HAD KERAS <= 280 AKSARA)]")
    print("=" * 70)
    print(full_text)
    print("-" * 70)
    print(f"📏 Jumlah Aksara: {len(full_text)} / 280 aksara (Kalis Terpotong)")
    print("=" * 70)

    img_path = payload.get("local_image_path", "")
    success, info, msg = post_to_bluesky(
        full_text=full_text,
        affiliate_link=aff_link,
        byte_start=b_start,
        byte_end=b_end,
        image_path=img_path,
    )

    return success, msg


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST & LIVE POST] Menjalankan Enjin Persona Mama untuk Bluesky...")
    print("=" * 70)
    ok, message = run_bluesky_pipeline()
    print("=" * 70)