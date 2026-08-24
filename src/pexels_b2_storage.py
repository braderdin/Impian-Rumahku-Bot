#!/usr/bin/env python3
"""
Backblaze B2 Native REST Ephemeral Video Hosting Manager
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Authorizes and connects to Backblaze B2 via Native REST API
- Uploads local MP4 video file with SHA1 checksum validation (3x retry loop)
- Generates private signed download authorization token (3600s / 1 Hour validity)
- Self-check verification (HTTP 200 & video MIME type) before dispatching to Meta/Threads
- Automated post-dispatch ephemeral file cleanup (deletes temporary video from B2 bucket)
"""

import os
import sys
import time
import hashlib
import urllib.parse
import requests
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_b2_config


class BackblazeB2StorageManager:
    """Pengurus penghosan video efemeral Backblaze B2."""

    def __init__(self):
        self.key_id, self.app_key, self.bucket_name, self.bucket_id, self.cfg_err = get_b2_config()

    def is_configured(self) -> bool:
        """Semak status kelengkapan kunci Backblaze B2."""
        return bool(not self.cfg_err and self.key_id and self.app_key and self.bucket_name)

    def authorize_account(self) -> Tuple[bool, str, str, str, str]:
        """
        Mendapatkan sesi autentikasi B2 REST API.
        Memulangkan: (success, api_url, auth_token, download_url, error_message)
        """
        if not self.is_configured():
            return False, "", "", "", self.cfg_err or "Konfigurasi B2 tidak lengkap."

        auth_url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
        try:
            res = requests.get(auth_url, auth=(self.key_id, self.app_key), timeout=20)
            if res.status_code == 200:
                data = res.json()
                return True, data.get("apiUrl", ""), data.get("authorizationToken", ""), data.get("downloadUrl", ""), ""
            return False, "", "", "", f"B2 Auth HTTP {res.status_code}: {res.text[:80]}"
        except Exception as e:
            return False, "", "", "", f"Ralat autentikasi B2: {str(e)}"

    def get_upload_url(self, api_url: str, auth_token: str) -> Tuple[bool, str, str, str]:
        """
        Mendapatkan URL muat naik khusus bucket B2.
        Memulangkan: (success, upload_url, upload_auth_token, error_message)
        """
        url = f"{api_url}/b2api/v2/b2_get_upload_url"
        headers = {"Authorization": auth_token}
        payload = {"bucketId": self.bucket_id}

        # Jika bucket_id tiada, cari ID berdasarkan nama bucket
        if not self.bucket_id:
            try:
                list_b_url = f"{api_url}/b2api/v2/b2_list_buckets"
                b_res = requests.post(list_b_url, json={"accountId": self.key_id}, headers=headers, timeout=20)
                if b_res.status_code == 200:
                    for b in b_res.json().get("buckets", []):
                        if b.get("bucketName") == self.bucket_name:
                            self.bucket_id = b.get("bucketId")
                            payload["bucketId"] = self.bucket_id
                            break
            except Exception:
                pass

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=20)
            if res.status_code == 200:
                data = res.json()
                return True, data.get("uploadUrl", ""), data.get("authorizationToken", ""), ""
            return False, "", "", f"Gagal mendapatkan B2 Upload URL (HTTP {res.status_code}): {res.text[:80]}"
        except Exception as e:
            return False, "", "", f"Ralat B2 Upload URL: {str(e)}"

    def generate_signed_download_url(
        self,
        api_url: str,
        auth_token: str,
        download_url: str,
        file_name: str,
        valid_duration: int = 3600
    ) -> Tuple[bool, str, str]:
        """
        Menjana Signed Download URL sah selama valid_duration saat (lalai: 3600s / 1 jam).
        Memulangkan: (success, signed_url, error_message)
        """
        auth_down_url = f"{api_url}/b2api/v2/b2_get_download_authorization"
        headers = {"Authorization": auth_token}
        payload = {
            "bucketId": self.bucket_id,
            "fileNamePrefix": file_name,
            "validDurationInSeconds": valid_duration,
        }

        try:
            res = requests.post(auth_down_url, json=payload, headers=headers, timeout=15)
            if res.status_code == 200:
                download_auth_token = res.json().get("authorizationToken")
                encoded_file_name = urllib.parse.quote(file_name)
                base_file_url = f"{download_url}/file/{self.bucket_name}/{encoded_file_name}"
                signed_url = f"{base_file_url}?Authorization={download_auth_token}"
                return True, signed_url, ""
            return False, "", f"Gagal menjana token muat turun B2 (HTTP {res.status_code}): {res.text[:80]}"
        except Exception as e:
            return False, "", f"Ralat penjanaan signed URL B2: {str(e)}"

    def verify_video_accessibility(self, signed_url: str) -> bool:
        """
        Menguji sama ada pautan video boleh diakses secara langsung oleh crawler Meta (HTTP 200 & video stream).
        """
        try:
            res = requests.get(signed_url, stream=True, timeout=15)
            content_type = res.headers.get("Content-Type", "")
            return res.status_code == 200 and "video" in content_type.lower()
        except Exception:
            return False

    def upload_ephemeral_video(
        self,
        video_path: str,
        valid_duration: int = 3600
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Memuat naik video MP4 tempatan ke Backblaze B2, menjana Signed URL (3600s),
        dan mengesahkan kebolehcapaian fail secara kendiri (Self-check).
        Memulangkan: (success, result_dict, error_message)
        """
        if not os.path.exists(video_path):
            return False, {}, f"Fail video fizikal tidak ditemui: {video_path}"

        print("\n☁️ [B2 STORAGE] Memulakan proses penghosan video efemeral ke Backblaze B2...")

        # 1. Autentikasi
        auth_ok, api_url, auth_token, download_url, auth_err = self.authorize_account()
        if not auth_ok:
            return False, {}, auth_err

        file_name = f"reels_ephemeral_{int(time.time())}_{os.path.basename(video_path)}"
        encoded_file_name = urllib.parse.quote(file_name)

        with open(video_path, "rb") as f:
            file_bytes = f.read()

        file_size = len(file_bytes)
        sha1_hash = hashlib.sha1(file_bytes).hexdigest()
        file_id = None
        upload_err_msg = ""

        # 2. Gelung Percubaan Muat Naik (3x Retries)
        for attempt in range(1, 4):
            up_ok, upload_url, upload_auth, up_err = self.get_upload_url(api_url, auth_token)
            if not up_ok:
                upload_err_msg = up_err
                time.sleep(2)
                continue

            headers = {
                "Authorization": upload_auth,
                "X-Bz-File-Name": encoded_file_name,
                "Content-Type": "video/mp4",
                "X-Bz-Content-Sha1": sha1_hash,
                "Content-Length": str(file_size),
            }

            try:
                up_post = requests.post(upload_url, data=file_bytes, headers=headers, timeout=(10, 60))
                if up_post.status_code == 200:
                    file_id = up_post.json().get("fileId")
                    break
                else:
                    upload_err_msg = f"HTTP {up_post.status_code}: {up_post.text[:80]}"
            except requests.exceptions.RequestException as e:
                upload_err_msg = str(e)

            if attempt < 3:
                print(f"   ⚠️ [B2 RETRY] Percubaan {attempt}/3 gagal. Meminta pod baharu...")
                time.sleep(2)

        if not file_id:
            return False, {}, f"Gagal memuat naik video ke B2 selepas 3 percubaan: {upload_err_msg}"

        # 3. Jana Signed Download URL
        sign_ok, signed_url, sign_err = self.generate_signed_download_url(
            api_url=api_url,
            auth_token=auth_token,
            download_url=download_url,
            file_name=file_name,
            valid_duration=valid_duration
        )
        if not sign_ok:
            self.delete_ephemeral_file(api_url, auth_token, file_id, file_name)
            return False, {}, sign_err

        # 4. Self-check Kebolehcapaian Video
        print("   🔍 Menguji kebolehcapaian Signed URL video secara langsung...")
        if not self.verify_video_accessibility(signed_url):
            self.delete_ephemeral_file(api_url, auth_token, file_id, file_name)
            return False, {}, "Signed URL video B2 gagal melepasi semakan akses kendiri (Self-Check)."

        print(f"   ✅ [B2 SUCCESS] Video berjaya dihoskan: {signed_url[:60]}... (Sah {valid_duration // 60} minit)")

        result_payload = {
            "signed_url": signed_url,
            "file_id": file_id,
            "file_name": file_name,
            "api_url": api_url,
            "auth_token": auth_token,
            "file_size_bytes": file_size,
        }
        return True, result_payload, "Muat naik Backblaze B2 berjaya."

    def delete_ephemeral_file(self, api_url: str, auth_token: str, file_id: str, file_name: str) -> bool:
        """
        Memadam fail video sementara dari bucket B2 selepas proses penerbitan selesai.
        """
        if not file_id or not file_name or not api_url or not auth_token:
            return False

        del_url = f"{api_url}/b2api/v2/b2_delete_file_version"
        headers = {"Authorization": auth_token}
        payload = {"fileName": file_name, "fileId": file_id}

        try:
            res = requests.post(del_url, json=payload, headers=headers, timeout=15)
            if res.status_code == 200:
                print(f"   🧹 [B2 CLEANUP] Fail sementara '{file_name}' berjaya dipadam dari B2!")
                return True
        except Exception as e:
            print(f"   ⚠️ [B2 CLEANUP WARN] Gagal memadam fail B2: {e}")

        return False


# Singleton Instance
b2_storage = BackblazeB2StorageManager()