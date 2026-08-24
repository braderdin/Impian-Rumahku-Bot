#!/usr/bin/env python3
"""
Dynamic Configuration & Environment Manager
Impian Rumahku & Cerita Mama Ecosystem
Features:
- 100% Dynamic loading of environment variables (.env.local priority for local WSL, GitHub Secrets for cron)
- STRICT ZERO HARDCODE: All AI models, endpoints, and secrets read purely from environment variables
- Strict alignment with IRCM_* key conventions
- Malaysian Time (MYT / UTC+8) context generator
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
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


def get_myt_time_context() -> Tuple[str, str, str]:
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

    day_moods = {
        "Isnin": "Semangat awal minggu mengemas rumah yang bersih & segar",
        "Selasa": "Rutin praktikal mengurus ruang harian dengan kemas",
        "Rabu": "Idea susun atur ruang tengah minggu yang tenang",
        "Khamis": "Persiapan santai menjelang hujung minggu",
        "Jumaat": "Suasana damai dan rehat bersama keluarga",
        "Sabtu": "Aktiviti dekorasi dan kemas rumah hujung minggu",
        "Ahad": "Ketenangan rumah dan terapi susun atur ruang"
    }

    current_mood = day_moods.get(day_name, "Ketenangan dan praktikaliti hiasan rumah")
    time_context = f"{day_name}, {now.day} {month_name} {now.year}, {now.strftime('%I:%M %p')} (Waktu {period})"
    
    return time_context, period, current_mood


def get_openrouter_config() -> Tuple[Optional[str], Optional[str], Dict[str, str], str]:
    """
    Membaca tetapan OpenRouter API dan pemetaan model mengikut keutamaan
    SECARA MUTLAK daripada persekitaran (.env.local / GitHub Secrets).
    SIFAR MODEL HARDCODE.
    """
    base_url = (
        os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
        or os.getenv("OPENROUTER_BASE_URL", "").strip()
    )
    api_key = (
        os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )

    if not base_url or not api_key:
        return None, None, {}, "Kunci IRCM_OPENROUTER_BASE_URL atau IRCM_OPENROUTER_API_KEY tidak lengkap."

    endpoint_url = base_url if not base_url.endswith("/chat/completions") else base_url.replace("/chat/completions", "")
    
    # Baca 100% daripada ENV tanpa nilai lalai hardcoded
    models = {
        "vision_primary": os.getenv("IRCM_MODEL_VISION", "").strip(),
        "vision_fallback": os.getenv("IRCM_MODEL_VISION_FALLBACK_1", "").strip(),
        "primary": os.getenv("IRCM_MODEL_PRIMARY", "").strip(),
        "fallback_1": os.getenv("IRCM_MODEL_FALLBACK_1", "").strip(),
        "fallback_2": os.getenv("IRCM_MODEL_FALLBACK_2", "").strip(),
        "fallback_3": os.getenv("IRCM_MODEL_FALLBACK_3", "").strip(),
        "fallback_4": os.getenv("IRCM_MODEL_FALLBACK_4", "").strip(),
    }

    return endpoint_url, api_key, models, ""


def get_redis_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan sambungan Upstash Redis REST API."""
    url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not url or not token:
        return None, None, "Kunci IRCM_UPSTASH_REDIS_REST_URL atau IRCM_UPSTASH_REDIS_REST_TOKEN tiada."

    return url.rstrip("/"), token, ""


def get_vector_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan sambungan Upstash Vector REST API."""
    url = os.getenv("IRCM_UPSTASH_VECTOR_REST_URL", "").strip()
    token = os.getenv("IRCM_UPSTASH_VECTOR_REST_TOKEN", "").strip()

    if not url or not token:
        return None, None, "Kunci IRCM_UPSTASH_VECTOR_REST_URL atau IRCM_UPSTASH_VECTOR_REST_TOKEN tiada."

    return url.rstrip("/"), token, ""


def get_pexels_config() -> Tuple[Optional[str], str]:
    """Membaca kunci API Pexels."""
    api_key = os.getenv("IRCM_PEXELS_API_KEY", "").strip()
    if not api_key:
        return None, "Kunci IRCM_PEXELS_API_KEY tidak ditemui."
    return api_key, ""


def get_facebook_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan API Facebook Page."""
    page_id = os.getenv("IRCM_FB_META_PAGE_ID", "").strip()
    page_token = os.getenv("IRCM_FB_META_PAGE_ACCESS_TOKEN", "").strip()

    if not page_id or not page_token:
        return None, None, "Kunci IRCM_FB_META_PAGE_ID atau IRCM_FB_META_PAGE_ACCESS_TOKEN tiada."

    return page_id, page_token, ""


def get_instagram_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan API Instagram Professional Account."""
    account_id = os.getenv("IRCM_INSTAGRAM_ACCOUNT_ID", "").strip()
    access_token = os.getenv("IRCM_INSTAGRAM_ACCESS_TOKEN", "").strip()

    if not account_id or not access_token:
        return None, None, "Kunci IRCM_INSTAGRAM_ACCOUNT_ID atau IRCM_INSTAGRAM_ACCESS_TOKEN tiada."

    return account_id, access_token, ""


def get_threads_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan API Threads (User ID & Fallback Access Token)."""
    user_id = os.getenv("IRCM_THREADS_USER_ID", "").strip()
    fallback_token = os.getenv("IRCM_THREADS_ACCESS_TOKEN", "").strip()

    if not user_id:
        return None, None, "Kunci IRCM_THREADS_USER_ID tidak ditemui."

    return user_id, fallback_token, ""


def get_bluesky_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan autentikasi akaun Bluesky AT-Protocol."""
    handle = os.getenv("IRCM_BLUESKY_HANDLE", "").strip()
    app_pwd = os.getenv("IRCM_BLUESKY_APP_PASSWORD", "").strip()

    if not handle or not app_pwd:
        return None, None, "Kunci IRCM_BLUESKY_HANDLE atau IRCM_BLUESKY_APP_PASSWORD tiada."

    return handle, app_pwd, ""


def get_b2_config() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Membaca konfigurasi Backblaze B2 Storage."""
    key_id = os.getenv("IRCM_B2_KEY_ID", "").strip() or os.getenv("IRCM_B2_ACCOUNT_KEY_ID", "").strip()
    app_key = os.getenv("IRCM_B2_APPLICATION_KEY", "").strip()
    bucket_name = os.getenv("IRCM_B2_BUCKET_NAME", "").strip()
    bucket_id = os.getenv("IRCM_B2_BUCKET_ID", "").strip()

    if not key_id or not app_key or not bucket_name:
        return None, None, None, None, "Kunci konfigurasi Backblaze B2 tidak lengkap."

    return key_id, app_key, bucket_name, bucket_id, ""


def get_telegram_config() -> Tuple[Optional[str], Optional[str], str]:
    """Membaca tetapan Telegram Bot Audit."""
    bot_token = os.getenv("IRCM_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("IRCM_TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        return None, None, "Kunci IRCM_TELEGRAM_BOT_TOKEN atau IRCM_TELEGRAM_CHAT_ID tiada."

    return bot_token, chat_id, ""