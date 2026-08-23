#!/usr/bin/env python3
"""
Deep Diagnostic & Debugging Suite for Meta Threads & Backblaze B2
Impian Rumahku Ecosystem
Location: experiments/test_threads_debug.py

Checks:
1. Token retrieval from Upstash Redis ('auth:impianrumahku:threads_token')
2. Threads Account Verification (/me endpoint)
3. Backblaze B2 Upload & Public Access Verification (Ensuring Meta CDN can reach it)
4. Threads Media Container Creation with Full HTTP Response Dump
5. Container Status Polling (Checking for Meta processing errors)
6. Final Publishing & Ephemeral Cleanup
"""

import os
import sys
import time
import json
import hashlib
import requests
from pathlib import Path
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


def print_section(title: str):
    print("\n" + "=" * 75)
    print(f"🔍 {title}")
    print("=" * 75)


# ==============================================================================
# STEP 1: SEMAK TOKEN REDIS & PROFIL THREADS
# ==============================================================================

def debug_step_1_auth():
    print_section("STEP 1: SEMAKAN TOKEN UPSTASH REDIS & PROFIL THREADS")
    
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()
    user_id = os.getenv("IRCM_THREADS_USER_ID", "").strip()

    print(f"📌 Threads User ID (.env): {user_id}")
    print(f"📌 Upstash Redis URL: {redis_url[:35]}..." if redis_url else "❌ Tiada Redis URL")

    # Tarik Token dari Redis
    threads_token = None
    if redis_url and redis_token:
        try:
            r_res = requests.get(
                f"{redis_url.rstrip('/')}/get/auth:impianrumahku:threads_token",
                headers={"Authorization": f"Bearer {redis_token}"},
                timeout=10
            )
            if r_res.status_code == 200:
                raw_val = r_res.json().get("result")
                if raw_val:
                    threads_token = str(raw_val).strip()
                    print(f"✅ Token berjaya ditarik dari Redis: {threads_token[:15]}... (Panjang: {len(threads_token)})")
            else:
                print(f"⚠️ Redis HTTP {r_res.status_code}: {r_res.text}")
        except Exception as e:
            print(f"❌ Ralat sambungan Redis: {e}")

    if not threads_token:
        threads_token = os.getenv("IRCM_THREADS_ACCESS_TOKEN", "").strip()
        print(f"ℹ️ Menggunakan token sandaran dari .env: {threads_token[:15]}..." if threads_token else "❌ Tiada token dijumpai.")

    if not threads_token:
        print("❌ UJIAN GAGAL: Tiada Threads Access Token.")
        return None, None

    # Uji Profil Meta Threads (/me)
    print("\n📡 Mengesahkan Token dengan Meta Threads API (/me)...")
    me_url = f"https://graph.threads.net/v1.0/me?fields=id,username,name,threads_profile_picture_url&access_token={threads_token}"
    try:
        me_res = requests.get(me_url, timeout=15)
        print(f"   HTTP Status: {me_res.status_code}")
        print(f"   Response Body: {json.dumps(me_res.json(), indent=2)}")
        if me_res.status_code == 200:
            print("✅ Token SAH dan aktif di Meta Threads!")
            return threads_token, user_id
        else:
            print("❌ Token DITOLAK oleh Meta Threads API.")
            return None, None
    except Exception as e:
        print(f"❌ Ralat sambungan ke Threads /me: {e}")
        return None, None


# ==============================================================================
# STEP 2: UJI BACKBLAZE B2 UPLOAD & KEBOLEHCAPAIAN AWAM
# ==============================================================================

def debug_step_2_b2():
    print_section("STEP 2: UJIAN BACKBLAZE B2 UPLOAD & PUBLIC ACCESSIBILITY")

    key_id = os.getenv("IRCM_B2_KEY_ID", "").strip() or os.getenv("IRCM_B2_ACCOUNT_KEY_ID", "").strip()
    app_key = os.getenv("IRCM_B2_APPLICATION_KEY", "").strip()
    bucket_name = os.getenv("IRCM_B2_BUCKET_NAME", "").strip()
    bucket_id = os.getenv("IRCM_B2_BUCKET_ID", "").strip()

    print(f"📌 B2 Key ID: {key_id[:8]}..." if key_id else "❌ Tiada Key ID")
    print(f"📌 B2 Bucket Name: {bucket_name}")

    # Cari sebarang gambar ujian dalam temp/
    test_img = None
    if TEMP_DIR.exists():
        for f in TEMP_DIR.glob("*.jpg"):
            test_img = str(f)
            break

    if not test_img:
        # Cipta fail imej dummy jika tiada
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        test_img = str(TEMP_DIR / "debug_test.jpg")
        # Muat turun 1 gambar kecil untuk ujian
        r = requests.get("https://down-my.img.susercontent.com/file/7f1db6afc8e5000c05ebc9380cc06181", timeout=15)
        with open(test_img, "wb") as f:
            f.write(r.content)

    print(f"📸 Menggunakan fail imej ujian: {os.path.basename(test_img)} ({os.path.getsize(test_img)} bytes)")

    # 1. Authorize B2
    auth_url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
    res_auth = requests.get(auth_url, auth=(key_id, app_key), timeout=20)
    if res_auth.status_code != 200:
        print(f"❌ B2 Authorize Gagal (HTTP {res_auth.status_code}): {res_auth.text}")
        return None, None, None

    auth_data = res_auth.json()
    api_url = auth_data["apiUrl"]
    auth_token = auth_data["authorizationToken"]
    download_url = auth_data["downloadUrl"]
    print(f"✅ B2 Berjaya Log Masuk! Download URL: {download_url}")

    # Dapatkan Bucket ID jika belum ada
    if not bucket_id:
        b_res = requests.post(f"{api_url}/b2api/v2/b2_list_buckets", json={"accountId": key_id}, headers={"Authorization": auth_token})
        for b in b_res.json().get("buckets", []):
            if b.get("bucketName") == bucket_name:
                bucket_id = b.get("bucketId")
                break

    # 2. Dapatkan Upload URL
    up_url_res = requests.post(f"{api_url}/b2api/v2/b2_get_upload_url", json={"bucketId": bucket_id}, headers={"Authorization": auth_token})
    up_data = up_url_res.json()
    upload_url = up_data["uploadUrl"]
    upload_auth = up_data["authorizationToken"]

    # 3. Upload Fail
    b2_file_name = f"debug_threads_{int(time.time())}.jpg"
    with open(test_img, "rb") as f:
        file_bytes = f.read()

    headers = {
        "Authorization": upload_auth,
        "X-Bz-File-Name": b2_file_name,
        "Content-Type": "image/jpeg",
        "X-Bz-Content-Sha1": hashlib.sha1(file_bytes).hexdigest(),
        "Content-Length": str(len(file_bytes)),
    }
    up_post = requests.post(upload_url, data=file_bytes, headers=headers, timeout=30)
    if up_post.status_code != 200:
        print(f"❌ B2 Upload Gagal (HTTP {up_post.status_code}): {up_post.text}")
        return None, None, None

    file_id = up_post.json().get("fileId")
    public_image_url = f"{download_url}/file/{bucket_name}/{b2_file_name}"
    print(f"✅ Fail berjaya dimuat naik ke B2:")
    print(f"   🔗 URL: {public_image_url}")
    print(f"   🆔 File ID: {file_id}")

    # 4. Uji Kebolehcapaian Awam (Adakah Meta boleh buka URL ini tanpa login?)
    print("\n🌐 Menguji capaian awam URL B2 (Simulasi akses Meta Crawler)...")
    check_get = requests.get(public_image_url, timeout=15)
    print(f"   HTTP Status Akses Terus: {check_get.status_code}")
    print(f"   Content-Type Diterima: {check_get.headers.get('Content-Type')}")

    if check_get.status_code == 200 and "image" in check_get.headers.get("Content-Type", ""):
        print("✅ URL B2 Boleh Diakses Secara Terbuka (Public Accessible)!")
        return public_image_url, file_id, b2_file_name
    else:
        print("⚠️ AMARAN KRITIKAL: URL B2 ini dipromut sebagai PRIVATE atau memerlukan token!")
        print("   Sila pastikan Bucket B2 anda ditetapkan kepada 'Public' dalam tetapan Backblaze B2.")
        return public_image_url, file_id, b2_file_name


# ==============================================================================
# STEP 3: UJI POST THREADS MEDIA CONTAINER & PUBLISH (DEEP DEBUG)
# ==============================================================================

def debug_step_3_threads_post(token: str, user_id: str, image_url: str):
    print_section("STEP 3: UJIAN BEKAS MEDIA & PENERBITAN THREADS API")

    caption = (
        "✨ Ujian Sistem Automasi Threads\n\n"
        "Ini adalah ujian integrasi automatik sistem Mama untuk memastikan sambungan gambar B2 dan Threads lancar.\n\n"
        "💰 RM1.59\n"
        "🛒 Shopee: https://s.shopee.com.my/40fx3EQQvT\n\n"
        "#ImpianRumahku #TestBot"
    )

    base_threads_url = f"https://graph.threads.net/v1.0/{user_id}"

    # 1. Cipta Container
    create_url = f"{base_threads_url}/threads"
    create_payload = {
        "media_type": "IMAGE",
        "image_url": image_url,
        "text": caption,
        "access_token": token,
    }

    print("📤 [PERINGKAT 1] Menghantar permintaan penciptaan Container Media...")
    print(f"   Endpoint: {create_url}")
    print(f"   Image URL: {image_url}")

    c_res = requests.post(create_url, data=create_payload, timeout=30)
    print(f"   HTTP Status: {c_res.status_code}")
    print(f"   Response Body: {json.dumps(c_res.json(), indent=2)}")

    if c_res.status_code != 200:
        print("❌ GAGAL PADA PERINGKAT 1: Meta menolak penciptaan bekas media.")
        return False

    container_id = c_res.json().get("id")
    print(f"✅ Container Berjaya Dicipta! Container ID: {container_id}")

    # 2. Semakan Status (Polling)
    print("\n⏳ [PERINGKAT 2] Memeriksa status kesediaan pemprosesan media...")
    status_url = f"https://graph.threads.net/v1.0/{container_id}"
    ready = False

    for attempt in range(1, 8):
        time.sleep(3)
        s_res = requests.get(status_url, params={"fields": "id,status,error_message", "access_token": token}, timeout=15)
        print(f"   Percubaan #{attempt} Status: {s_res.status_code} | Body: {s_res.text}")
        if s_res.status_code == 200:
            s_data = s_res.json()
            status_val = s_data.get("status")
            if status_val == "FINISHED":
                print("   🎉 Media SELESAI diproses oleh Meta!")
                ready = True
                break
            elif status_val == "ERROR":
                print(f"   ❌ Meta melaporkan ralat media: {s_data.get('error_message')}")
                return False

    if not ready:
        print("⚠️ Status belum FINISHED selepas 21 saat, mencuba terbit terus...")

    # 3. Terbitkan Hantaran
    print("\n🚀 [PERINGKAT 3] Menerbitkan Container ke Threads Feed...")
    publish_url = f"{base_threads_url}/threads_publish"
    pub_res = requests.post(publish_url, data={"creation_id": container_id, "access_token": token}, timeout=30)
    
    print(f"   HTTP Status: {pub_res.status_code}")
    print(f"   Response Body: {json.dumps(pub_res.json(), indent=2)}")

    if pub_res.status_code == 200:
        post_id = pub_res.json().get("id")
        print(f"\n🎉 [BERJAYA SEPENUHNYA] Hantaran LIVE di akaun Threads! ID: {post_id}")
        return True
    else:
        print(f"\n❌ GAGAL PADA PENERBITAN: {pub_res.text}")
        return False


# ==============================================================================
# STEP 4: PADAM FAIL B2
# ==============================================================================

def debug_step_4_cleanup(file_id: str, file_name: str):
    print_section("STEP 4: PEMBERSIHAN FAIL B2")
    key_id = os.getenv("IRCM_B2_KEY_ID", "").strip() or os.getenv("IRCM_B2_ACCOUNT_KEY_ID", "").strip()
    app_key = os.getenv("IRCM_B2_APPLICATION_KEY", "").strip()

    if not file_id or not file_name:
        print("ℹ️ Tiada fail untuk dibersihkan.")
        return

    res_auth = requests.get("https://api.backblazeb2.com/b2api/v2/b2_authorize_account", auth=(key_id, app_key), timeout=15)
    if res_auth.status_code == 200:
        auth_data = res_auth.json()
        del_res = requests.post(
            f"{auth_data['apiUrl']}/b2api/v2/b2_delete_file_version",
            json={"fileName": file_name, "fileId": file_id},
            headers={"Authorization": auth_data["authorizationToken"]},
            timeout=15
        )
        if del_res.status_code == 200:
            print(f"✅ Fail '{file_name}' berjaya dipadam dari Backblaze B2.")
        else:
            print(f"⚠️ Gagal padam fail B2: {del_res.text}")


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def main():
    print("🚀 MEMULAKAN UJIAN DIAGNOSTIK MENYELURUH THREADS & B2")
    
    # Step 1
    token, user_id = debug_step_1_auth()
    if not token or not user_id:
        print("\n❌ Diagnostik dihentikan di Step 1 kerana masalah autentikasi.")
        return

    # Step 2
    b2_url, file_id, file_name = debug_step_2_b2()
    if not b2_url:
        print("\n❌ Diagnostik dihentikan di Step 2 kerana masalah Backblaze B2.")
        return

    # Step 3
    debug_step_3_threads_post(token, user_id, b2_url)

    # Step 4
    debug_step_4_cleanup(file_id, file_name)

    print("\n🏁 Ujian diagnostik selesai!")


if __name__ == "__main__":
    main()