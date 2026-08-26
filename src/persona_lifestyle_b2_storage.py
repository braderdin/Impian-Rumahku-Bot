#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Ephemeral Backblaze B2 Media Bridge
Location: src/persona_lifestyle_b2_storage.py

Features:
- Dynamic authentication with Backblaze B2 Native REST API (v2).
- Uploads temporary compressed images with SHA1 verification.
- Generates secure signed download URLs for Meta Instagram & Threads APIs.
- Instant post-publish purge (b2_delete_file_version) to keep storage 100% clean.
- Zero Hardcoded Keys: Reads IRCM_B2_* environment variables.
"""

import os
import sys
import time
import hashlib
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


def get_b2_credentials() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """
    Membaca tetapan sambungan Backblaze B2 daripada persekitaran.
    """
    key_id = (
        os.getenv("IRCM_B2_KEY_ID", "").strip()
        or os.getenv("IRCM_B2_ACCOUNT_KEY_ID", "").strip()
        or os.getenv("B2_KEY_ID", "").strip()
        or os.getenv("B2_ACCOUNT_KEY_ID", "").strip()
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

    if not key_id or not app_key:
        return None, None, None, None, "Kunci IRCM_B2_KEY_ID atau IRCM_B2_APPLICATION_KEY tidak lengkap."
    if not bucket_name and not bucket_id:
        return None, None, None, None, "IRCM_B2_BUCKET_NAME atau IRCM_B2_BUCKET_ID tidak lengkap."

    return key_id, app_key, bucket_name, bucket_id, ""


def authorize_b2_account() -> Tuple[bool, Dict[str, Any], str]:
    """
    Mendapatkan token pengesahan dan endpoint API B2 (b2_authorize_account).
    """
    key_id, app_key, bucket_name, bucket_id, err = get_b2_credentials()
    if err:
        return False, {}, err

    url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
    try:
        res = requests.get(url, auth=(key_id, app_key), timeout=15)
        if res.status_code == 200:
            data = res.json()
            return True, data, ""
        return False, {}, f"B2 Authorize HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return False, {}, f"Ralat sambungan B2 Authorize: {str(e)}"


def get_or_resolve_bucket_id(auth_data: Dict[str, Any], bucket_name: str, bucket_id: str) -> Tuple[bool, str, str]:
    """
    Mendapatkan bucketId jika hanya bucket_name yang diberikan.
    """
    if bucket_id:
        return True, bucket_id, ""

    api_url = auth_data.get("apiUrl", "")
    auth_token = auth_data.get("authorizationToken", "")
    account_id = auth_data.get("accountId", "")

    endpoint = f"{api_url}/b2api/v2/b2_list_buckets"
    headers = {"Authorization": auth_token}
    payload = {"accountId": account_id}

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            buckets = res.json().get("buckets", [])
            for b in buckets:
                if b.get("bucketName") == bucket_name:
                    return True, b.get("bucketId"), ""
            return False, "", f"Bucket '{bucket_name}' tidak ditemui dalam akaun B2."
        return False, "", f"B2 List Buckets HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return False, "", f"Ralat carian Bucket B2: {str(e)}"


def upload_temp_image_to_b2_signed(
    local_image_path: str,
    valid_duration_seconds: int = 1800
) -> Tuple[bool, str, str, str, str, str, str]:
    """
    Memuat naik imej tempatan ke Backblaze B2 dan menjana Signed Download URL (sah 30 minit).
    Memulangkan: (success, signed_url, file_id, file_name, api_url, auth_token, error_msg)
    """
    if not local_image_path or not os.path.exists(local_image_path):
        return False, "", "", "", "", "", "Fail imej fizikal tidak dijumpai."

    key_id, app_key, bucket_name, bucket_id_cfg, err = get_b2_credentials()
    if err:
        return False, "", "", "", "", "", err

    # 1. Authorize B2 Account
    auth_ok, auth_data, auth_err = authorize_b2_account()
    if not auth_ok:
        return False, "", "", "", "", "", auth_err

    api_url = auth_data.get("apiUrl", "")
    download_url_base = auth_data.get("downloadUrl", "")
    auth_token = auth_data.get("authorizationToken", "")

    # 2. Dapatkan Bucket ID
    b_ok, resolved_bucket_id, b_err = get_or_resolve_bucket_id(auth_data, bucket_name, bucket_id_cfg)
    if not b_ok:
        return False, "", "", "", "", "", b_err

    # 3. Dapatkan Upload URL
    get_upload_endpoint = f"{api_url}/b2api/v2/b2_get_upload_url"
    try:
        res_up_url = requests.post(
            get_upload_endpoint,
            json={"bucketId": resolved_bucket_id},
            headers={"Authorization": auth_token},
            timeout=15
        )
        if res_up_url.status_code != 200:
            return False, "", "", "", "", "", f"Gagal dapatkan Upload URL: {res_up_url.text}"

        up_url_data = res_up_url.json()
        upload_endpoint = up_url_data.get("uploadUrl")
        upload_token = up_url_data.get("authorizationToken")
    except Exception as e:
        return False, "", "", "", "", "", f"Ralat get_upload_url: {e}"

    # 4. Muat naik fail dengan SHA1 checksum
    timestamp_prefix = int(time.time())
    b2_file_name = f"lifestyle_temp_{timestamp_prefix}_{Path(local_image_path).name}"

    try:
        with open(local_image_path, "rb") as f:
            file_bytes = f.read()

        sha1_hash = hashlib.sha1(file_bytes).hexdigest()
        headers_upload = {
            "Authorization": upload_token,
            "X-Bz-File-Name": b2_file_name,
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(file_bytes)),
            "X-Bz-Content-Sha1": sha1_hash,
        }

        res_upload = requests.post(upload_endpoint, data=file_bytes, headers=headers_upload, timeout=30)
        if res_upload.status_code != 200:
            return False, "", "", "", "", "", f"B2 Upload HTTP {res_upload.status_code}: {res_upload.text}"

        uploaded_file_info = res_upload.json()
        file_id = uploaded_file_info.get("fileId", "")
        file_name = uploaded_file_info.get("fileName", b2_file_name)

    except Exception as e:
        return False, "", "", "", "", "", f"Ralat muat naik B2: {e}"

    # 5. Dapatkan Download Authorization Token (Signed URL)
    try:
        auth_down_endpoint = f"{api_url}/b2api/v2/b2_get_download_authorization"
        payload_auth = {
            "bucketId": resolved_bucket_id,
            "fileNamePrefix": file_name,
            "validDurationInSeconds": valid_duration_seconds
        }
        res_down_auth = requests.post(auth_down_endpoint, json=payload_auth, headers={"Authorization": auth_token}, timeout=15)
        
        if res_down_auth.status_code == 200:
            down_token = res_down_auth.json().get("authorizationToken", "")
            signed_url = f"{download_url_base}/file/{bucket_name}/{file_name}?Authorization={down_token}"
        else:
            # Fallback jika bucket bersifat public
            signed_url = f"{download_url_base}/file/{bucket_name}/{file_name}"

        print(f"☁️ [B2 STORAGE] Imej berjaya dimuat naik: {file_name} (ID: {file_id[:16]}...)")
        return True, signed_url, file_id, file_name, api_url, auth_token, ""

    except Exception as e:
        return False, "", file_id, file_name, api_url, auth_token, f"Ralat tanda tangan B2: {e}"


def delete_ephemeral_image_from_b2(
    api_url: str,
    auth_token: str,
    file_id: str,
    file_name: str
) -> bool:
    """
    Memadam fail imej sementara dari B2 serta-merta selepas pos selesai.
    """
    if not file_id or not file_name:
        return False

    # Jika token atau URL kosong, cuba dapatkan semula
    if not api_url or not auth_token:
        auth_ok, auth_data, _ = authorize_b2_account()
        if auth_ok:
            api_url = auth_data.get("apiUrl", "")
            auth_token = auth_data.get("authorizationToken", "")

    endpoint = f"{api_url}/b2api/v2/b2_delete_file_version"
    headers = {"Authorization": auth_token}
    payload = {"fileId": file_id, "fileName": file_name}

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            print(f"🧹 [B2 PURGE] Fail sementara '{file_name}' berjaya dipadam dari Backblaze B2.")
            return True
        else:
            print(f"⚠️ [B2 PURGE WARN] HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"⚠️ [B2 PURGE ERROR] {e}")

    return False


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Storan Ephemeral Backblaze B2...")
    print("=" * 70)

    # Buat imej dummy ujian
    test_img_path = TEMP_DIR / "test_b2_dummy.jpg"
    with Image.new("RGB", (300, 300), color=(100, 149, 237)) as img:
        img.save(test_img_path, "JPEG")

    print("1. Muat naik imej ujian ke B2...")
    ok, signed_url, fid, fname, api, tok, err = upload_temp_image_to_b2_signed(str(test_img_path))

    if ok:
        print(f"   ✅ URL Bertandatangan : {signed_url[:75]}...")
        print(f"   ✅ File ID             : {fid}")
        print("\n2. Memadam fail sementara dari B2...")
        del_ok = delete_ephemeral_image_from_b2(api, tok, fid, fname)
        print(f"   Status Padam: {del_ok}")
    else:
        print(f"   ❌ Ujian Gagal: {err}")

    if test_img_path.exists():
        test_img_path.unlink()
    print("=" * 70)