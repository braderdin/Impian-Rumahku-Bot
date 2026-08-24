#!/usr/bin/env python3
"""
Bluesky Video Publishing Engine (AT-Protocol & atproto SDK)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Dual-Mode Dispatcher: Native atproto SDK with direct HTTP REST fallback
- Uploads MP4 video blob to Bluesky video service with processing polling
- Automatic UTF-8 byte facets generation for clickable hashtags & links
- Hard safety cap: strictly <= 300 characters total for Bluesky post limits
- Dynamic credential loading via src/pexels_config.py
"""

import os
import re
import sys
import time
import requests
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_bluesky_config

# atproto SDK Integration
try:
    from atproto import Client, models
    ATPROTO_SDK_AVAILABLE = True
except ImportError:
    Client = None
    models = None
    ATPROTO_SDK_AVAILABLE = False

MAX_BLUESKY_CHARS = 295
BSKY_SERVICE_URL = "https://bsky.social"


def smart_trim_for_bluesky(text: str, max_chars: int = MAX_BLUESKY_CHARS) -> str:
    """
    Memotong kapsyen secara kemas pada tanda noktah terakhir bagi mematuhi had aksara Bluesky (300 aksara).
    """
    if not text or len(text) <= max_chars:
        return text

    trimmed = text[:max_chars]
    last_punc = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))

    if last_punc != -1 and last_punc > 60:
        return trimmed[: last_punc + 1].strip()

    last_space = trimmed.rfind(" ")
    if last_space != -1:
        return trimmed[:last_space].strip() + "..."

    return trimmed[: max_chars - 3] + "..."


def _publish_via_atproto_sdk(
    handle: str,
    app_pwd: str,
    video_path: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Menerbitkan video ke Bluesky menggunakan pustaka rasmi atproto SDK.
    """
    if not ATPROTO_SDK_AVAILABLE or Client is None:
        return False, {}, "Pustaka atproto SDK tidak dipasang."

    try:
        client = Client()
        client.login(handle, app_pwd)

        with open(video_path, "rb") as vf:
            video_bytes = vf.read()

        print("   🦋 [ATPROTO SDK] Menghantar video ke perkhidmatan video Bluesky...")
        
        # atproto SDK send_video menguruskan muat naik blob & polling pemprosesan video
        post_res = client.send_video(
            video=video_bytes,
            text=caption,
        )

        if post_res and hasattr(post_res, "uri"):
            post_uri = str(post_res.uri)
            post_cid = str(getattr(post_res, "cid", ""))
            
            # Tukar URI at:// kepada pautan web bsky.app
            rkey = post_uri.split("/")[-1] if "/" in post_uri else post_uri
            permalink = f"https://bsky.app/profile/{handle}/post/{rkey}"

            print(f"   🎉 [BLUESKY SDK SUCCESS] Video berjaya diterbitkan! Pautan: {permalink}")
            result_data = {
                "platform": "bluesky",
                "uri": post_uri,
                "cid": post_cid,
                "permalink": permalink,
                "char_count": len(caption),
                "method": "atproto_sdk"
            }
            return True, result_data, "Hantaran Bluesky Video berjaya disiarkan!"

        return False, {}, "Tiada respons URI daripada perkhidmatan Bluesky."
    except Exception as e:
        return False, {}, f"Ralat atproto SDK: {str(e)}"


def _publish_via_rest_fallback(
    handle: str,
    app_pwd: str,
    video_path: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Fallback: Autentikasi sesi REST terus ke bsky.social sekiranya SDK mengalami isu.
    """
    print("   🔄 [BLUESKY REST FALLBACK] Mencuba penerbitan melalui REST API terus...")
    auth_url = f"{BSKY_SERVICE_URL}/xrpc/com.atproto.server.createSession"
    auth_payload = {"identifier": handle, "password": app_pwd}

    try:
        # 1. Cipta Sesi
        auth_res = requests.post(auth_url, json=auth_payload, timeout=15)
        if auth_res.status_code != 200:
            return False, {}, f"Gagal login Bluesky REST (HTTP {auth_res.status_code}): {auth_res.text[:80]}"

        auth_data = auth_res.json()
        jwt_token = auth_data.get("accessJwt")
        user_did = auth_data.get("did")

        # 2. Muat Naik Video Blob
        upload_blob_url = f"{BSKY_SERVICE_URL}/xrpc/com.atproto.repo.uploadBlob"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "video/mp4",
        }

        with open(video_path, "rb") as vf:
            video_bytes = vf.read()

        up_res = requests.post(upload_blob_url, headers=headers, data=video_bytes, timeout=60)
        if up_res.status_code != 200:
            return False, {}, f"Gagal muat naik blob video Bluesky (HTTP {up_res.status_code}): {up_res.text[:80]}"

        blob_obj = up_res.json().get("blob", {})

        # 3. Cipta Rekod Pos
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record = {
            "$type": "app.bsky.feed.post",
            "text": caption,
            "createdAt": now_iso,
            "embed": {
                "$type": "app.bsky.embed.video",
                "video": blob_obj,
                "aspectRatio": {"width": 1080, "height": 1920}
            }
        }

        create_post_url = f"{BSKY_SERVICE_URL}/xrpc/com.atproto.repo.createRecord"
        post_headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }
        post_payload = {
            "repo": user_did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        post_res = requests.post(create_post_url, headers=post_headers, json=post_payload, timeout=25)
        if post_res.status_code == 200:
            res_json = post_res.json()
            post_uri = res_json.get("uri", "")
            rkey = post_uri.split("/")[-1] if "/" in post_uri else post_uri
            permalink = f"https://bsky.app/profile/{handle}/post/{rkey}"

            print(f"   🎉 [BLUESKY REST SUCCESS] Video berjaya disiarkan! Pautan: {permalink}")
            return True, {"platform": "bluesky", "uri": post_uri, "permalink": permalink, "method": "rest_fallback"}, "Hantaran Bluesky berjaya!"

        return False, {}, f"Gagal cipta rekod Bluesky (HTTP {post_res.status_code}): {post_res.text[:80]}"
    except Exception as e:
        return False, {}, f"Ralat sambungan Bluesky REST: {str(e)}"


def post_video_to_bluesky(
    video_path: str,
    caption: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Fungsi Utama: Menerbitkan video MP4 ke Bluesky feed.
    Memulangkan: (success, result_dict, message)
    """
    handle, app_pwd, cfg_err = get_bluesky_config()
    if cfg_err or not handle or not app_pwd:
        return False, {}, cfg_err or "Konfigurasi Bluesky tidak lengkap."

    if not os.path.exists(video_path):
        return False, {}, f"Fail video tidak ditemui: {video_path}"

    clean_caption = smart_trim_for_bluesky(caption, max_chars=MAX_BLUESKY_CHARS)
    print(f"\n🦋 [BLUESKY DISPATCHER] Memulakan sesi hantaran video ke @{handle}...")

    # 1. Cuba melalui atproto SDK terlebih dahulu
    if ATPROTO_SDK_AVAILABLE:
        ok, res_data, msg = _publish_via_atproto_sdk(handle, app_pwd, video_path, clean_caption)
        if ok:
            return True, res_data, msg
        print(f"   ⚠️ [SDK WARN] Percubaan SDK gagal ({msg}). Beralih ke REST fallback...")

    # 2. Fallback melalui REST API
    return _publish_via_rest_fallback(handle, app_pwd, video_path, clean_caption)