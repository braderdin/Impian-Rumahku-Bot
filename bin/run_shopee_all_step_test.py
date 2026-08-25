#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Master Local End-to-End Diagnostic & Test Runner
Location: bin/run_shopee_all_step_test.py

Pipeline Sequence:
- Step 0: Pre-Flight Environment & Secret Check (IRCM_* Priority)
- Step 1: Fetch candidate from Supabase & filter via Upstash Redis (30d) / Vector DB (2d)
- Step 2: Download image & generate Vision Review in Simple English (Plain English A2/B1)
- Step 3: AI Copywriter Persona Mama BM Translations & Captions Generation:
  * 3A: Facebook Page Post & 1st Comment (500 - 750 chars)
  * 3B: Instagram Feed Caption (400 - 600 chars)
  * 3C: Meta Threads Caption (<= 490 chars)
  * 3D: Bluesky Micro-post (<= 280 chars)
- Step 4: Interactive Mode Selection:
  * [1] LIVE POST  - Hantar ke Facebook, Instagram, Threads, dan Bluesky sebenar.
  * [2] DRY RUN    - Simulasi sahaja (tidak pos ke media sosial sebenar).
- Step 5: Telegram Summary Card & Audit Report
- Step 6: Database Locking (Redis, Vector, Supabase) & Temporary Cleanup
"""

import os
import re
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

# Import Teras dari src/ & bin/
try:
    from src.shopee_ocr_vision_reader import analyze_product_image_with_vision
    from src.shopee_Ai_persona_fb import generate_mama_fb_copy, assemble_fb_post_and_comment, post_to_facebook_page
    from src.shopee_Ai_persona_instagram import (
        generate_mama_instagram_copy, assemble_instagram_post, post_to_instagram_feed,
        upload_temp_image_to_b2_signed as upload_ig_b2, delete_ephemeral_image_from_b2 as delete_ig_b2
    )
    from src.shopee_Ai_persona_threads import (
        generate_mama_threads_copy, assemble_threads_post, post_to_threads_api, get_threads_config,
        upload_temp_image_to_b2_signed as upload_th_b2, delete_ephemeral_image_from_b2 as delete_th_b2
    )
    from src.shopee_Ai_persona_bluesky import generate_mama_bluesky_copy, assemble_bluesky_post, post_to_bluesky
    from src.shopee_telegram_audit import send_shopee_audit_report, has_successful_post
    from src.shopee_redis_filter import mark_shopee_product_posted
    from src.shopee_vector_filter import mark_shopee_vector_posted
    from src.shopee_supabase_db import mark_shopee_product_as_used
except ImportError:
    from shopee_ocr_vision_reader import analyze_product_image_with_vision
    from shopee_Ai_persona_fb import generate_mama_fb_copy, assemble_fb_post_and_comment, post_to_facebook_page
    from shopee_Ai_persona_instagram import (
        generate_mama_instagram_copy, assemble_instagram_post, post_to_instagram_feed,
        upload_temp_image_to_b2_signed as upload_ig_b2, delete_ephemeral_image_from_b2 as delete_ig_b2
    )
    from shopee_Ai_persona_threads import (
        generate_mama_threads_copy, assemble_threads_post, post_to_threads_api, get_threads_config,
        upload_temp_image_to_b2_signed as upload_th_b2, delete_ephemeral_image_from_b2 as delete_th_b2
    )
    from shopee_Ai_persona_bluesky import generate_mama_bluesky_copy, assemble_bluesky_post, post_to_bluesky
    from src.shopee_telegram_audit import send_shopee_audit_report, has_successful_post
    from src.shopee_redis_filter import mark_shopee_product_posted
    from src.shopee_vector_filter import mark_shopee_vector_posted
    from src.shopee_supabase_db import mark_shopee_product_as_used

from bin.run_shopee_prepare_and_generate import run_preparation_and_generation

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"
VISION_FILE = TEMP_DIR / "shopee_vision_ocr.json"

# ANSI Colors untuk Paparan Terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step_header(step_num: int, step_title: str):
    print("\n" + "═" * 78)
    print(f"🔹 [STEP {step_num}] {step_title.upper()}")
    print("═" * 78)


def check_environment_variables() -> bool:
    """
    Step 0: Menyemak ketersediaan semua kunci persekitaran IRCM_* sebelum memulakan ujian.
    """
    print_step_header(0, "Semakan Kredensial & Sambungan API (.env.local)")

    required_services = {
        "OpenRouter AI Engine": [
            ("IRCM_OPENROUTER_BASE_URL", "OPENROUTER_BASE_URL"),
            ("IRCM_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
            ("IRCM_MODEL_VISION", "MODEL_VISION"),
            ("IRCM_MODEL_PRIMARY", "OPENROUTER_MODEL"),
        ],
        "Supabase Database": [
            ("IRCM_SUPABASE_URL", "SUPABASE_URL"),
            ("IRCM_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
        ],
        "Upstash Redis DB": [
            ("IRCM_UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_URL"),
            ("IRCM_UPSTASH_REDIS_REST_TOKEN", "UPSTASH_REDIS_REST_TOKEN"),
        ],
        "Upstash Vector DB": [
            ("IRCM_UPSTASH_VECTOR_REST_URL", "UPSTASH_VECTOR_REST_URL"),
            ("IRCM_UPSTASH_VECTOR_REST_TOKEN", "UPSTASH_VECTOR_REST_TOKEN"),
        ],
        "Telegram Audit Bot": [
            ("IRCM_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
            ("IRCM_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"),
        ],
        "Facebook Meta Page": [
            ("IRCM_FB_META_PAGE_ID", "FB_PAGE_ID", "FACEBOOK_PAGE_ID"),
            ("IRCM_FB_META_PAGE_ACCESS_TOKEN", "FB_PAGE_ACCESS_TOKEN", "FACEBOOK_PAGE_ACCESS_TOKEN"),
        ],
        "Instagram Creator Feed": [
            ("IRCM_INSTAGRAM_ACCOUNT_ID", "INSTAGRAM_ACCOUNT_ID"),
            ("IRCM_INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN"),
        ],
        "Meta Threads API": [
            ("IRCM_THREADS_USER_ID", "THREADS_USER_ID"),
            ("IRCM_THREADS_ACCESS_TOKEN", "THREADS_ACCESS_TOKEN"),
        ],
        "Bluesky AT-Protocol": [
            ("IRCM_BLUESKY_HANDLE", "BLUESKY_HANDLE"),
            ("IRCM_BLUESKY_APP_PASSWORD", "BLUESKY_APP_PASSWORD"),
        ],
        "Backblaze B2 Storage": [
            ("IRCM_B2_KEY_ID", "B2_KEY_ID"),
            ("IRCM_B2_APPLICATION_KEY", "B2_APPLICATION_KEY"),
            ("IRCM_B2_BUCKET_NAME", "B2_BUCKET_NAME"),
        ],
    }

    critical_services = ["OpenRouter AI Engine", "Supabase Database", "Upstash Redis DB", "Upstash Vector DB"]
    all_critical_ok = True

    for service, key_tuples in required_services.items():
        missing_keys = []
        for key_tuple in key_tuples:
            found = False
            for k in key_tuple:
                val = os.getenv(k, "").strip()
                if val:
                    found = True
                    break
            if not found:
                missing_keys.append(key_tuple[0])

        if not missing_keys:
            print(f"  {GREEN}✔ [{service}]{RESET} Kunci lengkap.")
        else:
            print(f"  {YELLOW}⚠ [{service}]{RESET} Kunci tidak ditemui: {', '.join(missing_keys)}")
            if service in critical_services:
                all_critical_ok = False

    return all_critical_ok


def cleanup_temp_image(local_image_path: str = ""):
    """Memadam fail imej fizikal sementara dari folder temp/."""
    if local_image_path:
        img_p = Path(local_image_path)
        try:
            if img_p.exists():
                img_p.unlink()
                print(f"   🧹 [CLEANUP] Fail imej '{img_p.name}' berjaya dipadam.")
        except Exception as e:
            print(f"   ⚠️ [CLEANUP WARN] Gagal memadam imej: {e}")


def run_all_step_diagnostic():
    start_total_time = time.time()
    print("=" * 78)
    print("🧪 [DIAGNOSTIC TEST RUNNER] SHOPEE FEED AUTO-POSTER (WITH DRY-RUN OPTION)")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 78)

    # =========================================================================
    # STEP 0: SEMAKAN KUNCI PERSEKITARAN
    # =========================================================================
    env_ready = check_environment_variables()
    if not env_ready:
        print(f"\n{RED}❌ [ABORT] Kunci pangkalan data atau AI teras tidak lengkap dalam .env.local!{RESET}")
        sys.exit(1)

    # =========================================================================
    # STEP 1: FETCH CALON SHOPEE DARI SUPABASE, REDIS & VECTOR FILTER
    # =========================================================================
    print_step_header(1, "Pengambilan & Penapisan Calon Produk Shopee (Supabase / Redis / Vector)")
    payload = run_preparation_and_generation()
    if not payload or not PAYLOAD_FILE.exists():
        print(f"{RED}❌ [ABORT] Gagal mendapatkan calon produk Shopee.{RESET}")
        return

    product_id = payload.get("shopee_product_id")
    product_name = payload.get("shopee_product_name")
    brand = payload.get("shopee_brand")
    price = payload.get("shopee_price")
    affiliate_link = payload.get("shopee_affiliate_link")

    # =========================================================================
    # STEP 2: MUAT TURUN IMEJ & ULASAN VISION (SIMPLE ENGLISH A2/B1)
    # =========================================================================
    print_step_header(2, "Muat Turun Imej & Analisis OpenRouter Vision (Simple Plain English)")
    vision_payload = analyze_product_image_with_vision(payload, max_attempts=3, delay_seconds=2)
    mama_english_review = vision_payload.get("mama_english_review", "")
    local_image_path = vision_payload.get("local_image_path", "")

    print(f"\n🧠 Model Vision : {vision_payload.get('vision_model_used')}")
    print(f"📝 Ulasan Visual (Simple English):\n\"{mama_english_review}\"")
    print(f"📏 Panjang Aksara: {len(mama_english_review)} aksara (Sasaran: <= 500)")

    # =========================================================================
    # STEP 3: OLAHAN TERJEMAHAN AYAT PERSONA MAMA (BM) MERENTASI 4 PLATFORM
    # =========================================================================
    print_step_header(3, "Olahan Copywriting Persona Mama (BM) Merentasi 4 Platform")

    print("\n⏳ [3A] Menjana Ulasan Facebook Page (Story + 1st Comment)...")
    fb_story = generate_mama_fb_copy(vision_payload)
    fb_caption, fb_comment = assemble_fb_post_and_comment(vision_payload, fb_story)

    print("\n⏳ [3B] Menjana Kapsyen Instagram Feed (Tepat 2 Ayat Gaya Hidup Kemas)...")
    ig_story = generate_mama_instagram_copy(vision_payload)
    ig_caption = assemble_instagram_post(vision_payload, ig_story)

    print("\n⏳ [3C] Menjana Luahan Santai Threads (Had Keras <= 490 Aksara)...")
    th_story = generate_mama_threads_copy(vision_payload)
    th_caption = assemble_threads_post(vision_payload, th_story)

    print("\n⏳ [3D] Menjana Mikro Ulasan Bluesky (Tepat 1 Ayat Padu <= 280 Aksara)...")
    bs_story = generate_mama_bluesky_copy(vision_payload)
    bs_full_text, bs_link, bs_bstart, bs_bend = assemble_bluesky_post(vision_payload, bs_story)

    # Simpan hasil teks AI ke fail state
    ai_captions = {
        "facebook": fb_caption,
        "facebook_comment": fb_comment,
        "instagram": ig_caption,
        "threads": th_caption,
        "bluesky": bs_full_text,
    }
    payload["ai_captions"] = ai_captions
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # Paparan Pratonton Lengkap Sebelum Memilih Mod
    print("\n" + "=" * 78)
    print("📋 [PRATONTON LENGKAP HASIL TERJEMAHAN PERSONA MAMA]")
    print("=" * 78)
    print(f"\n📘 {BOLD}1. FACEBOOK PAGE FEED ({len(fb_caption)} aksara):{RESET}\n{fb_caption}")
    print(f"\n💬 {BOLD}FACEBOOK 1ST COMMENT:{RESET}\n{fb_comment}")
    print("-" * 78)
    print(f"\n📸 {BOLD}2. INSTAGRAM FEED ({len(ig_caption)} aksara):{RESET}\n{ig_caption}")
    print("-" * 78)
    print(f"\n🧵 {BOLD}3. META THREADS FEED ({len(th_caption)} aksara / 490):{RESET}\n{th_caption}")
    print("-" * 78)
    print(f"\n🦋 {BOLD}4. BLUESKY FEED ({len(bs_full_text)} aksara / 280):{RESET}\n{bs_full_text}")
    print("=" * 78)

    # =========================================================================
    # STEP 4: PILIHAN INTERAKTIF (LIVE POST VS DRY RUN)
    # =========================================================================
    print_step_header(4, "Pilihan Mod Pengedaran Media Sosial")

    print("PILIHAN MOD PENGUJIAN PENGEDARAN:")
    print("  [1] LIVE POST  - Hantar kandungan sebenar ke Facebook, Instagram, Threads, dan Bluesky.")
    print("  [2] DRY RUN    - Simulasi sahaja (tidak pos ke akaun media sosial sebenar).")

    try:
        choice = input("\nSila pilih mod [1 / 2] (Lalai: 2): ").strip()
    except EOFError:
        choice = "2"

    post_results = {}

    if choice == "1":
        print("\n🚀 [LIVE POST AKTIF] Memulakan pemposan ke 4 platform media sosial...\n")

        # 1. Facebook Page
        fb_ok, fb_info, fb_msg = post_to_facebook_page(
            image_path=local_image_path,
            image_url=vision_payload.get("shopee_picture_url", ""),
            post_caption=fb_caption,
            comment_text=fb_comment
        )
        post_results["facebook"] = {"status": "success", **fb_info} if fb_ok else {"status": "failed", "error": fb_msg}

        # 2. Instagram Feed (Signed B2 Image Bridge)
        ig_b2_ok, ig_b2_url, ig_fid, ig_fname, ig_api, ig_tok, ig_b2_err = upload_ig_b2(local_image_path)
        if ig_b2_ok:
            try:
                ig_ok, ig_info, ig_msg = post_to_instagram_feed(
                    account_id=os.getenv("IRCM_INSTAGRAM_ACCOUNT_ID", "").strip(),
                    access_token=os.getenv("IRCM_INSTAGRAM_ACCESS_TOKEN", "").strip(),
                    image_url=ig_b2_url,
                    caption=ig_caption
                )
                post_results["instagram"] = {"status": "success", **ig_info} if ig_ok else {"status": "failed", "error": ig_msg}
            finally:
                delete_ig_b2(ig_api, ig_tok, ig_fid, ig_fname)
        else:
            post_results["instagram"] = {"status": "failed", "error": ig_b2_err}

        # 3. Meta Threads (Signed B2 Image Bridge)
        th_uid, th_token, th_err = get_threads_config()
        if not th_err:
            th_b2_ok, th_b2_url, th_fid, th_fname, th_api, th_tok, th_b2_err = upload_th_b2(local_image_path)
            if th_b2_ok:
                try:
                    th_ok, th_info, th_msg = post_to_threads_api(
                        user_id=th_uid,
                        access_token=th_token,
                        image_url=th_b2_url,
                        caption=th_caption
                    )
                    post_results["threads"] = {"status": "success", **th_info} if th_ok else {"status": "failed", "error": th_msg}
                finally:
                    delete_th_b2(th_api, th_tok, th_fid, th_fname)
            else:
                post_results["threads"] = {"status": "failed", "error": th_b2_err}
        else:
            post_results["threads"] = {"status": "failed", "error": th_err}

        # 4. Bluesky AT-Protocol
        bs_ok, bs_info, bs_msg = post_to_bluesky(
            full_text=bs_full_text,
            affiliate_link=bs_link,
            byte_start=bs_bstart,
            byte_end=bs_bend,
            image_path=local_image_path
        )
        post_results["bluesky"] = {"status": "success", **bs_info} if bs_ok else {"status": "failed", "error": bs_msg}

    else:
        print("\n🛡️ [DRY RUN SIMULATION] Menggunakan data simulasi berjaya (Akaun asal tidak disentuh).")
        post_results = {
            "facebook": {"status": "success", "post_id": f"sim_fb_{product_id}", "type": "dry_run"},
            "instagram": {"status": "success", "media_id": f"sim_ig_{product_id}", "type": "dry_run"},
            "threads": {"status": "success", "thread_id": f"sim_th_{product_id}", "type": "dry_run"},
            "bluesky": {"status": "success", "uri": f"at://did:plc:sim/app.bsky.feed.post/{product_id}", "type": "dry_run"},
        }

    # Kemas kini post_results ke fail state payload
    payload["post_results"] = post_results
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # =========================================================================
    # STEP 5: LAPORAN RINGKASAN AUDIT TELEGRAM
    # =========================================================================
    print_step_header(5, "Penghantaran Kad Ringkasan & Audit Telegram")
    audit_ok, audit_msg = send_shopee_audit_report(payload)
    print(f"📊 Status Telegram Audit: {'✅ Berjaya Dihantar' if audit_ok else '⚠️ ' + audit_msg}")

    # =========================================================================
    # STEP 6: TRANSAKSI PANGKALAN DATA & PEMBERSIHAN FAIL
    # =========================================================================
    print_step_header(6, "Penguncian Pangkalan Data & Pembersihan Fail Sementara")

    if choice == "1" and has_successful_post(payload):
        # 1. Kunci Redis (30 Hari)
        mark_shopee_product_posted(product_id)
        print(f"✅ Redis: Kunci 'shopee:product:{product_id}' dikunci selama 30 hari.")

        # 2. Kunci Vector DB (2 Hari Window)
        mark_shopee_vector_posted(product_id, product_name)
        print(f"✅ Vector DB: Keserupaan semantik 'sp_{product_id}' dikunci.")

        # 3. Kemas kini Supabase (shopee_status_used = true)
        sb_ok, sb_msg = mark_shopee_product_as_used(product_id)
        print(f"✅ Supabase: {sb_msg}")
    else:
        print("⚪ [DRY RUN / SKIPPED] Status pangkalan data (Redis, Vector, Supabase) TIDAK dikunci.")
        print("ℹ️  Produk ini kekal berstatus 'unused' dan sedia digunakan pada masa hadapan.")

    # Pembersihan fail imej tempatan
    cleanup_temp_image(local_image_path)

    # =========================================================================
    # RINGKASAN AKHIR KEPUTUSAN
    # =========================================================================
    elapsed = time.time() - start_total_time
    print("\n" + "═" * 78)
    print(f"{BOLD}{GREEN}📊 LAPORAN KEPUTUSAN UJIAN SELESAI ({elapsed:.2f}s){RESET}")
    print("═" * 78)
    for platform, res in post_results.items():
        st = res.get("status", "unknown")
        badge = f"{GREEN}✔ SUCCESS{RESET}" if st == "success" else f"{RED}✖ FAILED ({res.get('error', '')[:30]}){RESET}"
        print(f"  • {BOLD}{platform.capitalize():<15}{RESET} : {badge}")
    print("═" * 78 + "\n")


if __name__ == "__main__":
    run_all_step_diagnostic()