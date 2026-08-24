#!/usr/bin/env python3
"""
Master Execution Pipeline: Automated 9:16 Video Reels Multi-Platform Publisher
Impian Rumahku & Cerita Mama Ecosystem
Workflow:
- Step 1: Vetted keyword selection (Redis 10-day deduplication) -> Pexels batch fetch (70 clips) -> MoviePy + Librosa beat stitching (30-40s).
- Step 2: Extract 4 chronological keyframe snapshots -> OpenRouter Vision synthesis review (~350-500 chars).
- Step 3: AI Copywriter Persona Mama BM adaptation (300-500 chars) -> Upstash Vector similarity check (2-day cooldown) -> B2 Ephemeral Video Upload.
- Step 4: Multi-platform publishing to Facebook Reels, Instagram Reels, Meta Threads, and Bluesky Video -> Telegram Audit Card.
- Step 5: Gatekeeper verification -> Redis 10-day keyword lock -> Redis 30-day video ID lock -> Vector embedding lock -> B2 & local temp cleanup.
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

# Import Modular Engines from src/
from src.pexels_config import get_myt_time_context
from src.pexels_redis_db import (
    mark_pexels_keyword_used,
    save_keyword_memory,
    mark_pexels_video_posted,
)
from src.pexels_vector_db import mark_story_vector_posted
from src.pexels_keyword_engine import get_fresh_vetted_keyword_candidates
from src.pexels_fetcher import fetch_and_filter_pexels_clips, download_all_selected_clips, cleanup_downloaded_clips
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
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def run_master_pipeline():
    print("=" * 78)
    print("🚀 [MASTER PIPELINE] MEMULAKAN AUTOMASI VIDEO REELS (CERITA MAMA)")
    print("   Facebook Reels | Instagram Reels | Meta Threads | Bluesky Video")
    print("=" * 78)

    time_context, period, day_mood = get_myt_time_context()
    print(f"⏰ [WAKTU SIARAN] : {time_context}")
    print(f"🌸 [SUASANA HARI] : {day_mood}")

    rendered_video_path = None
    downloaded_clip_paths = []
    b2_payload = None

    try:
        # =====================================================================
        # STEP 1: JANA KATA KUNCI, TARIK KLIP PEXELS & RENDER VIDEO (30-40s)
        # =====================================================================
        print("\n" + "─" * 78)
        print("📍 [LANGKAH 1] PEMILIHAN KATA KUNCI, PENARIKAN PEXELS & RENDERING MOVIEPY")
        print("─" * 78)

        candidate_keywords = get_fresh_vetted_keyword_candidates()
        if not candidate_keywords:
            print("❌ [ABORT] Tiada calon kata kunci yang melepasi saringan Redis.")
            return False

        selected_clips = []
        selected_keyword = None

        for kw_idx, kw in enumerate(candidate_keywords, 1):
            print(f"\n🎯 [PERCUBAAN {kw_idx}/{len(candidate_keywords)}] Menguji kata kunci: '{kw}'...")
            clips, err = fetch_and_filter_pexels_clips(query=kw, needed_count=5, batch_size=70)
            if clips and len(clips) >= 4:
                selected_clips = clips
                selected_keyword = kw
                print(f"   🎉 Berjaya memperoleh {len(clips)} klip vertikal bebas muka untuk '{kw}'!")
                break
            else:
                print(f"   ⚠️ Klip tidak mencukupi ({len(clips)} klip). Mencuba calon seterusnya...")

        if not selected_clips or not selected_keyword:
            print("❌ [ABORT] Kesemua calon kata kunci gagal memperoleh minima 4 klip video.")
            return False

        video_title = selected_keyword.title()
        video_ids = [c["id"] for c in selected_clips]

        # Muat turun klip tempatan
        downloaded_clip_paths = download_all_selected_clips(selected_clips)

        # Render video Reels (30 - 40 saat) bersama analisis rentak Librosa
        rendered_video_path, music_meta, duration_sec = render_stitched_reel(
            clips_data=selected_clips,
            target_min=30,
            target_max=40,
            output_dir=TEMP_DIR,
            filename_prefix="master_mama_reel"
        )

        if not rendered_video_path or not os.path.exists(rendered_video_path):
            print("❌ [ABORT] Gagal menjana fail video akhir MoviePy.")
            return False

        # =====================================================================
        # STEP 2: EKSTRAK 4 KEYFRAME & SINTESIS ULASAN OPENROUTER VISION
        # =====================================================================
        print("\n" + "─" * 78)
        print("📍 [LANGKAH 2] EKSTRAKSI 4 KEYFRAME & SINTESIS OPENROUTER VISION (EN)")
        print("─" * 78)

        keyframes, total_kb = extract_and_compress_keyframes(rendered_video_path, num_frames=4, max_dimension=384, quality=65)
        if not keyframes:
            print("⚠️ Gagal mengekstrak bingkai video. Meneruskan dengan fallback.")

        vision_review, vision_model, vision_payload = analyze_video_keyframes_with_vision(
            keyframes_list=keyframes,
            video_title=video_title,
            music_meta=music_meta,
            max_attempts=3,
            delay_seconds=2
        )

        # =====================================================================
        # STEP 3: OLAHAN PERSONA MAMA (BM 300-500 AKSARA) & HOSTING EFEMERAL B2
        # =====================================================================
        print("\n" + "─" * 78)
        print("📍 [LANGKAH 3] OLAHAN AI PERSONA MAMA (BM) & PENGHOSAN VIDEO EFEMERAL B2")
        print("─" * 78)

        final_caption_bm, raw_story_bm, copywriter_model = generate_mama_reel_story(
            vision_review=vision_review,
            video_title=video_title,
            music_meta=music_meta,
            max_vector_retries=2
        )

        print(f"\n📝 [KAPSYEN FINAL PERSONA MAMA ({len(final_caption_bm)} aksara)]:\n{final_caption_bm}")

        # Muat naik video ke Backblaze B2 Storage (Signed Download URL sah 1 jam)
        b2_signed_url = None
        if b2_storage.is_configured():
            b2_ok, b2_res, b2_err = b2_storage.upload_ephemeral_video(rendered_video_path, valid_duration=3600)
            if b2_ok:
                b2_payload = b2_res
                b2_signed_url = b2_res.get("signed_url")
            else:
                print(f"⚠️ [B2 STORAGE WARN] {b2_err}")

        # =====================================================================
        # STEP 4: PENERBITAN SILANG 4 PLATFORM & TELEGRAM AUDIT
        # =====================================================================
        print("\n" + "─" * 78)
        print("📍 [LANGKAH 4] PENERBITAN KE 4 PLATFORM MEDIA SOSIAL & TELEGRAM AUDIT")
        print("─" * 78)

        post_results = {}

        # 1. Facebook Reels
        print("\n🚀 [DISPATCH 1/4] Facebook Reels...")
        fb_ok, fb_res, fb_msg = post_reel_to_facebook(
            video_path=rendered_video_path,
            caption=final_caption_bm,
            enable_feed_fallback=True
        )
        post_results["facebook"] = fb_res if fb_ok else {"status": "failed", "error": fb_msg}

        # 2. Instagram Reels (Memerlukan URL Video B2)
        print("\n📸 [DISPATCH 2/4] Instagram Reels...")
        if b2_signed_url:
            ig_ok, ig_res, ig_msg = post_reel_to_instagram(
                video_url=b2_signed_url,
                caption=final_caption_bm
            )
            post_results["instagram"] = ig_res if ig_ok else {"status": "failed", "error": ig_msg}
        else:
            post_results["instagram"] = {"status": "failed", "error": "B2 Signed URL tidak tersedia"}

        # 3. Meta Threads Video (Memerlukan URL Video B2 & Token Redis)
        print("\n🧵 [DISPATCH 3/4] Meta Threads Video...")
        if b2_signed_url:
            th_ok, th_res, th_msg = post_video_to_threads(
                video_url=b2_signed_url,
                caption=final_caption_bm
            )
            post_results["threads"] = th_res if th_ok else {"status": "failed", "error": th_msg}
        else:
            post_results["threads"] = {"status": "failed", "error": "B2 Signed URL tidak tersedia"}

        # 4. Bluesky AT-Protocol Video
        print("\n🦋 [DISPATCH 4/4] Bluesky Video...")
        bs_ok, bs_res, bs_msg = post_video_to_bluesky(
            video_path=rendered_video_path,
            caption=final_caption_bm
        )
        post_results["bluesky"] = bs_res if bs_ok else {"status": "failed", "error": bs_msg}

        # Simpan snapshot pertama untuk kad audit Telegram jika ada
        snapshot_img_path = str(TEMP_DIR / f"audit_snapshot_{int(time.time())}.jpg")
        if keyframes and len(keyframes) > 0:
            try:
                import base64
                raw_b64 = keyframes[0]["data_uri"].split(",")[-1]
                with open(snapshot_img_path, "wb") as sf:
                    sf.write(base64.b64decode(raw_b64))
            except Exception:
                snapshot_img_path = ""
        else:
            snapshot_img_path = ""

        # Hantar laporan audit lengkap ke Telegram
        audit_payload = {
            "video_title": video_title,
            "video_theme_keyword": selected_keyword,
            "video_duration_seconds": duration_sec,
            "music_metadata": music_meta,
            "final_caption_bm": final_caption_bm,
            "vision_review_en": vision_review,
            "snapshot_image_path": snapshot_img_path,
            "post_results": post_results
        }
        send_pexels_reels_audit_report(audit_payload)

        # =====================================================================
        # STEP 5: PENGESAHAN GATEKEEPER, PENGUNCIAN STATUS & PEMBERSIHAN
        # =====================================================================
        print("\n" + "─" * 78)
        print("📍 [LANGKAH 5] PENGESAHAN GATEKEEPER & PENGUNCIAN STATUS PANGKALAN DATA")
        print("─" * 78)

        if has_any_successful_post(post_results):
            print("🎉 [GATEKEEPER PASSED] Sekurang-kurangnya 1 platform berjaya disiarkan!")

            # 1. Kunci Kata Kunci di Redis (TTL 10 Hari) & Simpan Memori
            mark_pexels_keyword_used(selected_keyword, ttl_seconds=10 * 86400)
            save_keyword_memory(selected_keyword, max_memories=10)

            # 2. Kunci Kesemua Video ID di Redis (TTL 30 Hari)
            for vid_id in video_ids:
                mark_pexels_video_posted(vid_id, ttl_seconds=30 * 86400)

            # 3. Kunci Embedding Teks BM di Vector DB (Penjara Cooldown 2 Hari)
            story_doc_id = f"{video_ids[0]}_{selected_keyword.replace(' ', '_')}"
            mark_story_vector_posted(story_doc_id, final_caption_bm)

            print("\n💾 [DATABASE LOCKED] Rekod Redis dan Upstash Vector berjaya dikunci.")
            return True
        else:
            print("\n❌ [GATEKEEPER FAILED] Semua platform media sosial gagal disiarkan.")
            return False

    finally:
        # Bersihkan fail efemeral di Backblaze B2
        if b2_payload:
            print("\n🧹 [B2 CLEANUP] Memadam fail video efemeral dari Backblaze B2...")
            b2_storage.delete_ephemeral_file(
                api_url=b2_payload.get("api_url", ""),
                auth_token=b2_payload.get("auth_token", ""),
                file_id=b2_payload.get("file_id", ""),
                file_name=b2_payload.get("file_name", "")
            )

        # Bersihkan klip muat turun & video tempatan
        cleanup_downloaded_clips(downloaded_clip_paths)
        if rendered_video_path and os.path.exists(rendered_video_path):
            try:
                os.remove(rendered_video_path)
            except Exception:
                pass


if __name__ == "__main__":
    success = run_master_pipeline()
    sys.exit(0 if success else 1)