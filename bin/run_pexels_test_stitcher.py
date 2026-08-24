#!/usr/bin/env python3
"""
Diagnostic Test Runner: Pexels Video Fetch + Librosa Audio + MoviePy Stitching Only
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Tests Step 1 standalone: AI keyword selection -> Pexels batch fetch -> Librosa tempo/beats -> MoviePy stitching (30-40s)
- Outputs rendered test video directly to experiments/pexels_output/
- Extracts 4 test keyframes to verify visual clarity and payload size
- Zero social media dispatch (Safe for local dry runs)
"""

import os
import sys
import json
import time
from pathlib import Path
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

from src.pexels_config import get_myt_time_context
from src.pexels_keyword_engine import get_fresh_vetted_keyword_candidates
from src.pexels_fetcher import fetch_and_filter_pexels_clips, download_all_selected_clips, cleanup_downloaded_clips
from src.pexels_video_stitcher import render_stitched_reel
from src.pexels_keyframe_extractor import extract_and_compress_keyframes

OUTPUT_DIR = PROJECT_ROOT / "experiments" / "pexels_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_stitcher_test():
    print("=" * 78)
    print("🧪 [DIAGNOSTIC TEST] PEXELS B-ROLL + LIBROSA AUDIO + MOVIEPY STITCHER (30-40s)")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 78)

    time_context, period, day_mood = get_myt_time_context()
    print(f"⏰ Konteks Waktu : {time_context} ({period})")
    print(f"🌸 Suasana Hari  : {day_mood}")

    # 1. Calon Kata Kunci
    print("\n💡 [STEP 1] Menjana calon kata kunci Home & Living segar...")
    candidate_keywords = get_fresh_vetted_keyword_candidates()
    print(f"📋 Calon Diterima: {candidate_keywords}")

    if not candidate_keywords:
        print("❌ Tiada calon kata kunci yang sah.")
        return

    # 2. Carian Pexels (per_page=70)
    selected_clips = []
    selected_keyword = None

    for idx, kw in enumerate(candidate_keywords, 1):
        print(f"\n🔍 [Ujian {idx}/{len(candidate_keywords)}] Carian Pexels: '{kw}'...")
        clips, err = fetch_and_filter_pexels_clips(query=kw, needed_count=5, batch_size=70)
        if clips and len(clips) >= 4:
            selected_clips = clips
            selected_keyword = kw
            print(f"   ✅ Diperoleh {len(clips)} klip vertikal 9:16 bebas muka!")
            break
        else:
            print(f"   ⚠️ Klip tidak mencukupi ({len(clips)} diperoleh). Mencuba seterusnya...")

    if not selected_clips or not selected_keyword:
        print("❌ Kesemua calon gagal memperoleh sekurang-kurangnya 4 klip.")
        return

    print(f"\n📋 [SENARAI KLIP TERPILIH ({len(selected_clips)} Video)]:")
    for i, c in enumerate(selected_clips, 1):
        print(f"   {i}. Pexels ID: {c['id']} | Resolusi: {c.get('width')}x{c.get('height')} | Durasi Asal: {c.get('duration')}s")

    # 3. Muat Turun Klip Tempatan
    downloaded_paths = download_all_selected_clips(selected_clips)

    # 4. Rendering MoviePy + Librosa (30 - 40 saat)
    try:
        rendered_path, music_meta, duration_sec = render_stitched_reel(
            clips_data=selected_clips,
            target_min=30,
            target_max=40,
            output_dir=OUTPUT_DIR,
            filename_prefix="test_stitcher_mama"
        )

        if not rendered_path or not os.path.exists(rendered_path):
            print("❌ Gagal merender video.")
            return

        # 5. Ujian Ekstraksi 4 Keyframe
        keyframes, total_kb = extract_and_compress_keyframes(rendered_path, num_frames=4, max_dimension=384, quality=65)

        print("\n" + "=" * 78)
        print("📊 [HASIL UJIAN STITCHER LENGKAP]")
        print("=" * 78)
        print(f"🎬 Tema Video       : {selected_keyword.title()}")
        print(f"📁 Lokasi Fail MP4  : {rendered_path}")
        print(f"⏱️ Durasi Video     : {duration_sec} Saat (Sasaran: 30 - 40s)")
        print(f"🎵 Muzik Latar      : {music_meta.get('title')} ({music_meta.get('artist')})")
        print(f"🥁 Tempo / Rentak   : {music_meta.get('tempo_bpm')} BPM | {len(music_meta.get('beat_timestamps', []))} Beats")
        print(f"✨ Vibe Muzik       : {music_meta.get('vibe')}")
        print(f"🖼️ Saiz 4 Keyframes : {total_kb:.1f} KB (Purata: {total_kb/max(1, len(keyframes)):.1f} KB/frame)")
        print("=" * 78)

    finally:
        cleanup_downloaded_clips(downloaded_paths)


if __name__ == "__main__":
    run_stitcher_test()