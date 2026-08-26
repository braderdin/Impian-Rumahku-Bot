#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Unsplash Visual Engine & Anti-Face Filter (Module 3)
Location: src/persona_lifestyle_image_engine.py

Features:
- AI Keyword Generator: Reads the Reddit idea context from temp/step1_reddit_context.json and generates 10 Unsplash visual search keywords in English.
- 40-Pool Ingestion: Makes 1 API request to Unsplash to fetch 40 photos matching the top keyword.
- Anti-Face Filter: Inspects image tags, descriptions, and metadata to reject human portraits/selfies (allowing only hands, food, plants, or interior styling).
- Redis 30-Day Dedup: Rejects Unsplash photo IDs used within the past 30 days via Upstash Redis REST API.
- Fast Compression: Selects the best matching image, compresses it to strictly < 50 KB (or 20-30 KB for multi-image groups), and saves it to temp/curated_unsplash.jpg.
- Step-by-Step Payload Storage: Saves image curation metadata to temp/step3_image_payload.json.
"""

import os
import re
import sys
import json
import time
import html
import random
import requests
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
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
TEMP_DIR.mkdir(parents=True, exist_ok=True)
STEP1_FILE = TEMP_DIR / "step1_reddit_context.json"
STEP3_OUTPUT_FILE = TEMP_DIR / "step3_image_payload.json"
CURATED_IMAGE_PATH = TEMP_DIR / "curated_unsplash.jpg"

# Senarai Tag Wajah Yang Ditegah (Anti-Face Filter)
FORBIDDEN_FACE_TAGS = {
    "face", "portrait", "smiling", "smile", "woman looking", "man looking",
    "close up face", "selfie", "girl looking at camera", "guy looking at camera",
    "facial expression", "headshot", "lip", "eyes looking", "model looking",
    "human face", "female portrait", "male portrait", "front face", "person looking"
}

ALLOWED_HUMAN_ANGLE_TAGS = {
    "hands typing", "back view", "rear view", "silhouette", "over the shoulder",
    "person typing", "sitting desk back", "unrecognizable person", "from behind", "cooking hands"
}

SAFE_TECH_KEYWORDS = [
    "minimalist cozy kitchen setup",
    "indoor house plants aesthetic",
    "warm wooden dining table",
    "cleaning and organizing home",
    "fresh herbs in ceramic pots",
    "simple rustic home cooking",
    "cozy living room daylight",
    "scandinavian interior styling"
]


def compress_image_to_target_kb(
    input_source: Any,
    output_path: Path,
    max_kb: int = 40
) -> Tuple[bool, str, int]:
    """
    Memampatkan imej kepada resolusi optimum dan saiz di bawah 40KB (atau 20-30 KB).
    """
    try:
        if isinstance(input_source, (str, Path)):
            img = Image.open(input_source)
        else:
            img = Image.open(BytesIO(input_source))

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Hadkan dimensi maksimum 480px untuk menjimatkan ruang & kelajuan VLM
        img.thumbnail((480, 480), Image.Resampling.LANCZOS)

        quality = 75
        final_size_kb = 0
        while quality >= 15:
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            size_kb = len(buffer.getvalue()) / 1024.0

            if size_kb <= max_kb or quality <= 15:
                with open(output_path, "wb") as f_out:
                    f_out.write(buffer.getvalue())
                final_size_kb = int(size_kb)
                break

            quality -= 10
            if quality < 50:
                img.thumbnail((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)

        return True, str(output_path), final_size_kb
    except Exception as e:
        print(f"⚠️ [IMAGE COMPRESS ERROR] {e}")
        return False, "", 0


def is_unsplash_id_posted(photo_id: str) -> bool:
    """Semak sama ada ID foto Unsplash pernah digunakan dalam tempoh 30 hari menerusi Redis."""
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not redis_url or not redis_token or not photo_id:
        return False

    endpoint = f"{redis_url.rstrip('/')}/"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["GET", f"posted:unsplash:{photo_id}"]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=6)
        if res.status_code == 200:
            return res.json().get("result") is not None
    except Exception:
        pass
    return False


def mark_unsplash_id_posted(photo_id: str, ttl_seconds: int = 2592000) -> bool:
    """Merekodkan ID foto Unsplash ke Redis dengan TTL 30 hari."""
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()

    if not redis_url or not redis_token or not photo_id:
        return False

    endpoint = f"{redis_url.rstrip('/')}/"
    headers = {"Authorization": f"Bearer {redis_token}", "Content-Type": "application/json"}
    payload = ["SET", f"posted:unsplash:{photo_id}", "1", "EX", str(ttl_seconds)]

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=6)
        return res.status_code == 200 and res.json().get("result") == "OK"
    except Exception:
        return False


def extract_json_array_robust(text: str) -> List[str]:
    """Mengekstrak senarai JSON array secara selamat daripada output model AI."""
    if not text:
        return []

    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    clean_text = re.sub(r"```json\s*", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"```\s*", "", clean_text)

    match = re.search(r"\[[\s\S]*?\]", clean_text)
    if match:
        try:
            parsed = json.loads(match.group(0).strip())
            if isinstance(parsed, list):
                result = []
                for item in parsed:
                    kw = " ".join(str(item).strip().split()[:3])
                    kw = re.sub(r"[^a-zA-Z0-9\s]", "", kw).strip().lower()
                    if len(kw) >= 3:
                        result.append(kw)
                if len(result) >= 3:
                    return result
        except Exception:
            pass

    fallback_matches = re.findall(r"[\"']([a-zA-Z0-9\s]{3,35})[\"']", clean_text)
    cleaned_fallback = []
    for item in fallback_matches:
        kw = " ".join(item.strip().split()[:3]).lower()
        if len(kw) >= 3 and kw not in cleaned_fallback:
            cleaned_fallback.append(kw)

    return cleaned_fallback if len(cleaned_fallback) >= 3 else SAFE_TECH_KEYWORDS


def generate_10_visual_keywords(title: str, description: str) -> List[str]:
    """
    Menggunakan OpenRouter Primary (dibaca daripada env) untuk menjana 10 kata kunci carian Unsplash.
    """
    base_url = os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
    api_key = os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
    model = os.getenv("IRCM_MODEL_PRIMARY", "").strip()

    if not base_url or not api_key or not model:
        return SAFE_TECH_KEYWORDS

    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }

    system_prompt = (
        "You are a Visual Director. Read the topic summary and generate EXACTLY 10 visual search keywords for Unsplash in English (2 to 3 words each).\n"
        "RULES:\n"
        "- Cozy, aesthetic, home, kitchen, plants, room styling, food, or lifestyle oriented.\n"
        "- NO personal names, no memes.\n"
        "- OUTPUT FORMAT: JSON Array of 10 strings ONLY.\n"
        "[\"keyword 1\", \"keyword 2\", ..., \"keyword 10\"]"
    )

    user_prompt = f"Topic Title: {title}\nSummary: {description[:300]}\n\nGenerate JSON Array with 10 Unsplash keywords:"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 250
    }

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            raw_content = res.json()["choices"][0]["message"]["content"].strip()
            keywords = extract_json_array_robust(raw_content)
            if keywords:
                return keywords
    except Exception as e:
        print(f"⚠️ [KEYWORD GEN ERROR] {e}")

    return SAFE_TECH_KEYWORDS


def is_photo_face_free(photo_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Memeriksa metadata foto Unsplash untuk menolak potret wajah / swafoto."""
    alt_desc = (photo_data.get("alt_description") or "").lower()
    desc = (photo_data.get("description") or "").lower()
    tags = photo_data.get("tags", [])
    tag_titles = [t.get("title", "").lower() for t in tags if isinstance(t, dict)]

    combined_text = f"{alt_desc} {desc} {' '.join(tag_titles)}"

    for forbidden in FORBIDDEN_FACE_TAGS:
        if re.search(r'\b' + re.escape(forbidden) + r'\b', combined_text):
            if any(allowed in combined_text for allowed in ALLOWED_HUMAN_ANGLE_TAGS):
                return True, "Dibenarkan (Sudut Tangan / Belakang)"
            return False, f"Ditolak (Dikesan Wajah: '{forbidden}')"

    return True, "Lulus (Sifar Wajah)"


def fetch_unsplash_images(keyword: str, access_key: str, count: int = 40) -> List[Dict[str, Any]]:
    """Membuat 1 panggilan API ke Unsplash untuk menarik 40 keping gambar."""
    if not access_key:
        return []

    url = "https://api.unsplash.com/search/photos"
    params = {"query": keyword, "per_page": count, "page": 1, "client_id": access_key}

    try:
        res = requests.get(url, params=params, timeout=12)
        if res.status_code == 200:
            return res.json().get("results", [])
    except Exception as e:
        print(f"❌ [UNSPLASH API ERROR]: {e}")

    return []


def select_and_curate_unsplash_image() -> Optional[Dict[str, Any]]:
    """
    Modul Utama Step 3:
    - Membaca temp/step1_reddit_context.json
    - Menjana 10 kata kunci AI
    - Menarik 40 gambar dari Unsplash
    - Menapis anti-wajah dan semak Redis dedup 30 hari
    - Memampatkan imej terbaik ke < 50KB dan menyimpannya ke temp/curated_unsplash.jpg
    """
    if not STEP1_FILE.exists():
        print("⚠️ [STEP 3] Fail rujukan temp/step1_reddit_context.json tidak dijumpai.")
        return None

    try:
        with open(STEP1_FILE, "r", encoding="utf-8") as f:
            reddit_data = json.load(f)
    except Exception as e:
        print(f"⚠️ [STEP 3] Gagal membaca fail step1: {e}")
        return None

    title = reddit_data.get("title", "Rutin Harian Mama")
    description = reddit_data.get("description", "Inspirasi kehidupan suri rumah")

    # Membaca kunci IRCM_UNSPLASH_ACCESS_KEY
    unsplash_access_key = os.getenv("IRCM_UNSPLASH_ACCESS_KEY", "").strip() or os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    if not unsplash_access_key:
        print("⚠️ [STEP 3 WARN] Kunci IRCM_UNSPLASH_ACCESS_KEY tiada dalam persekitaran.")
        return None

    print(f"🔍 [STEP 3] Menjana 10 kata kunci visual berdasarkan tajuk: '{title[:40]}...'")
    keywords = generate_10_visual_keywords(title, description)

    selected_image_info = None

    for kw_idx, kw in enumerate(keywords[:3], 1):
        print(f"  📡 [Unsplash Query {kw_idx}/3]: Mencari 40 gambar bagi '{kw}'...")
        photos = fetch_unsplash_images(kw, unsplash_access_key, count=40)
        if not photos:
            continue

        scored = []
        context_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', f"{title} {description}".lower()))

        for photo in photos:
            photo_id = photo.get("id")
            img_url = photo.get("urls", {}).get("regular") or photo.get("urls", {}).get("full")
            if not photo_id or not img_url:
                continue

            # 1. Penapis Anti-Wajah Manusia
            is_face_free, _ = is_photo_face_free(photo)
            if not is_face_free:
                continue

            # 2. Semakan Dedup Redis (30 Hari)
            if is_unsplash_id_posted(photo_id):
                continue

            # 3. Kira Skor Keserasian
            alt_desc = (photo.get("alt_description") or photo.get("description") or "").lower()
            photo_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', alt_desc))
            relevance = len(photo_words.intersection(context_words))
            likes = photo.get("likes", 0)
            score = (relevance * 15) + min(likes, 50)

            scored.append({"score": score, "photo": photo, "url": img_url, "id": photo_id, "kw": kw})

        if scored:
            scored.sort(key=lambda x: x["score"], reverse=True)
            best = scored[0]
            
            # Muat turun dan mampatkan imej ke bawah 40KB
            try:
                img_res = requests.get(best["url"], timeout=15)
                if img_res.status_code == 200 and len(img_res.content) > 1000:
                    comp_ok, comp_path, comp_kb = compress_image_to_target_kb(img_res.content, CURATED_IMAGE_PATH, max_kb=40)
                    if comp_ok:
                        mark_unsplash_id_posted(best["id"])
                        selected_image_info = {
                            "source": "UNSPLASH_API",
                            "photo_id": best["id"],
                            "keyword_used": best["kw"],
                            "local_path": comp_path,
                            "size_kb": comp_kb,
                            "author": best["photo"].get("user", {}).get("name", "Unsplash Creator"),
                            "description": best["photo"].get("alt_description", best["kw"])
                        }
                        print(f"  🟢 [UNSPLASH WINNER] Gambar dipilih & dimampatkan ({comp_kb} KB) di {comp_path}")
                        break
            except Exception as e:
                print(f"  ⚠️ [IMAGE DOWNLOAD EXCEPTION]: {e}")

    # Jika gagal dengan kata kunci AI, guna sandaran selamat
    if not selected_image_info:
        fallback_kw = random.choice(SAFE_TECH_KEYWORDS)
        print(f"  🛡️ [Unsplash Fallback]: Mencuba kelompok selamat '{fallback_kw}'...")
        photos = fetch_unsplash_images(fallback_kw, unsplash_access_key, count=40)
        if photos:
            valid_photos = [p for p in photos if is_photo_face_free(p)[0] and not is_unsplash_id_posted(p.get("id"))]
            if valid_photos:
                chosen = random.choice(valid_photos)
                img_url = chosen["urls"].get("regular")
                try:
                    img_res = requests.get(img_url, timeout=15)
                    if img_res.status_code == 200:
                        comp_ok, comp_path, comp_kb = compress_image_to_target_kb(img_res.content, CURATED_IMAGE_PATH, max_kb=40)
                        if comp_ok:
                            mark_unsplash_id_posted(chosen.get("id"))
                            selected_image_info = {
                                "source": "UNSPLASH_EMERGENCY",
                                "photo_id": chosen.get("id"),
                                "keyword_used": fallback_kw,
                                "local_path": comp_path,
                                "size_kb": comp_kb,
                                "author": chosen.get("user", {}).get("name", "Unsplash Creator"),
                                "description": fallback_kw
                            }
                except Exception:
                    pass

    if selected_image_info:
        try:
            with open(STEP3_OUTPUT_FILE, "w", encoding="utf-8") as f_out:
                json.dump(selected_image_info, f_out, indent=2, ensure_ascii=False)
            print(f"💾 [STEP 3 PAYLOAD] Maklumat imej disimpan ke: {STEP3_OUTPUT_FILE.name}")
        except Exception as e:
            print(f"⚠️ [STEP 3 WARN] Gagal menyimpan fail JSON payload: {e}")

        return selected_image_info

    print("❌ [STEP 3 ERROR] Gagal mendapatkan imej Unsplash yang sah.")
    return None


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Modul Visual Unsplash & Anti-Face Filter (Step 3)...")
    print("=" * 70)
    res = select_and_curate_unsplash_image()
    if res:
        print("\n✅ PEMILIHAN IMEJ BERJAYA:")
        print(f"ID Foto   : {res['photo_id']}")
        print(f"Kata Kunci: {res['keyword_used']}")
        print(f"Fail Storan: {res['local_path']} (~{res['size_kb']} KB)")
    else:
        print("\n❌ Gagal memilih imej.")
    print("=" * 70)