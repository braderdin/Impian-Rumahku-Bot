#!/usr/bin/env python3
"""
Upstash Vector Semantic Anti-Spam Manager for Video Reels
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Guardrail keserupaan makna kapsyen Bahasa Melayu (Cosine Similarity >= 0.85, Window 2 Hari)
- Mencegah perkongsian ayat/tema yang bertindih dalam tempoh bertenang 2 hari (172,800s)
- Format Dokumen Vektor: impianrumahku:vector:text_cooldown:<story_id>
- Menyokong operasi /query-data, /upsert-data, dan /delete
"""

import sys
import time
import requests
from pathlib import Path
from typing import Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_vector_config

# Tetapan Keserupaan & Masa Luput
SIMILARITY_THRESHOLD = 0.85          # Skor >= 0.85 (85%) dianggap tema/ayat serupa
TIME_WINDOW_2_DAYS = 2 * 86400       # 2 Hari dalam saat (172,800 saat)
VECTOR_PREFIX = "impianrumahku:vector:text_cooldown"


def _safe_parse_timestamp(val) -> int:
    """Menukar nilai timestamp metadata kepada format integer selamat."""
    if val is None:
        return 0
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return 0


def is_similar_story_posted(
    story_text: str,
    threshold: float = SIMILARITY_THRESHOLD,
    window_seconds: int = TIME_WINDOW_2_DAYS,
) -> bool:
    """
    Menyemak sama ada teks penceritaan Bahasa Melayu yang serupa (>= 85% Cosine Similarity)
    pernah disiarkan dalam tempoh 2 hari lepas (172,800s) melalui Upstash Vector REST API.
    """
    if not story_text or len(story_text.strip()) < 40:
        return False

    vector_url, vector_token, err = get_vector_config()
    if err or not vector_url or not vector_token:
        print(f"⚠️ [VECTOR CONFIG WARN] {err}")
        return False

    query_url = f"{vector_url}/query-data"
    headers = {"Authorization": f"Bearer {vector_token}", "Content-Type": "application/json"}
    payload = {
        "data": str(story_text).strip(),
        "topK": 5,
        "includeMetadata": True,
    }

    try:
        res = requests.post(query_url, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            results = res.json().get("result", [])
            current_time = int(time.time())

            for match in results:
                score = match.get("score", 0.0)
                metadata = match.get("metadata", {}) or {}
                item_type = metadata.get("type", "")

                if item_type != "mama_reel_story":
                    continue

                posted_at = _safe_parse_timestamp(metadata.get("posted_at", 0))
                time_diff = current_time - posted_at if posted_at > 0 else 999999999

                if score >= threshold and time_diff < window_seconds:
                    matched_snippet = metadata.get("story_snippet", "Kapsyen Serupa")
                    hours_ago = time_diff / 3600
                    print(
                        f"⏭️ [VECTOR MATCH] Kapsyen bertema serupa dikesan ({score * 100:.1f}%) dengan: "
                        f"'{matched_snippet}' ({hours_ago:.1f} jam lepas < 2 Hari). Wajib jana semula."
                    )
                    return True
        else:
            print(f"⚠️ [VECTOR QUERY HTTP {res.status_code}]: {res.text[:80]}")
    except Exception as e:
        print(f"⚠️ [VECTOR CHECK WARN]: {e}")

    return False


def mark_story_vector_posted(story_id: str, story_text: str) -> bool:
    """
    Menyimpan vector embedding teks penceritaan Bahasa Melayu ke dalam Upstash Vector DB.
    ID Format: impianrumahku:vector:text_cooldown:<story_id>
    """
    if not story_id or not story_text:
        return False

    vector_url, vector_token, err = get_vector_config()
    if err or not vector_url or not vector_token:
        return False

    upsert_url = f"{vector_url}/upsert-data"
    headers = {"Authorization": f"Bearer {vector_token}", "Content-Type": "application/json"}

    current_time = int(time.time())
    snippet = story_text[:120] + "..." if len(story_text) > 120 else story_text
    doc_id = f"{VECTOR_PREFIX}:{str(story_id).strip()}"

    payload = {
        "id": doc_id,
        "data": str(story_text).strip(),
        "metadata": {
            "story_snippet": str(snippet),
            "posted_at": current_time,
            "type": "mama_reel_story",
        },
    }

    try:
        res = requests.post(upsert_url, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            print(f"🟢 [VECTOR SUCCESS] Embedding teks '{doc_id}' disimpan ke Vector DB (Penjara Cooldown 2 Hari).")
            return True
        else:
            print(f"⚠️ [VECTOR UPSERT HTTP {res.status_code}]: {res.text[:80]}")
    except Exception as e:
        print(f"⚠️ [VECTOR SAVE WARN]: {e}")

    return False


def delete_story_vector(story_id: str) -> bool:
    """
    Memadam rekod embedding teks daripada Vector DB (untuk tujuan rollback).
    """
    if not story_id:
        return False

    vector_url, vector_token, err = get_vector_config()
    if err or not vector_url or not vector_token:
        return False

    delete_url = f"{vector_url}/delete"
    headers = {"Authorization": f"Bearer {vector_token}", "Content-Type": "application/json"}
    doc_id = f"{VECTOR_PREFIX}:{str(story_id).strip()}"
    payload = {"ids": [doc_id]}

    try:
        res = requests.post(delete_url, json=payload, headers=headers, timeout=10)
        return res.status_code == 200
    except Exception:
        return False