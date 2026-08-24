#!/usr/bin/env python3
"""
Upstash Redis REST Lifecycle & Deduplication Manager
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Keyword Exact Match Deduplication with TTL 10 Days (864,000s)
  Key Format: impianrumahku:redis:pexels:keyword:<clean_keyword>
- Keyword Memory Bank (LPUSH + LTRIM 10 latest)
  Key Format: impianrumahku:redis:pexels:keyword_memory
- Video ID Deduplication with TTL 30 Days (2,592,000s)
  Key Format: impianrumahku:redis:pexels:video_id:<video_id>
- Dynamic retrieval of active Threads access token
  Key Format: auth:impianrumahku:threads_token
"""

import re
import sys
import requests
from pathlib import Path
from typing import List, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_redis_config

# Pemalar Masa Luput (TTL)
KEYWORD_TTL_SECONDS = 10 * 86400        # 10 Hari (864,000 saat)
VIDEO_ID_TTL_SECONDS = 30 * 86400       # 30 Hari (2,592,000 saat)

# Kunci Redis Khas
REDIS_KEYWORD_PREFIX = "impianrumahku:redis:pexels:keyword"
REDIS_KEYWORD_MEMORY_KEY = "impianrumahku:redis:pexels:keyword_memory"
REDIS_VIDEO_PREFIX = "impianrumahku:redis:pexels:video_id"
REDIS_THREADS_TOKEN_KEY = "auth:impianrumahku:threads_token"


def _clean_keyword_slug(keyword: str) -> str:
    """Menukar teks kata kunci kepada bentuk slug bersih dan seragam."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", keyword.lower().strip()).strip("_")
    return cleaned


# ==============================================================================
# 1. DEDUPLIKASI KATA KUNCI PEXELS (10 HARI)
# ==============================================================================

def is_pexels_keyword_used(keyword: str) -> bool:
    """
    Semak sama ada kata kunci tema pernah digunakan dalam tempoh 10 hari lepas.
    Format Kunci: impianrumahku:redis:pexels:keyword:<clean_keyword>
    """
    if not keyword:
        return False

    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        print(f"⚠️ [REDIS CONFIG WARN] {err}")
        return False

    slug = _clean_keyword_slug(keyword)
    redis_key = f"{REDIS_KEYWORD_PREFIX}:{slug}"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["GET", redis_key]

    try:
        res = requests.post(f"{redis_url}/", json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            result = res.json().get("result")
            return result is not None and str(result) != "null"
    except Exception as e:
        print(f"⚠️ [REDIS KEYWORD CHECK WARN]: {e}")

    return False


def mark_pexels_keyword_used(keyword: str, ttl_seconds: int = KEYWORD_TTL_SECONDS) -> bool:
    """
    Mengunci kata kunci tema ke dalam Redis dengan nilai 'USED' dan TTL 10 Hari (864,000s).
    """
    if not keyword:
        return False

    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        return False

    slug = _clean_keyword_slug(keyword)
    redis_key = f"{REDIS_KEYWORD_PREFIX}:{slug}"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["SET", redis_key, "USED", "EX", str(ttl_seconds)]

    try:
        res = requests.post(f"{redis_url}/", json=payload, headers=headers, timeout=10)
        if res.status_code == 200 and res.json().get("result") == "OK":
            days = ttl_seconds // 86400
            print(f"💾 [REDIS KEYWORD] Kunci '{redis_key}' dikunci ({days} Hari TTL).")
            return True
    except Exception as e:
        print(f"⚠️ [REDIS KEYWORD SAVE WARN]: {e}")

    return False


# ==============================================================================
# 2. BANK INGATAN KATA KUNCI (10 KATA KUNCI TERAKHIR)
# ==============================================================================

def get_recent_keyword_memories(limit: int = 10) -> List[str]:
    """
    Mengambil 10 sejarah kata kunci terakhir daripada Redis untuk rujukan prompt AI.
    Kunci: impianrumahku:redis:pexels:keyword_memory
    """
    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        return []

    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["LRANGE", REDIS_KEYWORD_MEMORY_KEY, "0", str(limit - 1)]

    try:
        res = requests.post(f"{redis_url}/", json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            result = res.json().get("result", [])
            if isinstance(result, list):
                return [str(item) for item in result if item]
    except Exception as e:
        print(f"⚠️ [REDIS KEYWORD MEMORY READ WARN]: {e}")

    return []


def save_keyword_memory(keyword: str, max_memories: int = 10) -> bool:
    """
    Menyimpan kata kunci baharu ke dalam senarai ingatan Redis (LPUSH)
    dan mengekalkan maksimum 10 rekod terkini sahaja (LTRIM).
    """
    if not keyword:
        return False

    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        return False

    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    pipeline_payload = [
        ["LPUSH", REDIS_KEYWORD_MEMORY_KEY, str(keyword).strip()],
        ["LTRIM", REDIS_KEYWORD_MEMORY_KEY, "0", str(max_memories - 1)],
    ]

    try:
        res = requests.post(f"{redis_url}/pipeline", json=pipeline_payload, headers=headers, timeout=10)
        if res.status_code == 200:
            print(f"🧠 [REDIS MEMORY] Kata kunci '{keyword}' disimpan ke Bank Ingatan (Maksimum {max_memories} terkini).")
            return True
    except Exception as e:
        print(f"⚠️ [REDIS KEYWORD MEMORY SAVE WARN]: {e}")

    return False


# ==============================================================================
# 3. DEDUPLIKASI VIDEO ID PEXELS (30 HARI)
# ==============================================================================

def is_pexels_video_posted(video_id: str) -> bool:
    """
    Semak sama ada ID video Pexels pernah dimuat naik dalam tempoh 30 hari lepas.
    Format Kunci: impianrumahku:redis:pexels:video_id:<video_id>
    """
    clean_id = str(video_id or "").strip()
    if not clean_id:
        return False

    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        return False

    redis_key = f"{REDIS_VIDEO_PREFIX}:{clean_id}"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["GET", redis_key]

    try:
        res = requests.post(f"{redis_url}/", json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            result = res.json().get("result")
            return result is not None and str(result) != "null"
    except Exception as e:
        print(f"⚠️ [REDIS VIDEO CHECK WARN]: {e}")

    return False


def mark_pexels_video_posted(video_id: str, ttl_seconds: int = VIDEO_ID_TTL_SECONDS) -> bool:
    """
    Menandakan ID video Pexels ke Redis dengan nilai 'USED' dan TTL 30 Hari (2,592,000s).
    """
    clean_id = str(video_id or "").strip()
    if not clean_id:
        return False

    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        return False

    redis_key = f"{REDIS_VIDEO_PREFIX}:{clean_id}"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["SET", redis_key, "USED", "EX", str(ttl_seconds)]

    try:
        res = requests.post(f"{redis_url}/", json=payload, headers=headers, timeout=10)
        if res.status_code == 200 and res.json().get("result") == "OK":
            print(f"💾 [REDIS VIDEO ID] Video ID '{clean_id}' dikunci (30 Hari TTL).")
            return True
    except Exception as e:
        print(f"⚠️ [REDIS VIDEO SAVE WARN]: {e}")

    return False


# ==============================================================================
# 4. TOKEN AKTIF THREADS DARI REDIS
# ==============================================================================

def get_active_threads_token_from_redis() -> Optional[str]:
    """
    Membaca token aktif Threads terus daripada Upstash Redis (Kunci: auth:impianrumahku:threads_token).
    """
    redis_url, redis_token, err = get_redis_config()
    if err or not redis_url or not redis_token:
        return None

    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["GET", REDIS_THREADS_TOKEN_KEY]

    try:
        res = requests.post(f"{redis_url}/", json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            token_val = res.json().get("result")
            if token_val and isinstance(token_val, str) and len(token_val.strip()) > 20:
                print("🔑 [THREADS AUTH] Berjaya membaca token aktif terkini daripada Upstash Redis.")
                return token_val.strip()
    except Exception as e:
        print(f"⚠️ [REDIS THREADS TOKEN WARN]: {e}")

    return None