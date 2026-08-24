#!/usr/bin/env python3
"""
Threads Video Publishing Engine (Meta Threads API via B2 Video Hosting)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Reads active access token dynamically from Redis (auth:impianrumahku:threads_token) with .env fallback
- Ingests Backblaze B2 Signed Video URL for direct Meta ingestion
- Strict caption formatting trimmed safely within Threads character limit (<= 490 characters)
- 2-Stage Threads Video Container lifecycle (threads -> status polling -> threads_publish)
- Detailed error reporting and permalink resolution
"""

import sys
import time
import requests
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_threads_config
from src.pexels_redis_db import get_active_threads_token_from_redis

THREADS_BASE_URL = "https://graph.threads.net/v1.0"
MAX_THREADS_CAPTION_CHARS = 490


def smart_trim_threads_caption(text: str, max_chars: int = MAX_THREADS_CAPTION_CHARS) -> str:
    """
    Memotong kapsyen secara kemas pada tanda noktah terakhir di bawah had ketat 500 aksara Threads.
    """
    if not text or len(text) <= max_chars:
        return text

    trimmed = text[:max_chars]
    last_punc = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))

    if last_punc != -1 and last_punc > 80:
        return trimmed[: last_punc + 1].strip()

    last_space = trimmed.rfind(" ")
    if last_space != -1:
        return trimmed[:last_space].strip() + "..."

    return trimmed[: max_chars - 3] + "..."


def _wait_for_threads_video_encoding(
    container_id: str,
    access_token: str,
    timeout_seconds: int = 120
) -> Tuple[bool, str]:
    """
    Menyemak status pemprosesan video container Threads secara berkala sehingga FINISHED.
    """
    status_url = f"{THREADS_BASE_URL}/{container_id}"
    params = {"fields": "status,error_message", "access_token": access_token}
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        time.sleep(6)
        try:
            res = requests.get(status_url, params=params, timeout=15)
            if res.status_code == 200:
                res_data = res.json()
                status = res_data.get("status", "")
                if status in ["FINISHED", "PUBLISHED"]:
                    return True, "FINISHED"
                elif status in ["ERROR", "EXPIRED"]:
                    return False, f"Status pemprosesan Threads: {status} ({res_data.get('error_message', '')})"
            print(f"   ⏳ [THREADS ENCODING WAIT] Menunggu pemprosesan video Threads ({int(time.time() - start_time)}s)...")
        except Exception:
            pass

    return True, "TIMEOUT_ASSUME_READY"


def post_video_to_threads(
    video_url: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menerbitkan video ke Threads API menggunakan pautan video (cth: Backblaze B2 Signed URL).
    Memulangkan: (success, result_dict, message)
    """
    user_id, fallback_token, cfg_err = get_threads_config()
    if cfg_err or not user_id:
        return False, {}, cfg_err or "Kunci IRCM_THREADS_USER_ID tidak ditemui."

    # Utamakan token aktif terkini daripada Upstash Redis
    active_token = get_active_threads_token_from_redis() or fallback_token
    if not active_token:
        return False, {}, "Kunci Threads Access Token tidak ditemui dalam Redis mahupun persekitaran."

    if not video_url or not video_url.startswith("http"):
        return False, {}, "URL video tidak sah untuk penerbitan Threads."

    clean_caption = smart_trim_threads_caption(caption, max_chars=MAX_THREADS_CAPTION_CHARS)
    print(f"\n🧵 [THREADS DISPATCHER] Memulakan hantaran ke Threads User ID: {user_id}...")

    try:
        # ---------------------------------------------------------------------
        # LANGKAH 1: Cipta Threads Media Container (media_type: VIDEO)
        # ---------------------------------------------------------------------
        print("   📦 [THREADS STEP 1] Mencipta Threads Media Container...")
        create_url = f"{THREADS_BASE_URL}/{user_id}/threads"
        create_payload = {
            "media_type": "VIDEO",
            "video_url": video_url,
            "text": clean_caption,
            "access_token": active_token,
        }

        res_create = requests.post(create_url, data=create_payload, timeout=35)
        create_json = res_create.json()

        if res_create.status_code != 200 or "id" not in create_json:
            err_msg = create_json.get("error", {}).get("message", res_create.text)
            print(f"   ❌ [THREADS STEP 1 FAILED] {err_msg}")
            return False, {"step": 1, "error": err_msg}, f"Gagal cipta container Threads: {err_msg}"

        container_id = create_json.get("id")
        print(f"   ✅ [THREADS STEP 1 SUCCESS] Container ID: {container_id}")

        # ---------------------------------------------------------------------
        # LANGKAH 2: Tunggu Status Selesai Diproses (Status Polling)
        # ---------------------------------------------------------------------
        print("   ⏳ [THREADS STEP 2] Menunggu status pemprosesan video Threads...")
        ready_ok, status_msg = _wait_for_threads_video_encoding(container_id, active_token, timeout_seconds=120)
        if not ready_ok:
            print(f"   ❌ [THREADS STEP 2 FAILED] {status_msg}")
            return False, {"step": 2, "error": status_msg}, status_msg

        # ---------------------------------------------------------------------
        # LANGKAH 3: Terbitkan Hantaran Video (threads_publish)
        # ---------------------------------------------------------------------
        print("   🚀 [THREADS STEP 3] Menerbitkan hantaran video ke Threads Feed...")
        pub_url = f"{THREADS_BASE_URL}/{user_id}/threads_publish"
        pub_payload = {
            "creation_id": container_id,
            "access_token": active_token,
        }

        res_pub = requests.post(pub_url, data=pub_payload, timeout=35)
        pub_json = res_pub.json()

        if res_pub.status_code == 200 and "id" in pub_json:
            thread_id = pub_json.get("id")
            permalink = f"https://www.threads.net/post/{thread_id}"
            print(f"   🎉 [THREADS SUCCESS] Video Threads berjaya diterbitkan! Pautan: {permalink}")
            result_data = {
                "platform": "threads",
                "thread_id": thread_id,
                "permalink": permalink,
                "char_count": len(clean_caption)
            }
            return True, result_data, "Threads Video berjaya disiarkan!"
        else:
            err_msg = pub_json.get("error", {}).get("message", res_pub.text)
            print(f"   ❌ [THREADS STEP 3 FAILED] {err_msg}")
            return False, {"step": 3, "error": err_msg}, f"Gagal menerbitkan Threads: {err_msg}"

    except Exception as e:
        print(f"   ❌ [THREADS DISPATCHER EXCEPTION]: {e}")
        return False, {}, f"Ralat Threads Dispatcher: {str(e)}"