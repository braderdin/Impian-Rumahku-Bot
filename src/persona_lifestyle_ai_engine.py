#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Central AI Orchestrator & Router
Location: src/persona_lifestyle_ai_engine.py

Routing Flow:
1. Local GGUF Engine (src/persona_lifestyle_ai_gguf.py)
2. OpenRouter Engine (src/persona_lifestyle_ai_openrouter.py)
3. Deterministic Mama Rule-Based Generator (Zero-fail fallback)
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Modular
from src.persona_lifestyle_ai_gguf import generate_lifestyle_captions_gguf, HAS_LLAMA_CPP
from src.persona_lifestyle_ai_openrouter import generate_lifestyle_captions_openrouter


def generate_platform_rule_based_copy(context_payload: Dict[str, Any]) -> Dict[str, str]:
    """Penjana sandaran peraturan Mama jika semua model AI tidak dapat dicapai."""
    niche_title = context_payload.get("niche", {}).get("niche_title", "Kehidupan Harian")
    period = context_payload.get("datetime", {}).get("period", "Hari Ini")

    fb_text = (
        f"Waktu {period.lower()} macam ni memang seronok bila dapat luangkan masa tenangkan fikiran di rumah. "
        f"Bila cerita pasal {niche_title.lower()}, banyak perkara kecil yang memudahkan urusan harian keluarga Mama. "
        f"Bila rumah tersusun rapi, hati pun rasa lapang dan tenang tanpa perlu pening kepala."
    )
    ig_text = (
        f"Bila masuk waktu {period.lower()}, Mama suka luangkan masa kemaskan sudut santai rumah. "
        f"Susun atur ringkas untuk {niche_title.lower()} macam ni bukan sahaja jimat ruang, malah nampak kemas elok dan sedap mata memandang."
    )
    th_text = (
        f"Waktu {period.lower()} macam ni baru Mama sempat rehat sekejap lepas kemas ruang {niche_title.lower()}. "
        f"Rasa puas hati bila tengok semuanya tersusun rapi. Korang petang ni sempat buat apa di rumah?"
    )
    bs_text = (
        f"Waktu {period.lower()} santai macam ni, seronok bila tengok ruang {niche_title.lower()} tersusun kemas dan sedap mata memandang."
    )

    return {
        "facebook": fb_text,
        "instagram": ig_text,
        "threads": th_text,
        "bluesky": bs_text
    }


def generate_all_lifestyle_captions(
    context_payload: Dict[str, Any],
    local_image_path: Optional[str] = None
) -> Tuple[Dict[str, str], str]:
    """
    Router Utama: Mengurus giliran antara Local GGUF, OpenRouter, dan Rule-Based.
    """
    # 1. Panggil GGUF Tempatan Jika Pustaka llama_cpp Tersedia (GitHub Actions)
    if HAS_LLAMA_CPP:
        captions_gguf = generate_lifestyle_captions_gguf(context_payload, local_image_path)
        if captions_gguf:
            return captions_gguf, "LOCAL_QWEN35_GGUF"

    # 2. Panggil OpenRouter Engine (Local PC Run / Fallback)
    captions_or, model_used = generate_lifestyle_captions_openrouter(context_payload, local_image_path)
    if captions_or:
        return captions_or, model_used

    # 3. Rule-Based Fallback Jika Semua Enjin AI Gagal
    print("🛡️ [ROUTER FALLBACK] Mengaktifkan Rule-Based Mama Fallback...")
    rule_captions = generate_platform_rule_based_copy(context_payload)
    return rule_captions, "RULE_BASED_FALLBACK"


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Router Modular AI Persona Lifestyle...")
    print("=" * 70)

    from src.persona_lifestyle_context import build_lifestyle_context_payload

    dummy_context = build_lifestyle_context_payload()
    result_caps, engine_name = generate_all_lifestyle_captions(dummy_context)

    print(f"\n🚀 Enjin Digunakan: {engine_name}\n")
    for platform, text in result_caps.items():
        print(f"📱 [{platform.upper()}] ({len(text)} aksara):")
        print(f"\"{text}\"\n")
    print("=" * 70)