#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Master Local End-to-End Diagnostic & Test Runner
Location: bin/run_persona_lifestyle_master_runner.py

Pipeline Sequence:
- Step 0: Pre-Flight Environment & Secret Check (IRCM_* Priority)
- Step 1: Prepare Context, Mood & Curate Topic (Plain Text or Reddit Curated)
- Step 2: AI Multi-Platform Copywriting Generation (FB, IG, Threads, Bluesky)
- Step 3: Interactive Mode Selection:
  * [1] LIVE POST  - Posts to real Facebook, Instagram, Threads, and Bluesky accounts.
  * [2] DRY RUN    - Simulation mode (Does not touch social media or lock DB keys).
- Step 4: Telegram Summary Card & Audit Report
- Step 5: Database Locking (Redis 10-Day, Vector 2-Day) & Cleanup (If Live Post)
"""

import os
import sys
import json
import time
import argparse
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

# Import Enjin Teras & Pelaksana
from bin.run_persona_lifestyle_prepare import run_lifestyle_prepare_step
from bin.run_persona_lifestyle_generate import run_lifestyle_generate_step
from src.persona_lifestyle_media_dispatcher import dispatch_lifestyle_to_all_platforms
from src.persona_lifestyle_telegram_audit import send_lifestyle_telegram_audit_report, has_successful_lifestyle_post
from src.persona_lifestyle_filter import commit_lifestyle_topic_lock

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step_header(step_num: int, step_title: str):
    print("\n" + "═" * 78)
    print(f"🔹 [STEP {step_num}] {step_title.upper()}")
    print("═" * 78)


def check_environment_variables() -> bool:
    """Step 0: Menyemak ketersediaan kunci persekitaran IRCM_*."""
    print_step_header(0, "Semakan Kredensial & Sambungan API (.env.local)")

    required_services = {
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
            ("IRCM_FB_META_PAGE_ID", "FB_PAGE_ID"),
            ("IRCM_FB_META_PAGE_ACCESS_TOKEN", "FB_PAGE_ACCESS_TOKEN"),
        ],
        "Instagram Creator Feed": [
            ("IRCM_INSTAGRAM_ACCOUNT_ID", "INSTAGRAM_ACCOUNT_ID"),
            ("IRCM_INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN"),
        ],
        "Meta Threads API": [
            ("IRCM_THREADS_USER_ID", "THREADS_USER_ID"),
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

    critical_services = ["Upstash Redis DB", "Upstash Vector DB", "Telegram Audit Bot"]
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


def run_master_lifestyle_diagnostic():
    start_total_time = time.time()
    print("=" * 78)
    print("🧪 [MASTER DIAGNOSTIC RUNNER] PERSONA LIFESTYLE MAMA (WITH DRY-RUN OPTION)")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 78)

    parser = argparse.ArgumentParser(description="Master Diagnostic: Lifestyle Mama Runner")
    parser.add_argument("--reddit", action="store_true", help="Aktifkan sumber inspirasi Reddit bergambar.")
    parser.add_argument("--niche", type=str, default=None, help="Paksa niche tertentu.")
    args = parser.parse_args()

    # =========================================================================
    # STEP 0: SEMAKAN KUNCI PERSEKITARAN
    # =========================================================================
    env_ready = check_environment_variables()
    if not env_ready:
        print(f"\n{RED}❌ [ABORT] Kunci pangkalan data teras tidak lengkap dalam .env.local!{RESET}")
        sys.exit(1)

    # =========================================================================
    # STEP 1: PERSEDIAAN KONTEKS & PENAPISAN TOPIK
    # =========================================================================
    print_step_header(1, "Persediaan Konteks, Mood & Saringan Topik")
    payload = run_lifestyle_prepare_step(use_reddit=args.reddit, force_niche=args.niche)
    if not payload or not PAYLOAD_FILE.exists():
        print(f"{RED}❌ [ABORT] Gagal menyediakan konteks hantaran.{RESET}")
        return

    # =========================================================================
    # STEP 2: PENJANAAN AYAT 4 PLATFORM OLEH AI
    # =========================================================================
    print_step_header(2, "Penjanaan Ayat Persona Mama (Local VLM / OpenRouter Fallback)")
    gen_ok = run_lifestyle_generate_step()
    if not gen_ok:
        print(f"{RED}❌ [ABORT] Gagal menjana ayat AI.{RESET}")
        return

    # Muat semula payload terkini
    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    captions = payload.get("ai_captions", {})
    local_image_path = payload.get("local_image_path", "")
    topic_id = payload.get("topic_id", "")
    topic_text = payload.get("topic_lock_text", "")
    niche_key = payload.get("niche", {}).get("niche_key", "lifestyle")

    # =========================================================================
    # STEP 3: PILIHAN INTERAKTIF (LIVE POST VS DRY RUN)
    # =========================================================================
    print_step_header(3, "Pilihan Mod Pengedaran Media Sosial")
    print("PILIHAN MOD PENGUJIAN PENGEDARAN:")
    print("  [1] LIVE POST  - Hantar kandungan sebenar ke Facebook, Instagram, Threads, dan Bluesky.")
    print("  [2] DRY RUN    - Simulasi sahaja (tidak pos ke media sosial & tidak kunci database).")

    try:
        choice = input("\nSila pilih mod [1 / 2] (Lalai: 2): ").strip()
    except EOFError:
        choice = "2"

    post_results = {}

    if choice == "1":
        print("\n🚀 [LIVE POST AKTIF] Memulakan pemposan ke 4 platform media sosial...\n")
        post_results = dispatch_lifestyle_to_all_platforms(
            captions=captions,
            local_image_path=local_image_path if local_image_path else None
        )
    else:
        print("\n🛡️ [DRY RUN SIMULATION] Menggunakan data simulasi berjaya (Akaun asal tidak disentuh).")
        post_results = {
            "facebook": {"status": "success", "post_id": f"sim_fb_{topic_id}", "type": "dry_run"},
            "threads": {"status": "success", "thread_id": f"sim_th_{topic_id}", "type": "dry_run"},
            "instagram": {"status": "success" if local_image_path else "skipped", "media_id": f"sim_ig_{topic_id}", "type": "dry_run"},
            "bluesky": {"status": "success", "uri": f"at://did:plc:sim/app.bsky.feed.post/{topic_id}", "type": "dry_run"},
        }

    # Kemas kini post_results ke state payload
    payload["post_results"] = post_results
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # =========================================================================
    # STEP 4: LAPORAN RINGKASAN AUDIT TELEGRAM
    # =========================================================================
    print_step_header(4, "Penghantaran Kad Ringkasan & Audit Telegram")
    audit_ok, audit_msg = send_lifestyle_telegram_audit_report(payload)
    print(f"📊 Status Telegram Audit: {'✅ Berjaya Dihantar' if audit_ok else '⚠️ ' + audit_msg}")

    # =========================================================================
    # STEP 5: TRANSAKSI PANGKALAN DATA & PEMBERSIHAN FAIL
    # =========================================================================
    print_step_header(5, "Penguncian Pangkalan Data & Pembersihan Fail Sementara")

    if choice == "1" and has_successful_lifestyle_post(payload):
        lock_ok = commit_lifestyle_topic_lock(
            topic_id=topic_id,
            topic_text=topic_text,
            category=niche_key
        )
        if lock_ok:
            print(f"✅ Redis & Vector: Topik '{topic_id}' berjaya dikunci (10 Hari / 2 Hari).")
    else:
        print("⚪ [DRY RUN / SKIPPED] Status pangkalan data (Redis & Vector) TIDAK dikunci.")
        print("ℹ️  Topik ini kekal bebas dan sedia digunakan pada masa hadapan.")

    # Pembersihan fail imej tempatan
    cleanup_temp_image(local_image_path)

    # =========================================================================
    # RINGKASAN AKHIR KEPUTUSAN
    # =========================================================================
    elapsed = time.time() - start_total_time
    print("\n" + "═" * 78)
    print(f"{BOLD}{GREEN}📊 LAPORAN DIAGNOSTIK LIFESTYLE SELESAI ({elapsed:.2f}s){RESET}")
    print("═" * 78)
    for platform, res in post_results.items():
        st = res.get("status", "unknown")
        badge = f"{GREEN}✔ SUCCESS{RESET}" if st == "success" else f"{RED}✖ FAILED ({res.get('error', '')[:30]}){RESET}"
        if st == "skipped":
            badge = f"{YELLOW}⚪ SKIPPED{RESET}"
        print(f"  • {BOLD}{platform.capitalize():<15}{RESET} : {badge}")
    print("═" * 78 + "\n")


if __name__ == "__main__":
    run_master_lifestyle_diagnostic()