#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Reddit Topic & Visual Curator Engine
Location: src/persona_lifestyle_reddit_reader.py

Features:
- Fetches trending/hot clean community posts from curated subreddits.
- Filters out NSFW, stickied/mod posts, and video-only posts.
- Extracts clean English context & title for AI adaptation.
- Downloads and compresses up to 4 images to strictly < 50KB each.
- Integrates with persona_lifestyle_filter to skip previously used posts.
- Zero Hardcoded API Keys: Uses standard Reddit public JSON endpoints with custom User-Agent.
"""

import os
import re
import sys
import time
import base64
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

# Import Penapis Dwi-Lapisan
from src.persona_lifestyle_filter import is_lifestyle_topic_duplicate

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def clean_reddit_text(text: str) -> str:
    """
    Membersihkan markdown, pautan luar, dan aksara pelik daripada teks Reddit.
    """
    if not text:
        return ""
    # Buang URL markdown [text](http://...)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Buang URL langsung
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Buang tag spoiler dan format reddit
    cleaned = re.sub(r">!|!<|#|\*|_|~", "", cleaned)
    # Buang aksara bukan Latin/standard
    cleaned = re.sub(r"[^\x00-\x7F]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def compress_image_to_under_50kb(
    input_source: Any,
    output_path: Path,
    max_kb: int = 50
) -> Tuple[bool, str, int]:
    """
    Memampatkan imej kepada resolusi optimum dan saiz di bawah 50KB.
    """
    try:
        if isinstance(input_source, (str, Path)):
            img = Image.open(input_source)
        else:
            img = Image.open(BytesIO(input_source))

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Hadkan dimensi maksimum 480px untuk menjimatkan token visual AI
        img.thumbnail((480, 480), Image.Resampling.LANCZOS)

        quality = 80
        final_size_kb = 0
        while quality >= 20:
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            size_kb = len(buffer.getvalue()) / 1024.0

            if size_kb <= max_kb or quality <= 20:
                with open(output_path, "wb") as f_out:
                    f_out.write(buffer.getvalue())
                final_size_kb = int(size_kb)
                break

            quality -= 10
            if quality < 50:
                img.thumbnail((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)

        return True, str(output_path), final_size_kb
    except Exception as e:
        print(f"⚠️ [IMG COMPRESS ERROR] {e}")
        return False, "", 0


def extract_media_urls_from_reddit_post(post_data: Dict[str, Any]) -> List[str]:
    """
    Mengekstrak sehingga 4 URL imej statik daripada pos Reddit (tunggal atau galeri).
    """
    image_urls = []
    
    # 1. Semak pos galeri (media_metadata)
    media_metadata = post_data.get("media_metadata", {})
    gallery_data = post_data.get("gallery_data", {}).get("items", [])
    
    if media_metadata and gallery_data:
        for item in gallery_data[:4]:
            media_id = item.get("media_id")
            m_info = media_metadata.get(media_id, {})
            # Ambil URL resolusi tertinggi yang sedia ada
            s_info = m_info.get("s", {})
            raw_url = s_info.get("u") or s_info.get("gif")
            if raw_url:
                clean_url = raw_url.replace("&amp;", "&")
                image_urls.append(clean_url)
        if image_urls:
            return image_urls

    # 2. Semak URL langsung (url_overridden_by_dest / url)
    direct_url = post_data.get("url_overridden_by_dest") or post_data.get("url", "")
    if any(direct_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        image_urls.append(direct_url)
        return image_urls

    # 3. Semak preview images
    preview_images = post_data.get("preview", {}).get("images", [])
    if preview_images:
        source_url = preview_images[0].get("source", {}).get("url", "")
        if source_url:
            image_urls.append(source_url.replace("&amp;", "&"))

    return image_urls[:4]


def fetch_curated_reddit_post(
    subreddits: List[str],
    require_image: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Mengimbas subreddit terpilih, menapis pos yang belum pernah digunakan,
    dan memulangkan satu pos yang bersih serta sah untuk dijadikan inspirasi AI.
    """
    headers = {"User-Agent": USER_AGENT}

    for sub in subreddits:
        endpoint = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
        print(f"📡 [REDDIT READER] Menyemak komuniti: r/{sub}...")

        try:
            res = requests.get(endpoint, headers=headers, timeout=12)
            if res.status_code != 200:
                print(f"⚠️ [REDDIT HTTP {res.status_code}] r/{sub}: {res.text[:80]}")
                continue

            data = res.json().get("data", {}).get("children", [])
            if not data:
                continue

            for child in data:
                p = child.get("data", {})
                # Tapis pos moderator, NSFW atau stickied
                if p.get("stickied") or p.get("over_18") or p.get("is_video"):
                    continue

                raw_title = p.get("title", "").strip()
                raw_selftext = p.get("selftext", "").strip()
                post_id = p.get("id", "")

                # Semak penapis pendua Redis & Vector
                full_text_for_check = f"{raw_title} {raw_selftext[:100]}"
                is_dup, _ = is_lifestyle_topic_duplicate(full_text_for_check)
                if is_dup:
                    continue

                image_urls = extract_media_urls_from_reddit_post(p)

                # Jika mod memerlukan imej tetapi pos tiada imej, langkau
                if require_image and not image_urls:
                    continue

                clean_t = clean_reddit_text(raw_title)
                clean_desc = clean_reddit_text(raw_selftext)[:400]

                # Muat turun dan mampatkan imej (maksimum 4 imej < 50KB)
                local_images = []
                for idx, img_url in enumerate(image_urls, 1):
                    try:
                        img_res = requests.get(img_url, headers=headers, timeout=15)
                        if img_res.status_code == 200 and len(img_res.content) > 1000:
                            out_p = TEMP_DIR / f"reddit_{post_id}_{idx}.jpg"
                            comp_ok, comp_path, comp_kb = compress_image_to_under_50kb(img_res.content, out_p, max_kb=50)
                            if comp_ok:
                                local_images.append({
                                    "local_path": comp_path,
                                    "size_kb": comp_kb,
                                    "original_url": img_url
                                })
                    except Exception as e:
                        print(f"⚠️ [IMG DOWNLOAD ERROR] {e}")

                if require_image and not local_images:
                    continue

                print(f"🎯 [REDDIT FOUND] r/{sub} | ID: {post_id} | Imej: {len(local_images)} fail")
                return {
                    "source_platform": "reddit",
                    "subreddit": sub,
                    "post_id": post_id,
                    "title": clean_t,
                    "description": clean_desc,
                    "permalink": f"https://reddit.com{p.get('permalink', '')}",
                    "local_images": local_images,
                    "image_count": len(local_images),
                    "author": p.get("author", "Community Member")
                }

        except Exception as e:
            print(f"⚠️ [REDDIT FETCH ERROR] r/{sub}: {e}")

    return None


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Pembaca & Pemampat Reddit (Maksimum 4 Imej < 50KB)...")
    print("=" * 70)

    test_subs = ["houseplants", "MalaysianFood", "DIY"]
    post_result = fetch_curated_reddit_post(test_subs, require_image=True)

    if post_result:
        print("\n✅ POS REDDIT BERJAYA DIPEROLEHI:")
        print(f"Subreddit : r/{post_result['subreddit']}")
        print(f"Tajuk     : {post_result['title']}")
        print(f"Deskripsi : {post_result['description'][:150]}...")
        print(f"Bil Imej  : {post_result['image_count']} fail sedia di temp/")
        for img in post_result["local_images"]:
            print(f"  • {Path(img['local_path']).name} ({img['size_kb']} KB)")
    else:
        print("\n❌ Tiada pos sesuai dijumpai.")
    print("=" * 70)