#!/usr/bin/env python3
"""
Dedicated Pexels 9:16 Video Keyword Generation & Deduplication Engine
Impian Rumahku & Cerita Mama Ecosystem
Features:
- SIFAR MODEL HARDCODE: Strictly reads IRCM_MODEL_PRIMARY & Fallbacks from env
- 10-Keyword Redis Memory Bank Ingestion
- Deduplication filter against Redis (10-day TTL check)
"""

import sys
import json
import time
import requests
from pathlib import Path
from typing import List, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_openrouter_config, get_myt_time_context
from src.pexels_seeds import PEXELS_HOME_LIVING_SEEDS, get_random_seeds, get_fallback_seeds, sanitize_keyword
from src.pexels_redis_db import is_pexels_keyword_used, get_recent_keyword_memories


def _call_openrouter_for_keywords(
    base_url: str,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.75
) -> List[str]:
    """Menghantar permintaan terus ke model OpenRouter API untuk menjana 10 kata kunci JSON array."""
    endpoint = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        "temperature": temperature,
    }

    try:
        res = requests.post(endpoint, headers=headers, json=payload, timeout=(8, 25))
        if res.status_code == 200:
            res_json = res.json()
            raw_content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            import re
            match = re.search(r'\[[\s\S]*?\]', raw_content)
            if match:
                candidates_raw = json.loads(match.group(0))
                cleaned_list = []
                for item in candidates_raw:
                    clean_kw = sanitize_keyword(str(item))
                    if len(clean_kw) >= 5:
                        cleaned_list.append(clean_kw)
                
                if len(cleaned_list) >= 5:
                    return cleaned_list
        else:
            print(f"   ⚠️ [HTTP {res.status_code}] Model {model_name}: {res.text[:80]}")
    except Exception as e:
        print(f"   ⚠️ [AI KEYWORD EXCEPTION] Model {model_name}: {e}")

    return []


def generate_10_keyword_candidates(
    recent_memories: Optional[List[str]] = None,
    rejected_keywords: Optional[List[str]] = None,
) -> List[str]:
    """Menjana 10 calon kata kunci carian video Pexels menggunakan hierarki model persekitaran."""
    base_url, api_key, models_dict, cfg_err = get_openrouter_config()
    if cfg_err or not base_url or not api_key:
        print(f"⚠️ [CONFIG WARN] {cfg_err}. Menggunakan senarai benih sandaran.")
        return get_fallback_seeds(10)

    time_context, period, day_mood = get_myt_time_context()
    sampled_seeds = get_random_seeds(5)

    recent_context = ""
    if recent_memories:
        recent_str = ", ".join([f"'{k}'" for k in recent_memories[:10]])
        recent_context = f"\nBANK INGATAN KATA KUNCI LEPAS (DILARANG ULANG TEMA SAMA):\n[{recent_str}]\n"

    rejected_context = ""
    if rejected_keywords:
        rejected_str = ", ".join([f"'{k}'" for k in rejected_keywords])
        rejected_context = f"\nPERHATIAN - KATA KUNCI INI BARU DITOLAK DALAM TAPISAN (JANA TEMA BERBEZA):\n[{rejected_str}]\n"

    system_prompt = (
        "You are an expert Home & Living aesthetic video curator for vertical 9:16 reels.\n"
        "TASK:\n"
        "Generate EXACTLY 10 fresh, highly aesthetic English search queries for Pexels video search.\n"
        "Focus exclusively on cozy home aesthetics, kitchen organizing, tidy pantry, living spaces, and domestic decluttering.\n\n"
        "STRICT NEGATIVE CONSTRAINTS:\n"
        "1. STRICTLY NO human faces, closeups of people, models, selfies, streamers, or gamers.\n"
        "2. STRICTLY NO sensitive animals (no dogs, no puppies, no pigs).\n"
        "3. Focus on aesthetic objects, textures, surfaces, sunlight, organizing bins, kitchen tools, and plants.\n"
        "4. Each query MUST be 2 to 4 words in plain English.\n"
        "5. Return ONLY a valid JSON array of strings.\n\n"
        f"TIME CONTEXT: {time_context} ({day_mood})\n"
        f"INSPIRATION SEEDS: {', '.join(sampled_seeds)}"
        f"{recent_context}{rejected_context}"
    )

    user_prompt = "Generate 10 fresh faceless Home & Living aesthetic search keywords in JSON array format."

    # Susun senarai model aktif daripada konfigurasi ENV
    model_hierarchy = [
        (models_dict.get("primary", "").strip(), "Primary Model"),
        (models_dict.get("fallback_1", "").strip(), "Fallback Model 1"),
        (models_dict.get("fallback_2", "").strip(), "Fallback Model 2"),
        (models_dict.get("fallback_3", "").strip(), "Fallback Model 3"),
    ]
    model_hierarchy = [(m, label) for m, label in model_hierarchy if m]

    for model_name, model_label in model_hierarchy:
        print(f"\n🧠 [KEYWORD AI] Mencuba {model_label}: '{model_name}'...")
        for attempt in range(1, 3):
            candidates = _call_openrouter_for_keywords(
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.75 if not rejected_keywords else 0.85
            )
            if candidates and len(candidates) >= 5:
                print(f"   ✅ [{model_label} Berjaya] Diterima {len(candidates)} calon kata kunci segar.")
                return candidates

            if attempt < 2:
                time.sleep(2)

    print("🛡️ [FALLBACK SEEDS AKTIF] Kesemua model AI tergendala. Menggunakan kata kunci benih sandaran.")
    return get_fallback_seeds(10)


def get_fresh_vetted_keyword_candidates() -> List[str]:
    """Menjana 10 calon kata kunci segar dan menapisnya melalui Redis (penjara 10 hari)."""
    recent_memories = get_recent_keyword_memories(limit=10)
    if recent_memories:
        print(f"🧠 [KEYWORD MEMORY] Memuatkan {len(recent_memories)} sejarah kata kunci lepas dari Redis.")

    passed_candidates = []
    rejected_in_r1 = []

    print("\n💡 [PEXELS KEYWORD ENGINE] [Pusingan 1] Menjana 10 calon kata kunci...")
    candidates_r1 = generate_10_keyword_candidates(recent_memories=recent_memories)

    for idx, kw in enumerate(candidates_r1, 1):
        if is_pexels_keyword_used(kw):
            print(f"  ⏭️ [REDIS SKIP] Calon #{idx} '{kw}' pernah digunakan dalam tempoh 10 hari.")
            rejected_in_r1.append(kw)
            continue

        print(f"  ✅ [LULUS TAPISAN] Calon #{idx} '{kw}' sah & segar.")
        passed_candidates.append(kw)

    if not passed_candidates:
        print("\n⚠️ [RETRY LOOP] Kesemua calon Pusingan 1 pernah digunakan. Meminta pusingan alternatif dari AI...")
        candidates_r2 = generate_10_keyword_candidates(
            recent_memories=recent_memories,
            rejected_keywords=rejected_in_r1
        )

        for idx, kw in enumerate(candidates_r2, 1):
            if is_pexels_keyword_used(kw):
                print(f"  ⏭️ [REDIS SKIP R2] '{kw}' pernah digunakan.")
                continue
            passed_candidates.append(kw)

    if not passed_candidates:
        print("⚠️ [SEEDS FALLBACK] Mengimbas senarai 40 kata kunci asas Home & Living...")
        for seed in PEXELS_HOME_LIVING_SEEDS:
            clean_seed = sanitize_keyword(seed)
            if not is_pexels_keyword_used(clean_seed):
                passed_candidates.append(clean_seed)
            if len(passed_candidates) >= 5:
                break

    return passed_candidates