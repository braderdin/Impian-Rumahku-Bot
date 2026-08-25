#!/usr/bin/env python3
"""
Shopee AI Persona Threads Generator & Auto-Poster (MYT-Time Aware & Emoji-Scrubbed)
Impian Rumahku Ecosystem (Step 3 & 4 Threads Pipeline)
Features:
- Reads temp/shopee_vision_ocr.json
- Time-Aware Context: Injects Malaysian Time (MYT / UTC+8) for natural lifestyle tone
- Short Friendly Moniker: Relatable, friendly daily storytelling
- Title Cleaner: Removes raw emojis, CJK symbols, and brackets automatically
- Raw Payload: No max_tokens restriction, fixed temperature=0.40 for stable completion
- Hard safety cap: <= 490 characters total (Threads 500 character limit)
- Dynamic Active Token: Reads Redis 'auth:impianrumahku:threads_token' first, fallback to .env
- Private Ephemeral B2 Hosting: 3x Upload & Pod Re-fetch Retry Loop (Signed 600s URL -> Auto Delete)
- 2-Stage Threads Media Container creation & status polling
- 100% Code-Locked: Affiliate link and price remain immutable
"""

import os
import re
import sys
import time
import json
import hashlib
import urllib.parse
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
MAX_THREADS_HARD_CAP = 490


# ==============================================================================
# 1. KONFIGURASI WAKTU MALAYSIA (MYT / UTC+8)
# ==============================================================================

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


# ==============================================================================
# 2. KONFIGURASI THREADS, B2 STORAGE & OPENROUTER
# ==============================================================================

def get_redis_threads_token() -> Optional[str]:
    """
    Membaca token aktif Threads terus daripada Upstash Redis (Kunci: auth:impianrumahku:threads_token).
    """
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not redis_url or not redis_token:
        return None

    endpoint = f"{redis_url.rstrip('/')}/get/auth:impianrumahku:threads_token"
    headers = {"Authorization": f"Bearer {redis_token}"}

    try:
        res = requests.get(endpoint, headers=headers, timeout=10)
        if res.status_code == 200:
            token_val = res.json().get("result")
            if token_val and isinstance(token_val, str) and len(token_val) > 20:
                return token_val.strip()
    except Exception as e:
        print(f"⚠️ [REDIS TOKEN WARN] Gagal membaca token Threads dari Redis: {e}")

    return None


def get_threads_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Mendapatkan Threads User ID dan Access Token (Utamakan Redis Token).
    """
    user_id = (
        os.getenv("IRCM_THREADS_USER_ID", "").strip()
        or os.getenv("THREADS_USER_ID", "").strip()
    )

    access_token = get_redis_threads_token()
    token_source = "Upstash Redis"

    if not access_token:
        access_token = (
            os.getenv("IRCM_THREADS_ACCESS_TOKEN", "").strip()
            or os.getenv("THREADS_ACCESS_TOKEN", "").strip()
        )
        token_source = ".env/Secret"

    if not user_id or not access_token:
        return None, None, "Kunci IRCM_THREADS_USER_ID atau Threads Access Token tidak ditemui."

    print(f"🔑 [THREADS AUTH] Menggunakan token aktif daripada: {token_source}")
    return user_id, access_token, ""


def get_b2_config() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """
    Membaca tetapan Backblaze B2 Storage daripada persekitaran.
    """
    key_id = (
        os.getenv("IRCM_B2_KEY_ID", "").strip()
        or os.getenv("IRCM_B2_ACCOUNT_KEY_ID", "").strip()
        or os.getenv("B2_KEY_ID", "").strip()
    )
    app_key = (
        os.getenv("IRCM_B2_APPLICATION_KEY", "").strip()
        or os.getenv("B2_APPLICATION_KEY", "").strip()
    )
    bucket_name = (
        os.getenv("IRCM_B2_BUCKET_NAME", "").strip()
        or os.getenv("B2_BUCKET_NAME", "").strip()
    )
    bucket_id = (
        os.getenv("IRCM_B2_BUCKET_ID", "").strip()
        or os.getenv("B2_BUCKET_ID", "").strip()
    )

    if not key_id or not app_key or not bucket_name:
        return None, None, None, None, "Konfigurasi Backblaze B2 tidak lengkap."

    return key_id, app_key, bucket_name, bucket_id, ""


def get_openrouter_config() -> Tuple[Optional[str], Optional[str], List[str], str]:
    """
    Membaca tetapan OpenRouter dan senarai model mengikut keutamaan.
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


# ==============================================================================
# 3. PENGHOSAN EFEMERAL BACKBLAZE B2 PRIVATE (SIGNED URL & AUTO-DELETE)
# ==============================================================================

def b2_authorize(key_id: str, app_key: str) -> Tuple[bool, str, str, str, str]:
    """Mendapatkan sesi autentikasi B2 REST API."""
    url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
    try:
        res = requests.get(url, auth=(key_id, app_key), timeout=20)
        if res.status_code == 200:
            data = res.json()
            return True, data.get("apiUrl", ""), data.get("authorizationToken", ""), data.get("downloadUrl", ""), ""
        return False, "", "", "", f"B2 Auth Gagal (HTTP {res.status_code}): {res.text}"
    except Exception as e:
        return False, "", "", "", f"Ralat B2 Auth: {e}"


def upload_temp_image_to_b2_signed(image_path: str) -> Tuple[bool, str, str, str, str, str, str]:
    """
    Memuat naik fail gambar tempatan ke Private B2 Bucket dan menjana Signed URL (600s).
    Dilengkapi gelung 3x percubaan bagi mengatasi ralat pod connection timeout.
    """
    if not image_path or not os.path.exists(image_path):
        return False, "", "", "", "", "", "Fail imej fizikal tidak wujud untuk dimuat naik ke B2."

    key_id, app_key, bucket_name, bucket_id, cfg_err = get_b2_config()
    if cfg_err:
        return False, "", "", "", "", "", cfg_err

    auth_ok, api_url, auth_token, download_url, auth_err = b2_authorize(key_id, app_key)
    if not auth_ok:
        return False, "", "", "", "", "", auth_err

    if not bucket_id:
        list_b_url = f"{api_url}/b2api/v2/b2_list_buckets"
        b_res = requests.post(list_b_url, json={"accountId": key_id}, headers={"Authorization": auth_token}, timeout=20)
        if b_res.status_code == 200:
            for b in b_res.json().get("buckets", []):
                if b.get("bucketName") == bucket_name:
                    bucket_id = b.get("bucketId")
                    break

    file_name = f"threads_ephemeral_{int(time.time())}_{os.path.basename(image_path)}"
    encoded_file_name = urllib.parse.quote(file_name)

    with open(image_path, "rb") as f:
        file_bytes = f.read()

    sha1_hash = hashlib.sha1(file_bytes).hexdigest()
    file_id = None
    upload_err_msg = ""

    for attempt in range(1, 4):
        get_up_url = f"{api_url}/b2api/v2/b2_get_upload_url"
        try:
            up_res = requests.post(get_up_url, json={"bucketId": bucket_id}, headers={"Authorization": auth_token}, timeout=20)
            if up_res.status_code != 200:
                upload_err_msg = f"Gagal mendapatkan B2 Upload URL: {up_res.text}"
                time.sleep(2)
                continue

            up_data = up_res.json()
            upload_url = up_data.get("uploadUrl")
            upload_auth = up_data.get("authorizationToken")

            headers = {
                "Authorization": upload_auth,
                "X-Bz-File-Name": encoded_file_name,
                "Content-Type": "image/jpeg",
                "X-Bz-Content-Sha1": sha1_hash,
                "Content-Length": str(len(file_bytes)),
            }

            upload_post = requests.post(upload_url, data=file_bytes, headers=headers, timeout=(10, 40))
            if upload_post.status_code == 200:
                file_id = upload_post.json().get("fileId")
                break
            else:
                upload_err_msg = f"HTTP {upload_post.status_code}: {upload_post.text}"
        except requests.exceptions.RequestException as e:
            upload_err_msg = f"Ralat rangkaian B2: {e}"

        if attempt < 3:
            print(f"   ⚠️ [B2 RETRY] Percubaan {attempt}/3 gagal ({upload_err_msg[:60]}...). Meminta pod baharu...")
            time.sleep(2)

    if not file_id:
        return False, "", "", "", "", "", f"Gagal muat naik ke B2 selepas 3 percubaan: {upload_err_msg}"

    try:
        down_auth_url = f"{api_url}/b2api/v2/b2_get_download_authorization"
        down_payload = {
            "bucketId": bucket_id,
            "fileNamePrefix": file_name,
            "validDurationInSeconds": 600,
        }
        down_res = requests.post(down_auth_url, json=down_payload, headers={"Authorization": auth_token}, timeout=15)

        if down_res.status_code == 200:
            download_token = down_res.json().get("authorizationToken")
            base_file_url = f"{download_url}/file/{bucket_name}/{encoded_file_name}"
            signed_url = f"{base_file_url}?Authorization={download_token}"
            print(f"   ☁️ [B2 SIGNED URL GENERATED] Sah selama 10 minit untuk Meta Crawler.")
            return True, signed_url, file_id, file_name, api_url, auth_token, ""
        else:
            return False, "", "", "", "", "", f"Gagal menjana B2 Signed Token: {down_res.text}"

    except Exception as e:
        return False, "", "", "", "", "", f"Ralat penjanaan token B2: {e}"


def delete_ephemeral_image_from_b2(api_url: str, auth_token: str, file_id: str, file_name: str) -> bool:
    """Memadam fail imej sementara dari B2 Private Bucket."""
    if not file_id or not file_name or not api_url or not auth_token:
        return False

    del_url = f"{api_url}/b2api/v2/b2_delete_file_version"
    payload = {"fileName": file_name, "fileId": file_id}
    headers = {"Authorization": auth_token}

    try:
        res = requests.post(del_url, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            print(f"   🧹 [B2 CLEANUP] Fail sementara B2 '{file_name}' berjaya dipadam!")
            return True
    except Exception as e:
        print(f"⚠️ [B2 CLEANUP WARN] Gagal padam fail B2: {e}")

    return False


# ==============================================================================
# 4. PENJANAAN AYAT PERSONA MAMA (THREADS: HAD KERAS <= 490 AKSARA)
# ==============================================================================

def clean_shopee_title(title: str, max_len: int = 35) -> str:
    """
    Membuang emoji mentah, aksara Cina/asing, dan memotong tajuk pendek mengikut perkataan penuh.
    """
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
    """Membersihkan tag pemikiran, menormalkan tanda baca, dan membuang emoji AI."""
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

    match = re.search(r"^([\s\S]*[.!?])", cleaned.strip())
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def validate_threads_text(text: str) -> Tuple[bool, str]:
    """Menyemak kualiti teks ulasan Threads (60 hingga 220 aksara)."""
    if not text or len(text) < 60:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima 60)."
    if len(text) > 230:
        return False, f"Teks terlalu panjang ({len(text)} aksara, maksima 230)."

    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan simbol atau aksara tidak sah."

    return True, ""


def generate_fallback_threads_story(product_name: str) -> str:
    """Teks sandaran asas khas Threads jika AI gagal."""
    clean_name = clean_shopee_title(product_name, max_len=30)
    short_name = clean_name.split("|")[0].split("-")[0].strip()[:28]
    return f"Senang kerja bila ada {short_name} ni kat rumah. Ringan, praktikal dan sangat membantu bila nak kemaskan ruang harian."


def generate_mama_threads_copy(payload: Dict[str, Any]) -> str:
    """
    Menjana luahan santai harian Threads Mama dengan had ringkas dan bersahaja.
    """
    raw_name = payload.get("shopee_product_name", "")
    clean_name = clean_shopee_title(raw_name, max_len=30)
    brand = payload.get("shopee_brand", "Shopee Preferred")
    vision_en = payload.get("mama_english_review", "") or payload.get("visual_analysis_en", {}).get("summary_text", "")
    short_vision = vision_en[:180]
    time_context, period = get_myt_time_context()

    endpoint_url, api_key, models, cfg_err = get_openrouter_config()
    if cfg_err or not models:
        return generate_fallback_threads_story(raw_name)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "Anda adalah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang mesra, "
        "santai, dan suka berkongsi luahan harian yang 'relatable' di Threads.\n\n"
        "Tugasan Utama:\n"
        "1. Fahami fungsi utama produk daripada tajuk dan rujukan visual English yang diberikan.\n"
        "2. Ringkaskan tajuk panjang Shopee menjadi nama panggilan harian yang ringkas (contoh: 'tisu basah ni', 'rak rempah ni', 'tumbler ni', 'alas kaki serap air ni').\n"
        "3. Tulis 1 atau 2 ayat luahan santai bersahaja dalam Bahasa Melayu Malaysia tulen (sekitar 20 hingga 35 patah perkataan sahaja).\n"
        "4. Tulis seperti bercerita santai dengan rakan media sosial tentang betapa senangnya bila ada barang ini untuk urusan rumah.\n\n"
        "Pantangan Ketat:\n"
        "- DILARANG sebut harga atau perkataan 'RM' (harga dipasang oleh kod).\n"
        "- DILARANG letak pautan/URL Shopee di dalam ayat ulasan.\n"
        "- DILARANG guna emoji sama sekali (kod python akan pasang emoji).\n"
        "- DILARANG guna perkataan Indonesia (seperti bisa, banget, nggak, ngak, yuk, bikin, gampang, cobain).\n"
        "- Gunakan frasa Melayu santai harian (contoh: senang betul kerja, jimat masa, tak pening kepala, kemas elok).\n"
        "- Pastikan ayat lengkap dan diakhiri dengan tanda noktah (.).\n"
        "- Terus berikan ayat ulasan tanpa sebarang mukadimah atau tag pemikiran."
    )

    user_prompt = (
        f"Konteks Waktu Siaran: {time_context}\n"
        f"Nama Asal Produk: {clean_name}\n"
        f"Jenama: {brand}\n"
        f"Rujukan Visual (English Mudah): {short_vision}\n\n"
        f"Sila olah luahan santai Threads Mama (ringkaskan tajuk jadi nama panggilan dalam ayat):"
    )

    for model_name in models:
        print(f"\n🧠 [AI THREADS] Mencuba Model: {model_name}...")
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
                res = requests.post(endpoint_url, headers=headers, json=post_payload, timeout=35)
                if res.status_code == 200:
                    raw_text = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_ai_output(raw_text)

                    is_valid, err_msg = validate_threads_text(clean_text)
                    if is_valid:
                        print(f"   ✅ [Model Berjaya: {model_name}] ({len(clean_text)} aksara).")
                        return clean_text
                    else:
                        print(f"   ⚠️ [Kualiti Gagal ({attempt}/2)]: {err_msg}")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:80]}")
            except Exception as e:
                print(f"   ⚠️ [Ralat Model ({attempt}/2)]: {e}")

            time.sleep(2)

    return generate_fallback_threads_story(raw_name)


def assemble_threads_post(payload: Dict[str, Any], story_text: str) -> str:
    """
    Menyusun kapsyen Threads lengkap dengan had keras <= 490 aksara.
    """
    raw_name = payload.get("shopee_product_name", "")
    short_title = clean_shopee_title(raw_name, max_len=30)
    price = float(payload.get("shopee_price", 0.0))
    affiliate_link = payload.get("shopee_affiliate_link", "").strip()

    header = f"✨ {short_title}\n\n"
    footer = (
        f"\n\n💰 Harga: RM{price:.2f}\n"
        f"🛒 Shopee: {affiliate_link}\n\n\n"
        f"#ImpianRumahku #CeritaMama #KemasRumah #RacunShopee"
    )

    fixed_len = len(header) + len(footer)
    max_story_len = MAX_THREADS_HARD_CAP - fixed_len

    if len(story_text) > max_story_len:
        trimmed = story_text[:max_story_len]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        if match:
            story_text = match.group(1).strip()
        else:
            story_text = trimmed.rstrip() + "..."

    return f"{header}{story_text}{footer}".strip()


# ==============================================================================
# 5. DISPATCHER & PENERBITAN THREADS API
# ==============================================================================

def post_to_threads_api(
    user_id: str,
    access_token: str,
    image_url: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menerbitkan hantaran bergambar ke Threads melalui Meta Graph API.
    """
    base_threads_url = f"https://graph.threads.net/v1.0/{user_id}"

    create_url = f"{base_threads_url}/threads"
    create_payload = {
        "media_type": "IMAGE",
        "image_url": image_url,
        "text": caption,
        "access_token": access_token,
    }

    try:
        print("   📦 Mencipta Threads Media Container...")
        c_res = requests.post(create_url, data=create_payload, timeout=30)
        if c_res.status_code != 200:
            return False, {}, f"Gagal cipta container Threads (HTTP {c_res.status_code}): {c_res.text}"

        container_id = c_res.json().get("id")
        print(f"   ✅ Container dicipta (ID: {container_id}). Menunggu pemprosesan imej Meta...")

        status_url = f"https://graph.threads.net/v1.0/{container_id}"
        is_ready = False

        for check_i in range(1, 7):
            time.sleep(3)
            s_res = requests.get(status_url, params={"fields": "status,error_message", "access_token": access_token}, timeout=20)
            if s_res.status_code == 200:
                s_data = s_res.json()
                status = s_data.get("status")
                if status == "FINISHED":
                    is_ready = True
                    break
                elif status == "ERROR":
                    return False, {}, f"Ralat pemprosesan imej Threads: {s_data.get('error_message')}"
            print(f"   ⏳ Semakan status media ({check_i}/6)...")

        if not is_ready:
            print("   ⚠️ Amaran masa tamat status, mencuba terbit terus...")

        publish_url = f"{base_threads_url}/threads_publish"
        pub_payload = {
            "creation_id": container_id,
            "access_token": access_token,
        }

        p_res = requests.post(publish_url, data=pub_payload, timeout=30)
        if p_res.status_code == 200:
            published_id = p_res.json().get("id")
            print(f"   🎉 [THREADS BERJAYA] Hantaran diterbitkan! ID: {published_id}")
            return True, {"platform": "threads", "thread_id": published_id, "char_count": len(caption)}, "Hantaran Threads berjaya!"
        return False, {}, f"Gagal menerbitkan Threads (HTTP {p_res.status_code}): {p_res.text}"

    except Exception as e:
        return False, {}, f"Ralat sambungan Threads API: {e}"


def run_threads_pipeline() -> Tuple[bool, str]:
    """
    Fungsi Pengendali Utama Modul Threads.
    """
    if not INPUT_JSON_FILE.exists():
        return False, f"Fail input {INPUT_JSON_FILE.name} tidak ditemui dalam folder temp/."

    user_id, access_token, auth_err = get_threads_config()
    if auth_err:
        return False, auth_err

    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    local_img = payload.get("local_image_path", "")
    print(f"\n🚀 [THREADS PIPELINE] Memulakan muat naik imej sementara ke Backblaze B2 (Signed Mode)...")
    b2_ok, b2_signed_url, b2_file_id, b2_file_name, b2_api_url, b2_auth_token, b2_err = upload_temp_image_to_b2_signed(local_img)
    if not b2_ok:
        return False, f"Gagal menyediakan Signed URL imej untuk Threads: {b2_err}"

    post_ok = False
    post_msg = ""

    try:
        story_bm = generate_mama_threads_copy(payload)
        final_caption = assemble_threads_post(payload, story_bm)

        print("\n" + "=" * 70)
        print("📝 [PRATONTON HANTARAN THREADS (HAD KERAS <= 490 AKSARA)]")
        print("=" * 70)
        print(final_caption)
        print("-" * 70)
        print(f"📏 Jumlah Aksara: {len(final_caption)} / 500 aksara")
        print("=" * 70)

        print(f"\n📡 Menghantar hantaran ke akaun Threads (User ID: {user_id})...")
        post_ok, post_info, post_msg = post_to_threads_api(
            user_id=user_id,
            access_token=access_token,
            image_url=b2_signed_url,
            caption=final_caption,
        )

    finally:
        print("\n🧹 [CLEANUP] Membersihkan fail imej sementara dari Backblaze B2...")
        delete_ephemeral_image_from_b2(b2_api_url, b2_auth_token, b2_file_id, b2_file_name)

    return post_ok, post_msg


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST & LIVE POST] Menjalankan Enjin Persona Mama untuk Threads...")
    print("=" * 70)
    ok, message = run_threads_pipeline()
    print("=" * 70)