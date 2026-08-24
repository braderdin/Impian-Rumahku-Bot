#!/usr/bin/env python3
"""
Diagnostic Multi-Platform Dispatcher Test Runner
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Tests end-to-end media publishing without re-rendering videos
- Locates the latest rendered MP4 from experiments/pexels_output/ (or accepts CLI path)
- Uploads video to Backblaze B2 (generates private Signed URL)
- Dispatches simultaneously to:
  1. Facebook Reels (Meta Graph API)
  2. Instagram Reels (via B2 Signed URL)
  3. Meta Threads Video (via B2 Signed URL + Redis Token)
  4. Bluesky Video (AT-Protocol Video Blob)
- Dispatches formatted Telegram Summary Card & Audit Log
- Automatically cleans up ephemeral video from Backblaze B2 post-test
"""

import os
import sys
import glob
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
from src.pexels_b2_storage import b2_storage
from src.pexels_dispatcher_fb import post_reel_to_facebook
from src.pexels_dispatcher_ig import post_reel_to_instagram
from src.pexels_dispatcher_threads import post_video_to_threads
from src.pexels_dispatcher_bluesky import post_video_to_bluesky
from src.pexels_telegram_audit import send_pexels_reels_audit_report

OUTPUT_DIR = PROJECT_ROOT / "experiments" / "pexels_output"
TEMP_DIR = PROJECT_ROOT / "temp"


def find_latest_test_video() -> Optional[str]:
    """Mencari fail video MP4 terkini dalam folder experiments/pexels_output/."""
    mp4_files = glob.glob(str(OUTPUT_DIR / "*.mp4"))
    if not mp4_files:
        # Cuba cari di temp/
        mp4_files = glob.glob(str(TEMP_DIR / "*.mp4"))

    if not mp4_files:
        return None

    # Susun mengikut masa ubah suai terkini
    mp4_files.sort(key=os.path.getmtime, reverse=True)
    return mp4_files[0]


def run_dispatch_test(video_file_path: Optional[str] = None):
    print("=" * 78)
    print("🧪 [DIAGNOSTIC TEST] PENGEDARAN VIDEO 4 PLATFORM & TELEGRAM AUDIT")
    print("   Facebook Reels | Instagram Reels | Meta Threads | Bluesky Video")
    print("=" * 78)

    # 1. Tentukan Fail Video
    target_video = video_file_path or find_latest_test_video()
    if not target_video or not os.path.exists(target_video):
        print(f"❌ [ABORT] Tiada fail video MP4 dijumpai di {OUTPUT_DIR}. Sila jalankan test stitcher dahulu.")
        return

    time_context, period, day_mood = get_myt_time_context()
    file_size_mb = os.path.getsize(target_video) / (1024 * 1024)

    print(f"📁 [FAIL VIDEO DIPILIH] : {target_video} ({file_size_mb:.2f} MB)")
    print(f"⏰ [KONTEKS WAKTU MYT]   : {time_context} ({period})")
    print(f"🌸 [MOOD HARI INI]      : {day_mood}")

    # Teks Contoh Kapsyen Ujian Persona Mama
    sample_title = "Aesthetic Home Closet & Wardrobe Organizing"
    sample_story = (
        f"Bila ruang almari dan pakaian tersusun kemas macam ni, rasa lapang sangat fikiran kita. "
        f"Susun atur yang praktikal bukan saja sedap dipandang mata, tapi memudahkan rutin harian sekeluarga."
    )
    sample_caption = (
        f"✨ {sample_title}\n\n"
        f"{sample_story}\n\n"
        f"#ImpianRumahku #CeritaMama #KemasRumah #DekoRumah #ReelsMalaysia"
    )

    b2_payload = None
    b2_signed_url = None

    try:
        # 2. Muat Naik ke Backblaze B2 (Signed URL)
        print("\n" + "─" * 78)
        print("☁️ [STEP 1] MEMUAT NAIK VIDEO KE BACKBLAZE B2 EFEMERAL")
        print("─" * 78)

        if b2_storage.is_configured():
            b2_ok, b2_res, b2_err = b2_storage.upload_ephemeral_video(target_video, valid_duration=3600)
            if b2_ok:
                b2_payload = b2_res
                b2_signed_url = b2_res.get("signed_url")
                print(f"✅ [B2 SIGNED URL] : {b2_signed_url[:65]}...")
            else:
                print(f"❌ [B2 ERROR] : {b2_err}")
        else:
            print("⚠️ [B2 SKIPPED] Konfigurasi Backblaze B2 tidak lengkap dalam .env.local.")

        # 3. Pengedaran ke 4 Saluran Media Sosial
        print("\n" + "─" * 78)
        print("🚀 [STEP 2] MEMULAKAN PENGEDARAN SILANG 4 PLATFORM")
        print("─" * 78)

        post_results = {}

        # A. Facebook Reels
        print("\n1️⃣ [FACEBOOK REELS]")
        fb_ok, fb_res, fb_msg = post_reel_to_facebook(
            video_path=target_video,
            caption=sample_caption,
            enable_feed_fallback=True
        )
        post_results["facebook"] = fb_res if fb_ok else {"status": "failed", "error": fb_msg}

        # B. Instagram Reels (Memerlukan URL Video B2)
        print("\n2️⃣ [INSTAGRAM REELS]")
        if b2_signed_url:
            ig_ok, ig_res, ig_msg = post_reel_to_instagram(
                video_url=b2_signed_url,
                caption=sample_caption
            )
            post_results["instagram"] = ig_res if ig_ok else {"status": "failed", "error": ig_msg}
        else:
            print("   ⚠️ Instagram Reels memerlukan B2 Signed URL.")
            post_results["instagram"] = {"status": "failed", "error": "B2 URL tiada"}

        # C. Meta Threads Video (Memerlukan URL Video B2 & Token Redis)
        print("\n3️⃣ [META THREADS VIDEO]")
        if b2_signed_url:
            th_ok, th_res, th_msg = post_video_to_threads(
                video_url=b2_signed_url,
                caption=sample_caption
            )
            post_results["threads"] = th_res if th_ok else {"status": "failed", "error": th_msg}
        else:
            print("   ⚠️ Threads Video memerlukan B2 Signed URL.")
            post_results["threads"] = {"status": "failed", "error": "B2 URL tiada"}

        # D. Bluesky Video
        print("\n4️⃣ [BLUESKY AT-PROTOCOL VIDEO]")
        bs_ok, bs_res, bs_msg = post_video_to_bluesky(
            video_path=target_video,
            caption=sample_caption
        )
        post_results["bluesky"] = bs_res if bs_ok else {"status": "failed", "error": bs_msg}

        # 4. Hantar Laporan Audit ke Telegram
        print("\n" + "─" * 78)
        print("📢 [STEP 3] MENGHANTAR KAD AUDIT LENGKAP KE TELEGRAM")
        print("─" * 78)

        audit_payload = {
            "video_title": sample_title,
            "video_theme_keyword": "home closet wardrobe organizing aesthetic",
            "video_duration_seconds": 35,
            "music_metadata": {
                "title": "Robot Strut",
                "artist": "Impian Rumahku Composer",
                "vibe": "Muzik Estetik Santai Impian Rumahku"
            },
            "final_caption_bm": sample_caption,
            "vision_review_en": "Diagnostic dispatch test of the automated video publishing pipeline.",
            "snapshot_image_path": "",
            "post_results": post_results
        }

        tg_ok, tg_msg = send_pexels_reels_audit_report(audit_payload)
        print(f"📊 Status Telegram Audit: {'✅ Berjaya Dihantar' if tg_ok else f'⚠️ Gagal ({tg_msg})'}")

    finally:
        # 5. Pembersihan Automatik Fail Efemeral B2
        if b2_payload:
            print("\n" + "─" * 78)
            print("🧹 [CLEANUP] MEMADAM FAIL VIDEO SEMENTARA DARI BACKBLAZE B2")
            print("─" * 78)
            b2_storage.delete_ephemeral_file(
                api_url=b2_payload.get("api_url", ""),
                auth_token=b2_payload.get("auth_token", ""),
                file_id=b2_payload.get("file_id", ""),
                file_name=b2_payload.get("file_name", "")
            )

    print("\n" + "=" * 78)
    print("🎉 [TEST DISPATCH SELESAI] Sila semak aplikasi media sosial dan saluran Telegram anda.")
    print("=" * 78)


if __name__ == "__main__":
    cli_video_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_dispatch_test(cli_video_path)