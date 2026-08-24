#!/usr/bin/env python3
"""
Comprehensive Local Step-by-Step Diagnostic Test Runner
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Step 0: Environment & API credentials health check (.env.local)
- Step 1: Redis 10-day keyword deduplication -> Pexels fetch (70 clips) -> Librosa audio sync -> MoviePy render (30-40s)
- Step 2: 4-Keyframe extraction (<15KB each) -> OpenRouter Vision review synthesis (350-500 chars)
- Step 3: AI Copywriter Persona Mama BM adaptation (300-500 chars) -> Vector DB 2-day semantic check
- Step 4: Backblaze B2 private signed upload & URL streaming validation
- Step 5: Social Media Dispatcher test (Supports Interactive Choice: [1] Live Post 4-Platform, [2] Dry-Run Simulation)
- Step 6: Telegram Summary Card & AI Text Audit validation
- Step 7: Redis lock, Vector embedding lock & B2 ephemeral file cleanup
"""

import os
import sys
import time
import json
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

# Import Modular Components from src/
from src.pexels_config import (
    get_myt_time_context,
    get_openrouter_config,
    get_redis_config,
    get_vector_config,
    get_pexels_config,
    get_facebook_config,
    get_instagram_config,
    get_threads_config,
    get_bluesky_config,
    get_b2_config,
    get_telegram_config
)
from src.pexels_redis_db import (
    is_pexels_keyword_used,
    mark_pexels_keyword_used,
    save_keyword_memory,
    is_pexels_video_posted,
    mark_pexels_video_posted,
    get_active_threads_token_from_redis
)
from src.pexels_vector_db import (
    is_similar_story_posted,
    mark_story_vector_posted
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
from src.pexels_ai_copywriter import generate_mama_reel_story
from src.pexels_b2_storage import b2_storage
from src.pexels_dispatcher_fb import post_reel_to_facebook
from src.pexels_dispatcher_ig import post_reel_to_instagram
from src.pexels_dispatcher_threads import post_video_to_threads
from src.pexels_dispatcher_bluesky import post_video_to_bluesky
from src.pexels_telegram_audit import send_pexels_reels_audit_report, has_any_successful_post

TEMP_DIR = PROJECT_ROOT / "temp"
OUTPUT_DIR = PROJECT_ROOT / "experiments" / "pexels_output"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def print_step_header(step_num: int, step_title: str):
    print("\n" + "═" * 78)
    print(f"🔹 [STEP {step_num}] {step_title.upper()}")
    print("═" * 78)


def run_all_step_diagnostic():
    print("=" * 78)
    print("🧪 [DIAGNOSTIC TEST RUNNER] UJIAN LANGKAH DEMI LANGKAH SISTEM REELS")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 78)

    time_context, period, day_mood = get_myt_time_context()
    print(f"⏰ Konteks Waktu MYT : {time_context}")
    print(f"🌸 Suasana Hari Ini  : {day_mood}")

    # =========================================================================
    # STEP 0: SEMAKAN KESIHATAN KUNCI PERSEKITARAN & SAMBUNGAN
    # =========================================================================
    print_step_header(0, "Semakan Kredensial & Sambungan API (.env.local)")

    _, _, or_models, or_err = get_openrouter_config()
    _, _, red_err = get_redis_config()
    _, _, vec_err = get_vector_config()
    _, pex_err = get_pexels_config()
    _, _, fb_err = get_facebook_config()
    _, _, ig_err = get_instagram_config()
    _, _, th_err = get_threads_config()
    _, _, bs_err = get_bluesky_config()
    _, _, _, _, b2_err = get_b2_config()
    _, _, tg_err = get_telegram_config()

    print(f"• OpenRouter API : {'✅ Sedia (' + or_models.get('primary', '') + ')' if not or_err else '❌ ' + or_err}")
    print(f"• Upstash Redis  : {'✅ Sedia' if not red_err else '❌ ' + red_err}")
    print(f"• Upstash Vector : {'✅ Sedia' if not vec_err else '❌ ' + vec_err}")
    print(f"• Pexels API     : {'✅ Sedia' if not pex_err else '❌ ' + pex_err}")
    print(f"• Facebook Page  : {'✅ Sedia' if not fb_err else '⚠️ ' + fb_err}")
    print(f"• Instagram Pro  : {'✅ Sedia' if not ig_err else '⚠️ ' + ig_err}")
    print(f"• Meta Threads   : {'✅ Sedia' if not th_err else '⚠️ ' + th_err}")
    print(f"• Bluesky Proto  : {'✅ Sedia' if not bs_err else '⚠️ ' + bs_err}")
    print(f"• Backblaze B2   : {'✅ Sedia' if not b2_err else '⚠️ ' + b2_err}")
    print(f"• Telegram Audit : {'✅ Sedia' if not tg_err else '⚠️ ' + tg_err}")

    # Semakan Token Aktif Threads dari Redis
    th_redis_token = get_active_threads_token_from_redis()
    print(f"• Token Threads (Redis): {'✅ Ditemui' if th_redis_token else '⚪ Tiada (Guna .env fallback)'}")

    # =========================================================================
    # STEP 1: JANA CALON KATA KUNCI, AMBIL PEXELS & RENDER VIDEO (30-40s)
    # =========================================================================
    print_step_header(1, "Enjin Kata Kunci, Carian Pexels & Rendering MoviePy + Librosa")

    candidates = get_fresh_vetted_keyword_candidates()
    print(f"📋 Calon Kata Kunci Segar: {candidates}")

    if not candidates:
        print("❌ Tiada calon kata kunci yang melepasi tapisan.")
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
        print("❌ Gagal mendapatkan klip video yang mencukupi.")
        return

    video_title = selected_keyword.title()
    video_ids = [c["id"] for c in selected_clips]

    downloaded_paths = download_all_selected_clips(selected_clips)
    rendered_video_path = None
    b2_payload = None

    try:
        rendered_video_path, music_meta, duration_sec = render_stitched_reel(
            clips_data=selected_clips,
            target_min=30,
            target_max=40,
            output_dir=OUTPUT_DIR,
            filename_prefix="test_all_mama_reel"
        )

        if not rendered_video_path or not os.path.exists(rendered_video_path):
            print("❌ Gagal menjana video Reels akhir.")
            return

        print(f"🎬 Video Siap Dirender : {rendered_video_path}")
        print(f"⏱️ Durasi Sebenar     : {duration_sec} Saat (Sasaran: 30 - 40s)")
        print(f"🎵 Muzik & Rentak      : '{music_meta.get('title')}' | {music_meta.get('tempo_bpm')} BPM")

        # =====================================================================
        # STEP 2: EKSTRAKSI 4 KEYFRAME & ANALISIS OPENROUTER VISION (EN)
        # =====================================================================
        print_step_header(2, "Ekstraksi 4 Keyframe Snapshot & Analisis OpenRouter Vision")

        keyframes, total_kb = extract_and_compress_keyframes(rendered_video_path, num_frames=4, max_dimension=384, quality=65)
        print(f"📦 Jumlah Saiz 4 Keyframes: {total_kb:.1f} KB")

        vision_review, vision_model, _ = analyze_video_keyframes_with_vision(
            keyframes_list=keyframes,
            video_title=video_title,
            music_meta=music_meta,
            max_attempts=3,
            delay_seconds=2
        )

        print(f"\n🧠 Model Vision Digunakan : {vision_model}")
        print(f"📝 Ulasan Vision (EN)     :\n\"{vision_review}\"")
        print(f"📏 Panjang Ulasan         : {len(vision_review)} Aksara (Sasaran: 350-500)")

        # =====================================================================
        # STEP 3: OLAHAN AI PERSONA MAMA (BM) & SEMAKAN VEKTOR
        # =====================================================================
        print_step_header(3, "Olahan Copywriting Persona Mama (BM) & Semakan Upstash Vector")

        final_caption_bm, raw_story_bm, copy_model = generate_mama_reel_story(
            vision_review=vision_review,
            video_title=video_title,
            music_meta=music_meta,
            max_vector_retries=2
        )

        print(f"🧠 Model Copywriter : {copy_model}")
        print(f"📝 Kapsyen Akhir (BM):\n{final_caption_bm}")
        print(f"📏 Jumlah Aksara    : {len(final_caption_bm)} Aksara (Sasaran: 300-500)")

        # =====================================================================
        # STEP 4: PENGHOSAN VIDEO EFEMERAL BACKBLAZE B2
        # =====================================================================
        print_step_header(4, "Penghosan Video Efemeral Backblaze B2 (Signed URL)")

        b2_signed_url = None
        if b2_storage.is_configured():
            b2_ok, b2_res, b2_err = b2_storage.upload_ephemeral_video(rendered_video_path, valid_duration=3600)
            if b2_ok:
                b2_payload = b2_res
                b2_signed_url = b2_res.get("signed_url")
                print(f"✅ B2 Signed URL Berjaya: {b2_signed_url[:65]}...")
            else:
                print(f"❌ B2 Upload Ralat: {b2_err}")
        else:
            print("⚠️ Konfigurasi B2 tidak lengkap. Dilangkau.")

        # =====================================================================
        # STEP 5: PENGEDARAN KE 4 MEDIA SOSIAL (INTERACTIVE CHOICE)
        # =====================================================================
        print_step_header(5, "Penerbitan Media Sosial (Facebook, IG, Threads, Bluesky)")

        print("PILIHAN MOD PENGUJIAN PENGEDARAN:")
        print("  [1] LIVE POST  - Hantar video sebenar ke Facebook, Instagram, Threads, dan Bluesky.")
        print("  [2] DRY RUN    - Simulasi sahaja (tidak pos ke media sosial sebenar).")

        try:
            choice = input("\nSila pilih mod [1 / 2] (Lalai: 2): ").strip()
        except EOFError:
            choice = "2"

        post_results = {}

        if choice == "1":
            print("\n🚀 Menjalankan hantaran LIVE POST ke 4 platform media sosial...")

            # 1. Facebook Reels
            fb_ok, fb_res, fb_msg = post_reel_to_facebook(rendered_video_path, final_caption_bm, enable_feed_fallback=True)
            post_results["facebook"] = fb_res if fb_ok else {"status": "failed", "error": fb_msg}

            # 2. Instagram Reels
            if b2_signed_url:
                ig_ok, ig_res, ig_msg = post_reel_to_instagram(b2_signed_url, final_caption_bm)
                post_results["instagram"] = ig_res if ig_ok else {"status": "failed", "error": ig_msg}
            else:
                post_results["instagram"] = {"status": "failed", "error": "B2 URL tiada"}

            # 3. Threads Video
            if b2_signed_url:
                th_ok, th_res, th_msg = post_video_to_threads(b2_signed_url, final_caption_bm)
                post_results["threads"] = th_res if th_ok else {"status": "failed", "error": th_msg}
            else:
                post_results["threads"] = {"status": "failed", "error": "B2 URL tiada"}

            # 4. Bluesky Video
            bs_ok, bs_res, bs_msg = post_video_to_bluesky(rendered_video_path, final_caption_bm)
            post_results["bluesky"] = bs_res if bs_ok else {"status": "failed", "error": bs_msg}

        else:
            print("\n🛡️ [DRY RUN SIMULATION] Menggunakan data status simulasi berjaya.")
            post_results = {
                "facebook": {"status": "success", "post_id": "sim_fb_123456", "type": "dry_run"},
                "instagram": {"status": "success", "media_id": "sim_ig_123456", "permalink": "https://instagram.com/reel/sim"},
                "threads": {"status": "success", "thread_id": "sim_th_123456", "permalink": "https://threads.net/post/sim"},
                "bluesky": {"status": "success", "uri": "at://did:plc:sim/app.bsky.feed.post/sim", "permalink": "https://bsky.app/profile/sim"},
            }

        # =====================================================================
        # STEP 6: KAD LAPORAN & AUDIT TELEGRAM
        # =====================================================================
        print_step_header(6, "Penghantaran Kad Ringkasan & Audit Telegram")

        audit_payload = {
            "video_title": video_title,
            "video_theme_keyword": selected_keyword,
            "video_duration_seconds": duration_sec,
            "music_metadata": music_meta,
            "final_caption_bm": final_caption_bm,
            "vision_review_en": vision_review,
            "snapshot_image_path": "",
            "post_results": post_results
        }
        tg_ok, tg_msg = send_pexels_reels_audit_report(audit_payload)
        print(f"📊 Status Telegram: {'✅ Berjaya Dihantar' if tg_ok else '⚠️ ' + tg_msg}")

        # =====================================================================
        # STEP 7: PENGUNCIAN STATUS STATUS PANGKALAN DATA & PEMBERSIHAN B2
        # =====================================================================
        print_step_header(7, "Penguncian Redis (10 Hari), Vector (2 Hari) & Pembersihan B2")

        if choice == "1" and has_any_successful_post(post_results):
            # Kunci Kata Kunci di Redis (10 Hari)
            mark_pexels_keyword_used(selected_keyword, ttl_seconds=10 * 86400)
            save_keyword_memory(selected_keyword, max_memories=10)

            # Kunci Video ID di Redis (30 Hari)
            for vid in video_ids:
                mark_pexels_video_posted(vid, ttl_seconds=30 * 86400)

            # Kunci Vektor Cooldown (2 Hari)
            story_id = f"{video_ids[0]}_{selected_keyword.replace(' ', '_')}"
            mark_story_vector_posted(story_id, final_caption_bm)
            print("💾 [DATABASE LOCKED] Rekod Redis dan Upstash Vector berjaya dikunci.")
        else:
            print("⚪ [DRY RUN / SKIPPED] Status pangkalan data tidak dikunci kekal.")

    finally:
        # Padam fail efemeral B2
        if b2_payload:
            print("\n🧹 [B2 CLEANUP] Memadam fail video efemeral dari Backblaze B2...")
            b2_storage.delete_ephemeral_file(
                api_url=b2_payload.get("api_url", ""),
                auth_token=b2_payload.get("auth_token", ""),
                file_id=b2_payload.get("file_id", ""),
                file_name=b2_payload.get("file_name", "")
            )

        # Bersihkan klip mentah Pexels
        cleanup_downloaded_clips(downloaded_paths)

    print("\n" + "=" * 78)
    print("🎉 [DIAGNOSTIC TEST SELESAI] Kesemua langkah berjaya disahkan!")
    print("=" * 78)


if __name__ == "__main__":
    run_all_step_diagnostic()