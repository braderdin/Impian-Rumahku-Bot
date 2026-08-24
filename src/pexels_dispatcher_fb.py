#!/usr/bin/env python3
"""
Facebook Reels Video Publishing Engine (Meta Graph API)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- 3-Phase Meta Video Reels Upload Protocol (Start -> Binary Rupload -> Finish/Publish)
- Automatic fallback to Facebook Page Feed Video if Reels upload hits API limitations
- Reads IRCM_FB_META_* configuration dynamically from src/pexels_config.py
- Returns detailed diagnostics and post identifiers
"""

import os
import sys
import requests
from pathlib import Path
from typing import Dict, Any, Tuple

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_facebook_config

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
GRAPH_VIDEO_BASE_URL = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}"


def upload_video_to_facebook_feed_fallback(
    page_id: str,
    page_token: str,
    video_path: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Fallback: Memuat naik video terus ke Facebook Page Feed sekiranya FB Reels dihadkan atau gagal.
    """
    if not page_id or not page_token or not os.path.exists(video_path):
        return False, {}, "Parameter tidak sah atau fail video tidak ditemui."

    url = f"{GRAPH_VIDEO_BASE_URL}/{page_id}/videos"
    payload = {
        "description": caption,
        "access_token": page_token,
    }

    try:
        with open(video_path, "rb") as vf:
            files = {"source": (os.path.basename(video_path), vf, "video/mp4")}
            res = requests.post(url, data=payload, files=files, timeout=90)

        data = res.json()
        if res.status_code in [200, 201] and "id" in data:
            post_id = data.get("id")
            permalink = f"https://www.facebook.com/{post_id}"
            print(f"   🎉 [FB FEED FALLBACK SUCCESS] Video berjaya dipos ke Facebook Feed! (ID: {post_id})")
            return True, {"platform": "facebook", "post_id": post_id, "permalink": permalink, "type": "feed_fallback"}, "Hantaran FB Feed berjaya disiarkan!"
        else:
            err_msg = data.get("error", {}).get("message", res.text)
            return False, {"error": err_msg}, f"Gagal muat naik ke FB Feed: {err_msg}"
    except Exception as e:
        return False, {}, f"Ralat sambungan FB Feed: {str(e)}"


def post_reel_to_facebook(
    video_path: str,
    caption: str,
    enable_feed_fallback: bool = True
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menerbitkan video MP4 ke Facebook Reels melalui 3 fasa Meta Graph API.
    Memulangkan: (success, result_dict, message)
    """
    page_id, page_token, cfg_err = get_facebook_config()
    if cfg_err or not page_id or not page_token:
        return False, {}, cfg_err or "Konfigurasi Facebook Page tidak lengkap."

    if not os.path.exists(video_path):
        return False, {}, f"Fail video tidak dijumpai: {video_path}"

    file_size = os.path.getsize(video_path)
    start_url = f"{GRAPH_BASE_URL}/{page_id}/video_reels"

    print(f"\n🚀 [FB REELS DISPATCHER] Memulakan sesi hantaran ke FB Page ID: {page_id}...")

    try:
        # ---------------------------------------------------------------------
        # FASA 1: Mulakan Sesi Muat Naik (Upload Phase: start)
        # ---------------------------------------------------------------------
        print("   🎬 [FB REEL STEP 1] Meminta sesi muat naik Reel daripada Meta...")
        res_start = requests.post(
            start_url,
            data={"upload_phase": "start", "access_token": page_token},
            timeout=30,
        )
        start_json = res_start.json()
        if res_start.status_code != 200 or "video_id" not in start_json:
            err_msg = start_json.get("error", {}).get("message", res_start.text)
            print(f"   ⚠️ [FB REEL STEP 1 FAILED] {err_msg}")

            if enable_feed_fallback:
                print("   🔄 [FALLBACK AKTIF] Beralih ke muat naik standard Facebook Page Feed...")
                return upload_video_to_facebook_feed_fallback(page_id, page_token, video_path, caption)
            return False, {"step": 1, "error": err_msg}, f"Gagal sesi FB Reel: {err_msg}"

        video_id = start_json.get("video_id")
        upload_url = start_json.get("upload_url")
        print(f"   ✅ [FB REEL STEP 1 SUCCESS] Video ID Sesi: {video_id}")

        # ---------------------------------------------------------------------
        # FASA 2: Muat Naik Binary Video (Rupload Server)
        # ---------------------------------------------------------------------
        print("   🎬 [FB REEL STEP 2] Memuat naik Binary Video MP4 ke Meta Server...")
        with open(video_path, "rb") as vf:
            video_bytes = vf.read()

        upload_headers = {
            "Authorization": f"OAuth {page_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream",
        }

        res_upload = requests.post(upload_url, headers=upload_headers, data=video_bytes, timeout=120)
        if res_upload.status_code != 200:
            err_msg = f"HTTP {res_upload.status_code}: {res_upload.text[:80]}"
            print(f"   ⚠️ [FB REEL STEP 2 FAILED] {err_msg}")

            if enable_feed_fallback:
                print("   🔄 [FALLBACK AKTIF] Beralih ke muat naik standard Facebook Page Feed...")
                return upload_video_to_facebook_feed_fallback(page_id, page_token, video_path, caption)
            return False, {"step": 2, "error": err_msg}, f"Gagal muat naik binary FB Reel: {err_msg}"

        print("   ✅ [FB REEL STEP 2 SUCCESS] Muat naik binary selesai!")

        # ---------------------------------------------------------------------
        # FASA 3: Terbitkan Reel (Upload Phase: finish)
        # ---------------------------------------------------------------------
        print("   🎬 [FB REEL STEP 3] Menerbitkan video ke Facebook Reels...")
        finish_payload = {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
            "access_token": page_token,
        }

        res_finish = requests.post(start_url, data=finish_payload, timeout=30)
        finish_json = res_finish.json()

        if res_finish.status_code == 200 and finish_json.get("success", False):
            permalink = f"https://www.facebook.com/reel/{video_id}"
            print(f"   🎉 [FB REEL SUCCESS] Facebook Reel berjaya diterbitkan! (ID: {video_id})")
            result_data = {
                "platform": "facebook",
                "post_id": video_id,
                "permalink": permalink,
                "type": "reel",
                "char_count": len(caption)
            }
            return True, result_data, "Facebook Reel berjaya disiarkan!"
        else:
            err_msg = finish_json.get("error", {}).get("message", res_finish.text)
            print(f"   ⚠️ [FB REEL STEP 3 FAILED] {err_msg}")

            if enable_feed_fallback:
                print("   🔄 [FALLBACK AKTIF] Beralih ke muat naik standard Facebook Page Feed...")
                return upload_video_to_facebook_feed_fallback(page_id, page_token, video_path, caption)
            return False, {"step": 3, "error": err_msg}, f"Gagal menerbitkan FB Reel: {err_msg}"

    except Exception as e:
        print(f"   ❌ [FB DISPATCHER EXCEPTION]: {e}")
        if enable_feed_fallback:
            print("   🔄 [FALLBACK AKTIF] Mencuba muat naik fallback ke FB Feed...")
            return upload_video_to_facebook_feed_fallback(page_id, page_token, video_path, caption)
        return False, {}, f"Ralat Facebook Dispatcher: {str(e)}"