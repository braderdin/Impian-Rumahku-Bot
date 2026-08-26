#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Reddit Topic & Text Idea Curator Engine (Pure Text Mode)
Location: src/persona_lifestyle_reddit_reader.py

Features:
- Pure Text & Topic Idea Curator: Zero Reddit image extraction/downloading (prevents XML parsing & 403 image block errors).
- Dual-Engine Ingestion: Uses Reddit JSON API first, automatically falls back to RSS/Atom XML on HTTP 403/blocks.
- Content Cleaners: Strips HTML entities, markdown tags, spoilers, and external URLs.
- Deduplication Guardrail: Integrates with persona_lifestyle_filter (Redis 10-Day & Vector 2-Day checks).
- Step-by-Step Payload Storage: Saves the extracted idea context to temp/step1_reddit_context.json.
- Courtesy Delay: 1.5s sleep buffer between community scans to prevent HTTP 429 rate limits.
"""

import os
import re
import sys
import time
import html
import json
import requests
import xml.etree.ElementTree as ET
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

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
STEP1_OUTPUT_FILE = TEMP_DIR / "step1_reddit_context.json"

# Import Penapis Dwi-Lapisan Redis & Vector
from src.persona_lifestyle_filter import is_lifestyle_topic_duplicate

DEFAULT_SUBREDDITS = [
    "MalaysianFood", "houseplants", "organization", "DIY",
    "food", "IndoorGarden", "CozyPlaces", "Frugal", "Baking"
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
}


def clean_reddit_text(raw_text: str, max_chars: int = 600) -> str:
    """
    Membersihkan tag HTML, pautan markdown, spoiler, dan simbol asing daripada teks Reddit.
    """
    if not raw_text:
        return ""

    text = html.unescape(raw_text)

    # Buang tag HTML
    text = re.sub(r'<[^>]+>', ' ', text)

    if text.strip() in ["[removed]", "[deleted]"]:
        return ""

    # Buang spoiler markdown, link markdown [text](http...), dan URL langsung
    text = re.sub(r'>!([\s\S]*?)!<', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(?i)\n+\s*(?:edit|update|tldr|tl;dr|ps)[\s\S]*$', '', text)
    text = re.sub(r'[*_~`#]', '', text)

    # Buang simbol bukan Latin standard
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = " ".join(lines).strip()

    if len(cleaned) > max_chars:
        trimmed = cleaned[:max_chars]
        last_punct = max(trimmed.rfind('.'), trimmed.rfind('!'), trimmed.rfind('?'))
        if last_punct > 100:
            cleaned = trimmed[:last_punct + 1].strip()
        else:
            cleaned = trimmed.rsplit(' ', 1)[0].strip() + "..."

    return cleaned


# =============================================================================
# ENJIN 1: PENGAMBILAN TEKS VIA JSON API
# =============================================================================
def fetch_via_json(subreddit: str, limit: int = 25) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Menarik senarai pos teks daripada endpoint JSON rasmi Reddit."""
    clean_sub = subreddit.replace("r/", "").strip()
    endpoint = f"https://www.reddit.com/r/{clean_sub}/hot.json?limit={limit}&raw_json=1"

    try:
        res = requests.get(endpoint, headers=BROWSER_HEADERS, timeout=10)
        if res.status_code != 200:
            return False, [], f"JSON HTTP {res.status_code}"

        data = res.json().get("data", {}).get("children", [])
        if not data:
            return False, [], "JSON tiada senarai pos."

        candidates = []
        for child in data:
            p = child.get("data", {})
            if p.get("stickied") or p.get("over_18"):
                continue

            raw_title = p.get("title", "").strip()
            raw_selftext = p.get("selftext", "").strip()
            post_id = p.get("id", "")
            if not raw_title or not post_id:
                continue

            clean_t = clean_reddit_text(raw_title, max_chars=140)
            clean_desc = clean_reddit_text(raw_selftext, max_chars=500)

            candidates.append({
                "post_id": post_id,
                "subreddit": clean_sub,
                "title": clean_t,
                "description": clean_desc if clean_desc else clean_t,
                "permalink": f"https://www.reddit.com{p.get('permalink', '')}",
                "author": p.get("author", "Community Member"),
                "score": p.get("score", 0),
                "source_engine": "JSON_API"
            })

        return True, candidates, f"JSON: {len(candidates)} pos teks diterima."
    except Exception as e:
        return False, [], f"JSON Error: {e}"


# =============================================================================
# ENJIN 2: PENGAMBILAN TEKS VIA RSS ATOM XML (SANDARAN KEBAL HTTP 403)
# =============================================================================
def fetch_via_rss(subreddit: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Menarik teks pos melalui suapan RSS Atom XML (kebal sekatan 403)."""
    clean_sub = subreddit.replace("r/", "").strip()
    endpoint = f"https://www.reddit.com/r/{clean_sub}/hot.rss"

    try:
        res = requests.get(endpoint, headers=RSS_HEADERS, timeout=12)
        if res.status_code != 200:
            return False, [], f"RSS HTTP {res.status_code}"

        root = ET.fromstring(res.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns)
        if not entries:
            return False, [], "RSS tiada entri ditemui."

        candidates = []
        for index, entry in enumerate(entries):
            title_elem = entry.find('atom:title', ns)
            link_elem = entry.find('atom:link', ns)
            content_elem = entry.find('atom:content', ns)
            author_elem = entry.find('atom:author/atom:name', ns)
            id_elem = entry.find('atom:id', ns)

            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            permalink = link_elem.attrib.get('href', '') if link_elem is not None else ""
            raw_html = content_elem.text if content_elem is not None and content_elem.text else ""
            author = author_elem.text.replace("/u/", "") if author_elem is not None and author_elem.text else "Community Member"
            post_id = id_elem.text.split("_")[-1] if id_elem is not None and id_elem.text else f"rss_{index}"

            if not title or author in ["[deleted]", "AutoModerator"]:
                continue

            clean_t = clean_reddit_text(title, max_chars=140)
            clean_desc = clean_reddit_text(raw_html, max_chars=500)

            candidates.append({
                "post_id": post_id,
                "subreddit": clean_sub,
                "title": clean_t,
                "description": clean_desc if clean_desc else clean_t,
                "permalink": permalink,
                "author": author,
                "score": 50,
                "source_engine": "RSS_ATOM_FEED"
            })

        return True, candidates, f"RSS: {len(candidates)} pos teks diekstrak."
    except Exception as e:
        return False, [], f"RSS Error: {e}"


# =============================================================================
# ENJIN PENGURUS UTAMA IDEA TEKS REDDIT (STEP 1)
# =============================================================================
def fetch_curated_reddit_post(subreddits: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    Mengimbas subreddit sasaran menggunakan dwi-enjin (JSON -> RSS Fallback),
    menapis pendua melalui Redis/Vector, dan menyimpan idea ke temp/step1_reddit_context.json.
    """
    target_subs = subreddits if subreddits else DEFAULT_SUBREDDITS

    for sub_idx, sub in enumerate(target_subs):
        print(f"📡 [REDDIT READER] Mengimbas idea teks komuniti: r/{sub}...")

        # 1. Cuba JSON API dahulu
        ok, candidates, msg = fetch_via_json(sub)
        if not ok or not candidates:
            print(f"  ⚠️ [{msg}] Beralih ke sandaran RSS Atom XML...")
            # 2. Fallback kepada RSS XML jika JSON gagal / disekat
            ok_rss, candidates_rss, msg_rss = fetch_via_rss(sub)
            if ok_rss and candidates_rss:
                candidates = candidates_rss
                print(f"  ✅ [RSS FEED AKTIF] {msg_rss}")
            else:
                print(f"  ⚠️ [RSS GAGAL]: {msg_rss}")
                time.sleep(1.5)
                continue

        # 3. Tapis calon pos teks menggunakan penapis dwi-lapisan
        for item in candidates:
            clean_t = item.get("title", "")
            clean_desc = item.get("description", "")
            post_id = item.get("post_id", "")

            # Semak Penapis Dwi-Lapisan (Redis 10 Hari & Vector 2 Hari)
            full_text_for_check = f"{clean_t} {clean_desc[:120]}"
            is_dup, dup_reason = is_lifestyle_topic_duplicate(full_text_for_check)
            if is_dup:
                continue

            result_payload = {
                "source_platform": "reddit",
                "source_engine": item["source_engine"],
                "subreddit": sub,
                "post_id": post_id,
                "title": clean_t,
                "description": clean_desc,
                "permalink": item.get("permalink", f"https://reddit.com/r/{sub}"),
                "author": item.get("author", "Community Member"),
                "score": item.get("score", 0),
                "curated_at": int(time.time())
            }

            # Simpan status sementara ke temp/step1_reddit_context.json
            try:
                with open(STEP1_OUTPUT_FILE, "w", encoding="utf-8") as f_out:
                    json.dump(result_payload, f_out, indent=2, ensure_ascii=False)
                print(f"💾 [STEP 1 PAYLOAD] Idea topik disimpan ke: {STEP1_OUTPUT_FILE.name}")
            except Exception as e:
                print(f"⚠️ [STEP 1 WARN] Gagal menyimpan {STEP1_OUTPUT_FILE.name}: {e}")

            print(f"🎯 [REDDIT IDEA WINNER] r/{sub} | ID: {post_id} ({item['source_engine']}) | Tajuk: '{clean_t[:45]}...'")
            return result_payload

        # Jeda 1.5 saat antara komuniti bagi mengelakkan ralat HTTP 429
        time.sleep(1.5)

    print("⚠️ [REDDIT READER] Tiada pos teks baharu yang melepasi tapisan dedup.")
    return None


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Pembaca Teks & Idea Reddit (Sifar Gambar Reddit)...")
    print("=" * 70)

    test_subs = ["MalaysianFood", "houseplants", "organization", "DIY"]
    post_result = fetch_curated_reddit_post(test_subs)

    if post_result:
        print("\n✅ IDEA TEKS REDDIT BERJAYA DIPEROLEHI:")
        print(f"Subreddit : r/{post_result['subreddit']} ({post_result['source_engine']})")
        print(f"Tajuk     : {post_result['title']}")
        print(f"Deskripsi : {post_result['description'][:150]}...")
        print(f"Fail JSON : {STEP1_OUTPUT_FILE}")
    else:
        print("\n❌ Tiada idea teks yang sesuai dijumpai.")
    print("=" * 70)