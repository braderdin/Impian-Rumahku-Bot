#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Multi-Platform Media Dispatcher Engine
Location: src/persona_lifestyle_media_dispatcher.py

Features:
- Facebook Page: Dispatches text or photo post via Graph API.
- Instagram Feed: Dispatches photo post via signed B2 image bridge (or gracefully skips text-only).
- Meta Threads: Reads active bearer token directly from Redis 'auth:impianrumahku:threads_token'.
- Bluesky Feed: Dispatches text or image post via AT-Protocol with facet formatting.
- Isolated Error Handling: One platform failure does not block the others.
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
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

# Import Storan B2
from src.persona_lifestyle_b2_storage import upload_temp_image_to_b2_signed, delete_ephemeral_image_from_b2

REDIS_THREADS_TOKEN_KEY = "auth:impianrumahku:threads_token"


# =============================================================================
# 1. PENGURUSAN TOKEN THREADS DARI REDIS
# =============================================================================
def get_active_threads_token_from_redis() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca token aktif Threads terus dari Redis ('auth:impianrumahku:threads_token').
    """
    user_id = os.getenv("IRCM_THREADS_USER_ID", "").strip() or os.getenv("THREADS_USER_ID", "").strip()
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not redis_url or not redis_token:
        # Fallback kepada env biasa jika Redis tiada
        env_token = os.getenv("IRCM_THREADS_ACCESS_TOKEN", "").strip()
        if env_token and user_id:
            return user_id, env_token, ""
        return None, None, "Kredensial Upstash Redis untuk Threads token tidak lengkap."

    endpoint = f"{redis_url.rstrip('/')}/"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["GET", REDIS_THREADS_TOKEN_KEY]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=8)
        if res.status_code == 200:
            token_val = res.json().get("result")
            if token_val and str(token_val) != "null":
                return user_id, str(token_val).strip(), ""
    except Exception as e:
        print(f"⚠️ [THREADS TOKEN REDIS WARN] {e}")

    # Fallback env jika Redis kosong
    env_token = os.getenv("IRCM_THREADS_ACCESS_TOKEN", "").strip()
    if env_token and user_id:
        return user_id, env_token, ""

    return None, None, f"Kunci '{REDIS_THREADS_TOKEN_KEY}' tidak dijumpai dalam Redis."


# =============================================================================
# 2. PLATFORM 1: FACEBOOK PAGE FEED
# =============================================================================
def dispatch_to_facebook(
    caption: str,
    local_image_path: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], str]:
    """Menghantar teks atau foto ke Facebook Page Feed."""
    page_id = os.getenv("IRCM_FB_META_PAGE_ID", "").strip() or os.getenv("FB_PAGE_ID", "").strip()
    page_token = os.getenv("IRCM_FB_META_PAGE_ACCESS_TOKEN", "").strip() or os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()

    if not page_id or not page_token:
        return False, {}, "Kunci IRCM_FB_META_PAGE_* tidak lengkap."

    try:
        if local_image_path and os.path.exists(local_image_path):
            url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
            with open(local_image_path, "rb") as img_file:
                files = {"source": img_file}
                data = {"access_token": page_token, "caption": caption}
                res = requests.post(url, data=data, files=files, timeout=35)
        else:
            url = f"https://graph.facebook.com/v21.0/{page_id}/feed"
            data = {"access_token": page_token, "message": caption}
            res = requests.post(url, data=data, timeout=25)

        if res.status_code == 200:
            res_data = res.json()
            post_id = res_data.get("id") or res_data.get("post_id")
            return True, {"post_id": post_id, "char_count": len(caption)}, "Hantaran FB berjaya!"
        return False, {}, f"FB HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return False, {}, f"Ralat Facebook: {str(e)}"


# =============================================================================
# 3. PLATFORM 2: INSTAGRAM FEED
# =============================================================================
def dispatch_to_instagram(
    caption: str,
    signed_image_url: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], str]:
    """Menghantar foto ke Instagram Feed via Graph API Container."""
    account_id = os.getenv("IRCM_INSTAGRAM_ACCOUNT_ID", "").strip() or os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
    access_token = os.getenv("IRCM_INSTAGRAM_ACCESS_TOKEN", "").strip() or os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()

    if not account_id or not access_token:
        return False, {}, "Kunci IRCM_INSTAGRAM_* tidak lengkap."

    # Instagram Graph API memerlukan imej untuk membuat pos Feed
    if not signed_image_url:
        print("ℹ️ [INSTAGRAM] Tiada imej disertakan. Hantaran Instagram teks sahaja dilangkau secara selamat.")
        return True, {"status": "skipped", "reason": "text_only_no_image"}, "Instagram dilangkau (tiada imej)."

    try:
        # 1. Bina Media Container
        create_url = f"https://graph.facebook.com/v21.0/{account_id}/media"
        payload_container = {
            "image_url": signed_image_url,
            "caption": caption,
            "access_token": access_token
        }
        res_c = requests.post(create_url, json=payload_container, timeout=30)
        if res_c.status_code != 200:
            return False, {}, f"IG Container HTTP {res_c.status_code}: {res_c.text}"

        creation_id = res_c.json().get("id")

        # 2. Terbitkan Media Container
        publish_url = f"https://graph.facebook.com/v21.0/{account_id}/media_publish"
        payload_pub = {"creation_id": creation_id, "access_token": access_token}
        res_p = requests.post(publish_url, json=payload_pub, timeout=30)

        if res_p.status_code == 200:
            media_id = res_p.json().get("id")
            return True, {"media_id": media_id, "char_count": len(caption)}, "Hantaran Instagram berjaya!"
        return False, {}, f"IG Publish HTTP {res_p.status_code}: {res_p.text}"

    except Exception as e:
        return False, {}, f"Ralat Instagram: {str(e)}"


# =============================================================================
# 4. PLATFORM 3: META THREADS FEED
# =============================================================================
def dispatch_to_threads(
    caption: str,
    signed_image_url: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], str]:
    """Menghantar teks atau imej ke Meta Threads API menggunakan token Redis."""
    user_id, access_token, token_err = get_active_threads_token_from_redis()
    if token_err:
        return False, {}, token_err

    try:
        # 1. Bina Container
        create_url = f"https://graph.threads.net/v1.0/{user_id}/threads"
        if signed_image_url:
            data_container = {
                "media_type": "IMAGE",
                "image_url": signed_image_url,
                "text": caption,
                "access_token": access_token
            }
        else:
            data_container = {
                "media_type": "TEXT_POST",
                "text": caption,
                "access_token": access_token
            }

        res_c = requests.post(create_url, data=data_container, timeout=30)
        if res_c.status_code != 200:
            return False, {}, f"Threads Container HTTP {res_c.status_code}: {res_c.text}"

        creation_id = res_c.json().get("id")

        # 2. Terbitkan Container
        publish_url = f"https://graph.threads.net/v1.0/{user_id}/threads_publish"
        data_pub = {"creation_id": creation_id, "access_token": access_token}
        res_p = requests.post(publish_url, data=data_pub, timeout=30)

        if res_p.status_code == 200:
            thread_id = res_p.json().get("id")
            return True, {"thread_id": thread_id, "char_count": len(caption)}, "Hantaran Threads berjaya!"
        return False, {}, f"Threads Publish HTTP {res_p.status_code}: {res_p.text}"

    except Exception as e:
        return False, {}, f"Ralat Threads: {str(e)}"


# =============================================================================
# 5. PLATFORM 4: BLUESKY FEED (AT-PROTOCOL)
# =============================================================================
def dispatch_to_bluesky(
    caption: str,
    local_image_path: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], str]:
    """Menghantar teks atau imej ke Bluesky AT-Protocol."""
    handle = os.getenv("IRCM_BLUESKY_HANDLE", "").strip() or os.getenv("BLUESKY_HANDLE", "").strip()
    app_pw = os.getenv("IRCM_BLUESKY_APP_PASSWORD", "").strip() or os.getenv("BLUESKY_APP_PASSWORD", "").strip()

    if not handle or not app_pw:
        return False, {}, "Kunci IRCM_BLUESKY_* tidak lengkap."

    pds_url = "https://bsky.social"

    try:
        # 1. Create Session
        sess_url = f"{pds_url}/xrpc/com.atproto.server.createSession"
        sess_res = requests.post(sess_url, json={"identifier": handle, "password": app_pw}, timeout=15)
        if sess_res.status_code != 200:
            return False, {}, f"Bluesky Auth HTTP {sess_res.status_code}: {sess_res.text}"

        sess_data = sess_res.json()
        access_jwt = sess_data.get("accessJwt")
        did = sess_data.get("did")
        auth_headers = {"Authorization": f"Bearer {access_jwt}"}

        # 2. Upload Blob Imej (Jika Ada)
        embed_payload = None
        if local_image_path and os.path.exists(local_image_path):
            with open(local_image_path, "rb") as f:
                img_data = f.read()

            upload_url = f"{pds_url}/xrpc/com.atproto.repo.uploadBlob"
            blob_headers = {**auth_headers, "Content-Type": "image/jpeg"}
            blob_res = requests.post(upload_url, data=img_data, headers=blob_headers, timeout=25)

            if blob_res.status_code == 200:
                blob_json = blob_res.json().get("blob")
                embed_payload = {
                    "$type": "app.bsky.embed.images",
                    "images": [{"alt": "Impian Rumahku Lifestyle", "image": blob_json}]
                }

        # 3. Create Record
        import datetime
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

        record = {
            "$type": "app.bsky.feed.post",
            "text": caption,
            "createdAt": now_utc,
        }
        if embed_payload:
            record["embed"] = embed_payload

        create_rec_url = f"{pds_url}/xrpc/com.atproto.repo.createRecord"
        rec_payload = {"repo": did, "collection": "app.bsky.feed.post", "record": record}
        rec_res = requests.post(create_rec_url, json=rec_payload, headers=auth_headers, timeout=20)

        if rec_res.status_code == 200:
            uri = rec_res.json().get("uri")
            return True, {"uri": uri, "char_count": len(caption)}, "Hantaran Bluesky berjaya!"
        return False, {}, f"Bluesky Record HTTP {rec_res.status_code}: {rec_res.text}"

    except Exception as e:
        return False, {}, f"Ralat Bluesky: {str(e)}"


# =============================================================================
# 6. PENGURUS PENGEDARAN BERPUSAT (MASTER DISPATCHER)
# =============================================================================
def dispatch_lifestyle_to_all_platforms(
    captions: Dict[str, str],
    local_image_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Mengedarkan teks/media ke 4 platform serentak dengan pengurusan B2 ephemeral.
    """
    results: Dict[str, Any] = {}
    signed_b2_url = None
    b2_fid, b2_fname, b2_api, b2_tok = "", "", "", ""

    # Muat naik ke B2 jika imej tempatan wujud
    if local_image_path and os.path.exists(local_image_path):
        b2_ok, signed_b2_url, b2_fid, b2_fname, b2_api, b2_tok, b2_err = upload_temp_image_to_b2_signed(local_image_path)
        if not b2_ok:
            print(f"⚠️ [B2 WARN] {b2_err}")

    try:
        # 1. Facebook Page
        fb_cap = captions.get("facebook", "")
        fb_ok, fb_info, fb_msg = dispatch_to_facebook(fb_cap, local_image_path)
        results["facebook"] = {"status": "success", **fb_info} if fb_ok else {"status": "failed", "error": fb_msg}

        # 2. Instagram Feed
        ig_cap = captions.get("instagram", "")
        ig_ok, ig_info, ig_msg = dispatch_to_instagram(ig_cap, signed_b2_url)
        results["instagram"] = {"status": "success", **ig_info} if ig_ok else {"status": "failed", "error": ig_msg}

        # 3. Meta Threads
        th_cap = captions.get("threads", "")
        th_ok, th_info, th_msg = dispatch_to_threads(th_cap, signed_b2_url)
        results["threads"] = {"status": "success", **th_info} if th_ok else {"status": "failed", "error": th_msg}

        # 4. Bluesky Feed
        bs_cap = captions.get("bluesky", "")
        bs_ok, bs_info, bs_msg = dispatch_to_bluesky(bs_cap, local_image_path)
        results["bluesky"] = {"status": "success", **bs_info} if bs_ok else {"status": "failed", "error": bs_msg}

    finally:
        # Padam fail dari B2 serta-merta
        if b2_fid and b2_fname:
            delete_ephemeral_image_from_b2(b2_api, b2_tok, b2_fid, b2_fname)

    return results


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Pengedar Media Sosial...")
    print("=" * 70)

    u_id, t_tok, t_err = get_active_threads_token_from_redis()
    print(f"Semakan Token Threads Redis: {'✅ Sah' if not t_err else '⚠️ ' + t_err}")
    print("=" * 70)