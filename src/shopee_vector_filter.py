#!/usr/bin/env python3
"""
Shopee Upstash Vector Semantic Anti-Spam Filter Engine
Impian Rumahku Ecosystem
Features:
- Reads strictly IRCM_UPSTASH_VECTOR_* environment variables (GitHub Secret aligned)
- 2-Day Time Window (172,800s) & 80% Cosine Similarity Threshold
- Prevents posting semantically similar products consecutively
- Safe timestamp parser to handle legacy string/int metadata seamlessly
- Direct /query-data, /upsert-data, and /delete REST operations
- Integrated pipeline selector for candidate batches from Supabase & Redis
"""

import os
import sys
import time
import json
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

# Tetapan Keserupaan & Masa Luput (Penjarakan 2 Hari / 80% Cosine Similarity)
DEFAULT_SIMILARITY_THRESHOLD = 0.80
DEFAULT_WINDOW_SECONDS = 172800  # 2 Hari dalam saat (2 * 24 * 60 * 60)


def get_vector_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca tetapan sambungan Upstash Vector REST API daripada persekitaran (.env / GitHub Secrets).
    Merujuk khusus kepada kunci IRCM_UPSTASH_VECTOR_REST_URL dan IRCM_UPSTASH_VECTOR_REST_TOKEN.
    """
    vector_url = (
        os.getenv("IRCM_UPSTASH_VECTOR_REST_URL", "").strip()
        or os.getenv("IRCM_UPSTASH_VECTOR_ENDPOINT_URL", "").strip()
    )
    vector_token = os.getenv("IRCM_UPSTASH_VECTOR_REST_TOKEN", "").strip()

    if not vector_url or not vector_token:
        return None, None, "Kunci IRCM_UPSTASH_VECTOR_REST_URL atau IRCM_UPSTASH_VECTOR_REST_TOKEN tidak lengkap dalam persekitaran."

    return vector_url.rstrip("/"), vector_token, ""


def get_shopee_vector_id(product_id: Any) -> str:
    """
    Menjana format ID Dokumen Vector khusus Shopee.
    Format: sp_<product_id> (cth: sp_24101317984)
    """
    clean_id = str(product_id or "").strip()
    return f"sp_{clean_id}"


def _safe_parse_timestamp(val: Any) -> int:
    """
    Menukar nilai timestamp metadata lama/baru kepada integer selamat.
    Mengelakkan ralat jika metadata tersimpan dalam bentuk string atau float.
    """
    if val is None:
        return 0
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return 0


def is_similar_shopee_product_posted(
    product_title: str,
    vector_url: Optional[str] = None,
    vector_token: Optional[str] = None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    window_seconds: int = DEFAULT_WINDOW_SECONDS
) -> bool:
    """
    Menyemak sama ada terdapat produk Shopee dengan makna/tema serupa (Cosine Similarity >= 80%)
    yang pernah dipos dalam tempoh 2 hari (172,800 saat) melalui Upstash Vector REST API.
    Memulangkan True jika produk serupa wujud (Wajib Langkau), False jika unik/selamat.
    """
    if not vector_url or not vector_token:
        v_url, v_token, err = get_vector_config()
        if err:
            print(f"⚠️ [VECTOR CONFIG WARN] {err}")
            return False
        vector_url, vector_token = v_url, v_token

    clean_title = str(product_title or "").strip()
    if not clean_title:
        return False

    endpoint = f"{vector_url}/query-data"
    headers = {
        "Authorization": f"Bearer {vector_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "data": clean_title,
        "topK": 5,
        "includeMetadata": True,
    }

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            results = res.json().get("result", [])
            current_time = int(time.time())

            for match in results:
                try:
                    score = float(match.get("score", 0.0))
                except (ValueError, TypeError):
                    score = 0.0

                metadata = match.get("metadata", {}) or {}
                posted_at_raw = metadata.get("posted_at", 0)
                posted_at = _safe_parse_timestamp(posted_at_raw)

                # Jika posted_at = 0 (rekod usang tanpa tarikh sah), abaikan sekatan masa
                time_diff = current_time - posted_at if posted_at > 0 else 999999999

                if score >= threshold and time_diff < window_seconds:
                    matched_title = metadata.get("title") or metadata.get("product_name") or "Produk Serupa"
                    hours_ago = time_diff / 3600
                    print(
                        f"⏭️ [VECTOR MATCH] Produk tema serupa dikesan! '{clean_title[:45]}...' mirip "
                        f"({score * 100:.1f}%) dengan '{str(matched_title)[:45]}...' ({hours_ago:.1f} jam lepas). Langkau."
                    )
                    return True
        else:
            print(f"⚠️ [VECTOR WARN] HTTP {res.status_code} semasa carian vektor: {res.text}")
    except Exception as e:
        print(f"⚠️ [VECTOR WARN] Gagal membuat semakan di Upstash Vector DB: {e}")

    return False


def find_first_vector_unique_product(
    candidates: List[Dict[str, Any]],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    window_seconds: int = DEFAULT_WINDOW_SECONDS
) -> Optional[Dict[str, Any]]:
    """
    Mengimbas senarai calon produk yang telah lulus tapisan Redis satu persatu,
    dan memulangkan PRODUK PERTAMA yang bebas daripada persamaan semantik dalam tempoh 2 hari.
    """
    if not candidates:
        return None

    v_url, v_token, err = get_vector_config()
    if err:
        print(f"⚠️ [VECTOR CONFIG ERROR] {err}. Memilih calon pertama sebagai fallback.")
        return candidates[0]

    print(f"🧠 [VECTOR PIPELINE] Memulakan saringan semantik (Threshold: {threshold * 100:.0f}%, Tempoh: {window_seconds // 3600} Jam)...")

    for idx, item in enumerate(candidates, 1):
        p_name = item.get("shopee_product_name", "")
        p_id = item.get("shopee_product_id", "")

        is_similar = is_similar_shopee_product_posted(
            product_title=p_name,
            vector_url=v_url,
            vector_token=v_token,
            threshold=threshold,
            window_seconds=window_seconds,
        )

        if not is_similar:
            print(f"🎯 [VECTOR WINNER] Calon #{idx} LULUS tapisan semantik: [{p_id}] {p_name[:50]}...")
            return item

    print("⚠️ [VECTOR PIPELINE WARN] Tiada produk yang 100% unik daripada senarai calon semasa. Menggunakan calon pertama sebagai sandaran.")
    return candidates[0]


def mark_shopee_vector_posted(
    product_id: Any,
    product_title: str,
    vector_url: Optional[str] = None,
    vector_token: Optional[str] = None
) -> bool:
    """
    Menyimpan embedding tajuk produk ke dalam Upstash Vector DB.
    Format ID: sp_<product_id>
    Metadata: platform: shopee, product_id, title, posted_at
    """
    if not vector_url or not vector_token:
        v_url, v_token, err = get_vector_config()
        if err:
            print(f"⚠️ [VECTOR CONFIG ERROR] {err}")
            return False
        vector_url, vector_token = v_url, v_token

    clean_id = str(product_id or "").strip()
    clean_title = str(product_title or "").strip()
    if not clean_id or not clean_title:
        return False

    endpoint = f"{vector_url}/upsert-data"
    headers = {
        "Authorization": f"Bearer {vector_token}",
        "Content-Type": "application/json",
    }

    doc_id = get_shopee_vector_id(clean_id)
    current_time = int(time.time())

    payload = {
        "id": doc_id,
        "data": clean_title,
        "metadata": {
            "platform": "shopee",
            "product_id": clean_id,
            "title": clean_title,
            "posted_at": current_time,
        },
    }

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            print(f"🟢 [VECTOR SUCCESS] Embedding '{clean_title[:40]}...' (ID: {doc_id}) berjaya disimpan ke Vector DB.")
            return True
        else:
            print(f"⚠️ [VECTOR ERROR] Ralat HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"⚠️ [VECTOR WARN] Gagal menyimpan rekod embedding ke Upstash Vector DB: {e}")

    return False


def delete_shopee_vector_posted(
    product_id: Any,
    vector_url: Optional[str] = None,
    vector_token: Optional[str] = None
) -> bool:
    """
    Memadam rekod embedding produk Shopee dari Vector DB (jika berlaku rollback).
    """
    if not vector_url or not vector_token:
        v_url, v_token, err = get_vector_config()
        if err:
            return False
        vector_url, vector_token = v_url, v_token

    clean_id = str(product_id or "").strip()
    if not clean_id:
        return False

    endpoint = f"{vector_url}/delete"
    headers = {
        "Authorization": f"Bearer {vector_token}",
        "Content-Type": "application/json",
    }
    doc_id = get_shopee_vector_id(clean_id)
    payload = {"ids": [doc_id]}

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        return res.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST RUN] Menguji Enjin Penapis Vektor Semantik (Shopee)...")
    print("=" * 70)

    test_product_id = "99999999999"
    test_title_a = "Set Periuk Kuali Non Stick Granit Anti Calar Dapur Gas Induksi"
    test_title_b = "Periuk Non-Stick Granite Cookware Set Kuali Masak Dapur Viral"
    test_title_c = "Rak Kasut Bertingkat Pintu Almari Kasut Plastik Lipat Jimat Ruang"

    print("1. Semak Produk Asal Sebelum Disimpan:")
    is_sim = is_similar_shopee_product_posted(test_title_a)
    print(f"   Hasil: {is_sim} (Harus False jika belum ada)")

    print("\n2. Simpan Embedding Produk Asal ke Vector DB...")
    mark_shopee_vector_posted(test_product_id, test_title_a)
    
    # Beri masa 2 saat untuk Upstash Vector selesai indexing
    print("⏳ Menunggu 2 saat untuk pelayan Upstash selesai indexing...")
    time.sleep(2)

    print("\n3. Uji Kesan Produk Tajuk Semantik Serupa (Title B)...")
    is_sim_b = is_similar_shopee_product_posted(test_title_b)
    print(f"   Hasil Kesan Serupa: {is_sim_b} (Harus True)")

    print("\n4. Uji Kesan Produk Kategori Berbeza Sepenuhnya (Title C)...")
    is_sim_c = is_similar_shopee_product_posted(test_title_c)
    print(f"   Hasil Kesan Serupa: {is_sim_c} (Harus False)")

    print("\n5. Ujian Padam Rekod Vektor (Rollback)...")
    del_ok = delete_shopee_vector_posted(test_product_id)
    print(f"   Padam Status: {del_ok}")

    print("\n6. Semak Semula Selepas Dipadam:")
    is_sim_after = is_similar_shopee_product_posted(test_title_b)
    print(f"   Hasil Selepas Padam: {is_sim_after} (Harus False)")
    print("=" * 70)