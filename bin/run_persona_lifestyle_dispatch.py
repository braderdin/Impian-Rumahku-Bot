#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Step 3 Runner (Multi-Platform Social Media Dispatcher)
Location: bin/run_persona_lifestyle_dispatch.py

Features:
- Reads AI-generated captions and image paths from temp/lifestyle_payload.json.
- Dispatches content across Facebook Page, Instagram Feed, Meta Threads, and Bluesky.
- Automatically handles signed ephemeral Backblaze B2 image bridging for Meta APIs.
- Updates post IDs and status into temp/lifestyle_payload.json.
- Isolated Dispatch: Failure on one platform does not interrupt the remaining platforms.
"""

import sys
import json
import time
from pathlib import Path
from typing import Any, Dict

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Pengedar Media dari src/
from src.persona_lifestyle_media_dispatcher import dispatch_lifestyle_to_all_platforms

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"


def print_banner(text: str):
    print("\n" + "═" * 78)
    print(f"🚀 {text.upper()}")
    print("═" * 78)


def run_lifestyle_dispatch_step() -> bool:
    start_time = time.time()
    print_banner("[STEP 3] PENGEDARAN KANDUNGAN KE 4 MEDIA SOSIAL SERENTAK")

    # 1. Semak kewujudan fail state Step 2
    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tidak dijumpai. Sila jalankan Step 1 & 2 dahulu.")
        sys.exit(1)

    try:
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"❌ [ABORT] Gagal membaca fail payload: {e}")
        sys.exit(1)

    captions = payload.get("ai_captions", {})
    local_image = payload.get("local_image_path", "")

    if not captions or not captions.get("facebook"):
        print("❌ [ABORT] Teks janaan AI tiada dalam fail payload. Sila jalankan Step 2 semula.")
        sys.exit(1)

    print(f"📦 ID Topik       : {payload.get('topic_id', 'N/A')}")
    print(f"🌿 Niche          : {payload.get('niche', {}).get('niche_title', 'Gaya Hidup')}")
    print(f"🖼️ Imej Disertakan: {'Ya (' + Path(local_image).name + ')' if local_image else 'Tiada (Teks Sahaja)'}")

    # 2. Hantar ke 4 Platform Media Sosial
    print("\n📡 Memulakan penghantaran ke Facebook, Instagram, Threads, dan Bluesky...")
    dispatch_results = dispatch_lifestyle_to_all_platforms(
        captions=captions,
        local_image_path=local_image if local_image else None
    )

    elapsed = time.time() - start_time

    # 3. Paparan Keputusan Hantaran Setiap Platform
    print("\n" + "-" * 78)
    print("📊 [STATUS KEPUTUSAN PENGEDARAN MEDIA SOSIAL]")
    print("-" * 78)

    for platform, res in dispatch_results.items():
        st = res.get("status", "unknown").upper()
        if st == "SUCCESS":
            pid = res.get("post_id") or res.get("thread_id") or res.get("media_id") or res.get("uri") or "OK"
            print(f"  • {platform.capitalize():<12} : ✅ BERJAYA (ID: {str(pid)[:24]})")
        elif st == "SKIPPED":
            reason = res.get("reason", "Dilangkau")
            print(f"  • {platform.capitalize():<12} : ⚪ DILANGKAU ({reason})")
        else:
            err = res.get("error", "Ralat tidak diketahui")
            print(f"  • {platform.capitalize():<12} : ❌ GAGAL ({str(err)[:50]})")
    print("-" * 78)

    # 4. Kemas kini State Payload
    payload["step"] = 3
    payload["post_results"] = dispatch_results
    payload["dispatch_duration_sec"] = round(elapsed, 2)

    try:
        with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n💾 [PAYLOAD UPDATED] Keputusan pengedaran disimpan ke: {PAYLOAD_FILE.name}")
        print_banner(f"STEP 3 SELESAI ({elapsed:.2f}S)")
        return True
    except Exception as e:
        print(f"❌ [PAYLOAD WRITE ERROR] {e}")
        return False


if __name__ == "__main__":
    run_lifestyle_dispatch_step()