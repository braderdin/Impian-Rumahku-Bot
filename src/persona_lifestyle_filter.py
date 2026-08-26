#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Dual-Layer Deduplication & Memory Gatekeeper
Location: src/persona_lifestyle_filter.py

Features:
- Layer 1: Upstash Redis Exact Topic MD5 Match with 10-Day TTL (864,000s).
- Layer 2: Upstash Vector Semantic Similarity Filter (85% Threshold, 2-Day Window / 172,800s).
- Memory Manager: Pushes and trims 5 latest topics to Redis list buffer.
- Safe rollback functions for dry-run or error handling.
- Zero hardcoded credentials: Reads IRCM_UPSTASH_* environment variables.
"""

import os
import re
import sys
import time
import hashlib
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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

REDIS_TTL_10_DAYS = 864000      # 10 Hari dalam saat (10 * 24 * 60 * 60)
VECTOR_TTL_2_DAYS = 172800      # 2 Hari dalam saat (2 * 24 * 60 * 60)
VECTOR_SIMILARITY_THRESHOLD = 0.85
REDIS_RECENT_BUFFER_KEY = "impianrumahku:redis:lifestyle:recent_topics"
MAX_MEMORY_BUFFER = 5


def get_filter_credentials() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """
    Membaca kredensial Upstash Redis dan Vector REST API secara dinamik.
    """
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()
    vector_url = (
        os.getenv("IRCM_UPSTASH_VECTOR_REST_URL", "").strip()
        or os.getenv("IRCM_UPSTASH_VECTOR_ENDPOINT_URL", "").strip()
    )
    vector_token = os.getenv("IRCM_UPSTASH_VECTOR_REST_TOKEN", "").strip()

    errs = []
    if not redis_url or not redis_token:
        errs.append("IRCM_UPSTASH_REDIS_REST_*")
    if not vector_url or not vector_token:
        errs.append("IRCM_UPSTASH_VECTOR_REST_*")

    err_msg = f"Kunci persekitaran tidak lengkap: {', '.join(errs)}" if errs else ""
    return (
        redis_url.rstrip("/") if redis_url else None,
        redis_token,
        vector_url.rstrip("/") if vector_url else None,
        vector_token,
        err_msg
    )


def compute_topic_hash(topic_text: str) -> str:
    """
    Menghasilkan hash MD5 ringkas daripada teks topik yang telah dinormalkan.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", str(topic_text or "").lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return hashlib.md5(cleaned.encode("utf-8")).hexdigest()[:16]


def is_topic_in_redis_prison(topic_text: str) -> bool:
    """
    Semakan Lapisan 1: Memeriksa sama ada hash topik wujud dalam tahanan 10 hari Redis.
    Kunci: impianrumahku:redis:lifestyle:<md5_hash>
    """
    redis_url, redis_token, _, _, _ = get_filter_credentials()
    if not redis_url or not redis_token:
        return False

    thash = compute_topic_hash(topic_text)
    redis_key = f"impianrumahku:redis:lifestyle:{thash}"
    endpoint = f"{redis_url}/"
    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    payload = ["GET", redis_key]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=8)
        if res.status_code == 200:
            result = res.json().get("result")
            if result is not None and str(result) != "null":
                print(f"🔒 [REDIS PRISON] Topik '{topic_text[:40]}...' wujud dalam rekod 10 hari (Key: {redis_key}).")
                return True
    except Exception as e:
        print(f"⚠️ [REDIS CHECK WARN] {e}")

    return False


def is_topic_in_vector_prison(
    topic_text: str,
    threshold: float = VECTOR_SIMILARITY_THRESHOLD,
    window_seconds: int = VECTOR_TTL_2_DAYS
) -> bool:
    """
    Semakan Lapisan 2: Memeriksa persamaan semantik (>= 85%) dalam tempoh 2 hari di Upstash Vector.
    """
    _, _, vector_url, vector_token, _ = get_filter_credentials()
    if not vector_url or not vector_token:
        return False

    clean_text = str(topic_text or "").strip()
    if not clean_text:
        return False

    endpoint = f"{vector_url}/query-data"
    headers = {
        "Authorization": f"Bearer {vector_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "data": clean_text,
        "topK": 5,
        "includeMetadata": True,
    }

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            results = res.json().get("result", [])
            current_time = int(time.time())

            for match in results:
                score = float(match.get("score", 0.0))
                meta = match.get("metadata", {}) or {}
                posted_at = int(meta.get("posted_at", 0))

                time_diff = current_time - posted_at if posted_at > 0 else 999999999
                if score >= threshold and time_diff < window_seconds:
                    matched_title = meta.get("title") or meta.get("topic") or "Topik Serupa"
                    hours_ago = time_diff / 3600
                    print(
                        f"🧠 [VECTOR PRISON] Topik semantik serupa dikesan ({score * 100:.1f}%)! "
                        f"Mirip: '{str(matched_title)[:45]}...' ({hours_ago:.1f} jam lepas). Wajib dilangkau."
                    )
                    return True
    except Exception as e:
        print(f"⚠️ [VECTOR CHECK WARN] {e}")

    return False


def is_lifestyle_topic_duplicate(topic_text: str) -> Tuple[bool, str]:
    """
    Pemeriksaan Bersepadu: Menapis topik melalui Redis (10 hari) dan Vector DB (2 hari / 85%).
    Memulangkan (True, sebab) jika pendua, (False, '') jika unik dan selamat digunakan.
    """
    if not topic_text or len(topic_text.strip()) < 5:
        return True, "Teks topik kosong atau terlalu pendek."

    # 1. Semakan Pantas Redis Exact Hash
    if is_topic_in_redis_prison(topic_text):
        return True, "Topik tepat pernah disiarkan dalam tempoh 10 hari (Redis Lock)."

    # 2. Semakan Semantik Upstash Vector
    if is_topic_in_vector_prison(topic_text, threshold=VECTOR_SIMILARITY_THRESHOLD, window_seconds=VECTOR_TTL_2_DAYS):
        return True, "Topik semantik serupa (>85%) disiarkan dalam tempoh 48 jam (Vector Lock)."

    return False, ""


def commit_lifestyle_topic_lock(
    topic_id: str,
    topic_text: str,
    category: str = "lifestyle"
) -> bool:
    """
    Mengunci topik ke Redis (TTL 10 Hari), Upstash Vector (TTL 2 Hari),
    dan memasukkan ringkasan topik ke senarai memori penimbal (recent_topics list).
    """
    redis_url, redis_token, vector_url, vector_token, err_cfg = get_filter_credentials()
    clean_id = str(topic_id or "").strip()
    clean_text = str(topic_text or "").strip()

    if not clean_id or not clean_text:
        return False

    current_time = int(time.time())
    thash = compute_topic_hash(clean_text)
    redis_lock_key = f"impianrumahku:redis:lifestyle:{thash}"
    vector_doc_id = f"impianrumahku:vector:lifestyle:{clean_id}"

    success_redis = False
    success_vector = False

    # 1. Kunci Redis (10 Hari) & Masukkan ke Penimbal Memori
    if redis_url and redis_token:
        headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
        endpoint = f"{redis_url}/"

        # Simpan kunci 10 hari
        payload_set = ["SET", redis_lock_key, "1", "EX", str(REDIS_TTL_10_DAYS)]
        try:
            res_set = requests.post(endpoint, json=payload_set, headers=headers, timeout=8)
            if res_set.status_code == 200:
                success_redis = True
                print(f"🔒 [REDIS LOCK SUCCESS] Kunci '{redis_lock_key}' disimpan (TTL 10 Hari).")

            # Tolak ke senarai memori topik terkini (LPUSH + LTRIM)
            short_summary = clean_text[:80].replace("\n", " ")
            payload_lpush = ["LPUSH", REDIS_RECENT_BUFFER_KEY, short_summary]
            payload_ltrim = ["LTRIM", REDIS_RECENT_BUFFER_KEY, "0", str(MAX_MEMORY_BUFFER - 1)]

            requests.post(endpoint, json=payload_lpush, headers=headers, timeout=8)
            requests.post(endpoint, json=payload_ltrim, headers=headers, timeout=8)
            print(f"💾 [MEMORY BUFFER] Topik ditolak ke senarai memori: \"{short_summary}\"")
        except Exception as e:
            print(f"⚠️ [REDIS COMMIT ERROR] {e}")

    # 2. Simpan Embedding ke Upstash Vector (2 Hari)
    if vector_url and vector_token:
        headers_vec = {"Authorization": f"Bearer {vector_token}", "Content-Type": "application/json"}
        endpoint_vec = f"{vector_url}/upsert-data"

        payload_vec = {
            "id": vector_doc_id,
            "data": clean_text,
            "metadata": {
                "platform": "lifestyle_mama",
                "category": category,
                "topic_id": clean_id,
                "title": clean_text[:120],
                "posted_at": current_time
            }
        }
        try:
            res_vec = requests.post(endpoint_vec, json=payload_vec, headers=headers_vec, timeout=10)
            if res_vec.status_code == 200:
                success_vector = True
                print(f"🧠 [VECTOR UPSERT SUCCESS] ID '{vector_doc_id}' direkodkan ke Vector DB.")
        except Exception as e:
            print(f"⚠️ [VECTOR COMMIT ERROR] {e}")

    return success_redis or success_vector


def delete_lifestyle_topic_lock(topic_id: str, topic_text: str) -> bool:
    """
    Fungsi undur balik (rollback) jika berlaku kegagalan hantaran.
    """
    redis_url, redis_token, vector_url, vector_token, _ = get_filter_credentials()
    clean_id = str(topic_id or "").strip()
    thash = compute_topic_hash(topic_text)
    redis_lock_key = f"impianrumahku:redis:lifestyle:{thash}"
    vector_doc_id = f"impianrumahku:vector:lifestyle:{clean_id}"

    if redis_url and redis_token:
        try:
            requests.post(f"{redis_url}/", json=["DEL", redis_lock_key], headers={"Authorization": f"Bearer {redis_token}"}, timeout=8)
        except Exception:
            pass

    if vector_url and vector_token:
        try:
            requests.post(f"{vector_url}/delete", json={"ids": [vector_doc_id]}, headers={"Authorization": f"Bearer {vector_token}"}, timeout=8)
        except Exception:
            pass

    return True


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Penapis Dwi-Lapisan Persona Lifestyle...")
    print("=" * 70)

    test_id = "test_sample_001"
    sample_topic = "Pokok monstera di ruang tamu mula keluar daun baru lepas letak baja organik"

    print("1. Semak keunikan topik baru:")
    is_dup, reason = is_lifestyle_topic_duplicate(sample_topic)
    print(f"   Keputusan: Duplicate={is_dup} | Sebab: {reason}")

    print("\n2. Uji kunci topik ke Redis & Vector:")
    locked = commit_lifestyle_topic_lock(test_id, sample_topic, category="tanaman")
    print(f"   Status Kunci: {locked}")

    print("\n3. Semak semula selepas dikunci:")
    is_dup_after, reason_after = is_lifestyle_topic_duplicate(sample_topic)
    print(f"   Keputusan Selepas Kunci: Duplicate={is_dup_after} | Sebab: {reason_after}")

    print("\n4. Rollback / Padam Ujian Kunci:")
    delete_lifestyle_topic_lock(test_id, sample_topic)
    print("   Ujian Padam Kunci Selesai.")
    print("=" * 70)