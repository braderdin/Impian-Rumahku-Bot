#!/usr/bin/env python3
"""
Instagram Reels Video Publishing Engine (Meta Graph API)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Ingests Backblaze B2 Signed Video URL (Direct video streaming container creation)
- 2-Stage Instagram Reels Container Lifecycle (media -> status polling -> media_publish)
- Async video encoding status verification loop (checks for FINISHED/PUBLISHED state)
- Automatic permalink and media ID extraction
- Dynamic credentials loading via src/pexels_config.py
"""

import sys
import time
import requests
from pathlib import Path
from typing import Dict, Any, Tuple

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_instagram_config

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def _wait_for_instagram_video_encoding(
    container_id: str,
    access_token: str,
    timeout_seconds: int = 90
) -> Tuple[bool, str]:
    """
    Menyemak status pemprosesan media container Instagram secara berkala sehingga FINISHED.
    """
    status_url = f"{GRAPH_BASE_URL}/{container_id}"
    params = {"fields": "status_code,status", "access_token": access_token}
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        time.sleep(5)
        try:
            res = requests.get(status_url, params=params, timeout=15)
            if res.status_code == 200:
                res_data = res.json()
                status_code = res_data.get("status_code", "")
                if status_code in ["FINISHED", "PUBLISHED"]:
                    return True, "FINISHED"
                elif status_code in ["ERROR", "EXPIRED"]:
                    return False, f"Pemprosesan video Instagram gagal: {status_code} ({res_data.get('status', '')})"
            print(f"   ⏳ [IG ENCODING WAIT] Menunggu pemprosesan video Meta ({int(time.time() - start_time)}s)...")
        except Exception:
            pass

    return True, "TIMEOUT_ASSUME_READY"


def _get_instagram_media_permalink(media_id: str, access_token: str) -> str:
    """
    Mendapatkan pautan permalink rasmi hantaran Reel Instagram yang telah diterbitkan.
    """
    url = f"{GRAPH_BASE_URL}/{media_id}"
    params = {"fields": "permalink", "access_token": access_token}
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json().get("permalink", f"https://www.instagram.com/reel/{media_id}/")
    except Exception:
        pass
    return f"https://www.instagram.com/reel/{media_id}/"


def post_reel_to_instagram(
    video_url: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menerbitkan video ke Instagram Reels menggunakan pautan video (cth: Backblaze B2 Signed URL).
    Memulangkan: (success, result_dict, message)
    """
    account_id, access_token, cfg_err = get_instagram_config()
    if cfg_err or not account_id or not access_token:
        return False, {}, cfg_err or "Konfigurasi akaun Instagram Professional tidak lengkap."

    if not video_url or not video_url.startswith("http"):
        return False, {}, "URL video tidak sah untuk penerbitan Instagram."

    print(f"\n📸 [IG REELS DISPATCHER] Memulakan hantaran ke Instagram Account ID: {account_id}...")

    try:
        # ---------------------------------------------------------------------
        # LANGKAH 1: Cipta Media Container Reels
        # ---------------------------------------------------------------------
        print("   📦 [IG REEL STEP 1] Mencipta Media Container Reels di Meta Graph API...")
        create_url = f"{GRAPH_BASE_URL}/{account_id}/media"
        create_payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token,
        }

        res_create = requests.post(create_url, data=create_payload, timeout=35)
        create_json = res_create.json()

        if res_create.status_code != 200 or "id" not in create_json:
            err_msg = create_json.get("error", {}).get("message", res_create.text)
            print(f"   ❌ [IG REEL STEP 1 FAILED] {err_msg}")
            return False, {"step": 1, "error": err_msg}, f"Gagal cipta container IG: {err_msg}"

        container_id = create_json.get("id")
        print(f"   ✅ [IG REEL STEP 1 SUCCESS] Container ID: {container_id}")

        # ---------------------------------------------------------------------
        # LANGKAH 2: Tunggu Status Selesai Diproses (Status Polling)
        # ---------------------------------------------------------------------
        print("   ⏳ [IG REEL STEP 2] Menunggu status penukaran kod (transcoding) video Meta...")
        ready_ok, status_msg = _wait_for_instagram_video_encoding(container_id, access_token, timeout_seconds=90)
        if not ready_ok:
            print(f"   ❌ [IG REEL STEP 2 FAILED] {status_msg}")
            return False, {"step": 2, "error": status_msg}, status_msg

        # ---------------------------------------------------------------------
        # LANGKAH 3: Terbitkan Reel (media_publish)
        # ---------------------------------------------------------------------
        print("   🚀 [IG REEL STEP 3] Menerbitkan Instagram Reel...")
        pub_url = f"{GRAPH_BASE_URL}/{account_id}/media_publish"
        pub_payload = {
            "creation_id": container_id,
            "access_token": access_token,
        }

        res_pub = requests.post(pub_url, data=pub_payload, timeout=35)
        pub_json = res_pub.json()

        if res_pub.status_code == 200 and "id" in pub_json:
            media_id = pub_json.get("id")
            permalink = _get_instagram_media_permalink(media_id, access_token)
            print(f"   🎉 [IG REEL SUCCESS] Instagram Reel berjaya diterbitkan! Pautan: {permalink}")
            result_data = {
                "platform": "instagram",
                "media_id": media_id,
                "permalink": permalink,
                "char_count": len(caption)
            }
            return True, result_data, "Instagram Reel berjaya disiarkan!"
        else:
            err_msg = pub_json.get("error", {}).get("message", res_pub.text)
            print(f"   ❌ [IG REEL STEP 3 FAILED] {err_msg}")
            return False, {"step": 3, "error": err_msg}, f"Gagal menerbitkan IG Reel: {err_msg}"

    except Exception as e:
        print(f"   ❌ [IG DISPATCHER EXCEPTION]: {e}")
        return False, {}, f"Ralat Instagram Dispatcher: {str(e)}"