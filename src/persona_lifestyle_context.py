#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Context, Mood Matrix & Memory Engine
Location: src/persona_lifestyle_context.py

Features:
- Malaysian Time (MYT / UTC+8) Real-Time Synchronization.
- 7-Day Day-Specific Persona Mood & Energy Matrix.
- 4-Phase Time-of-Day Context (Pagi, Tengah Hari, Petang, Malam).
- 7 Lifestyle Niche Rotation Engine.
- Dynamic Memory Buffer: Retrieves 3-5 latest generated topics from Upstash Redis.
- Zero Hardcoded Keys: Reads dynamically from environment (.env.local / GitHub Secrets).
"""

import os
import sys
import json
import random
import requests
from datetime import datetime, timezone, timedelta
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

REDIS_RECENT_TOPICS_KEY = "impianrumahku:redis:lifestyle:recent_topics"


def get_myt_datetime_info() -> Dict[str, Any]:
    """
    Mendapatkan waktu rasmi Malaysia (MYT / UTC+8) beserta fasa waktu.
    """
    myt_zone = timezone(timedelta(hours=8))
    now = datetime.now(myt_zone)

    days_bm = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
    months_bm = [
        "Januari", "Februari", "Mac", "April", "Mei", "Jun",
        "Julai", "Ogos", "September", "Oktober", "November", "Disember"
    ]

    day_name = days_bm[now.weekday()]
    month_name = months_bm[now.month - 1]
    hour = now.hour

    if 5 <= hour < 12:
        period = "Pagi"
        period_context = "Suasana pagi tenang selepas urus anak ke sekolah atau sarapan ringan."
    elif 12 <= hour < 14:
        period = "Tengah Hari"
        period_context = "Waktu tengah hari, rehat sekejap lepas masak lauk tengah hari atau mengemas dapur."
    elif 14 <= hour < 19:
        period = "Petang"
        period_context = "Waktu petang santai, siram pokok di laman atau sediakan minum petang untuk keluarga."
    else:
        period = "Malam"
        period_context = "Waktu malam tenang bila anak-anak dah tidur, masa me-time sambil layan drama atau rehatkan badan."

    formatted_str = f"{day_name}, {now.day} {month_name} {now.year}, {now.strftime('%I:%M %p')}"

    return {
        "timestamp": int(now.timestamp()),
        "day_name": day_name,
        "day_index": now.weekday(),  # 0 = Isnin, 6 = Ahad
        "date_str": f"{now.day} {month_name} {now.year}",
        "time_str": now.strftime("%I:%M %p"),
        "hour": hour,
        "period": period,
        "period_context": period_context,
        "formatted_full": formatted_str
    }


def get_daily_mood_matrix(day_index: int, period: str) -> Dict[str, str]:
    """
    Menjana tona emosi (*mood*) dan fokus penceritaan mengikut hari dan waktu harian.
    """
    mood_map = {
        0: {  # Isnin
            "mood_name": "Semangat Bermula & Praktikal",
            "tone": "Positif, kemas, bersedia mulakan minggu baharu dengan tenang tanpa kelam-kabut."
        },
        1: {  # Selasa
            "mood_name": "Produktif & Teratur",
            "tone": "Fokus pada rutin harian rumah tangga, tip penjimatan masa dan ruang."
        },
        2: {  # Rabu
            "mood_name": "Santai Pertengahan Minggu",
            "tone": "Santai, bersahaja, berkongsi rasa lega bila kerja rumah selesai awal."
        },
        3: {  # Khamis
            "mood_name": "Refleksi & Persediaan Hujung Minggu",
            "tone": "Tenang, berkongsi rancangan rehat dan idea mudah untuk dapur dan keluarga."
        },
        4: {  # Jumaat
            "mood_name": "Ceria, Syukur & Bersih",
            "tone": "Penuh kesyukuran, suasana kemas rumah sebelum hujung minggu tiba."
        },
        5: {  # Sabtu
            "mood_name": "Keluarga, Masakan & Aktiviti Santai",
            "tone": "Ceria, santai luangkan masa dengan anak-anak, berjalan atau eksperimen dapur."
        },
        6: {  # Ahad
            "mood_name": "Me-Time, Kebun & Persediaan Mental",
            "tone": "Tenang, rawat pokok bunga, kemas bilik santai, persiapan menghadapi minggu baru."
        }
    }

    selected = mood_map.get(day_index, mood_map[0])
    return {
        "mood_name": selected["mood_name"],
        "tone_description": selected["tone"],
        "time_phase": period
    }


def get_niche_rotation(day_index: int, period: str, force_niche: Optional[str] = None) -> Dict[str, Any]:
    """
    Memilih niche penceritaan daripada 7 niche utama secara seimbang mengikut matriks waktu.
    """
    niches = {
        "tanaman": {
            "title": "Tanaman, Bunga & Pasu Hiasan",
            "prompt_hook": "Cerita pengalaman jaga pokok hiasan, pasu gantung, tip siram air, atau daun layu kembali segar di balkoni/laman.",
            "subreddits": ["houseplants", "gardening"]
        },
        "makanan": {
            "title": "Makanan, Resepi Ringkas & Dapur Mama",
            "prompt_hook": "Cerita aroma masakan harian, resepi jimat bahan dapur, cara perap lauk mudah, atau idea minum petang.",
            "subreddits": ["MalaysianFood", "EatCheapAndHealthy"]
        },
        "diy": {
            "title": "DIY Rumah & Solusi Jimat Ruang",
            "prompt_hook": "Projek susun atur perabot kecil, betulkan susunan laci, guna barang terpakai jadi bekas berguna.",
            "subreddits": ["DIY", "organization"]
        },
        "affiliate_santai": {
            "title": "Tip Tambah Pendapatan Sampingan & Affiliate",
            "prompt_hook": "Pengalaman suri rumah tambah duit belanja dapur secara santai dari rumah, kongsi link barang berguna tanpa rasa terpaksa.",
            "subreddits": ["sidehustle", "Frugal"]
        },
        "movie_drama": {
            "title": "Santai Movie & Drama Melayu",
            "prompt_hook": "Bercakap santai tentang jalan cerita drama petang atau filem keluarga yang ditonton waktu rehat malam.",
            "subreddits": ["movies", "television"]
        },
        "hal_semasa": {
            "title": "Hal Semasa & Cuaca Harian",
            "prompt_hook": "Komen santai tentang cuaca panas terik atau hujan lebat, harga barang dapur semasa, atau suasana kejiranan.",
            "subreddits": ["malaysia", "CasualConversation"]
        },
        "santai_keluarga": {
            "title": "Santai Anak, Berjalan & Piknik",
            "prompt_hook": "Aktiviti bersama anak-anak di rumah, bawa keluarga jalan taman, atau luahan penat tapi bahagia jadi ibu.",
            "subreddits": ["Parenting", "happy"]
        }
    }

    if force_niche and force_niche in niches:
        chosen_key = force_niche
    else:
        # Penjadualan niche pintar mengikut waktu & hari
        schedule_matrix = {
            0: ["tanaman", "makanan", "affiliate_santai", "santai_keluarga"],
            1: ["makanan", "diy", "hal_semasa", "movie_drama"],
            2: ["diy", "tanaman", "makanan", "affiliate_santai"],
            3: ["affiliate_santai", "hal_semasa", "diy", "movie_drama"],
            4: ["makanan", "tanaman", "santai_keluarga", "hal_semasa"],
            5: ["santai_keluarga", "makanan", "diy", "movie_drama"],
            6: ["tanaman", "santai_keluarga", "affiliate_santai", "tanaman"],
        }
        period_idx = {"Pagi": 0, "Tengah Hari": 1, "Petang": 2, "Malam": 3}.get(period, 0)
        daily_pool = schedule_matrix.get(day_index, schedule_matrix[0])
        chosen_key = daily_pool[period_idx % len(daily_pool)]

    info = niches[chosen_key]
    return {
        "niche_key": chosen_key,
        "niche_title": info["title"],
        "prompt_hook": info["prompt_hook"],
        "suggested_subreddits": info["subreddits"]
    }


def fetch_recent_topic_memories(limit: int = 4) -> List[str]:
    """
    Mengambil 3-5 topik/ayat terakhir dari Upstash Redis list untuk dijadikan memori AI.
    """
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not redis_url or not redis_token:
        return []

    endpoint = f"{redis_url.rstrip('/')}/"
    headers = {
        "Authorization": f"Bearer {redis_token}",
        "Content-Type": "application/json",
    }
    payload = ["LRANGE", REDIS_RECENT_TOPICS_KEY, "0", str(limit - 1)]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=8)
        if res.status_code == 200:
            result = res.json().get("result", [])
            if isinstance(result, list):
                return [str(item) for item in result if item]
    except Exception as e:
        print(f"⚠️ [MEMORY BUFFER WARN] Gagal memuat turun memori topik dari Redis: {e}")

    return []


def build_lifestyle_context_payload(
    force_niche: Optional[str] = None,
    reddit_source: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Membina payload konteks menyeluruh untuk disalurkan terus kepada enjin penjanaan AI.
    """
    dt_info = get_myt_datetime_info()
    mood_info = get_daily_mood_matrix(dt_info["day_index"], dt_info["period"])
    niche_info = get_niche_rotation(dt_info["day_index"], dt_info["period"], force_niche=force_niche)
    recent_memories = fetch_recent_topic_memories(limit=4)

    payload = {
        "datetime": dt_info,
        "mood": mood_info,
        "niche": niche_info,
        "recent_memories": recent_memories,
        "reddit_source": reddit_source or {},
        "persona_profile": {
            "name": "Mama",
            "community": "Impian Rumahku & Cerita Mama",
            "identity": "Wanita Melayu awal 30-an, suri rumah berdikari, mesra, praktikal, dan bercakap santai tanpa gaya kaku.",
            "language_rule": "Bahasa Melayu harian Malaysia tulen sahaja. DILARANG guna istilah Indonesia, DILARANG emoji, DILARANG simbol asing."
        }
    }

    return payload


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Konteks & Memori Persona Lifestyle...")
    print("=" * 70)
    ctx = build_lifestyle_context_payload()
    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    print("=" * 70)