#!/usr/bin/env python3
"""
Diagnostic Test Runner: Vision AI (EN) -> Local Mesolitica NanoT5 Translation (BM)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Step 0: Semakan konfigurasi (.env.local)
- Step 1: Jana kata kunci -> Ambil klip Pexels -> Cantum video MoviePy + Librosa (30-40s)
- Step 2: Ekstrak 4 Keyframe -> Analisis OpenRouter Vision (Teks EN ~350-500 aksara)
- Step 3: Terjemahan tempatan BM menggunakan mesolitica/nanot5-base-malaysian-translation-v2.1
- Sifar pangkalan data lock & sifar hantaran media sosial (Khusus untuk kajian ayat BM)
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

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

# Import komponen modular projek
from src.pexels_config import (
    get_myt_time_context,
    get_openrouter_config,
    get_pexels_config
)
from src.pexels_keyword_engine import get_fresh_vetted_keyword_candidates
from src.pexels_fetcher import (
    fetch_and_filter_pexels_clips,
    download_all_selected_clips,
    cleanup_downloaded_clips
)
from src.pexels_video_stitcher import render_stitched_reel
from src.pexels_keyframe_extractor import extract_and_compress_keyframes
from src.pexels_vision_engine import analyze_video_keyframes_with_vision

OUTPUT_DIR = PROJECT_ROOT / "experiments" / "pexels_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Nama model terjemahan tempatan Mesolitica
LOCAL_TRANSLATION_MODEL = "mesolitica/nanot5-base-malaysian-translation-v2.1"


def print_step_header(step_num: int, step_title: str):
    print("\n" + "═" * 78)
    print(f"🔹 [STEP {step_num}] {step_title.upper()}")
    print("═" * 78)


def translate_with_local_mesolitica(english_text: str):
    """Menterjemah teks ulasan English ke Bahasa Melayu menggunakan model tempatan Mesolitica NanoT5."""
    print(f"⏳ Memuatkan model tempatan '{LOCAL_TRANSLATION_MODEL}'...")
    start_load = time.time()
    
    tokenizer = AutoTokenizer.from_pretrained(LOCAL_TRANSLATION_MODEL)
    model = AutoModelForSeq2SeqLM.from_pretrained(LOCAL_TRANSLATION_MODEL)
    
    load_duration = time.time() - start_load
    print(f"✅ Model sedia ({load_duration:.2f}s). Memulakan inferens CPU...")

    # Format arahan model Mesolitica NanoT5 v2.1
    prompt = f"terjemah ke Melayu: {english_text.strip()}"
    inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)

    start_gen = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            num_beams=2,
            no_repeat_ngram_size=3,  # Menghalang pengulangan frasa
            repetition_penalty=1.2,  # Memastikan kosa kata pelbagai
            early_stopping=True
        )

    translated_bm = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    gen_duration = time.time() - start_gen

    return translated_bm, gen_duration


def run_vision_to_local_translation_test():
    print("=" * 78)
    print("🧪 [DIAGNOSTIC TEST] VISION AI (EN) -> LOCAL TRANSLATION MESOLITICA (BM)")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 78)

    time_context, period, day_mood = get_myt_time_context()
    print(f"⏰ Konteks Waktu MYT : {time_context} ({period})")
    print(f"🌸 Suasana Hari Ini  : {day_mood}")

    # =========================================================================
    # STEP 0: SEMAKAN KREDENSIAL ASAS
    # =========================================================================
    print_step_header(0, "Semakan Kredensial Pexels & OpenRouter Vision (.env.local)")
    _, _, or_models, or_err = get_openrouter_config()
    _, pex_err = get_pexels_config()

    print(f"• OpenRouter API : {'✅ Sedia (' + or_models.get('vision', '') + ')' if not or_err else '❌ ' + or_err}")
    print(f"• Pexels API     : {'✅ Sedia' if not pex_err else '❌ ' + pex_err}")

    if or_err or pex_err:
        print("❌ Kredensial tidak lengkap dalam .env.local. Ujian dihentikan.")
        return

    # =========================================================================
    # STEP 1: JANA KATA KUNCI, CARI PEXELS & RENDER VIDEO
    # =========================================================================
    print_step_header(1, "Penjanaan Kata Kunci & Rendering Video Pexels")
    candidates = get_fresh_vetted_keyword_candidates()
    print(f"📋 Calon Kata Kunci: {candidates}")

    if not candidates:
        print("❌ Tiada calon kata kunci.")
        return

    selected_clips = []
    selected_keyword = None

    for idx, kw in enumerate(candidates, 1):
        print(f"\n🔍 [Carian Pexels {idx}/{len(candidates)}] Menguji: '{kw}'...")
        clips, err = fetch_and_filter_pexels_clips(query=kw, needed_count=5, batch_size=70)
        if clips and len(clips) >= 4:
            selected_clips = clips
            selected_keyword = kw
            print(f"   ✅ Diperoleh {len(clips)} klip vertikal bebas muka!")
            break

    if not selected_clips or not selected_keyword:
        print("❌ Gagal memperoleh klip video.")
        return

    video_title = selected_keyword.title()
    downloaded_paths = download_all_selected_clips(selected_clips)

    try:
        rendered_video_path, music_meta, duration_sec = render_stitched_reel(
            clips_data=selected_clips,
            target_min=30,
            target_max=40,
            output_dir=OUTPUT_DIR,
            filename_prefix="test_local_trans_reel"
        )

        if not rendered_video_path or not os.path.exists(rendered_video_path):
            print("❌ Gagal merender video.")
            return

        print(f"🎬 Video Siap Dirender : {rendered_video_path}")
        print(f"⏱️ Durasi Sebenar     : {duration_sec}s | Muzik: '{music_meta.get('title')}'")

        # =====================================================================
        # STEP 2: EKSTRAKSI 4 KEYFRAME & ANALISIS OPENROUTER VISION (EN)
        # =====================================================================
        print_step_header(2, "Ekstraksi 4 Keyframe & Analisis OpenRouter Vision (EN)")
        keyframes, total_kb = extract_and_compress_keyframes(
            rendered_video_path, num_frames=4, max_dimension=384, quality=65
        )
        print(f"📦 Saiz 4 Keyframes Termampat: {total_kb:.1f} KB")

        vision_review, vision_model, _ = analyze_video_keyframes_with_vision(
            keyframes_list=keyframes,
            video_title=video_title,
            music_meta=music_meta,
            max_attempts=3,
            delay_seconds=2
        )

        print(f"\n🧠 Model Vision Digunakan : {vision_model}")
        print(f"📝 Ulasan Vision Asal (EN):\n\"{vision_review}\"")
        print(f"📏 Panjang Aksara (EN)    : {len(vision_review)} Aksara")

        # =====================================================================
        # STEP 3: TERJEMAHAN TEMPATAN (MESOLITICA NANOT5 - BM MALAYSIA)
        # =====================================================================
        print_step_header(3, "Terjemahan Tempatan Mesolitica NanoT5 (Tanpa OpenRouter)")
        
        bm_translation, trans_duration = translate_with_local_mesolitica(vision_review)

        # =====================================================================
        # PAPARAN HASIL AKHIR & KAJIAN LENGGOK BAHASA
        # =====================================================================
        print("\n" + "═" * 78)
        print("📊 [HASIL KAJIAN TERJEMAHAN BAHASA MELAYU DI TERMINAL]")
        print("═" * 78)
        print(f"🏷️ Tema / Kata Kunci : {video_title}")
        print(f"⏱️ Masa Terjemah    : {trans_duration:.2f} saat (Inference CPU)")
        print(f"📏 Panjang Teks (BM) : {len(bm_translation)} Aksara")
        print("-" * 78)
        print("📄 TEKS ASAL (VISION REVIEW - EN):")
        print(f"\"{vision_review}\"")
        print("-" * 78)
        print("🇲🇾 HASIL TERJEMAHAN BM TEMPATAN (MESOLITICA NANOT5):")
        print(f"\"{bm_translation}\"")
        print("═" * 78)
        print("🛡️ [UJIAN SELESAI] Tiada sebarang pos dihantar ke media sosial.")
        print("═" * 78)

    finally:
        cleanup_downloaded_clips(downloaded_paths)


if __name__ == "__main__":
    run_vision_to_local_translation_test()