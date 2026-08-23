#!/usr/bin/env python3
"""
Shopee Redis Deduplication & Anti-Spam Filter Engine
Impian Rumahku Ecosystem
Features:
- Reads strictly IRCM_UPSTASH_REDIS_* environment variables (GitHub Secret aligned)
- High-performance MGET Batch Checking (100 items per 1 HTTP Request)
- Atomic TTL Expiry (Default 30 Days: 2,592,000s)
- Direct single key GET / SET / DEL helpers with rollback support
- Fast pipeline integration for candidates from src/shopee_supabase_db.py
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
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

# Masa luput lalai 30 Hari dalam saat (30 * 24 * 60 * 60 = 2,592,000 saat)
DEFAULT_TTL_SECONDS = 2592000


def get_redis_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca tetapan sambungan Upstash Redis REST daripada persekitaran (.env / GitHub Secrets).
    Merujuk khusus kepada kunci IRCM_UPSTASH_REDIS_REST_URL dan IRCM_UPSTASH_REDIS_REST_TOKEN.
    """
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not redis_url or not redis_token:
        return None, None, "Kunci IRCM_UPSTASH_REDIS_REST_URL atau IRCM_UPSTASH_REDIS_REST_TOKEN tidak lengkap dalam persekitaran."

    return redis_url.rstrip("/"), redis_token, ""


def get_shopee_redis_key(product_id: Any) -> str:
    """
    Menjana format kunci Redis khusus Shopee berdasarkan product_id.
    Format: shopee:product:<product_id>
    """
    clean_id = str(product_id or "").strip()
    return f"shopee:product:{clean_id}"


def is_shopee_product_posted(
    product_id: Any,
    redis_url: Optional[str] = None,
    redis_token: Optional[str] = None
) -> bool:
    """
    Menyemak sama ada product_id Shopee pernah dihantar dalam tempoh 30 hari lepas (Semakan Tunggal).
    Memulangkan True jika kunci wujud, False jika tiada / belum dipos.
    """
    if not redis_url or not redis_token:
        r_url, r_token, err = get_redis_config()
        if err:
            print(f"⚠️ [REDIS CONFIG WARN] {err}")
            return False
        redis_url, redis_token = r_url, r_token

    clean_id = str(product_id or "").strip()
    if not clean_id:
        return False

    redis_key = get_shopee_redis_key(clean_id)
    endpoint = f"{redis_url}/"
    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    payload = ["GET", redis_key]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            res_json = res.json()
            result = res_json.get("result")
            if result is not None and str(result) != "null":
                return True
        else:
            print(f"⚠️ [REDIS WARN] HTTP {res.status_code} semasa menyemak kunci '{redis_key}': {res.text}")
    except Exception as e:
        print(f"⚠️ [REDIS WARN] Gagal berhubung dengan Upstash Redis API: {e}")

    return False


def batch_check_shopee_products_posted(
    product_ids: List[str],
    chunk_size: int = 100,
    redis_url: Optional[str] = None,
    redis_token: Optional[str] = None
) -> Set[str]:
    """
    Menyemak status puluhan/ratusan ID produk menggunakan arahan pukal MGET (100 item / 1 HTTP Request).
    Memulangkan Set[str] yang mengandungi ID produk yang SUDAH PERNAH DIPOS (wujud di Redis).
    """
    if not product_ids:
        return set()

    if not redis_url or not redis_token:
        r_url, r_token, err = get_redis_config()
        if err:
            print(f"⚠️ [REDIS CONFIG WARN] {err}")
            return set()
        redis_url, redis_token = r_url, r_token

    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    endpoint = f"{redis_url}/"

    posted_ids: Set[str] = set()
    total_ids = len(product_ids)
    clean_ids = [str(pid).strip() for pid in product_ids if str(pid).strip()]

    for i in range(0, len(clean_ids), chunk_size):
        chunk = clean_ids[i : i + chunk_size]
        keys = [get_shopee_redis_key(pid) for pid in chunk]
        
        payload = ["MGET"] + keys

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            if res.status_code == 200:
                results = res.json().get("result", [])
                if isinstance(results, list):
                    for pid, val in zip(chunk, results):
                        if val is not None and str(val) != "null":
                            posted_ids.add(pid)
            else:
                print(f"⚠️ [REDIS BATCH WARN] HTTP {res.status_code} pada kelompok {i+1}-{i+len(chunk)}: {res.text}")
        except Exception as e:
            print(f"⚠️ [REDIS BATCH ERROR] Ralat semasa semakan pukal: {e}")

    req_count = (total_ids + chunk_size - 1) // chunk_size
    print(f"🔍 [REDIS BATCH CHECK] {total_ids} produk disemak dalam {req_count} HTTP request. Dijumpai {len(posted_ids)} produk pernah dipos.")
    return posted_ids


def filter_unposted_shopee_products(
    candidates: List[Dict[str, Any]],
    chunk_size: int = 100
) -> List[Dict[str, Any]]:
    """
    Menapis senarai calon produk dari Supabase dan memulangkan HANYA produk yang BELUM PERNAH DIPOS di Redis.
    Menggunakan semakan pantas MGET (100 item/request).
    """
    if not candidates:
        return []

    product_ids = [str(item.get("shopee_product_id", "")).strip() for item in candidates if item.get("shopee_product_id")]
    already_posted_set = batch_check_shopee_products_posted(product_ids, chunk_size=chunk_size)

    unposted_candidates = [
        item for item in candidates
        if str(item.get("shopee_product_id", "")).strip() not in already_posted_set
    ]

    print(f"🛡️ [REDIS FILTER RESULT] Dari {len(candidates)} calon, {len(unposted_candidates)} produk LULUS (Belum pernah dipos).")
    return unposted_candidates


def mark_shopee_product_posted(
    product_id: Any,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    redis_url: Optional[str] = None,
    redis_token: Optional[str] = None
) -> bool:
    """
    Menyimpan product_id Shopee ke Redis dengan nilai '1' dan TTL 30 Hari secara atomik.
    Perintah Upstash REST via POST: ["SET", key, "1", "EX", ttl_seconds]
    """
    if not redis_url or not redis_token:
        r_url, r_token, err = get_redis_config()
        if err:
            print(f"⚠️ [REDIS CONFIG ERROR] {err}")
            return False
        redis_url, redis_token = r_url, r_token

    clean_id = str(product_id or "").strip()
    if not clean_id:
        return False

    redis_key = get_shopee_redis_key(clean_id)
    endpoint = f"{redis_url}/"
    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    payload = ["SET", redis_key, "1", "EX", str(ttl_seconds)]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            res_json = res.json()
            if res_json.get("result") == "OK":
                days = ttl_seconds // 86400
                print(f"💾 [REDIS SUCCESS] Kunci '{redis_key}' direkodkan dengan TTL {ttl_seconds}s (~{days} Hari).")
                return True
        else:
            print(f"⚠️ [REDIS ERROR] Gagal menyimpan kunci. HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"⚠️ [REDIS WARN] Gagal menyimpan kunci ke Redis: {e}")

    return False


def delete_shopee_product_posted(
    product_id: Any,
    redis_url: Optional[str] = None,
    redis_token: Optional[str] = None
) -> bool:
    """
    Memadam kunci product_id Shopee dari Redis (berguna jika perlu undur balik / rollback).
    """
    if not redis_url or not redis_token:
        r_url, r_token, err = get_redis_config()
        if err:
            return False
        redis_url, redis_token = r_url, r_token

    clean_id = str(product_id or "").strip()
    if not clean_id:
        return False

    redis_key = get_shopee_redis_key(clean_id)
    endpoint = f"{redis_url}/"
    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    payload = ["DEL", redis_key]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        return res.status_code == 200 and res.json().get("result") == 1
    except Exception:
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST RUN] Menguji Enjin Penapis Upstash Redis (Shopee)...")
    print("=" * 70)
    
    test_id = "99999999999"
    print(f"1. Ujian Semak Sebelum Set: ID {test_id} -> {is_shopee_product_posted(test_id)}")
    
    print("2. Ujian Simpan Kunci (TTL 60 saat)...")
    mark_shopee_product_posted(test_id, ttl_seconds=60)
    
    print(f"3. Ujian Semak Selepas Set: ID {test_id} -> {is_shopee_product_posted(test_id)}")
    
    print("4. Ujian Batch MGET 3 Dummy ID...")
    dummy_ids = [test_id, "88888888888", "77777777777"]
    posted = batch_check_shopee_products_posted(dummy_ids, chunk_size=100)
    print(f"   ID Dikesan Pernah Dipos: {posted}")
    
    print("5. Ujian Padam Kunci (Rollback)...")
    delete_shopee_product_posted(test_id)
    print(f"   Semak Semula: ID {test_id} -> {is_shopee_product_posted(test_id)}")
    print("=" * 70)