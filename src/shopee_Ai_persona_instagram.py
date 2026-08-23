#!/usr/bin/env python3
"""
Shopee AI Persona Instagram Generator & Auto-Poster
Impian Rumahku Ecosystem (Step 3 & 4 Instagram Pipeline)
Features:
- Reads temp/shopee_vision_ocr.json
- Generates warm Malaysian homemaker ("Mama") copywriting (400 - 700 chars total)
- Includes home decor / organizing hashtags and locked Shopee link
- Private Ephemeral B2 Hosting: Uploads image -> Generates Signed URL (600s) -> Posts -> Deletes from B2
- 2-Stage Instagram Graph API Container Creation & Publishing
- AI Cascading: Primary (2x) -> Fallback 1 (2x) -> Fallback 2 (2x) -> Rule-based fallback
- 100% Code-Locked Affiliate Link and Product Price
"""

import os
import re
import sys
import time
import json
import hashlib
import urllib.parse
import requests
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
GRAPH_API_VERSION = "v21.0"


# ==============================================================================
# 1. KONFIGURASI INSTAGRAM & B2 STORAGE
# ==============================================================================

def get_instagram_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca tetapan API Instagram Professional Account daripada persekitaran.
    """
    account_id = (
        os.getenv("IRCM_INSTAGRAM_ACCOUNT_ID", "").strip()
        or os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
    )
    access_token = (
        os.getenv("IRCM_INSTAGRAM_ACCESS_TOKEN", "").strip()
        or os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    )

    if not account_id or not access_token:
        return None, None, "Kunci IRCM_INSTAGRAM_ACCOUNT_ID atau IRCM_INSTAGRAM_ACCESS_TOKEN tidak lengkap."

    return account_id, access_token, ""


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
    Membaca tetapan OpenRouter dan senarai model mengikut hierarki.
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
# 2. PENGHOSAN EFEMERAL BACKBLAZE B2 PRIVATE (SIGNED URL & AUTO-DELETE)
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
    Memuat naik fail gambar tempatan ke Private B2 Bucket dan menjana Signed Download URL (600s).
    """
    if not image_path or not os.path.exists(image_path):
        return False, "", "", "", "", "", "Fail imej fizikal tidak wujud untuk dimuat naik ke B2."

    key_id, app_key, bucket_name, bucket_id, cfg_err = get_b2_config()
    if cfg_err:
        return False, "", "", "", "", "", cfg_err

    # 1. Authorize
    auth_ok, api_url, auth_token, download_url, auth_err = b2_authorize(key_id, app_key)
    if not auth_ok:
        return False, "", "", "", "", "", auth_err

    # Bucket ID fallback
    if not bucket_id:
        list_b_url = f"{api_url}/b2api/v2/b2_list_buckets"
        b_res = requests.post(list_b_url, json={"accountId": key_id}, headers={"Authorization": auth_token}, timeout=20)
        if b_res.status_code == 200:
            for b in b_res.json().get("buckets", []):
                if b.get("bucketName") == bucket_name:
                    bucket_id = b.get("bucketId")
                    break

    # 2. Get Upload URL
    get_up_url = f"{api_url}/b2api/v2/b2_get_upload_url"
    up_res = requests.post(get_up_url, json={"bucketId": bucket_id}, headers={"Authorization": auth_token}, timeout=20)
    if up_res.status_code != 200:
        return False, "", "", "", "", "", f"Gagal mendapatkan B2 Upload URL: {up_res.text}"

    up_data = up_res.json()
    upload_url = up_data.get("uploadUrl")
    upload_auth = up_data.get("authorizationToken")

    # 3. Upload Binary
    file_name = f"ig_ephemeral_{int(time.time())}_{os.path.basename(image_path)}"
    encoded_file_name = urllib.parse.quote(file_name)

    with open(image_path, "rb") as f:
        file_bytes = f.read()

    headers = {
        "Authorization": upload_auth,
        "X-Bz-File-Name": encoded_file_name,
        "Content-Type": "image/jpeg",
        "X-Bz-Content-Sha1": hashlib.sha1(file_bytes).hexdigest(),
        "Content-Length": str(len(file_bytes)),
    }

    try:
        upload_post = requests.post(upload_url, data=file_bytes, headers=headers, timeout=40)
        if upload_post.status_code != 200:
            return False, "", "", "", "", "", f"Gagal upload ke B2 (HTTP {upload_post.status_code}): {upload_post.text}"

        file_id = upload_post.json().get("fileId")

        # 4. Jana Signed Token (600 saat)
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
            print(f"   ☁️ [B2 SIGNED URL GENERATED] Sah selama 10 minit untuk Meta Instagram.")
            return True, signed_url, file_id, file_name, api_url, auth_token, ""
        else:
            return False, "", "", "", "", "", f"Gagal menjana B2 Signed Token: {down_res.text}"

    except Exception as e:
        return False, "", "", "", "", "", f"Ralat muat naik B2: {e}"


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
# 3. PENJANAAN AYAT PERSONA MAMA (INSTAGRAM: 400 - 700 AKSARA TOTAL)
# ==============================================================================

def clean_shopee_title(title: str, max_len: int = 40) -> str:
    """Memotong tajuk pendek mengikut sempadan perkataan penuh."""
    if not title:
        return "Barang Rumah Praktikal"
    cleaned = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", "", title)
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
    """Membersihkan tag pemikiran dan membuang emoji AI."""
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


def validate_instagram_text(text: str) -> Tuple[bool, str]:
    """Menyemak kualiti teks ulasan Instagram (150 hingga 320 aksara)."""
    if not text or len(text) < 120:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima 120)."
    if len(text) > 350:
        return False, f"Teks terlalu panjang ({len(text)} aksara, maksima 350)."

    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan simbol atau aksara tidak sah."

    return True, ""


def generate_fallback_instagram_story(product_name: str, brand: str) -> str:
    """Teks sandaran asas khas Instagram jika AI gagal."""
    clean_name = clean_shopee_title(product_name, max_len=30)
    return (
        f"Mama nak kongsi satu lagi penemuan berguna untuk deko dan kemaskan rumah kita. "
        f"{clean_name} daripada {brand} ni memang praktikal, senang nak simpan dan memudahkan rutin harian suri rumah."
    )


def generate_mama_instagram_copy(payload: Dict[str, Any]) -> str:
    """
    Menjana penceritaan santai Bahasa Melayu khas untuk Instagram Feed (180-280 aksara).
    """
    raw_name = payload.get("shopee_product_name", "")
    clean_name = clean_shopee_title(raw_name, max_len=30)
    brand = payload.get("shopee_brand", "Shopee Preferred")
    vision_en = payload.get("mama_english_review", "") or payload.get("visual_analysis_en", {}).get("summary_text", "")
    short_vision = vision_en[:200]

    endpoint_url, api_key, models, cfg_err = get_openrouter_config()
    if cfg_err or not models:
        return generate_fallback_instagram_story(raw_name, brand)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "Anda adalah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang mesra dan suka berkongsi idea hiasan/kemas rumah.\n"
        "Tugasan: Tulis 2 ayat ulasan santai bersahaja dalam BAHASA MELAYU MALAYSIA TULEN.\n\n"
        "PANDUAN PENTING:\n"
        "1. Gunakan nada perbualan mesra suri rumah ('Mama suka betul...', 'Kemas dan senang sangat...', 'Bila guna ni...').\n"
        "2. JANGAN guna terjemahan kaku seperti 'Saya melihat...' atau perkataan Indonesia.\n"
        "3. Panjang teks cerita WAJIB di antara 150 hingga 250 aksara.\n"
        "4. JANGAN sebut harga/'RM', JANGAN letak link/URL, JANGAN guna emoji.\n"
        "5. Pastikan ayat lengkap bernoktah (.)."
    )

    user_prompt = f"Produk: {clean_name} ({brand})\nRujukan Visual: {short_vision}\nAyat ulasan santai Mama:"

    for model_name in models:
        print(f"\n🧠 [AI INSTAGRAM] Mencuba Model: {model_name}...")
        for attempt in range(1, 3):
            try:
                post_payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                res = requests.post(endpoint_url, headers=headers, json=post_payload, timeout=35)
                if res.status_code == 200:
                    raw_text = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean_text = clean_ai_output(raw_text)

                    is_valid, err_msg = validate_instagram_text(clean_text)
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

    return generate_fallback_instagram_story(raw_name, brand)


def assemble_instagram_post(payload: Dict[str, Any], story_text: str) -> str:
    """
    Menyusun kapsyen Instagram Feed lengkap (400 - 700 aksara) dengan susun atur kemas.
    """
    raw_name = payload.get("shopee_product_name", "")
    short_title = clean_shopee_title(raw_name, max_len=35)
    price = float(payload.get("shopee_price", 0.0))
    affiliate_link = payload.get("shopee_affiliate_link", "").strip()

    header = f"✨ {short_title}\n\n"
    body = f"{story_text}\n\n"
    price_and_link = (
        f"💰 Harga: RM{price:.2f}\n"
        f"🛒 Link Shopee: {affiliate_link}\n\n"
    )
    hashtags = (
        "#ImpianRumahku #CeritaMama #KemasRumah #DekoRumah #DekoDapur "
        "#RacunShopee #TipsSuriRumah #HomeDecorMalaysia"
    )

    full_caption = f"{header}{body}{price_and_link}{hashtags}".strip()

    # Kawalan Had Maksimum 700 Aksara
    if len(full_caption) > 700:
        fixed_len = len(header) + len(price_and_link) + len(hashtags)
        available_story = 690 - fixed_len
        if len(story_text) > available_story:
            trimmed = story_text[:available_story]
            match = re.search(r"^([\s\S]*[.!?])", trimmed)
            story_text = match.group(1).strip() if match else trimmed.rstrip() + "..."
            full_caption = f"{header}{story_text}\n\n{price_and_link}{hashtags}".strip()

    return full_caption


# ==============================================================================
# 4. DISPATCHER & PENERBITAN INSTAGRAM FEED
# ==============================================================================

def post_to_instagram_feed(
    account_id: str,
    access_token: str,
    image_url: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menerbitkan hantaran bergambar ke Instagram Feed (Meta Graph API):
    1. Cipta Media Container (image_url & caption)
    2. Semak status kesediaan kontena
    3. Terbitkan Media Container ke Instagram Feed
    """
    base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{account_id}"

    # 1. Cipta Media Container
    create_url = f"{base_url}/media"
    create_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }

    try:
        print("   📦 Mencipta Instagram Media Container...")
        c_res = requests.post(create_url, data=create_payload, timeout=30)
        if c_res.status_code != 200:
            return False, {}, f"Gagal cipta container Instagram (HTTP {c_res.status_code}): {c_res.text}"

        container_id = c_res.json().get("id")
        print(f"   ✅ Container dicipta (ID: {container_id}). Menunggu pemprosesan imej Meta...")

        # 2. Polling Status Kesediaan (Maksimum 5 percubaan, sela 3 saat)
        status_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{container_id}"
        is_ready = False

        for check_i in range(1, 6):
            time.sleep(3)
            s_res = requests.get(status_url, params={"fields": "status_code", "access_token": access_token}, timeout=20)
            if s_res.status_code == 200:
                status_code = s_res.json().get("status_code")
                if status_code in ["FINISHED", "PUBLISHED"]:
                    is_ready = True
                    break
                elif status_code == "ERROR":
                    return False, {}, f"Ralat pemprosesan imej Instagram: {s_res.text}"
            print(f"   ⏳ Semakan status media ({check_i}/5)...")

        if not is_ready:
            print("   ⚠️ Status belum selesai penuh, mencuba terbit terus...")

        # 3. Terbitkan Kontena ke Feed
        publish_url = f"{base_url}/media_publish"
        pub_payload = {
            "creation_id": container_id,
            "access_token": access_token,
        }

        p_res = requests.post(publish_url, data=pub_payload, timeout=30)
        if p_res.status_code == 200:
            published_id = p_res.json().get("id")
            print(f"   🎉 [INSTAGRAM BERJAYA] Hantaran diterbitkan! ID: {published_id}")
            return True, {"platform": "instagram", "media_id": published_id, "char_count": len(caption)}, "Hantaran Instagram berjaya!"
        return False, {}, f"Gagal menerbitkan Instagram (HTTP {p_res.status_code}): {p_res.text}"

    except Exception as e:
        return False, {}, f"Ralat sambungan Instagram API: {e}"


def run_instagram_pipeline() -> Tuple[bool, str]:
    """
    Fungsi Pengendali Utama Modul Instagram:
    1. Membaca temp/shopee_vision_ocr.json
    2. Upload imej ke Backblaze B2 (Private Signed URL 600s)
    3. Jana penceritaan santai Mama & susun kapsyen (400 - 700 aksara)
    4. Pos ke Instagram Feed API
    5. Padam imej daripada B2 Storage serta-merta
    """
    if not INPUT_JSON_FILE.exists():
        return False, f"Fail input {INPUT_JSON_FILE.name} tidak ditemui dalam folder temp/."

    account_id, access_token, auth_err = get_instagram_config()
    if auth_err:
        return False, auth_err

    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # 1. Pengehosan Imej ke Backblaze B2 (Signed URL)
    local_img = payload.get("local_image_path", "")
    print(f"\n🚀 [INSTAGRAM PIPELINE] Memulakan muat naik imej ke Backblaze B2 (Signed Mode)...")
    b2_ok, b2_signed_url, b2_file_id, b2_file_name, b2_api_url, b2_auth_token, b2_err = upload_temp_image_to_b2_signed(local_img)
    if not b2_ok:
        return False, f"Gagal menyediakan Signed URL imej untuk Instagram: {b2_err}"

    post_ok = False
    post_msg = ""

    try:
        # 2. Bina Ayat Persona Mama
        story_bm = generate_mama_instagram_copy(payload)
        final_caption = assemble_instagram_post(payload, story_bm)

        print("\n" + "=" * 70)
        print("📝 [PRATONTON HANTARAN INSTAGRAM FEED (400 - 700 AKSARA)]")
        print("=" * 70)
        print(final_caption)
        print("-" * 70)
        print(f"📏 Jumlah Aksara: {len(final_caption)} / 700 aksara")
        print("=" * 70)

        # 3. Terbitkan ke Instagram Feed
        print(f"\n📡 Menghantar hantaran ke akaun Instagram (Account ID: {account_id})...")
        post_ok, post_info, post_msg = post_to_instagram_feed(
            account_id=account_id,
            access_token=access_token,
            image_url=b2_signed_url,
            caption=final_caption,
        )

    finally:
        # 4. Pembersihan Ephemeral: Padam fail dari B2 Storage
        print("\n🧹 [CLEANUP] Membersihkan fail imej sementara dari Backblaze B2...")
        delete_ephemeral_image_from_b2(b2_api_url, b2_auth_token, b2_file_id, b2_file_name)

    return post_ok, post_msg


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST & LIVE POST] Menjalankan Enjin Persona Mama untuk Instagram...")
    print("=" * 70)
    ok, message = run_instagram_pipeline()
    print("=" * 70)