#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Central AI Orchestrator & Router
Location: src/persona_lifestyle_ai_engine.py

Routing Flow:
1. Local GGUF Engine (src/persona_lifestyle_ai_gguf.py) [Fast-bypass if llama_cpp is absent]
2. Dedicated OpenRouter Engine (src/persona_lifestyle_ai_openrouter.py) [Vision / Primary -> Fallback]
3. Deterministic Mama Rule-Based Generator (100% Zero-Fail Safety Net)
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
    """
    Penjana sandaran peraturan Persona Mama mengikut 5 fasa waktu sekiranya semua enjin AI gagal.
    """
    niche_title = context_payload.get("niche", {}).get("niche_title", "Kehidupan Harian")
    dt = context_payload.get("datetime", {})
    period = dt.get("period", "Hari Ini").lower()

    if "pagi" in period:
        fb_text = (
            f"Selamat pagi semua. Awal pagi macam ni memang seronok bila dapat mulakan urusan rumah dengan tenang. "
            f"Bila cerita pasal {niche_title.lower()}, banyak perkara kecil yang memudahkan kerja harian keluarga Mama. "
            f"Bila ruang tersusun kemas dan teratur, hati pun rasa lapang nak memulakan hari."
        )
        ig_text = (
            f"Pagi-pagi macam ni Mama suka luangkan masa kemaskan sudut santai rumah lepas siap sarapan. "
            f"Susun atur ringkas untuk {niche_title.lower()} macam ni bukan sahaja jimat ruang, malah nampak kemas elok dan sedap mata memandang."
        )
        th_text = (
            f"Pagi ni Mama sempat kemaskan ruang {niche_title.lower()} sebelum sambung kerja lain. "
            f"Bila tengok semuanya tersusun rapi, rasa bersemangat sikit nak mula hari. Korang dah siap sarapan ke tu?"
        )
        bs_text = (
            f"Pagi yang tenang bila dapat luangkan masa uruskan ruang {niche_title.lower()} supaya nampak kemas dan sedap mata memandang."
        )
    elif "tengah hari" in period:
        fb_text = (
            f"Waktu tengah hari panas terik macam ni, baru dapat rehat sekejap di sofa lepas siap urusan dapur. "
            f"Bila sentuh bab {niche_title.lower()}, Mama suka cara yang praktikal supaya tak membebankan urusan keluarga. "
            f"Yang penting dapur bersih, ruang tersusun elok dan suasana rumah rasa tenang."
        )
        ig_text = (
            f"Lepas siap masak lauk tengah hari dan kemas dapur, Mama suka rehat sekejap tengok susun atur rumah. "
            f"Penjagaan ringkas untuk {niche_title.lower()} macam ni buat ruang nampak lebih damai dan sedap mata memandang."
        )
        th_text = (
            f"Selesai juga masak lauk tengah hari dan lap dapur. Baru dapat duduk rehat sekejap sambil belek ruang {niche_title.lower()}. "
            f"Korang tengah hari ni masak apa untuk keluarga?"
        )
        bs_text = (
            f"Rehat sekejap waktu tengah hari lepas kemas dapur. Seronok tengok sudut {niche_title.lower()} tersusun rapi."
        )
    elif "petang" in period:
        fb_text = (
            f"Waktu petang santai macam ni memang seronok bila dapat luangkan masa tenangkan fikiran di rumah. "
            f"Bila cerita pasal {niche_title.lower()}, banyak perkara kecil yang memudahkan urusan harian keluarga Mama. "
            f"Bila ruang tersusun rapi, hati pun rasa lapang dan tenang sambil nikmati minum petang."
        )
        ig_text = (
            f"Bila masuk waktu petang, Mama suka luangkan masa santai sambil belek sudut kegemaran rumah. "
            f"Susun atur ringkas untuk {niche_title.lower()} macam ni bukan sahaja jimat ruang, malah nampak kemas elok dan sedap mata memandang."
        )
        th_text = (
            f"Waktu petang santai macam ni baru Mama sempat rehat sekejap lepas siap kemaskan ruang {niche_title.lower()}. "
            f"Rasa puas hati bila tengok semuanya tersusun rapi. Korang petang ni minum air apa?"
        )
        bs_text = (
            f"Waktu petang santai macam ni, seronok bila tengok ruang {niche_title.lower()} tersusun kemas dan sedap mata memandang."
        )
    elif "awal malam" in period:
        fb_text = (
            f"Selesai makan malam bersama keluarga, waktu macam ni seronok dapat duduk sembang santai di ruang tamu. "
            f"Bila urusan {niche_title.lower()} dah siap dikemas elok, suasana malam pun rasa lebih tenang tanpa pening kepala. "
            f"Perkara kecil macam ni yang buat urusan rumah tangga rasa lebih teratur."
        )
        ig_text = (
            f"Lepas siap kemas meja makan dan dapur, Mama suka luangkan masa rehatkan fikiran di sudut santai. "
            f"Kekalkan kekemasan untuk {niche_title.lower()} memang membantu mudahkan rutin harian keluarga setiap hari."
        )
        th_text = (
            f"Selesai makan malam dan kemas dapur, baru dapat duduk santai dengan keluarga sambil sembang pasal {niche_title.lower()}. "
            f"Korang makan malam apa hari ni?"
        )
        bs_text = (
            f"Selesai makan malam dan kemas dapur, rasa lapang bila tengok ruang {niche_title.lower()} tersusun rapi."
        )
    else:  # lewat malam
        fb_text = (
            f"Waktu lewat malam bila anak-anak dah tidur memang waktu terbaik untuk Mama rehatkan badan dan tenangkan fikiran. "
            f"Bila tengok ruang {niche_title.lower()} dah siap tersusun elok, rasa puas hati dan bersedia untuk hari esok. "
            f"Suasana rumah yang damai buat tidur malam pun jadi lebih lena."
        )
        ig_text = (
            f"Waktu me-time lewat malam macam ni Mama suka nikmati ketenangan sudut rumah yang dah siap dikemas. "
            f"Ruang {niche_title.lower()} yang tersusun rapi buat suasana malam rasa lebih mendamaikan dan sedap mata memandang."
        )
        th_text = (
            f"Anak-anak dah tidur, barulah Mama sempat rehat layan me-time sekejap lepas kemas ruang {niche_title.lower()}. "
            f"Korang waktu malam macam ni biasa rehat buat apa?"
        )
        bs_text = (
            f"Waktu me-time malam yang tenang bila anak-anak dah tidur dan ruang {niche_title.lower()} tersusun elok."
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
    Router Utama: Menyelaraskan penjanaan teks ulasan merentasi 4 platform media sosial.
    Hierarki: Local GGUF (jika ada llama_cpp) -> OpenRouter (Vision/Primary/Fallback) -> Rule-Based.
    """
    # 1. Panggil GGUF Tempatan Jika Pustaka llama_cpp Tersedia (GitHub Actions Environment)
    if HAS_LLAMA_CPP:
        print("🚀 [ROUTER] Mengesan enjin tempatan llama_cpp. Memulakan inferens GGUF...")
        captions_gguf = generate_lifestyle_captions_gguf(context_payload, local_image_path)
        if captions_gguf:
            return captions_gguf, "LOCAL_QWEN35_GGUF"
        print("⚠️ [ROUTER WARN] Local GGUF gagal menjana. Beralih ke OpenRouter...")
    else:
        print("⚡ [ROUTER FAST-BYPASS] llama_cpp tidak dipasang secara lokal. Melangkau terus ke OpenRouter...")

    # 2. Panggil OpenRouter Engine (Vision Utamakan jika ada imej, Primary Text untuk teks sahaja)
    captions_or, model_used = generate_lifestyle_captions_openrouter(context_payload, local_image_path)
    if captions_or:
        return captions_or, model_used

    # 3. Rule-Based Fallback Jika Semua Enjin AI Gagal (100% Zero-Fail)
    print("🛡️ [ROUTER FALLBACK] Semua enjin AI gagal/sesak. Mengaktifkan Rule-Based Mama Fallback...")
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