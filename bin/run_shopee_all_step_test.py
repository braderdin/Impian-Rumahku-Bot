#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Master Local End-to-End Test Runner
Location: bin/run_shopee_all_step_test.py

Pipeline Sequence:
- Step 0: Pre-Flight Environment & Configuration Check (IRCM_* Priority)
- Step 1: Fetch candidate from Supabase & filter via Upstash Redis/Vector DB
- Step 2: Download image & generate Mama English Vision Review (IRCM_MODEL_VISION)
- Step 3A: Post to Facebook Page Feed & dispatch affiliate link in first comment
- Step 3B: Upload ephemeral B2 signed image & post to Instagram Feed
- Step 3C: Upload ephemeral B2 signed image & post to Meta Threads Feed (Redis token)
- Step 3D: Direct binary blob upload & post to Bluesky Feed with link facets
- Step 4 - 8: Telegram audit card, Safety Gatekeeper, Redis/Vector/Supabase commit & cleanup
"""

import os
import sys
import json
import time
import traceback
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

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"

# ANSI Colors untuk Visual Terminal di WSL Ubuntu
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(title: str, color: str = CYAN):
    width = 75
    print(f"\n{color}{BOLD}{'=' * width}")
    print(f" {title.center(width - 2)} ")
    print(f"{'=' * width}{RESET}")


def check_environment_variables() -> bool:
    """
    Step 0: Menyemak ketersediaan semua kunci persekitaran IRCM_* sebelum memulakan ujian.
    """
    print_banner("STEP 0: PRE-FLIGHT ENVIRONMENT & SECRET CHECK", YELLOW)

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


def run_full_pipeline_test():
    start_total_time = time.time()
    print_banner("🧪 SHOPEE FEED AUTO-POSTER: END-TO-END MASTER TEST", BOLD + MAGENTA)

    # 1. Semakan Kunci Persekitaran
    env_ready = check_environment_variables()
    if not env_ready:
        print(f"\n{RED}❌ [ABORT] Kunci pangkalan data atau AI teras tidak lengkap dalam .env.local!{RESET}")
        sys.exit(1)

    step_results = {}

    # =========================================================================
    # STEP 1: FETCH, FILTER & INITIALIZE PAYLOAD
    # =========================================================================
    try:
        from bin.run_shopee_prepare_and_generate import run_preparation_and_generation
        payload = run_preparation_and_generation()
        if payload and PAYLOAD_FILE.exists():
            step_results["Step 1 (Prepare & Filter)"] = "SUCCESS"
        else:
            raise RuntimeError("Gagal menghasilkan fail temp/shopee_payload.json")
    except Exception as e:
        print(f"\n{RED}❌ [STEP 1 FAILED]:{RESET} {e}")
        step_results["Step 1 (Prepare & Filter)"] = f"FAILED: {str(e)}"
        print_banner("UJIAN DIBATALKAN KERANA LANGKAH 1 GAGAL", RED)
        return

    # =========================================================================
    # STEP 2: OCR VISION & MAMA ENGLISH REVIEW
    # =========================================================================
    try:
        from bin.run_shopee_ocr_vison_reader import run_vision_step
        run_vision_step()
        step_results["Step 2 (Vision Reader)"] = "SUCCESS"
    except Exception as e:
        print(f"\n{RED}❌ [STEP 2 FAILED]:{RESET} {e}")
        step_results["Step 2 (Vision Reader)"] = f"FAILED: {str(e)}"
        print_banner("UJIAN DIBATALKAN KERANA LANGKAH 2 GAGAL", RED)
        return

    # =========================================================================
    # STEP 3A: FACEBOOK PAGE FEED & COMMENT
    # =========================================================================
    try:
        from bin.run_shopee_post_fb import run_facebook_step
        run_facebook_step()
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            fb_res = json.load(f).get("post_results", {}).get("facebook", {})
        step_results["Step 3A (Facebook Page)"] = "SUCCESS" if fb_res.get("status") == "success" else f"FAILED ({fb_res.get('error', 'Unknown')[:35]})"
    except Exception as e:
        print(f"\n{RED}❌ [STEP 3A FAILED]:{RESET} {e}")
        step_results["Step 3A (Facebook Page)"] = f"FAILED: {str(e)}"

    # =========================================================================
    # STEP 3B: INSTAGRAM FEED VIA B2 BRIDGE
    # =========================================================================
    try:
        from bin.run_shopee_post_instagram import run_instagram_step
        run_instagram_step()
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            ig_res = json.load(f).get("post_results", {}).get("instagram", {})
        step_results["Step 3B (Instagram Feed)"] = "SUCCESS" if ig_res.get("status") == "success" else f"FAILED ({ig_res.get('error', 'Unknown')[:35]})"
    except Exception as e:
        print(f"\n{RED}❌ [STEP 3B FAILED]:{RESET} {e}")
        step_results["Step 3B (Instagram Feed)"] = f"FAILED: {str(e)}"

    # =========================================================================
    # STEP 3C: META THREADS FEED VIA B2 BRIDGE
    # =========================================================================
    try:
        from bin.run_shopee_post_threads import run_threads_step
        run_threads_step()
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            th_res = json.load(f).get("post_results", {}).get("threads", {})
        step_results["Step 3C (Meta Threads)"] = "SUCCESS" if th_res.get("status") == "success" else f"FAILED ({th_res.get('error', 'Unknown')[:35]})"
    except Exception as e:
        print(f"\n{RED}❌ [STEP 3C FAILED]:{RESET} {e}")
        step_results["Step 3C (Meta Threads)"] = f"FAILED: {str(e)}"

    # =========================================================================
    # STEP 3D: BLUESKY AT-PROTOCOL FEED
    # =========================================================================
    try:
        from bin.run_shopee_post_blsky import run_bluesky_step
        run_bluesky_step()
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            bs_res = json.load(f).get("post_results", {}).get("bluesky", {})
        step_results["Step 3D (Bluesky Feed)"] = "SUCCESS" if bs_res.get("status") == "success" else f"FAILED ({bs_res.get('error', 'Unknown')[:35]})"
    except Exception as e:
        print(f"\n{RED}❌ [STEP 3D FAILED]:{RESET} {e}")
        step_results["Step 3D (Bluesky Feed)"] = f"FAILED: {str(e)}"

    # =========================================================================
    # STEP 4 - 8: AUDIT TELEGRAM, GATEKEEPER & TRANSACTION COMMIT
    # =========================================================================
    try:
        from bin.run_shopee_audit_and_commit import run_audit_and_commit
        run_audit_and_commit()
        step_results["Step 4-8 (Audit & Commit)"] = "SUCCESS"
    except SystemExit as se:
        if se.code == 0:
            step_results["Step 4-8 (Audit & Commit)"] = "SUCCESS"
        else:
            step_results["Step 4-8 (Audit & Commit)"] = f"BLOCKED (Exit Code: {se.code})"
    except Exception as e:
        print(f"\n{RED}❌ [STEP 4-8 FAILED]:{RESET} {e}")
        step_results["Step 4-8 (Audit & Commit)"] = f"FAILED: {str(e)}"

    # =========================================================================
    # RINGKASAN AKHIR KEPUTUSAN UJIAN (TEST SUMMARY)
    # =========================================================================
    elapsed = time.time() - start_total_time
    print_banner("📊 LAPORAN KEPUTUSAN UJIAN KESELURUHAN PIPELINE", BOLD + GREEN)
    print(f"⏱️ Masa Larian Keseluruhan: {elapsed:.2f} saat\n")

    for step_name, status in step_results.items():
        if "SUCCESS" in status:
            status_badge = f"{GREEN}✔ {status}{RESET}"
        elif "BLOCKED" in status:
            status_badge = f"{YELLOW}⚠ {status}{RESET}"
        else:
            status_badge = f"{RED}✖ {status}{RESET}"
        print(f"  • {BOLD}{step_name:<35}{RESET} : {status_badge}")

    print(f"\n{BOLD}{'=' * 75}{RESET}\n")


if __name__ == "__main__":
    run_full_pipeline_test()