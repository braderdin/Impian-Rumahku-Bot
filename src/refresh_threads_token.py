import os
import requests

THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"
REDIS_TOKEN_KEY = "auth:impianrumahku:threads_token"  # Kunci khusus projek Impian Rumahku

def get_active_threads_token(redis_url="", redis_token="", fallback_token=""):
    """
    Mengambil token Threads terkini dari Upstash Redis.
    Jika tiada di Redis, guna fallback_token dari environment variable.
    """
    if redis_url and redis_token:
        try:
            clean_url = redis_url.rstrip("/")
            headers = {
                "Authorization": f"Bearer {redis_token}",
                "Content-Type": "application/json",
            }
            res = requests.post(
                f"{clean_url}/", 
                json=["GET", REDIS_TOKEN_KEY], 
                headers=headers, 
                timeout=5
            )
            if res.status_code == 200:
                cached_token = res.json().get("result")
                if cached_token and len(cached_token) > 20:
                    return cached_token
        except Exception as e:
            print(f"⚠️ [REDIS WARN] Gagal membaca token dari Redis: {e}")

    return fallback_token

def save_threads_token_to_redis(redis_url, redis_token, access_token, expires_in=5184000):
    """
    Menyimpan token Threads baharu ke Upstash Redis dengan TTL 60 hari.
    """
    if not redis_url or not redis_token or not access_token:
        return False

    clean_url = redis_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    try:
        res = requests.post(
            f"{clean_url}/",
            json=["SET", REDIS_TOKEN_KEY, access_token, "EX", str(expires_in)],
            headers=headers,
            timeout=5,
        )
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ [REDIS WARN] Gagal menyimpan token ke Redis: {e}")
        return False

def refresh_threads_long_lived_token(current_token):
    """
    Membuat panggilan ke Meta API untuk memperbaharui Long-Lived Token Threads.
    """
    if not current_token:
        return False, "Token Threads sedia ada kosong atau tidak sah.", None

    params = {
        "grant_type": "th_refresh_token",
        "access_token": current_token
    }

    try:
        res = requests.get(THREADS_REFRESH_URL, params=params, timeout=15)
        if res.status_code == 200:
            data = res.json()
            new_token = data.get("access_token")
            expires_in = data.get("expires_in", 5184000) # Default ~60 hari
            return True, new_token, expires_in
        else:
            return False, f"Meta API HTTP {res.status_code}: {res.text}", None
    except Exception as e:
        return False, f"Ralat Rangkaian semasa Refresh Token: {str(e)}", None