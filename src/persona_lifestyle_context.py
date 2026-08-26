#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Context, 5-Phase Mood Matrix & Themed Subreddit Engine
Location: src/persona_lifestyle_context.py

Features:
- Malaysian Time (MYT / UTC+8) Real-Time Synchronization.
- 5 Realistic Time-of-Day Phases:
  1. Pagi (05:00 - 11:59) -> Sarapan, sidai baju, mula rutin rumah.
  2. Tengah Hari (12:00 - 14:29) -> Cuaca terik, siap masak lauk, rehat sekejap.
  3. Petang (14:30 - 18:59) -> Minum petang, siram pokok laman, anak santai.
  4. Awal Malam / Makan Malam (19:00 - 21:29) -> Makan malam keluarga, kemas dapur (Bukan waktu tidur).
  5. Lewat Malam (21:30 - 04:59) -> Anak dah tidur, me-time Mama layan drama/rehat.
- 7-Day Day-Specific Persona Mood & Energy Matrix.
- 7 Lifestyle Niche Rotation Engine with 3-4 Curated Text-Idea Subreddits per niche.
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
    Mendapatkan waktu rasmi Malaysia (MYT / UTC+8) dengan pembahagian 5 fasa waktu yang tepat.
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
    minute = now.minute
    time_float = hour + (minute / 60.0)

    # 5 Fasa Waktu Realistik Malaysia
    if 5.0 <= time_float < 12.0:
        period = "Pagi"
        period_context = "Suasana pagi segar selepas selesai sarapan, sidai baju dan mula urusan kerja rumah."
    elif 12.0 <= time_float < 14.5:  # 12:00 PM - 02:29 PM
        period = "Tengah Hari"
        period_context = "Waktu tengah hari panas terik, rehat sekejap lepas siap masak lauk dapur dan kemas singki."
    elif 14.5 <= time_float < 19.0:  # 02:30 PM - 06:59 PM
        period = "Petang"
        period_context = "Waktu petang santai, nikmati minum petang keluarga, siram pokok di laman atau tengok anak main di luar."
    elif 19.0 <= time_float < 21.5:  # 07:00 PM - 09:29 PM
        period = "Awal Malam"
        period_context = "Waktu makan malam keluarga, kemas meja makan dan dapur lepas makan, atau sembang santai di ruang tamu bersama anak-anak."
    else:  # 09:30 PM - 04:59 AM
        period = "Lewat Malam"
        period_context = "Waktu lewat malam tenang bila anak-anak dah tidur, masa me-time Mama berehat layan drama atau belek telefon."

    formatted_str = f"{day_name}, {now.day} {month_name} {now.year}, {now.strftime('%I:%M %p')}"

    return {
        "timestamp": int(now.timestamp()),
        "day_name": day_name,
        "day_index": now.weekday(),  # 0 = Isnin, 6 = Ahad
        "date_str": f"{now.day} {month_name} {now.year}",
        "time_str": now.strftime("%I:%M %p"),
        "hour": hour,
        "minute": minute,
        "period": period,
        "period_context": period_context,
        "formatted_full": formatted_str
    }


def get_daily_mood_matrix(day_index: int, period: str) -> Dict[str, str]:
    """
    Menjana tona emosi (mood) mengikut hari dan 5 fasa waktu harian.
    """
    mood_map = {
        0: {  # Isnin
            "mood_name": "Semangat Bermula & Ruang Kemas",
            "tone": "Positif, kemas, bersedia mulakan minggu baharu dengan tenang dan praktikal."
        },
        1: {  # Selasa
            "mood_name": "Produktif, Dapur & Resepi Jimat",
            "tone": "Fokus pada pengurusan dapur, tip jimat masa, bahan dapur dan susun atur rapi."
        },
        2: {  # Rabu
            "mood_name": "Santai Pertengahan Minggu & Laman Hijau",
            "tone": "Santai, bersahaja, berkongsi rasa seronok bila kerja rumah siap awal sambil belek pokok."
        },
        3: {  # Khamis
            "mood_name": "Kreatif, DIY & Tambah Pendapatan",
            "tone": "Praktikal, idea susun atur kreatif, kongsi tips jimat belanja dan barang berguna rumah."
        },
        4: {  # Jumaat
            "mood_name": "Ceria, Syukur & Masakan Istimewa",
            "tone": "Penuh kesyukuran, suasana ceria menyambut hujung minggu dengan hidangan sedap."
        },
        5: {  # Sabtu
            "mood_name": "Keluarga, Anak-anak & Santai Hujung Minggu",
            "tone": "Ceria, riang luangkan masa berkualiti dengan anak-anak dan aktiviti santai di rumah."
        },
        6: {  # Ahad
            "mood_name": "Me-Time, Refleksi & Ketenangan Rumah",
            "tone": "Tenang, santai di sudut kegemaran rumah, bersiap sedia untuk minggu baharu."
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
    Memilih niche penceritaan dan 3-4 subreddit sumber idea teks mengikut matriks 7 hari x 5 fasa waktu.
    """
    niches = {
        "tanaman": {
            "title": "Tanaman, Bunga & Terapi Laman Hijau",
            "prompt_hook": "Cerita pengalaman jaga pokok hiasan, pasu gantung, tip siram air, siram baja, dan daun segar di balkoni atau laman rumah.",
            "subreddits": ["houseplants", "IndoorGarden", "gardening", "succulents"]
        },
        "makanan": {
            "title": "Makanan, Resepi Ringkas & Dapur Mama",
            "prompt_hook": "Cerita aroma masakan harian, resepi lauk jimat bahan dapur, tips perap lauk mudah, atau idea minum petang keluarga.",
            "subreddits": ["MalaysianFood", "food", "FoodPorn", "Baking", "Cooking"]
        },
        "diy": {
            "title": "DIY Rumah, Susun Atur & Jimat Ruang",
            "prompt_hook": "Idea susun laci, perabot kecil kemas rapi, susun atur ruang sempit jadi sedap mata memandang, dan guna barang terpakai.",
            "subreddits": ["organization", "DIY", "CozyPlaces", "declutter"]
        },
        "affiliate_santai": {
            "title": "Tip Tambah Pendapatan Sampingan & Barang Berguna",
            "prompt_hook": "Pengalaman suri rumah tambah duit belanja dapur secara santai dari rumah dan kongsi barang praktikal yang memudahkan kerja harian.",
            "subreddits": ["Frugal", "sidehustle", "organization", "simpleliving"]
        },
        "movie_drama": {
            "title": "Santai Me-Time, Movie & Drama Melayu",
            "prompt_hook": "Ulasan santai drama petang atau filem keluarga waktu me-time berehat di ruang tamu.",
            "subreddits": ["television", "movies", "CasualConversation", "CozyPlaces"]
        },
        "hal_semasa": {
            "title": "Hal Semasa, Cuaca & Suasana Kejiranan",
            "prompt_hook": "Bercakap santai tentang cuaca harian, harga barang dapur semasa, atau suasana damai di kawasan perumahan.",
            "subreddits": ["malaysia", "CasualConversation", "simpleliving", "CozyPlaces"]
        },
        "santai_keluarga": {
            "title": "Santai Anak, Rumah Tangga & Hujung Minggu",
            "prompt_hook": "Aktiviti santai bersama anak-anak di rumah, sediakan kudapan, atau luahan rasa bahagia menguruskan keluarga.",
            "subreddits": ["Parenting", "happy", "CasualConversation", "CozyPlaces"]
        }
    }

    if force_niche and force_niche in niches:
        chosen_key = force_niche
    else:
        # Penjadualan Pintar 7 Hari x 5 Fasa (Pagi, Tengah Hari, Petang, Awal Malam, Lewat Malam)
        schedule_matrix = {
            0: ["diy", "makanan", "tanaman", "hal_semasa", "movie_drama"],             # Isnin: Kemas & Produktif
            1: ["makanan", "diy", "makanan", "affiliate_santai", "movie_drama"],       # Selasa: Dapur & Resepi
            2: ["tanaman", "makanan", "tanaman", "santai_keluarga", "affiliate_santai"], # Rabu: Pokok & Laman
            3: ["affiliate_santai", "diy", "affiliate_santai", "hal_semasa", "movie_drama"], # Khamis: DIY & Duit Poket
            4: ["makanan", "makanan", "santai_keluarga", "makanan", "movie_drama"],     # Jumaat: Masakan & Jamuan
            5: ["santai_keluarga", "makanan", "santai_keluarga", "hal_semasa", "santai_keluarga"], # Sabtu: Aktiviti Anak
            6: ["tanaman", "diy", "tanaman", "santai_keluarga", "tanaman"],             # Ahad: Me-Time & Laman
        }

        period_idx_map = {
            "Pagi": 0,
            "Tengah Hari": 1,
            "Petang": 2,
            "Awal Malam": 3,
            "Lewat Malam": 4
        }
        period_idx = period_idx_map.get(period, 0)
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
    Mengambil 3-5 topik/ayat terakhir dari Upstash Redis list untuk dijadikan memori AI agar tidak berulang.
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
    Membina payload konteks menyeluruh untuk disalurkan terus kepada enjin AI dan Unsplash.
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
            "language_rule": "Bahasa Melayu harian Malaysia tulen sahaja. WAJIB bahasakan diri 'Mama'. DILARANG guna istilah Indonesia, DILARANG emoji, DILARANG simbol asing."
        }
    }

    return payload


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Konteks 5 Fasa Waktu Persona Lifestyle...")
    print("=" * 70)
    ctx = build_lifestyle_context_payload()
    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    print("=" * 70)