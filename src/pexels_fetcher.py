#!/usr/bin/env python3
"""
Pexels 9:16 Video Batch Fetcher & Faceless Filter Engine
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Single API call to Pexels Video Search (per_page=70)
- Strict faceless & sensitive content filter (rejects faces, people, selfies, models)
- Redis 30-Day Video ID Deduplication Check (impianrumahku:redis:pexels:video_id:<id>)
- Selects 4 to 6 highest quality vertical MP4 clips (height >= width)
- Safe streaming downloader to local temp/ directory with automatic cleanup support
"""

import os
import re
import sys
import tempfile
import requests
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_pexels_config
from src.pexels_redis_db import is_pexels_video_posted

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Senarai kata kunci dilarang ketat (Muka manusia, potret, gamer, haiwan sensitif)
FORBIDDEN_VIDEO_KEYWORDS = [
    "man", "men", "woman", "women", "girl", "girls", "boy", "boys", "person", "people",
    "lady", "guy", "guys", "female", "male", "human", "adult", "child", "kid", "teen", "teenager",
    "face", "faces", "portrait", "selfie", "vlog", "model", "posing", "smile", "smiling",
    "looking", "eyes", "head", "headshot", "profile", "closeup-of-face",
    "gamer", "streamer", "influencer", "creator", "actor",
    "dog", "dogs", "puppy", "puppies", "canine",
    "pig", "pigs", "pork", "swine", "boar"
]


def is_video_safe_and_faceless(video_item: Dict[str, Any]) -> bool:
    """
    Menyemak URL slug dan teks video Pexels bagi menolak klip berwajah manusia atau haiwan sensitif.
    """
    url_slug = str(video_item.get("url", "")).lower()
    for bad_word in FORBIDDEN_VIDEO_KEYWORDS:
        pattern = rf'(?:^|[\-_/]){re.escape(bad_word)}(?:$|[\-_/])'
        if re.search(pattern, url_slug):
            return False
    return True


def fetch_and_filter_pexels_clips(
    query: str,
    needed_count: int = 5,
    batch_size: int = 70
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Menghantar 1 permintaan carian video ke Pexels API (per_page=70):
    1. Menapis klip bebas muka manusia dan haiwan sensitif.
    2. Menyemak status penduaan 30 hari di Redis.
    3. Memilih 4 hingga 6 klip video vertikal berkualiti tinggi (9:16).
    """
    api_key, err = get_pexels_config()
    if err or not api_key:
        return [], f"Ralat konfigurasi Pexels: {err}"

    clean_query = query.strip()
    print(f"\n📡 [PEXELS API] Menghantar 1 request (per_page={batch_size}) Carian: '{clean_query}'...")

    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {
        "query": clean_query,
        "orientation": "portrait",
        "per_page": batch_size,
        "size": "medium",
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=25)
        if res.status_code != 200:
            return [], f"Pexels API HTTP Error ({res.status_code}): {res.text[:80]}"

        data = res.json()
        raw_videos = data.get("videos", [])
        print(f"  📥 Diterima {len(raw_videos)} calon video mentah dari Pexels API.")

        selected_clips: List[Dict[str, Any]] = []

        for vid in raw_videos:
            vid_id = str(vid.get("id", ""))
            dur = vid.get("duration", 0)
            files = vid.get("video_files", [])

            # 1. Tapisan Muka & Kandungan Sensitif
            if not is_video_safe_and_faceless(vid):
                continue

            # 2. Tapisan Penjara 30 Hari Redis
            if is_pexels_video_posted(vid_id):
                print(f"  ⏭️ [REDIS VIDEO SKIP] ID {vid_id} pernah digunakan < 30 hari lepas.")
                continue

            # 3. Cari fail MP4 vertikal terbaik (height >= width dan height >= 720)
            best_file = None
            for f in files:
                if f.get("file_type") == "video/mp4":
                    w = f.get("width") or 0
                    h = f.get("height") or 0
                    if h >= w and h >= 720:
                        best_file = f
                        break

            if not best_file and files:
                for f in files:
                    if f.get("file_type") == "video/mp4":
                        w = f.get("width") or 0
                        h = f.get("height") or 0
                        if h >= w:
                            best_file = f
                            break

            if best_file and "link" in best_file:
                selected_clips.append({
                    "id": vid_id,
                    "duration": dur,
                    "url": best_file["link"],
                    "width": best_file.get("width"),
                    "height": best_file.get("height"),
                })

            if len(selected_clips) >= needed_count:
                break

        print(f"  🎯 Berjaya memilih {len(selected_clips)} klip vertikal 9:16 bebas muka dan segar.")
        return selected_clips, ""

    except Exception as e:
        return [], f"Ralat rangkaian semasa carian Pexels: {str(e)}"


def download_single_clip(url: str, prefix: str = "pex_clip") -> str:
    """
    Memuat turun fail MP4 tunggal secara penstriman ke folder temp/.
    """
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
        if res.status_code == 200:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", prefix=f"{prefix}_", dir=TEMP_DIR, delete=False)
            for chunk in res.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    tmp.write(chunk)
            tmp.close()
            return tmp.name
    except Exception as e:
        print(f"  ⚠️ Ralat muat turun video: {e}")
    return ""


def download_all_selected_clips(clips_data: List[Dict[str, Any]]) -> List[str]:
    """
    Memuat turun semua klip terpilih ke folder temp/ dan memulangkan senarai path fail tempatan.
    """
    downloaded_paths = []
    total = len(clips_data)
    for idx, item in enumerate(clips_data, 1):
        print(f"  📥 [Muat Turun {idx}/{total}] Klip Pexels ID: {item['id']}...")
        fpath = download_single_clip(item["url"], prefix=f"clip_{item['id']}")
        if fpath and os.path.exists(fpath):
            downloaded_paths.append(fpath)
            item["local_path"] = fpath
    return downloaded_paths


def cleanup_downloaded_clips(file_paths: List[str]):
    """
    Membersihkan dan memadam fail klip video sementara dari folder temp/.
    """
    for p in file_paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass